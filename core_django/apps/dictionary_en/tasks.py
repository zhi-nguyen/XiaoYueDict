import os
import re
from celery import shared_task
from celery.exceptions import Retry
from .models import EnExample

@shared_task(bind=True, max_retries=5, default_retry_delay=5)
def translate_en_pure_text_task(self, text_input):
    """
    Celery task to handle async translation via Database lookup or Vertex AI Priority PayGo.
    """
    q_lower = text_input.lower().strip()
    cleaned_query = re.sub(r'[. , ! ?]+$', '', q_lower)
    if not cleaned_query:
        return {'error': 'No valid text provided', 'status': 'FAILED'}

    # Tầng 1: Tra cứu DB tiếng Anh
    match = EnExample.objects.filter(english__iexact=cleaned_query).first()
    if match:
        return {
            'translatedText': match.vietnamese,
            'source': 'database',
            'status': 'SUCCESS'
        }

    # Tầng 2: Gọi LLM (Vertex AI Priority PayGo)
    system_prompt = "Bạn là chuyên gia dịch thuật Anh-Việt xuất sắc. Hãy dịch văn bản một cách mượt mà và tự nhiên nhất. Chỉ trả về kết quả dịch."
    try:
        translated_text = None
        try:
            from google import genai
            from google.genai import errors
            
            client = genai.Client(
                vertexai=True,
                http_options={
                    'headers': {
                        'X-Vertex-AI-LLM-Shared-Request-Type': 'priority'
                    }
                }
            )
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
            result_data = {
                'translatedText': translated_text,
                'source': 'ai_translation',
                'status': 'SUCCESS'
            }
            # Lưu cache dài hạn tiếng Anh tách biệt
            cache.set(f"ai_trans_en:{text_input}", {"status": "success", "result": result_data}, timeout=7 * 24 * 60 * 60)
            return result_data
        else:
            raise Exception('Empty response')
            
    except Retry:
        raise
    except Exception as e:
        print(f"Translation Task Error: {e}")
        return {
            'error': f'Dịch vụ dịch thuật tạm thời không khả dụng. Chi tiết: {str(e)}',
            'status': 'FAILED'
        }

