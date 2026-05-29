import os
import re
from celery import shared_task
from .models import ZhExample

@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def translate_pure_text_task(self, text_input):
    """
    Celery task to handle async translation via Database lookup or Vertex AI / Gemini.
    """
    # Normalize text as requested by user
    q_lower = text_input.lower().strip()
    cleaned_query = re.sub(r'[。，、！？. , ! ?]+$', '', q_lower)
    if not cleaned_query:
        return {'error': 'No valid text provided', 'status': 'FAILED'}

    # Tầng 1: Kiểm tra Database (ZhExample)
    # Sử dụng iregex cho phép dấu câu tùy chọn ở cuối
    regex_pattern = r'^' + re.escape(cleaned_query) + r'[。，、！？. , ! ?]*$'
    match = ZhExample.objects.filter(chinese__iregex=regex_pattern).first()
    if match:
        return {
            'translatedText': match.vietnamese,
            'source': 'database',
            'status': 'SUCCESS'
        }

    # Tầng 2: Gọi AI Fallback (Gemini/GCP API)
    system_prompt = "Bạn là một chuyên gia dịch thuật tiếng Trung sang tiếng Việt. Hãy dịch một cách mượt mà và tự nhiên nhất, chỉ trả về kết quả, không giải thích gì thêm."
    
    try:
        translated_text = None
        
        try:
            # Attempt Vertex AI
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init()
            model = GenerativeModel(
                'gemini-2.5-flash',
                system_instruction=[system_prompt]
            )
            response = model.generate_content(q_lower)
            translated_text = response.text.strip()
        except Exception as e:
            print(f"Vertex AI failed in celery: {e}")
            # Fallback to standard Gemini API
            import google.generativeai as genai
            api_key = os.environ.get('GEMINI_API_KEY', '')
            if not api_key:
                raise Exception('No API keys configured for translation')
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=system_prompt)
            response = model.generate_content(q_lower)
            translated_text = response.text.strip()
            
        if translated_text:
            return {
                'translatedText': translated_text,
                'source': 'ai_translation',
                'status': 'SUCCESS'
            }
        else:
            raise Exception('Empty response from AI')
            
    except Exception as e:
        print(f"Translation Task Error: {e}")
        return {
            'error': f'Dịch vụ dịch thuật tạm thời không khả dụng. Chi tiết: {str(e)}',
            'status': 'FAILED'
        }
