import os
import re
from celery import shared_task
from .models import EnExample

@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def translate_en_pure_text_task(self, text_input):
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

    # Tầng 2: Gọi LLM
    system_prompt = "Bạn là chuyên gia dịch thuật Anh-Việt xuất sắc. Hãy dịch văn bản một cách mượt mà và tự nhiên nhất. Chỉ trả về kết quả dịch."
    try:
        translated_text = None
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init()
            model = GenerativeModel('gemini-2.5-flash', system_instruction=[system_prompt])
            response = model.generate_content(q_lower)
            translated_text = response.text.strip()
        except Exception:
            import google.generativeai as genai
            api_key = os.environ.get('GEMINI_API_KEY', '')
            if api_key:
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=system_prompt)
                response = model.generate_content(q_lower)
                translated_text = response.text.strip()

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
    except Exception as e:
        return {
            'error': f'Dịch vụ dịch thuật tạm thời không khả dụng. Chi tiết: {str(e)}',
            'status': 'FAILED'
        }
