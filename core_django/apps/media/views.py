import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.cache import cache
from .models import ZhEnMapping
from .tasks import get_word_by_id, generate_word_image_task, trigger_image_regeneration_task

logger = logging.getLogger(__name__)

class GetWordImageView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request, lang, word_id):
        redis_key = f"img:{lang}:{word_id}"
        cached_data = cache.get(redis_key)
        
        # 1. Cache Hit check
        if cached_data:
            return Response(cached_data)

        # 2. Check Database
        word = get_word_by_id(word_id, lang)
        if not word:
            return Response({"detail": "Word not found"}, status=404)

        if word.image_url:
            data = {"status": "ready", "image_url": word.image_url}
            cache.set(redis_key, data, timeout=None)  # Infinite cache
            return Response(data)

        # 2.5 Cross-Language Bridge — Mượn ảnh từ ngôn ngữ anh em qua ZhEnMapping
        bridged_url = self._try_cross_language_bridge(word, word_id, lang)
        if bridged_url:
            word.image_url = bridged_url
            word.save(update_fields=['image_url'])
            data = {"status": "ready", "image_url": bridged_url}
            cache.set(redis_key, data, timeout=None)
            return Response(data)

        # 3. Cache Miss & DB Miss -> Trigger Celery Task
        # Check if already generating (Redis lock flag)
        lock_key = f"generating:img:{lang}:{word_id}"
        if cache.get(lock_key):
            return Response({"status": "GENERATING"})

        # Get WebSocket routing ID
        user_id = None
        if request.user.is_authenticated:
            user_id = str(request.user.id)
        else:
            guest_id = request.query_params.get('guest_id')
            if guest_id:
                user_id = guest_id if str(guest_id).startswith('guest_') else f"guest_{guest_id}"

        # Acquire lock for 5 minutes
        cache.set(lock_key, True, timeout=300)
        cache.set(redis_key, {"status": "GENERATING"}, timeout=300)

        # Trigger Celery Task in the correct queue
        generate_word_image_task.apply_async(
            args=[str(word_id), lang, user_id],
            queue='queue_core'
        )
        
        return Response({"status": "GENERATING"}, status=202)

    @staticmethod
    def _try_cross_language_bridge(word, word_id, lang):
        """
        Tìm kiếm ảnh từ ngôn ngữ đối xứng qua bảng ZhEnMapping.
        
        Nếu lang='en' và EnWord chưa có ảnh → tìm ZhWord tương ứng có ảnh.
        Nếu lang='zh' và ZhWord chưa có ảnh → tìm EnWord tương ứng có ảnh.
        
        Returns: image_url (str) hoặc None
        """
        try:
            if lang == 'en':
                mapping = (
                    ZhEnMapping.objects
                    .filter(en_word_id=word_id)
                    .select_related('zh_word')
                    .first()
                )
                if mapping and mapping.zh_word and mapping.zh_word.image_url:
                    return mapping.zh_word.image_url
            elif lang == 'zh':
                mapping = (
                    ZhEnMapping.objects
                    .filter(zh_word_id=word_id)
                    .select_related('en_word')
                    .first()
                )
                if mapping and mapping.en_word and mapping.en_word.image_url:
                    return mapping.en_word.image_url
        except Exception as e:
            logger.warning(f"Cross-language bridge lookup failed: {e}")
        return None


class ReportInvalidImageView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = []

    def post(self, request):
        word_id = request.data.get('word_id')
        lang = request.data.get('lang', 'zh')
        if not word_id:
            return Response({"detail": "Tham số word_id không được để trống."}, status=400)

        redis_key = f"img:{lang}:{word_id}"
        lock_key = f"generating:img:{lang}:{word_id}"
        
        # CHỐT CHẶN BẢO VỆ (GUARDRAIL): Thiết lập cờ trạng thái giữ chỗ (Lock Placeholder)
        # Ngăn chặn hoàn toàn hiện tượng các requests đồng thời kích hoạt trùng tác vụ Celery
        cache.set(redis_key, {"status": "REGENERATING"}, timeout=300)
        cache.set(lock_key, True, timeout=300)

        # Đẩy tác vụ xử lý bất đồng bộ vào Celery để xóa file cũ và gọi API tái tạo ảnh mới
        user_id = str(request.user.id)
        trigger_image_regeneration_task.apply_async(
            args=[str(word_id), lang, user_id],
            queue='queue_core'
        )
        
        return Response({"detail": "Hình ảnh đang được hệ thống xử lý tái tạo bất đồng bộ."}, status=202)
