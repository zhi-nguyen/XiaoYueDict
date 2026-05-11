import os
import requests
from celery import shared_task
from .models import AssessmentTask

@shared_task
def process_audio_task(assessment_id, file_path, target_text=''):
    """
    Reads an audio file from local path and sends it to the ai-service-en for scoring.
    If target_text is provided, routes to GOP Read-Aloud scoring (Branch A).
    Otherwise, routes to Free Decoding ASR (Branch B).
    """
    try:
        task = AssessmentTask.objects.get(id=assessment_id)
    except AssessmentTask.DoesNotExist:
        print(f"Error: AssessmentTask {assessment_id} not found.")
        return {"error": "Task not found"}

    task.status = 'PROCESSING'
    task.save()

    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist.")
        task.status = 'FAILED'
        task.save()
        return {"error": "File not found"}

    ai_service_url = "http://ai-service-en:8000/api/v1/score"
    
    try:
        with open(file_path, 'rb') as f:
            files = {'audio_file': (os.path.basename(file_path), f, 'audio/wav')}
            data = {}
            if target_text and target_text.strip():
                data['target_text'] = target_text
            response = requests.post(ai_service_url, files=files, data=data)
            
            response.raise_for_status()
            score_data = response.json()
            
            # Extract score: Read-Aloud returns 'overall_score', Free Decoding returns 'fluency_score'
            score = score_data.get('overall_score') or score_data.get('fluency_score') if isinstance(score_data, dict) else score_data
            
            if score is not None:
                try:
                    task.score = float(score)
                except ValueError:
                    task.score = 0.0
            
            task.status = 'COMPLETED'
            task.save()
            
            print(f"Assessment {assessment_id} - Score result: {score_data}")
            return score_data
            
    except requests.exceptions.RequestException as e:
        print(f"Error calling ai-service-en: {e}")
        task.status = 'FAILED'
        task.save()
        return {"error": str(e)}
    except Exception as e:
        print(f"Unexpected error: {e}")
        task.status = 'FAILED'
        task.save()
        return {"error": str(e)}
