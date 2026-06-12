from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.db.models import Q, Case, When, Value, IntegerField, F, Exists, OuterRef
from django.contrib.postgres.search import SearchQuery
from django.db.models.functions import Length, StrIndex
from django.core.cache import cache

from .models import ZhWord, ZhExample
from .serializers import ZhWordSerializer
import re
import jieba

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'anonymous')

def get_translation_char_limit(user):
    if not user or not user.is_authenticated:
        return 150  # GUEST limit is 150 characters
    try:
        tier = user.subscription.tier if hasattr(user, 'subscription') else 'Free'
    except Exception:
        tier = 'Free'
        
    tier = tier.lower()
    if tier == 'plus':
        return 1000
    elif tier == 'pro':
        return 2000
    elif tier == 'premium':
        return 3000
    else: # free
        return 500



class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class ZhWordSearchView(generics.ListAPIView):
    serializer_class = ZhWordSerializer
    pagination_class = StandardResultsSetPagination

    def list(self, request, *args, **kwargs):
        query = self.request.query_params.get('q', '').strip()
        query_len = len(query)

        # [LỚP 2]: Kiểm tra và giới hạn độ dài đầu vào (Input Guardrail)
        if query_len > 100:
            return Response({"detail": "Từ khóa vượt quá độ dài cho phép."}, status=400)

        queryset = self.filter_queryset(self.get_queryset())
        
        exact_example = None
        
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

        # Kiểm tra DB Hit
        db_hit = queryset.exists() or (exact_example is not None)

        if query and not db_hit:
            # [LỚP 1]: DB Miss -> Kiểm tra AI Cache chống Cache Stampede
            ai_cache_key = f"ai_trans:{query}"
            cached_data = cache.get(ai_cache_key)

            if cached_data:
                # KỊCH BẢN A: Tác vụ đã hoàn tất và có dữ liệu phản hồi
                if cached_data.get('status') == 'success':
                    return Response(cached_data['result'])
                    
                # KỊCH BẢN B: Tác vụ đang được xử lý (Cơ chế ngăn chặn Cache Stampede)
                if cached_data.get('status') == 'processing':
                    # Trả về task_id hiện tại để Frontend tiếp tục quá trình Polling, không tính phạt Rate Limit
                    return Response({"task_id": cached_data['task_id']}, status=202)

            # =========================================================================
            # DB MISS & AI CACHE MISS (Khởi tạo tác vụ mới & Throttling)
            # =========================================================================
            user = request.user
            ident = f"user_{user.id}" if user.is_authenticated else f"ip_{get_client_ip(request)}"
            ai_throttle_key = f"throttle:ai_fallback:{ident}"
            
            try:
                redis_client = cache.client.get_client()
                current_ai_requests = redis_client.incr(ai_throttle_key)
                if current_ai_requests == 1:
                    redis_client.expire(ai_throttle_key, 60)
            except Exception:
                current_ai_requests = cache.get(ai_throttle_key, 0) + 1
                cache.set(ai_throttle_key, current_ai_requests, timeout=60)

            if current_ai_requests > 3:
                return Response(
                    {"detail": "Tài khoản đã vượt định mức dịch thuật từ vựng bằng AI. Vui lòng thử lại sau ít phút."}, 
                    status=429
                )

            # KÍCH HOẠT TÁC VỤ CELERY BẤT ĐỒNG BỘ
            from .tasks import translate_pure_text_task
            task = translate_pure_text_task.apply_async(args=[query], queue='queue_core')

            # THIẾT LẬP CỜ TRẠNG THÁI TRÊN REDIS (Sử dụng thời gian sống ngắn, ví dụ: 5 phút)
            cache.set(ai_cache_key, {"status": "processing", "task_id": task.id}, timeout=5 * 60)

            return Response({"task_id": task.id}, status=202)

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
        
        # Tokenize query for FTS Search
        tokenized_query = " ".join(jieba.cut(query))
        query_obj = SearchQuery(tokenized_query, config='simple')
        
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
        
        # [LỚP 2]: Kiểm soát độ dài nghiêm ngặt dựa theo phân khúc tài khoản
        limit = get_translation_char_limit(request.user)
        if len(text_input) > limit:
            return Response({
                "detail": f"Độ dài văn bản vượt quá hạn mức cho phép của tài khoản ({limit} ký tự).",
                "error": f"Độ dài văn bản vượt quá hạn mức cho phép của tài khoản ({limit} ký tự)."
            }, status=status.HTTP_400_BAD_REQUEST)

        # [LỚP 1]: Kiểm tra AI Cache chống Cache Stampede
        ai_cache_key = f"ai_trans:{text_input}"
        cached_data = cache.get(ai_cache_key)

        if cached_data:
            # KỊCH BẢN A: Tác vụ đã hoàn tất và có dữ liệu phản hồi
            if cached_data.get('status') == 'success':
                return Response(cached_data['result'])
                
            # KỊCH BẢN B: Tác vụ đang được xử lý (Cơ chế ngăn chặn Cache Stampede)
            if cached_data.get('status') == 'processing':
                # Trả về task_id hiện tại để Frontend tiếp tục quá trình Polling
                return Response({"task_id": cached_data['task_id']}, status=202)

        # Đẩy vào Celery queue_core và lấy task_id ngay lập tức
        task = translate_pure_text_task.apply_async(
            args=[text_input], 
            queue='queue_core'
        )
        
        # THIẾT LẬP CỜ TRẠNG THÁI TRÊN REDIS (Sử dụng thời gian sống ngắn, ví dụ: 5 phút)
        cache.set(ai_cache_key, {"status": "processing", "task_id": task.id}, timeout=5 * 60)
        
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