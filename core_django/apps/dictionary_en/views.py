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

        # Detect if query has Vietnamese characters (diacritics)
        vi_pattern = r'[àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđÀÁẢÃẠÂẦẤẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỸĐ]'
        is_vietnamese = bool(re.search(vi_pattern, query))
        q_lower = query.lower()

        def db_lookup():
            exact_example = None
            query_word_len = len(query.split())

            if 1 <= query_word_len <= 30:
                from .models import EnExample
                cleaned_query_end = re.sub(r'[. , ! ?]+$', '', query)
                cleaned_for_search = re.sub(r'[. , ! ? : ; ( ) \[ \] { } “ ” ‘ ’ \' "]+', ' ', query).strip()
                
                if not is_vietnamese:
                    # English query flow: check exact english match first
                    match = EnExample.objects.filter(english__iexact=cleaned_query_end).first()
                    
                    # Word boundary match for single-word English queries
                    if not match and cleaned_for_search and query_word_len == 1:
                        word_boundary_pattern = r'\y' + re.escape(cleaned_for_search) + r'\y'
                        match = (
                            EnExample.objects
                            .filter(english__iregex=word_boundary_pattern)
                            .order_by(Length('english'))
                            .first()
                        )
                    
                    # icontains fallback for multi-word English queries
                    if not match and cleaned_for_search and query_word_len > 1:
                        match = (
                            EnExample.objects
                            .filter(english__icontains=cleaned_for_search)
                            .order_by(Length('english'))
                            .first()
                        )
                else:
                    # Vietnamese translation fallback: check vietnamese column only
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

            # Check if there are matches in EnWord using fast B-tree queries
            if not is_vietnamese:
                has_exact_word = EnWord.objects.filter(word__iexact=query).exists()
                has_data = has_exact_word or (exact_example is not None)
            else:
                # For Vietnamese translation, check if translation_vi contains or fallback to exists
                queryset = self.get_queryset()
                has_data = queryset.only('id').exists() or (exact_example is not None)

            if has_data:
                if 'queryset' not in db_shared_container:
                    db_shared_container['queryset'] = self.get_queryset()
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
        
        # Detect if query has Vietnamese characters (diacritics)
        vi_pattern = r'[àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđÀÁẢÃẠÂẦẤẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỸĐ]'
        is_vietnamese = bool(re.search(vi_pattern, cleaned_query))

        # --- Pre-filtering optimization based on language ---
        if is_vietnamese:
            # 1. Vietnamese Query Flow: Search translation_vi and vietnamese in examples
            filter_q = Q(translation_vi__icontains=q_lower)
            
            if len(cleaned_query) >= 2:
                # Find matching word IDs from examples (trigram index scan)
                example_word_ids = list(
                    EnExample.objects.filter(
                        vietnamese__icontains=cleaned_query
                    ).values_list('word_id', flat=True).distinct()
                )
                if example_word_ids:
                    filter_q |= Q(id__in=example_word_ids)

            queryset = queryset.filter(filter_q)
            
            has_example_match = Exists(
                EnExample.objects.filter(word_id=OuterRef('pk'), vietnamese__icontains=cleaned_query)
            )
            
            # Match levels for Vietnamese: 3, 4, 5
            queryset = queryset.annotate(
                word_len=Length('word'),
                word_idx=StrIndex(Value(cleaned_query), F('word'))
            ).annotate(
                match_level=Case(
                    When(translation_vi__icontains=q_lower, then=Value(3)),
                    When(has_example_match, then=Value(4)),
                    When(word_idx__gt=0, then=Value(5)),
                    default=Value(999999),
                    output_field=IntegerField(),
                )
            )
        else:
            # 2. English Query Flow: Search English word and search_vector in examples
            filter_q = Q(word__iexact=cleaned_query) | Q(word__istartswith=cleaned_query)
            
            # SearchQuery for FTS Search on english config
            query_obj = SearchQuery(cleaned_query, config='english')
            
            if len(cleaned_query) >= 2:
                # Find matching word IDs from examples using English FTS only
                example_word_ids = list(
                    EnExample.objects.filter(
                        search_vector=query_obj
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
            
            has_example_match = Exists(
                EnExample.objects.filter(word_id=OuterRef('pk'), search_vector=query_obj)
            )
            
            # Match levels for English: 1, 2, 4, 5
            queryset = queryset.annotate(
                word_len=Length('word'),
                word_idx=StrIndex(Value(cleaned_query), F('word'))
            ).annotate(
                match_level=Case(
                    When(word__iexact=cleaned_query, then=Value(1)),
                    When(word__istartswith=cleaned_query, then=Value(2)),
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

        # 4. Filter match levels
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
