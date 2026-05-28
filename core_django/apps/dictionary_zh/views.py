from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import Q, Case, When, Value, IntegerField, F, Exists, OuterRef
from django.contrib.postgres.search import SearchQuery
from django.db.models.functions import Length, StrIndex

from .models import ZhWord, ZhExample
from .serializers import ZhWordSerializer
import re

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ZhWordSearchView(generics.ListAPIView):
    serializer_class = ZhWordSerializer
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        query = self.request.query_params.get('q', '').strip()
        
        exact_example = None
        query_len = len(query)
        
        # Chỉ quét ví dụ nếu độ dài hợp lý (từ 2 đến 100 ký tự)
        if 2 <= query_len <= 100:
            from .models import ZhExample
            
            # Làm sạch dấu câu ở cuối chuỗi truy vấn (nếu có)
            cleaned_query = re.sub(r'[。，、！？. , ! ?]+$', '', query)
            
            # 1. Thử tìm khớp chính xác hoàn toàn trước (cho phép dấu câu tùy chọn ở cuối)
            regex_pattern = r'^' + re.escape(cleaned_query) + r'[。，、！？. , ! ?]*$'
            match = ZhExample.objects.filter(chinese__iregex=regex_pattern).first()
            
            # 2. Nếu không khớp hoàn toàn, mới dùng contains (Quét chuỗi)
            if not match:
                match = ZhExample.objects.filter(chinese__contains=cleaned_query).first()
                
            if match:
                exact_example = {
                    'chinese': match.chinese,
                    'pinyin': match.pinyin,
                    'vietnamese': match.vietnamese
                }

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
            
        if not query:
            # If no query but HSK is provided, just return paginated results ordered by popularity
            return queryset.annotate(
                adjusted_rank=Case(
                    When(popularity_rank=0, then=Value(999999)),
                    default='popularity_rank',
                    output_field=IntegerField(),
                )
            ).order_by('adjusted_rank')

        q_lower = query.lower()
        query_obj = SearchQuery(query, config='simple')
        
        # 0. Subquery to check for example match without causing joins
        has_example_match = Exists(
            ZhExample.objects.filter(word=OuterRef('pk'), search_vector=query_obj)
        )
        
        # 1. Annotate word length and reverse match index
        queryset = queryset.annotate(
            word_len=Length('word'),
            word_idx=StrIndex(Value(query), F('word'))
        )
        
        # 2. Comprehensive search logic covering all cases
        queryset = queryset.annotate(
            match_level=Case(
                When(Q(word__exact=query) | Q(traditional__exact=query), then=Value(1)),
                When(Q(toneless_pinyin__iexact=q_lower) | Q(pinyin__iexact=q_lower), then=Value(2)),
                When(Q(word__startswith=query) | Q(traditional__startswith=query), then=Value(3)),
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
        if len(query) >= 2:
            queryset = queryset.filter(match_level__lte=8).distinct()
        else:
            queryset = queryset.filter(match_level__lte=7).distinct()
            
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
        text_input = request.data.get("text", "").strip()
        if not text_input:
            return Response({'error': 'No text provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Đẩy vào Celery queue_core và lấy task_id ngay lập tức
        task = translate_pure_text_task.apply_async(
            args=[text_input], 
            queue='queue_core'
        )
        
        return Response({
            "status": "PENDING",
            "task_id": task.id
        }, status=status.HTTP_202_ACCEPTED)

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