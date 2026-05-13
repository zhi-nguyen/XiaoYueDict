"""
English AI Pronunciation Service — FastAPI Application.

Uses Faster-Whisper (Large-v3, CTranslate2 INT8) for:
- Read-Aloud scoring (word-level confidence against target text)
- Free Decoding (ASR transcription + fluency score)

All inference runs on CPU with INT8 quantization.
"""
import os
import time
import tempfile
import uuid
import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

from inference_pipeline import PronunciationScorer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Global scorer instance — loaded once at startup
scorer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event: Load the Faster-Whisper model exactly ONCE at startup.
    The model is heavy (~1-3GB in RAM), so we avoid reloading per-request.
    """
    global scorer
    logger.info("🚀 Starting English AI Pronunciation Service...")

    start = time.time()
    try:
        scorer = PronunciationScorer()
        elapsed = time.time() - start
        logger.info(f"✅ PronunciationScorer initialized in {elapsed:.1f}s")
    except Exception as e:
        logger.error(f"❌ Failed to initialize PronunciationScorer: {e}")
        raise e

    yield

    logger.info("🛑 Shutting down English AI Service.")
    scorer = None


# ── FastAPI Application ──
app = FastAPI(
    title="English AI Pronunciation Service",
    description="Faster-Whisper Large-v3 (INT8 CPU) — Word-level pronunciation scoring",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def cleanup_temp_file(file_path: str):
    """Background task to delete temporary audio files."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        logger.warning(f"Failed to delete temp file {file_path}: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker orchestration."""
    return {
        "status": "healthy",
        "service": "ai_service_en",
        "model_loaded": scorer is not None,
    }


@app.post("/api/v1/score")
async def score_endpoint(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    target_text: str = Form(None),
):
    """
    Dual-Routing Endpoint:
    - Branch A: target_text provided → Read-Aloud (word-level scoring)
    - Branch B: target_text omitted  → Free Decoding (ASR + fluency)
    """
    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    # Save uploaded file to temp location
    temp_dir = tempfile.gettempdir()
    file_ext = os.path.splitext(audio_file.filename)[1] or ".wav"
    temp_file_path = os.path.join(temp_dir, f"audio_en_{uuid.uuid4().hex}{file_ext}")

    try:
        with open(temp_file_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save audio file: {str(e)}")

    background_tasks.add_task(cleanup_temp_file, temp_file_path)

    request_start = time.time()

    # ── BRANCH A: Read-Aloud ──
    if target_text and target_text.strip():
        logger.info(f"🔄 Read-Aloud mode. Target: '{target_text[:80]}...'")
        try:
            result = await run_in_threadpool(scorer.score_audio, temp_file_path, target_text)

            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])

            elapsed = time.time() - request_start
            logger.info(f"✅ Read-Aloud completed in {elapsed:.2f}s — Score: {result.get('overall_score')}")
            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Read-Aloud failed:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(e)}")

    # ── BRANCH B: Free Decoding ──
    else:
        logger.info("🔄 Free Decoding mode")
        try:
            result = await run_in_threadpool(scorer.decode_and_score, temp_file_path)

            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])

            elapsed = time.time() - request_start
            logger.info(f"✅ Free Decoding completed in {elapsed:.2f}s — Fluency: {result.get('fluency_score')}")
            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Free Decoding failed:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
