import os
import requests
from celery import shared_task
from .models import AssessmentTask

# AI service endpoints — keyed by language code
AI_SERVICE_URLS = {
    'en': os.environ.get('AI_SERVICE_EN_URL', 'http://ai-service-en:8000/api/v1/score'),
    'zh': os.environ.get('AI_SERVICE_ZH_URL', 'http://ai-service-zh:8001/api/v1/score'),
}


@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def process_audio_task(self, assessment_id, file_path, target_text='', language='en'):
    """
    Reads an audio file from local path and sends it to the appropriate AI service.
    Routes based on `language`:
      - 'en' → ai-service-en (Wav2Vec2 GOP)
      - 'zh' → ai-service-zh (Sherpa-ONNX)

    If target_text is provided, routes to Read-Aloud scoring (Branch A).
    Otherwise, routes to Free Decoding ASR (Branch B).
    """
    try:
        task = AssessmentTask.objects.get(id=assessment_id)
    except AssessmentTask.DoesNotExist:
        print(f"Error: AssessmentTask {assessment_id} not found.")
        return {"error": "Task not found"}

    task.status = 'PROCESSING'
    task.save(update_fields=['status'])

    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist.")
        task.status = 'FAILED'
        task.error_message = f"Audio file not found at {file_path}"
        task.save(update_fields=['status', 'error_message'])
        return {"error": "File not found"}

    # Determine the AI service URL based on language
    ai_service_url = AI_SERVICE_URLS.get(language)
    if not ai_service_url:
        task.status = 'FAILED'
        task.error_message = f"Unsupported language: {language}"
        task.save(update_fields=['status', 'error_message'])
        return {"error": f"Unsupported language: {language}"}

    try:
        with open(file_path, 'rb') as f:
            files = {'audio_file': (os.path.basename(file_path), f, 'audio/wav')}
            data = {}
            if target_text and target_text.strip():
                data['target_text'] = target_text

            response = requests.post(
                ai_service_url,
                files=files,
                data=data,
                timeout=30,  # 30s timeout for 5-10s processing budget + network
            )

            response.raise_for_status()
            score_data = response.json()

            # Store the full AI response for rich frontend display
            task.result_data = score_data

            # Extract the headline score for quick access
            if isinstance(score_data, dict):
                score = (
                    score_data.get('overall_score')
                    or score_data.get('fluency_score')
                )
                if score is not None:
                    try:
                        task.score = float(score)
                    except (ValueError, TypeError):
                        task.score = 0.0

            task.status = 'COMPLETED'
            task.save(update_fields=['status', 'score', 'result_data'])

            print(f"✅ Assessment {assessment_id} ({language}) - Score: {task.score}")
            return score_data

    except requests.exceptions.Timeout:
        error_msg = f"AI service ({language}) timed out after 30s"
        print(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        return {"error": error_msg}

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Cannot connect to AI service ({language}): {e}"
        print(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        # Retry on connection errors (service might be starting up)
        raise self.retry(exc=e)

    except requests.exceptions.RequestException as e:
        error_msg = f"AI service request failed ({language}): {e}"
        print(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        return {"error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error processing {assessment_id}: {e}"
        print(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        return {"error": error_msg}
