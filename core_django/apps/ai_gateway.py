import re
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache

class AIFallbackGateway:
    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'anonymous')

    @staticmethod
    def get_translation_char_limit(user, mode='zh'):
        """
        Lấy hạn mức ký tự (zh) hoặc số từ (en) dựa theo gói tài khoản.
        """
        if not user or not user.is_authenticated:
            return 150 if mode == 'zh' else 50 # Guest: 150 kí tự (zh) hoặc 50 từ (en)
        try:
            tier = user.subscription.tier if hasattr(user, 'subscription') else 'Free'
        except Exception:
            tier = 'Free'
            
        tier = tier.lower()
        if tier == 'plus':
            return 1000 if mode == 'zh' else 350
        elif tier == 'pro':
            return 2000 if mode == 'zh' else 700
        elif tier == 'premium':
            return 3000 if mode == 'zh' else 1000
        else: # Free
            return 500 if mode == 'zh' else 180

    @staticmethod
    def count_words(text, mode='zh'):
        """
        Cơ chế đếm linh hoạt:
        - zh: đếm ký tự (characters)
        - en: đếm từ độc lập (.split())
        """
        if not text:
            return 0
        if mode == 'en':
            return len(text.split())
        return len(text)

    @classmethod
    def handle_search_fallback(cls, request, query, db_lookup_func, task_func, cache_key_prefix="ai_trans", mode='zh'):
        """
        Logic điều phối phòng thủ chung cho API Tìm kiếm.
        """
        query_len = cls.count_words(query, mode=mode)
        max_limit = 100 if mode == 'zh' else 30 # Giới hạn từ khóa tìm kiếm: 100 kí tự (zh) hoặc 30 từ (en)

        if query_len > max_limit:
            msg = f"Từ khóa vượt quá độ dài cho phép ({max_limit} {'ký tự' if mode == 'zh' else 'từ'})."
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # Chạy hàm callback để kiểm tra DB Hit & Lưu dữ liệu vào closure container
        db_hit = db_lookup_func()

        if query and not db_hit:
            # Tra cứu bộ nhớ đệm AI (Redis Cache)
            ai_cache_key = f"{cache_key_prefix}:{query}"
            cached_data = cache.get(ai_cache_key)

            if cached_data:
                if cached_data.get('status') == 'success':
                    return Response(cached_data['result'])
                if cached_data.get('status') == 'processing':
                    return Response({"task_id": cached_data['task_id']}, status=status.HTTP_202_ACCEPTED)

            # Khống chế giới hạn Conditional Rate Limit (3 lần/phút)
            user = request.user
            ident = f"user_{user.id}" if user.is_authenticated else f"ip_{cls.get_client_ip(request)}"
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
                    {"detail": "Tài khoản đã vượt định mức dịch thuật bằng AI. Vui lòng thử lại sau ít phút."}, 
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            # Kích hoạt Celery Task dịch thuật
            user = request.user
            guest_id = request.data.get("guest_id") or request.query_params.get("guest_id")
            effective_user_id = str(user.id) if user.is_authenticated else guest_id

            task = task_func.apply_async(
                args=[query], 
                kwargs={"user_id": effective_user_id} if effective_user_id else {},
                queue='queue_core'
            )

            # Thiết lập trạng thái xử lý ngầm (chống Cache Stampede)
            cache.set(ai_cache_key, {"status": "processing", "task_id": task.id}, timeout=5 * 60)

            return Response({"task_id": task.id}, status=status.HTTP_202_ACCEPTED)

        return None

    @classmethod
    def handle_translation_fallback(cls, request, task_func, cache_key_prefix="ai_trans", mode='zh'):
        """
        Logic điều phối phòng thủ chung cho API Dịch thuật.
        """
        text_input = request.data.get("text", "").strip()
        if not text_input:
            return Response({'error': 'No text provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        limit = cls.get_translation_char_limit(request.user, mode=mode)
        text_len = cls.count_words(text_input, mode=mode)
        
        if text_len > limit:
            unit = "ký tự" if mode == 'zh' else "từ"
            msg = f"Độ dài văn bản vượt quá hạn mức cho phép của tài khoản ({limit} {unit})."
            return Response({
                "detail": msg,
                "error": msg
            }, status=status.HTTP_400_BAD_REQUEST)

        ai_cache_key = f"{cache_key_prefix}:{text_input}"
        cached_data = cache.get(ai_cache_key)

        if cached_data:
            if cached_data.get('status') == 'success':
                return Response(cached_data['result'])
            if cached_data.get('status') == 'processing':
                return Response({"task_id": cached_data['task_id']}, status=status.HTTP_202_ACCEPTED)

        user = request.user
        guest_id = request.data.get("guest_id") or request.query_params.get("guest_id")
        effective_user_id = str(user.id) if user.is_authenticated else guest_id

        task = task_func.apply_async(
            args=[text_input], 
            kwargs={"user_id": effective_user_id} if effective_user_id else {},
            queue='queue_core'
        )
        cache.set(ai_cache_key, {"status": "processing", "task_id": task.id}, timeout=5 * 60)
        
        return Response({
            "status": "PENDING",
            "task_id": task.id
        }, status=status.HTTP_202_ACCEPTED)
