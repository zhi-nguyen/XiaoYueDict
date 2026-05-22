import os
import subprocess
import logging
import requests
from celery import shared_task
from .models import AssessmentTask

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


# ── Celery Task ───────────────────────────────────────────────

@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def process_audio_task(self, assessment_id, file_path, target_text='', language='en'):
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

    task.status = 'PROCESSING'
    task.save(update_fields=['status'])

    if not os.path.exists(file_path):
        logger.error(f"File {file_path} does not exist.")
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
        cleanup_audio_files(file_path)
        return {"error": f"Unsupported language: {language}"}

    try:
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
                timeout=30,  # 30s timeout for 5-10s processing budget + network
            )

        # ── Handle AI service errors by status code ──
        if response.status_code == 503:
            # Server overloaded (OOM / model busy) → retry
            error_detail = response.json().get('detail', 'AI service overloaded')
            logger.warning(f"⚠️ AI service ({language}) returned 503: {error_detail}")
            task.status = 'PENDING'
            task.error_message = error_detail
            task.save(update_fields=['status', 'error_message'])
            raise self.retry(
                exc=Exception(error_detail),
                countdown=10,  # wait 10s before retry
            )

        if response.status_code == 400:
            # Client-side issue (no speech, bad input) → fail with user message
            error_detail = response.json().get('detail', 'Invalid audio input')
            logger.warning(f"⚠️ AI service ({language}) returned 400: {error_detail}")
            task.status = 'FAILED'
            task.error_message = error_detail
            task.save(update_fields=['status', 'error_message'])
            return {"error": error_detail}

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
        return score_data

    except requests.exceptions.Timeout:
        error_msg = f"AI service ({language}) timed out after 30s"
        logger.error(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        return {"error": error_msg}

    except requests.exceptions.ConnectionError as e:
        error_msg = f"Cannot connect to AI service ({language}): {e}"
        logger.error(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        # Retry on connection errors (service might be starting up)
        raise self.retry(exc=e)

    except requests.exceptions.RequestException as e:
        error_msg = f"AI service request failed ({language}): {e}"
        logger.error(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        return {"error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error processing {assessment_id}: {e}"
        logger.error(f"❌ {error_msg}")
        task.status = 'FAILED'
        task.error_message = error_msg
        task.save(update_fields=['status', 'error_message'])
        return {"error": error_msg}

    finally:
        # ── Step 4: Always cleanup temp audio files ──
        cleanup_audio_files(file_path, converted_path)
