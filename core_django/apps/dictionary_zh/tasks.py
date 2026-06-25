import os
import re
from celery import shared_task
from celery.exceptions import Retry
from .models import ZhExample
from core_project.ws_utils import ws_notify

@shared_task(bind=True, max_retries=5, default_retry_delay=5)
def translate_pure_text_task(self, text_input, user_id=None, direction='zh_vi'):
    """
    Celery task to handle async translation via Database lookup or Vertex AI Priority PayGo.
    """
    # Normalize text as requested by user
    q_lower = text_input.lower().strip()
    cleaned_query = re.sub(r'[。，、！？. , ! ?]+$', '', q_lower)
    if not cleaned_query:
        result = {'error': 'No valid text provided', 'status': 'FAILED'}
        if user_id:
            ws_notify(
                user_id=user_id,
                event_type='translation_failed',
                title='Dịch thuật thất bại',
                payload={'task_id': self.request.id, 'error': result['error']}
            )
        return result

    # Tầng 1: Kiểm tra Database (Chỉ dịch từ tiếng Trung sang tiếng Việt mới tra cứu DB)
    if direction == 'zh_vi':
        # Tầng 1.1: Kiểm tra Database (ZhExample)
        # Sử dụng iregex cho phép dấu câu tùy chọn ở cuối
        regex_pattern = r'^' + re.escape(cleaned_query) + r'[。，、！？. , ! ?]*$'
        match = ZhExample.objects.filter(chinese__iregex=regex_pattern).first()
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
                    payload={'task_id': self.request.id, **result}
                )
            return result

        # Tầng 1.2: Kiểm tra Database (ZhWord)
        from django.db.models import Q
        from .models import ZhWord
        word_match = ZhWord.objects.filter(Q(word=cleaned_query) | Q(traditional=cleaned_query)).first()
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
                    payload={'task_id': self.request.id, **result}
                )
            return result

    # Tầng 2: Gọi AI (Vertex AI Priority PayGo)
    if direction == 'vi_zh':
        system_prompt = "Bạn là một chuyên gia dịch thuật tiếng Việt sang tiếng Trung. Hãy dịch một cách mượt mà và tự nhiên nhất, chỉ trả về kết quả tiếng Trung (giản thể), không giải thích gì thêm."
    else:
        system_prompt = "Bạn là một chuyên gia dịch thuật tiếng Trung sang tiếng Việt. Hãy dịch một cách mượt mà và tự nhiên nhất, chỉ trả về kết quả, không giải thích gì thêm."
    
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
            result_data = {
                'translatedText': translated_text,
                'source': 'ai_translation',
                'status': 'SUCCESS'
            }
            # Lưu trữ kết quả AI dịch thuật thành công dài hạn (7 ngày) chống lặp cuộc gọi LLM
            cache.set(f"ai_trans:{direction}:{text_input}", {"status": "success", "result": result_data}, timeout=7 * 24 * 60 * 60)
            if user_id:
                ws_notify(
                    user_id=user_id,
                    event_type='translation_complete',
                    title='Dịch thuật hoàn tất',
                    payload={'task_id': self.request.id, **result_data}
                )
            return result_data
        else:
            raise Exception('Empty response from AI')
            
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
                payload={'task_id': self.request.id, 'error': result['error']}
            )
        return result
