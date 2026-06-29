import hashlib
import requests
import logging
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from celery import shared_task
from core_project.ws_utils import ws_notify

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def generate_tts_audio_task(self, task_id, user_id, text, voice, cache_key):
    logger.info(f"Starting async TTS task {task_id} for user {user_id}. Text: {text[:20]}...")
    try:
        # 1. Fetch audio binary from internal TTS service
        tts_internal_url = f"http://tts-service:8002/api/v1/tts?text={requests.utils.quote(text)}&voice={voice}"
        response = requests.get(tts_internal_url, timeout=15)
        response.raise_for_status()

        # 2. Save file to storage
        text_hash = hashlib.md5(f"{text}:{voice}".encode('utf-8')).hexdigest()
        filename = f"tts/{text_hash}.mp3"
        
        # Save to default storage (local media volume or GCS bucket depending on django config)
        saved_path = default_storage.save(filename, ContentFile(response.content))
        audio_url = default_storage.url(saved_path)

        # 3. Cache the URL to bypass generation next time
        cache.set(cache_key, audio_url, timeout=60 * 60 * 24 * 7) # Cache for 7 days

        logger.info(f"TTS audio generated successfully for task {task_id}. URL: {audio_url}")

        # 4. Notify client via WebSocket
        ws_notify(
            user_id=user_id,
            event_type='tts_complete',
            title='Đã sinh giọng nói thành công',
            payload={
                'task_id': task_id,
                'audio_url': audio_url,
                'text': text
            }
        )
        return {"status": "success", "audio_url": audio_url}

    except Exception as exc:
        logger.error(f"Error generating TTS for task {task_id}: {exc}")
        ws_notify(
            user_id=user_id,
            event_type='tts_failed',
            title='Lỗi sinh giọng nói',
            payload={
                'task_id': task_id,
                'error': str(exc)
            }
        )
        raise self.retry(exc=exc)
