from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.core.cache import cache
from celery.result import AsyncResult
import re
from django.db.models import Q, Case, When, Value, IntegerField, F, Exists, OuterRef
from django.contrib.postgres.search import SearchQuery
from django.db.models.functions import Length, StrIndex

from .models import EnWord, EnExample
from .serializers import EnWordSerializer
from apps.ai_gateway import AIFallbackGateway
from .tasks import translate_en_pure_text_task
from apps.dictionary_zh.views import StandardResultsSetPagination

class EnWordSearchView(generics.ListAPIView):
    serializer_class = EnWordSerializer
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        query = self.request.query_params.get('q', '').strip()
        db_shared_container = {}

        def db_lookup():
            queryset = self.get_queryset()
            exact_example = None
            query_word_len = len(query.split())

            if 1 <= query_word_len <= 30:
                cleaned_query_end = re.sub(r'[. , ! ?]+$', '', query)
                cleaned_for_search = re.sub(r'[. , ! ? : ; ( ) \[ \] { } “ ” ‘ ’ \' "]+', ' ', query).strip()
                
                # Step 1: Exact full-sentence match (highest priority)
                match = EnExample.objects.filter(english__iexact=cleaned_query_end).first()
                
                # Step 2: Word boundary match for single-word queries
                # Uses PostgreSQL \y (word boundary) to prevent "search" matching "research"
                if not match and cleaned_for_search and query_word_len == 1:
                    word_boundary_pattern = r'\y' + re.escape(cleaned_for_search) + r'\y'
                    match = (
                        EnExample.objects
                        .filter(english__iregex=word_boundary_pattern)
                        .order_by(Length('english'))
                        .first()
                    )
                
                # Step 3: icontains fallback for multi-word queries, prefer shorter sentences
                if not match and cleaned_for_search and query_word_len > 1:
                    match = (
                        EnExample.objects
                        .filter(english__icontains=cleaned_for_search)
                        .order_by(Length('english'))
                        .first()
                    )
                
                # Step 4: Vietnamese translation fallback
                if not match and cleaned_for_search:
                    match = (
                        EnExample.objects
                        .filter(vietnamese__icontains=cleaned_for_search)
                        .order_by(Length('vietnamese'))
                        .first()
                    )
                
                if match:
                    exact_example = {
                        'id': str(match.id),
                        'english': match.english,
                        'vietnamese': match.vietnamese
                    }

            has_data = queryset.exists() or (exact_example is not None)
            if has_data:
                db_shared_container['queryset'] = queryset
                db_shared_container['exact_example'] = exact_example
                return True
            return False

        # Tích hợp bảo vệ bằng Gateway dùng chung (Chế độ tiếng Anh 'en')
        gateway_response = AIFallbackGateway.handle_search_fallback(
            request=request,
            query=query,
            db_lookup_func=db_lookup,
            task_func=translate_en_pure_text_task,
            cache_key_prefix="ai_trans_en",
            mode='en'
        )

        if gateway_response:
            return gateway_response

        # DB Hit -> Lấy dữ liệu từ Closure tránh truy vấn trùng lặp
        queryset = db_shared_container['queryset']
        exact_example = db_shared_container['exact_example']

        page = self.paginate_queryset(queryset)
        if page is not None:
            response = self.get_paginated_response(self.get_serializer(page, many=True).data)
            response.data['exact_example_match'] = exact_example
            return response

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'exact_example_match': exact_example,
            'results': serializer.data
        })

    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        
        # Base Queryset with prefetch to solve N+1 Problem
        queryset = EnWord.objects.prefetch_related('examples')
        
        # Clean query: strip English punctuation
        cleaned_query = re.sub(r'[. , ! ? : ; ( ) \[ \] { } “ ” ‘ ’ \' "]+', ' ', query).strip()
            
        if not cleaned_query:
            # If no query, return empty or all words ordered alphabetically
            return queryset.order_by('word')

        q_lower = cleaned_query.lower()
        
        # SearchQuery for FTS Search
        query_obj = SearchQuery(cleaned_query, config='english')
        
        # --- Pre-filtering optimization ---
        filter_q = Q(word__iexact=cleaned_query) | Q(word__istartswith=cleaned_query)
        
        if len(cleaned_query) >= 2:
            filter_q |= Q(translation_vi__icontains=q_lower)
            
            # Find matching word IDs from examples
            example_word_ids = list(
                EnExample.objects.filter(
                    Q(search_vector=query_obj) | Q(vietnamese__icontains=cleaned_query)
                ).values_list('word_id', flat=True).distinct()
            )
            if example_word_ids:
                filter_q |= Q(id__in=example_word_ids)
                
            # Generate substrings of query for fast word_idx match
            substrings = []
            for i in range(len(cleaned_query)):
                for j in range(i + 2, len(cleaned_query) + 1):
                    sub = cleaned_query[i:j].strip()
                    if sub and len(sub) >= 2:
                        substrings.append(sub)
            substrings = list(set(substrings))
            if substrings:
                filter_q |= Q(word__in=substrings)
                
        queryset = queryset.filter(filter_q)
        
        # 0. Subquery to check for example match without causing joins
        has_example_match = Exists(
            EnExample.objects.filter(word_id=OuterRef('pk')).filter(
                Q(search_vector=query_obj) | Q(vietnamese__icontains=cleaned_query)
            )
        )
        
        # 1. Annotate word length and reverse match index
        queryset = queryset.annotate(
            word_len=Length('word'),
            word_idx=StrIndex(Value(cleaned_query), F('word'))
        )
        
        # 2. Comprehensive search logic covering all cases
        queryset = queryset.annotate(
            match_level=Case(
                When(word__iexact=cleaned_query, then=Value(1)),
                When(word__istartswith=cleaned_query, then=Value(2)),
                When(translation_vi__icontains=q_lower, then=Value(3)),
                When(has_example_match, then=Value(4)),
                When(word_idx__gt=0, then=Value(5)),
                default=Value(999999),
                output_field=IntegerField(),
            )
        )
        
        # 3. Conditional sorting length exclusively for Match Level 5
        queryset = queryset.annotate(
            reverse_sort_len=Case(
                When(match_level=5, then=F('word_len')),
                default=Value(0),
                output_field=IntegerField(),
            )
        )

        # 4. Filter and Distinct
        if len(cleaned_query) >= 2:
            queryset = queryset.filter(match_level__lte=5)
        else:
            queryset = queryset.filter(match_level__lte=4)
            
        # 5. Final Sort Order
        queryset = queryset.order_by('match_level', '-reverse_sort_len', 'word')
        
        return queryset


class EnPureTextTranslationView(APIView):
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        return AIFallbackGateway.handle_translation_fallback(
            request=request,
            task_func=translate_en_pure_text_task,
            cache_key_prefix="ai_trans_en",
            mode='en'
        )


class EnTranslationStatusView(APIView):
    throttle_classes = []

    def get(self, request, task_id):
        res = AsyncResult(task_id)
        if res.state == 'SUCCESS':
            result_data = res.result
            if result_data.get('status') == 'SUCCESS':
                return Response({
                    "status": "SUCCESS",
                    "translatedText": result_data.get('translatedText'),
                    "source": result_data.get('source')
                })
            return Response({
                "status": "FAILED", 
                "error": result_data.get('error', 'Lỗi không xác định')
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        elif res.state == 'FAILURE':
            return Response({"status": "FAILED", "error": "Task execution failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response({"status": res.state})
