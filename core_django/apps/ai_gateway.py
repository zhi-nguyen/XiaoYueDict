import re
import logging
import hashlib
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache

logger = logging.getLogger(__name__)


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
            direction = "zh_vi" if mode == 'zh' else "en_vi"
            import hashlib
            hashed_query = hashlib.md5(query.encode('utf-8')).hexdigest()
            ai_cache_key = f"{cache_key_prefix}:{direction}:{hashed_query}"
            cached_data = cache.get(ai_cache_key)

            if cached_data:
                if cached_data.get('status') == 'success':
                    return Response(cached_data['result'])
                if cached_data.get('status') == 'processing':
                    return Response({"status": "PENDING", "task_id": cached_data['task_id']}, status=status.HTTP_202_ACCEPTED)

            # Khống chế giới hạn Conditional Rate Limit theo Tier tài khoản (Tránh throttling khi tìm kiếm chuỗi ký tự dài)
            user = request.user
            if not user or not user.is_authenticated:
                ai_limit = 15  # Guest: 15 lần/phút
            else:
                try:
                    tier = user.subscription.tier if hasattr(user, 'subscription') else 'Free'
                except Exception:
                    tier = 'Free'
                
                tier = tier.lower()
                if tier == 'plus':
                    ai_limit = 60   # Plus: 60 lần/phút
                elif tier == 'pro':
                    ai_limit = 100  # Pro: 100 lần/phút
                elif tier == 'premium':
                    ai_limit = 120  # Premium: 120 lần/phút
                else:
                    ai_limit = 30   # Free: 30 lần/phút

            ident = f"user_{user.id}" if user and user.is_authenticated else f"ip_{cls.get_client_ip(request)}"
            ai_throttle_key = f"throttle:ai_fallback:{ident}"
            
            try:
                redis_client = cache.client.get_client()
                current_ai_requests = redis_client.incr(ai_throttle_key)
                if current_ai_requests == 1:
                    redis_client.expire(ai_throttle_key, 60)
            except Exception:
                current_ai_requests = cache.get(ai_throttle_key, 0) + 1
                cache.set(ai_throttle_key, current_ai_requests, timeout=60)

            if current_ai_requests > ai_limit:
                return Response(
                    {"detail": f"Tài khoản đã vượt định mức dịch thuật bằng AI của gói hiện tại ({ai_limit} lần/phút). Vui lòng thử lại sau ít phút."}, 
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            # Kích hoạt Celery Task dịch thuật
            user = request.user
            guest_id = request.data.get("guest_id") or request.query_params.get("guest_id")
            effective_user_id = str(user.id) if user.is_authenticated else guest_id

            if not effective_user_id:
                logger.warning(
                    f"⚠️ No user_id or guest_id found for AI search fallback task (query: {query}). "
                    "WebSocket notification will NOT be sent."
                )

            # Determine user tier for SLA routing
            if user and user.is_authenticated:
                user_tier = getattr(user.subscription, 'tier', 'Free') if hasattr(user, 'subscription') else 'Free'
            else:
                user_tier = 'Guest'

            task_kwargs = {"user_id": effective_user_id} if effective_user_id else {}
            task_kwargs["user_tier"] = user_tier

            task = task_func.apply_async(
                args=[query], 
                kwargs=task_kwargs
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
        
        direction = request.data.get("direction")
        if not direction:
            direction = "zh_vi" if mode == 'zh' else "en_vi"
        
        input_mode = 'en' if direction.startswith('vi_') else mode
        limit = cls.get_translation_char_limit(request.user, mode=input_mode)
        text_len = cls.count_words(text_input, mode=input_mode)
        
        if text_len > limit:
            unit = "ký tự" if input_mode == 'zh' else "từ"
            msg = f"Độ dài văn bản vượt quá hạn mức cho phép của tài khoản ({limit} {unit})."
            return Response({
                "detail": msg,
                "error": msg
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── Tầng 0: Tra cứu cơ sở dữ liệu đồng bộ (Chỉ áp dụng khi dịch sang Tiếng Việt) ──
        if direction in ['zh_vi', 'en_vi']:
            q_lower = text_input.lower().strip()
            
            if mode == 'zh':
                from apps.dictionary_zh.models import ZhWord, ZhExample
                from django.db.models import Q
                
                cleaned_query = re.sub(r'[。，、！？. , ! ?]+$', '', q_lower)
                if cleaned_query:
                    # 1. Check ZhExample (exact example match)
                    regex_pattern = r'^' + re.escape(cleaned_query) + r'[。，、！？. , ! ?]*$'
                    match = ZhExample.objects.filter(chinese__iregex=regex_pattern).first()
                    if match:
                        return Response({
                            'translatedText': match.vietnamese,
                            'source': 'database',
                            'status': 'SUCCESS'
                        }, status=status.HTTP_200_OK)
                    
                    # 2. Check ZhWord (dictionary word match)
                    word_match = ZhWord.objects.filter(Q(word=cleaned_query) | Q(traditional=cleaned_query)).first()
                    if word_match:
                        return Response({
                            'translatedText': word_match.translation_vi,
                            'source': 'database',
                            'status': 'SUCCESS'
                        }, status=status.HTTP_200_OK)
                        
            elif mode == 'en':
                from apps.dictionary_en.models import EnWord, EnExample
                
                cleaned_query = re.sub(r'[. , ! ?]+$', '', q_lower)
                if cleaned_query:
                    # 1. Check EnExample
                    match = EnExample.objects.filter(english__iexact=cleaned_query).first()
                    if match:
                        return Response({
                            'translatedText': match.vietnamese,
                            'source': 'database',
                            'status': 'SUCCESS'
                        }, status=status.HTTP_200_OK)
                    
                    # 2. Check EnWord
                    word_match = EnWord.objects.filter(word__iexact=cleaned_query).first()
                    if word_match:
                        return Response({
                            'translatedText': word_match.translation_vi,
                            'source': 'database',
                            'status': 'SUCCESS'
                        }, status=status.HTTP_200_OK)

        hashed_text = hashlib.md5(text_input.encode('utf-8')).hexdigest()
        ai_cache_key = f"{cache_key_prefix}:{direction}:{hashed_text}"
        cached_data = cache.get(ai_cache_key)

        if cached_data:
            if cached_data.get('status') == 'success':
                return Response(cached_data['result'])
            if cached_data.get('status') == 'processing':
                return Response({"status": "PENDING", "task_id": cached_data['task_id']}, status=status.HTTP_202_ACCEPTED)

        user = request.user
        guest_id = request.data.get("guest_id") or request.query_params.get("guest_id")
        effective_user_id = str(user.id) if user.is_authenticated else guest_id

        if not effective_user_id:
            logger.warning(
                f"⚠️ No user_id or guest_id found for AI translation fallback task (input: {text_input[:20]}...). "
                "WebSocket notification will NOT be sent."
            )

        # Determine user tier for SLA routing
        if user and user.is_authenticated:
            user_tier = getattr(user.subscription, 'tier', 'Free') if hasattr(user, 'subscription') else 'Free'
        else:
            user_tier = 'Guest'

        task_kwargs = {
            "user_id": effective_user_id,
            "direction": direction
        } if effective_user_id else {"direction": direction}
        task_kwargs["user_tier"] = user_tier

        task = task_func.apply_async(
            args=[text_input], 
            kwargs=task_kwargs
        )
        cache.set(ai_cache_key, {"status": "processing", "task_id": task.id}, timeout=5 * 60)
        
        return Response({
            "status": "PENDING",
            "task_id": task.id
        }, status=status.HTTP_202_ACCEPTED)
