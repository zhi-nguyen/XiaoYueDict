import os
import subprocess
import logging
import requests
import shutil
import json
from django.conf import settings
from celery import shared_task
from celery.exceptions import Retry, MaxRetriesExceededError
from requests.exceptions import RequestException
from google.cloud import storage
from .models import AssessmentTask
from core_project.ws_utils import ws_notify
from apps.subscriptions.middleware import refund_volume_limit

logger = logging.getLogger(__name__)

# AI service endpoints — keyed by language code
AI_SERVICE_URLS = {
    'en': os.environ.get('AI_SERVICE_EN_URL', 'http://ai-service-en:8000/api/v1/score'),
    'zh': os.environ.get('AI_SERVICE_ZH_URL', 'http://ai-service-zh:8001/api/v1/score'),
}

# ── Audio Pre-processing ─────────────────────────────────────

TARGET_SAMPLE_RATE = 16000   # 16 kHz — standard for speech models
TARGET_CHANNELS = 1          # mono


def convert_audio_to_16k(input_path: str) -> str:
    """
    Convert any audio file to 16 kHz, mono, 16-bit PCM WAV using ffmpeg.

    Returns the path to the converted file (suffix ``_16k.wav``).
    If the conversion fails, the original path is returned so inference
    can still be attempted.
    """
    base, _ = os.path.splitext(input_path)
    output_path = f"{base}_16k.wav"

    cmd = [
        "ffmpeg", "-y",            # overwrite without asking
        "-i", input_path,          # input
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-sample_fmt", "s16",      # 16-bit PCM
        "-f", "wav",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            size_kb = os.path.getsize(output_path) / 1024
            logger.info(
                f"🔊 Audio converted → 16 kHz mono WAV: "
                f"{os.path.basename(output_path)} ({size_kb:.1f} KB)"
            )
            return output_path
        else:
            logger.warning(
                f"⚠️ ffmpeg exited {result.returncode}, using original. "
                f"stderr: {result.stderr[:300]}"
            )
            return input_path

    except FileNotFoundError:
        logger.warning("⚠️ ffmpeg not found — skipping conversion, using original file")
        return input_path
    except subprocess.TimeoutExpired:
        logger.warning("⚠️ ffmpeg timed out — using original file")
        return input_path
    except Exception as exc:
        logger.warning(f"⚠️ Audio conversion error: {exc} — using original file")
        return input_path


# ── Temp file cleanup ─────────────────────────────────────────

def cleanup_audio_files(*paths):
    """Delete temporary audio files from disk."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"🗑️ Cleaned up: {os.path.basename(path)}")
            except OSError as exc:
                logger.warning(f"⚠️ Failed to delete {path}: {exc}")


def upload_to_gcs(local_path: str, target_blob_name: str, bucket_name: str) -> str:
    """
    Upload a local file to a GCS bucket.
    Uses the service account credentials pointed to by GOOGLE_APPLICATION_CREDENTIALS.
    """
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(target_blob_name)
        blob.upload_from_filename(local_path)
        logger.info(f"☁️ Uploaded successfully: gs://{bucket_name}/{target_blob_name}")
        return blob.public_url
    except Exception as e:
        logger.error(f"❌ Failed to upload {local_path} to GCS: {e}")
        raise e


# ── Celery Task ───────────────────────────────────────────────

@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def process_audio_task(self, assessment_id, file_path, target_text='', language='en', user_id=None, rate_limit_user_id=None):
    """
    Reads an audio file from local path and sends it to the appropriate AI service.
    Routes based on `language`:
      - 'en' → ai-service-en (Wav2Vec2 GOP)
      - 'zh' → ai-service-zh (Sherpa-ONNX)

    Pipeline:
      1. Convert audio → 16 kHz mono WAV (ffmpeg)
      2. Send to AI service
      3. Store result
      4. Cleanup all temp audio files
    """
    converted_path = None  # track for cleanup

    try:
        task = AssessmentTask.objects.get(id=assessment_id)
    except AssessmentTask.DoesNotExist:
        logger.error(f"AssessmentTask {assessment_id} not found.")
        return {"error": "Task not found"}

    # Reconstruct rate_limit_user_id if not provided
    if not rate_limit_user_id:
        if task.user:
            rate_limit_user_id = f"user:{task.user.id}"
        elif user_id:
            if str(user_id).startswith('user:') or str(user_id).startswith('guest:'):
                rate_limit_user_id = str(user_id)
            else:
                rate_limit_user_id = f"guest:{user_id}"
        else:
            rate_limit_user_id = "guest:anonymous"

    # Determine file size (rate_limit_bytes) for potential refund
    file_size = 0
    try:
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
        elif task.audio_file:
            file_size = task.audio_file.size
    except Exception as e:
        logger.warning(f"Could not determine file size for rate limit refund: {e}")

    task.status = 'PROCESSING'
    task.save(update_fields=['status'])

    try:
        # ── Pre-validation of file ──
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found at {file_path}")

        # Determine the AI service URL based on language
        ai_service_url = AI_SERVICE_URLS.get(language)
        if not ai_service_url:
            raise ValueError(f"Unsupported language: {language}")

        # ── Step 1: Convert to 16 kHz mono WAV ──
        converted_path = convert_audio_to_16k(file_path)
        send_path = converted_path  # use converted file for inference

        # ── Step 2: Send to AI service ──
        with open(send_path, 'rb') as f:
            files = {'audio_file': (os.path.basename(send_path), f, 'audio/wav')}
            data = {}
            if target_text and target_text.strip():
                data['target_text'] = target_text

            response = requests.post(
                ai_service_url,
                files=files,
                data=data,
                timeout=30,  # 30s timeout
            )

        # ── Handle AI service errors by status code ──
        # Lỗi Client (400) -> Không hoàn dung lượng
        if response.status_code == 400:
            error_detail = response.json().get('detail', 'Invalid audio input')
            logger.warning(f"⚠️ AI service ({language}) returned 400: {error_detail}")
            task.status = 'FAILED'
            task.error_message = error_detail
            task.save(update_fields=['status', 'error_message'])
            
            # Gửi thông báo WebSocket thất bại
            ws_notify(
                user_id=user_id,
                event_type='score_failed',
                title='Chấm điểm thất bại',
                payload={
                    'task_id': str(assessment_id),
                    'error': error_detail,
                    'language': language,
                },
            )
            
            return {"error": error_detail, "status": "failed", "reason": "client_error"}

        # Nếu AI Service phản hồi lỗi cấu trúc hệ thống (500, 502, 503, 504...)
        # Chủ động ném ngoại lệ để đi vào khối except xử lý retry hoặc hoàn tiền
        if response.status_code in [500, 502, 503, 504]:
            response.raise_for_status()

        response.raise_for_status()
        score_data = response.json()

        # ── Step 3: Store result ──
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

        logger.warning(f"✅ Assessment {assessment_id} ({language}) - Score: {task.score}")

        # ── Step 3.5: Save to Persistent Storage (GCS Bucket) ──
        try:
            # Determine folder name (user_id if available, else anonymous)
            raw_user_identifier = str(user_id).split(':')[-1] if user_id else "anonymous"
            user_folder = str(task.user.id) if task.user else raw_user_identifier
            
            bucket_name = os.environ.get('GS_BUCKET_NAME', 'cnen-bucket')
            ext = os.path.splitext(file_path)[1] or '.wav'
            
            gcs_audio_blob = f"assessments/{user_folder}/{assessment_id}{ext}"
            gcs_json_blob = f"assessments/{user_folder}/{assessment_id}.json"
            
            # Upload original audio file to GCS
            upload_to_gcs(file_path, gcs_audio_blob, bucket_name)
            
            # Write JSON data locally temporarily
            temp_json_path = f"{file_path}.json"
            json_data = {
                "id": str(task.id),
                "language": task.language,
                "score": task.score,
                "result_data": task.result_data,
                "created_at": task.created_at.isoformat()
            }
            with open(temp_json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
            
            # Upload JSON data to GCS
            upload_to_gcs(temp_json_path, gcs_json_blob, bucket_name)
            
            # Clean up temporary JSON file
            cleanup_audio_files(temp_json_path)
            
            logger.info(f"💾 Saved permanent files to GCS gs://{bucket_name}/assessments/{user_folder}/")
        except Exception as perm_err:
            logger.error(f"⚠️ Failed to save permanent files to GCS: {perm_err}")

        # Notify user via WebSocket
        ws_notify(
            user_id=user_id,
            event_type='score_complete',
            title=f'Chấm điểm hoàn tất — {task.score:.0f} điểm' if task.score else 'Chấm điểm hoàn tất',
            payload={
                'task_id': str(assessment_id),
                'score': task.score,
                'language': language,
            },
        )

        return score_data

    except FileNotFoundError as exc:
        logger.error(f"❌ File not found error: {exc}")
        task.status = 'FAILED'
        task.error_message = f"Audio file not found: {str(exc)}"
        task.save(update_fields=['status', 'error_message'])
        
        # Gửi thông báo WebSocket thất bại
        ws_notify(
            user_id=user_id,
            event_type='score_failed',
            title='Chấm điểm thất bại (Không tìm thấy tệp âm thanh)',
            payload={
                'task_id': str(assessment_id),
                'error': task.error_message,
                'language': language,
            },
        )
        
        if rate_limit_user_id and file_size:
            refund_volume_limit(rate_limit_user_id, file_size)
        return {"status": "error", "reason": "file_not_found_on_disk"}

    except (RequestException, Exception) as exc:
        logger.error(f"❌ Error processing {assessment_id}: {exc}")
        # Quản lý cơ chế retry đối với các sự cố gián đoạn mạng hoặc lỗi hệ thống
        try:
            countdown = 5
            # Nếu gặp lỗi 503 từ AI service, có thể chờ lâu hơn
            if hasattr(exc, 'response') and exc.response is not None and exc.response.status_code == 503:
                countdown = 10
                task.status = 'PENDING'
                error_detail = exc.response.json().get('detail', 'AI service overloaded')
                task.error_message = error_detail
                task.save(update_fields=['status', 'error_message'])
            else:
                task.status = 'FAILED'
                task.error_message = str(exc)
                task.save(update_fields=['status', 'error_message'])

            raise self.retry(exc=exc, countdown=countdown)

        except MaxRetriesExceededError:
            # Đã chạm ngưỡng thử lại tối đa. Hệ thống chính thức hủy bỏ tác vụ.
            # Tiến hành hoàn trả dung lượng tài nguyên cho người dùng.
            task.status = 'FAILED'
            task.error_message = f"Max retries exceeded: {str(exc)}"
            task.save(update_fields=['status', 'error_message'])
            
            # Gửi thông báo WebSocket thất bại
            ws_notify(
                user_id=user_id,
                event_type='score_failed',
                title='Chấm điểm thất bại (Hết lượt thử lại)',
                payload={
                    'task_id': str(assessment_id),
                    'error': task.error_message,
                    'language': language,
                },
            )
            
            if rate_limit_user_id and file_size:
                refund_volume_limit(rate_limit_user_id, file_size)
            return {"status": "error", "reason": "system_max_retries_exhausted"}

        except Retry:
            # Task đang được Celery đưa vào hàng đợi để retry (chưa hủy hoàn toàn).
            # Tuyệt đối không hoàn tiền tại đây.
            raise

        except Exception as inner_exc:
            # Bất kỳ lỗi bất ngờ nào xảy ra trong quá trình xử lý ngoại lệ
            task.status = 'FAILED'
            task.error_message = str(inner_exc)
            task.save(update_fields=['status', 'error_message'])
            if rate_limit_user_id and file_size:
                refund_volume_limit(rate_limit_user_id, file_size)
            raise inner_exc

    finally:
        # ── Step 4: Always cleanup temp audio files ──
        cleanup_audio_files(file_path, converted_path)
