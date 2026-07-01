import os
import re
from celery import shared_task
from celery.exceptions import Retry
from .models import EnExample
from core_project.ws_utils import ws_notify

@shared_task(bind=True, max_retries=5, default_retry_delay=5)
def translate_en_pure_text_task(self, text_input, user_id=None, direction='en_vi', **kwargs):
    """
    Celery task to handle async translation via Database lookup or Vertex AI Priority PayGo.
    """
    q_lower = text_input.lower().strip()
    cleaned_query = re.sub(r'[. , ! ?]+$', '', q_lower)
    if not cleaned_query:
        result = {'error': 'No valid text provided', 'status': 'FAILED'}
        if user_id:
            ws_notify(
                user_id=user_id,
                event_type='translation_failed',
                title='Dịch thuật thất bại',
                payload={'task_id': self.request.id, 'error': result['error']},
                persist=False,
            )
        return result

    # Tầng 1: Tra cứu DB tiếng Anh (Chỉ dịch từ tiếng Anh sang tiếng Việt mới tra cứu DB)
    if direction == 'en_vi':
        match = EnExample.objects.filter(english__iexact=cleaned_query).first()
        if match:
            result = {
                'translatedText': match.vietnamese,
                'source': 'database',
                'status': 'SUCCESS'
            }
            if user_id:
                ws_notify(
                    user_id=user_id,
                    event_type='translation_complete',
                    title='Dịch thuật hoàn tất',
                    payload={'task_id': self.request.id, **result},
                    persist=False,
                )
            return result

        # Tầng 1.2: Tra cứu DB tiếng Anh (EnWord)
        from .models import EnWord
        word_match = EnWord.objects.filter(word__iexact=cleaned_query).first()
        if word_match:
            result = {
                'translatedText': word_match.translation_vi,
                'source': 'database',
                'status': 'SUCCESS'
            }
            if user_id:
                ws_notify(
                    user_id=user_id,
                    event_type='translation_complete',
                    title='Dịch thuật hoàn tất',
                    payload={'task_id': self.request.id, **result},
                    persist=False,
                )
            return result

    # Tầng 2: Gọi LLM (Vertex AI Priority PayGo)
    if direction == 'vi_en':
        system_prompt = "Bạn là chuyên gia dịch thuật Việt-Anh xuất sắc. Hãy dịch văn bản một cách mượt mà và tự nhiên nhất. Chỉ trả về kết quả dịch."
    else:
        system_prompt = "Bạn là chuyên gia dịch thuật Anh-Việt xuất sắc. Hãy dịch văn bản một cách mượt mà và tự nhiên nhất. Chỉ trả về kết quả dịch."
    
    try:
        translated_text = None
        try:
            from apps.core_shared.ai_client import get_genai_client
            from google.genai import errors
            
            client = get_genai_client()
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=q_lower,
                config={
                    'system_instruction': system_prompt
                }
            )
            translated_text = response.text.strip()
        except errors.APIError as e:
            # Catch 429 Resource Exhausted / Rate limits to trigger Celery retry
            if e.code == 429 or "429" in str(e) or "ResourceExhausted" in str(e):
                import random
                countdown = (2 ** self.request.retries) + random.randint(1, 3)
                print(f"Vertex AI got 429, retrying task in {countdown}s (retry {self.request.retries})...")
                raise self.retry(exc=e, countdown=countdown)
            raise e

        if translated_text:
            from django.core.cache import cache
            import hashlib
            hashed_text = hashlib.md5(text_input.encode('utf-8')).hexdigest()
            result_data = {
                'translatedText': translated_text,
                'source': 'ai_translation',
                'status': 'SUCCESS'
            }
            # Lưu cache dài hạn tiếng Anh tách biệt
            cache.set(f"ai_trans_en:{direction}:{hashed_text}", {"status": "success", "result": result_data}, timeout=7 * 24 * 60 * 60)
            if user_id:
                ws_notify(
                    user_id=user_id,
                    event_type='translation_complete',
                    title='Dịch thuật hoàn tất',
                    payload={'task_id': self.request.id, **result_data},
                    persist=False,
                )
            return result_data
        else:
            raise Exception('Empty response')
            
    except Retry:
        raise
    except Exception as e:
        print(f"Translation Task Error: {e}")
        result = {
            'error': f'Dịch vụ dịch thuật tạm thời không khả dụng. Chi tiết: {str(e)}',
            'status': 'FAILED'
        }
        if user_id:
            ws_notify(
                user_id=user_id,
                event_type='translation_failed',
                title='Dịch thuật thất bại',
                payload={'task_id': self.request.id, 'error': result['error']},
                persist=False,
            )
        return result
