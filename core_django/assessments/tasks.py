import os
import requests
from celery import shared_task
from .models import AssessmentTask

@shared_task
def process_audio_task(assessment_id, file_path):
    """
    Reads an audio file from local path and sends it to the ai-service-en for scoring.
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

    ai_service_url = "http://ai-service-en:8000/api/score/english"
    
    try:
        with open(file_path, 'rb') as f:
            files = {'audio_file': (os.path.basename(file_path), f, 'audio/wav')}
            response = requests.post(ai_service_url, files=files)
            
            response.raise_for_status()
            score_data = response.json()
            
            # Extract score from response, expecting {"score": 85} format typically
            score = score_data.get('score') if isinstance(score_data, dict) else score_data
            
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
