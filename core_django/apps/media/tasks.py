import logging
import requests
from django.core.cache import cache
from celery import shared_task
from apps.dictionary_zh.models import ZhWord
from apps.dictionary_en.models import EnWord
from apps.media.models import ZhEnMapping
from core_project.ws_utils import ws_notify

logger = logging.getLogger(__name__)

IMAGE_SERVICE_URL = "http://image-service:8003/api/v1/image/generate"
IMAGE_DELETE_URL = "http://image-service:8003/api/v1/image/delete"

def get_word_by_id(word_id, lang):
    try:
        if lang == 'zh':
            return ZhWord.objects.get(pk=word_id)
        else:
            return EnWord.objects.get(pk=word_id)
    except (ZhWord.DoesNotExist, EnWord.DoesNotExist):
        return None


def _resolve_prompt_keyword(word_id, lang, word):
    """
    Chiến lược Ưu tiên Dữ liệu Đầu vào (Prompt Injection Priority):
    
    1. ZhEnMapping.en_translation (sanitized keyword) — ưu tiên tuyệt đối
    2. ZhWord.translation_en (first keyword) — graceful degradation
    3. word.word (từ vựng gốc) — last resort
    
    Returns: clean English keyword string for AI prompt
    """
    try:
        if lang == 'zh':
            mapping = ZhEnMapping.objects.filter(zh_word_id=word_id).first()
        else:
            mapping = ZhEnMapping.objects.filter(en_word_id=word_id).first()

        if mapping and mapping.en_translation:
            return mapping.en_translation
    except Exception as e:
        logger.warning(f"ZhEnMapping lookup failed for {word_id}: {e}")

    # Graceful Degradation: fallback to translation_en field
    translation_en = getattr(word, 'translation_en', '') or ''
    if translation_en:
        first_keyword = translation_en.split(',')[0].strip()
        if first_keyword:
            return first_keyword

    return word.word


@shared_task
def generate_word_image_task(word_id, lang, user_id):
    logger.info(f"Celery task: generating image for word_id={word_id}, lang={lang}, user={user_id}")
    word = get_word_by_id(word_id, lang)
    redis_key = f"img:{lang}:{word_id}"
    
    if not word:
        logger.error(f"Word {word_id} ({lang}) not found for image generation.")
        cache.delete(redis_key)
        return
        
    # Build a high quality prompt — Ưu tiên tuyệt đối ZhEnMapping.en_translation
    # (sanitized keyword) thay vì ZhWord.translation_en (có noise data)
    clean_keyword = _resolve_prompt_keyword(word_id, lang, word)
    if lang == 'zh':
        prompt = f"Flat design educational vector illustration visualizing the concept of the Chinese word '{clean_keyword}' ({word.word}). Modern clean graphic style, solid white background, no texts, no words, no letters, no typography."
    else:
        prompt = f"Flat design educational vector illustration visualizing the concept of the word '{clean_keyword}'. Modern clean graphic style, solid white background, no texts, no words, no letters, no typography."
    try:
        res = requests.post(IMAGE_SERVICE_URL, json={
            "word_id": str(word_id),
            "lang": lang,
            "prompt": prompt
        }, timeout=60)
        
        if res.status_code == 200:
            data = res.json()
            image_url = data.get("image_url")
            if image_url:
                # Save to database
                word.image_url = image_url
                word.save()
                
                # Cache to Redis
                cache_data = {"status": "ready", "image_url": image_url}
                cache.set(redis_key, cache_data, timeout=None)
                
                # Notify client via WebSocket
                ws_notify(
                    user_id=user_id,
                    event_type="image_complete",
                    title="Hình ảnh đã tải xong",
                    payload={"word_id": word_id, "image_url": image_url}
                )
                logger.info(f"Successfully generated and cached GCS image: {image_url}")
                return
        
        raise Exception(f"Image service returned status {res.status_code}: {res.text}")
        
    except Exception as e:
        logger.error(f"Failed to generate image for {word.word} ({word_id}): {e}")
        # Evict lock/cache so it can retry
        cache.delete(redis_key)
        # Notify failure via WS
        ws_notify(
            user_id=user_id,
            event_type="image_failed",
            title="Lỗi tải hình ảnh",
            payload={"word_id": word_id, "error": str(e)}
        )

@shared_task
def trigger_image_regeneration_task(word_id, lang, user_id):
    logger.info(f"Celery task: regenerating image for word_id={word_id}, lang={lang}, user={user_id}")
    word = get_word_by_id(word_id, lang)
    if not word:
        return

    # Delete existing GCS file via image-service
    try:
        res = requests.delete(IMAGE_DELETE_URL, json={
            "word_id": str(word_id),
            "lang": lang
        }, timeout=10)
        logger.info(f"Deleted old image from GCS: {res.status_code}")
    except Exception as e:
        logger.error(f"Failed to delete GCS image: {e}")

    # Reset DB image_url
    word.image_url = ''
    word.save()

    # Re-run generation
    generate_word_image_task(word_id, lang, user_id)
