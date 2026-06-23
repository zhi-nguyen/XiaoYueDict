from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import Q, Case, When, Value, IntegerField, F, Exists, OuterRef
from django.contrib.postgres.search import SearchQuery
from django.db.models.functions import Length, StrIndex
from django.core.cache import cache

from .models import ZhWord, ZhExample
from .serializers import ZhWordSerializer
from apps.ai_gateway import AIFallbackGateway
import re
import jieba


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ZhWordSearchView(generics.ListAPIView):
    serializer_class = ZhWordSerializer
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        query = self.request.query_params.get('q', '').strip()
        from .tasks import translate_pure_text_task

        db_shared_container = {}

        # Check if fallback is disabled
        fallback_param = request.query_params.get('fallback', 'true').lower() == 'true'

        if fallback_param:
            is_chinese = bool(re.search(r'[\u4e00-\u9fa5]', query))

            def db_lookup():
                queryset = self.filter_queryset(self.get_queryset())
                exact_example = None
                query_len = len(query)

                if 2 <= query_len <= 100:
                    from .models import ZhExample
                    cleaned_query_end = re.sub(r'[。，、！？. , ! ?]+$', '', query)
                    cleaned_for_search = re.sub(r'[。，、！？. , ! ? : ： ; ； ( ) （ ） \[ \] { } “ ” ‘ ’ \' "]+', ' ', query).strip()
                    regex_pattern = r'^' + re.escape(cleaned_query_end) + r'[。，、！？. , ! ?]*$'
                    
                    # Check Chinese field
                    match = ZhExample.objects.filter(chinese__iregex=regex_pattern).first()
                    if not match and cleaned_for_search:
                        match = ZhExample.objects.filter(chinese__icontains=cleaned_for_search).first()
                    
                    # Check Vietnamese field (Utilizes GIN Trigram index)
                    if not match and cleaned_for_search:
                        match = ZhExample.objects.filter(vietnamese__icontains=cleaned_for_search).first()
                    
                    if match:
                        exact_example = {
                            'chinese': match.chinese,
                            'pinyin': match.pinyin,
                            'vietnamese': match.vietnamese
                        }

                if is_chinese:
                    has_exact_word = ZhWord.objects.filter(Q(word=query) | Q(traditional=query)).exists()
                    has_data = has_exact_word or (exact_example is not None)
                else:
                    has_data = queryset.exists() or (exact_example is not None)

                if has_data:
                    db_shared_container['queryset'] = queryset
                    db_shared_container['exact_example'] = exact_example
                    return True
                return False

            # Ủy thác phòng thủ cho Gateway dùng chung (Chế độ tiếng Trung)
            gateway_response = AIFallbackGateway.handle_search_fallback(
                request=request,
                query=query,
                db_lookup_func=db_lookup,
                task_func=translate_pure_text_task,
                cache_key_prefix="ai_trans",
                mode='zh'
            )

            if gateway_response:
                return gateway_response
        else:
            queryset = self.filter_queryset(self.get_queryset())
            db_shared_container['queryset'] = queryset
            db_shared_container['exact_example'] = None

        # Phục hồi dữ liệu từ Closure, triệt tiêu Double Query!
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
        hsk = self.request.query_params.get('hsk', '').strip()
        
        # Base Queryset with prefetch to solve N+1 Problem
        queryset = ZhWord.objects.prefetch_related('examples')
        
        if hsk:
            queryset = queryset.filter(hsk_level=hsk)
            
        # Clean query: strip Chinese and English punctuation
        cleaned_query = re.sub(r'[。，、！？. , ! ? : ： ; ； ( ) （ ） \[ \] { } “ ” ‘ ’ \' "]+', ' ', query).strip()
            
        if not cleaned_query:
            # If no query but HSK is provided, just return paginated results ordered by popularity
            return queryset.annotate(
                adjusted_rank=Case(
                    When(popularity_rank=0, then=Value(999999)),
                    default='popularity_rank',
                    output_field=IntegerField(),
                )
            ).order_by('adjusted_rank')

        q_lower = cleaned_query.lower()
        
        # Tokenize query for FTS Search
        tokenized_query = " ".join(jieba.cut(cleaned_query))
        query_obj = SearchQuery(tokenized_query, config='simple')
        
        # 0. Subquery to check for example match without causing joins
        has_example_match = Exists(
            ZhExample.objects.filter(word_id=OuterRef('pk')).filter(
                Q(chinese__icontains=cleaned_query) | Q(vietnamese__icontains=cleaned_query)
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
                When(Q(word__exact=cleaned_query) | Q(traditional__exact=cleaned_query), then=Value(1)),
                When(Q(toneless_pinyin__iexact=q_lower) | Q(pinyin__iexact=q_lower), then=Value(2)),
                When(Q(word__startswith=cleaned_query) | Q(traditional__startswith=cleaned_query), then=Value(3)),
                When(Q(toneless_pinyin__istartswith=q_lower) | Q(pinyin__istartswith=q_lower), then=Value(4)),
                When(Q(translation_en__iexact=q_lower) | Q(han_viet__iexact=q_lower), then=Value(5)),
                When(Q(translation_vi__icontains=q_lower) | Q(han_viet__icontains=q_lower) | Q(translation_en__icontains=q_lower), then=Value(6)),
                When(has_example_match, then=Value(7)),
                When(word_idx__gt=0, then=Value(8)),
                default=Value(999999),
                output_field=IntegerField(),
            ),
            adjusted_rank=Case(
                When(popularity_rank=0, then=Value(999999)),
                default='popularity_rank',
                output_field=IntegerField(),
            )
        )
        
        # 3. Conditional sorting length exclusively for Match Level 8
        queryset = queryset.annotate(
            reverse_sort_len=Case(
                When(match_level=8, then=F('word_len')),
                default=Value(0),
                output_field=IntegerField(),
            )
        )

        # 4. Filter and Distinct
        if len(cleaned_query) >= 2:
            queryset = queryset.filter(match_level__lte=8)
        else:
            queryset = queryset.filter(match_level__lte=7)
            
        # 5. Final Sort Order
        queryset = queryset.order_by('match_level', '-reverse_sort_len', 'adjusted_rank', 'word_frequency')
        
        return queryset

from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.response import Response
from rest_framework import status
import os
from .tasks import translate_pure_text_task
from celery.result import AsyncResult

class PureTextTranslationView(APIView):
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        from .tasks import translate_pure_text_task
        return AIFallbackGateway.handle_translation_fallback(
            request=request,
            task_func=translate_pure_text_task,
            cache_key_prefix="ai_trans",
            mode='zh'
        )

class TranslationStatusView(APIView):
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
            else:
                return Response({
                    "status": "FAILED", 
                    "error": result_data.get('error', 'Lỗi không xác định')
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        elif res.state == 'FAILURE':
            return Response({
                "status": "FAILED", 
                "error": "Task execution failed"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
        # Nếu vẫn đang chạy hoặc nằm trong hàng đợi
        return Response({"status": res.state})