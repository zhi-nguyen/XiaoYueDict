import hashlib
import uuid
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from django.core.cache import cache

from .tts_tasks import generate_tts_audio_task

logger = logging.getLogger(__name__)

class TriggerTTSView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        text = request.query_params.get('text', '').strip()
        voice = request.query_params.get('voice', '').strip()

        if not text or not voice:
            return Response(
                {"error": "Both 'text' and 'voice' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Compute MD5 cache key
        text_hash = hashlib.md5(f"{text}:{voice}".encode('utf-8')).hexdigest()
        cache_key = f"tts:audio:{text_hash}"

        # 2. Check if the audio is already generated and cached
        cached_url = cache.get(cache_key)
        if cached_url:
            return Response(
                {
                    "status": "SUCCESS",
                    "audio_url": cached_url,
                    "text": text,
                    "voice": voice
                },
                status=status.HTTP_200_OK
            )

        # 3. Resolve user_id / guest_id for WebSocket routing
        if request.user.is_authenticated:
            user_id = str(request.user.id)
            user_tier = getattr(request.user.subscription, 'tier', 'Free') if hasattr(request.user, 'subscription') else 'Free'
        else:
            user_id = request.headers.get('X-Guest-ID') or request.query_params.get('guest_id')
            if not user_id:
                user_id = f"guest_{uuid.uuid4()}"
            user_tier = 'Guest'

        # 4. Trigger Celery background task
        task_id = str(uuid.uuid4())
        generate_tts_audio_task.apply_async(
            kwargs={
                'task_id': task_id,
                'user_id': user_id,
                'text': text,
                'voice': voice,
                'cache_key': cache_key,
                'user_tier': user_tier
            }
        )

        logger.info(f"Enqueued async TTS task {task_id} for user {user_id}. Text length: {len(text)}")

        return Response(
            {
                "status": "PENDING",
                "task_id": task_id,
                "text": text,
                "voice": voice
            },
            status=status.HTTP_202_ACCEPTED
        )
