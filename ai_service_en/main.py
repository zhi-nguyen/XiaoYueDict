"""
English AI Pronunciation Service — FastAPI entry point.

Serves the Wav2Vec2-based PronunciationScorer (ONNX INT8) via a REST API
that mirrors the ai_service_zh contract.

Endpoints:
  GET  /health        → Health check for Docker orchestration
  POST /api/v1/score  → Dual-routing pronunciation scoring
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

from inference_pipeline import EnglishPronunciationScorer

# Global scorer instance — initialised once at startup
scorer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the ONNX INT8 model exactly ONCE when the server starts."""
    global scorer
    logger.info("🚀 Starting English AI Service (ONNX INT8)...")

    try:
        scorer = EnglishPronunciationScorer()
        logger.info("✅ EnglishPronunciationScorer globally initialized.")
    except Exception as exc:
        logger.error(f"❌ Failed to initialize scorer: {exc}")
        raise exc

    yield

    logger.info("🛑 Shutting down English AI Service.")
    scorer = None


# ── FastAPI Application ──────────────────────────────────────
app = FastAPI(
    title="English AI Pronunciation Service",
    description=(
        "Microservice for English pronunciation scoring "
        "using Wav2Vec2 + ONNX INT8 quantization."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ──────────────────────────────────────────────────
def cleanup_temp_file(file_path: str):
    """Background task to remove temporary audio files after response."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"🗑️ Deleted temp file: {file_path}")
    except Exception as exc:
        logger.warning(f"⚠️ Failed to delete {file_path}: {exc}")


# ── Endpoints ────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Health check endpoint for Docker orchestration."""
    import torch
    
    cuda_active = False
    if scorer is not None and scorer.model_loaded and scorer.session is not None:
        active_providers = scorer.session.get_providers()
        cuda_active = "CUDAExecutionProvider" in active_providers or (
            hasattr(scorer, "whisper_model") 
            and scorer.whisper_model is not None 
            and getattr(scorer.whisper_model, "device", "") == "cuda"
        )

    return {
        "status": "healthy",
        "service": "ai_service_en",
        "model_loaded": scorer is not None and scorer.model_loaded,
        "runtime": "onnx_fp16" if cuda_active else "onnx_int8",
        "device": "cuda" if cuda_active else "cpu",
    }


@app.post("/api/v1/score")
async def score_endpoint(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    target_text: str = Form(None),
):
    """
    Dual-Routing Endpoint (mirrors ai_service_zh API contract):
      - Branch A: target_text provided → Read-Aloud scoring (word-level)
      - Branch B: target_text omitted  → Free Decoding (fluency)
    """
    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    # Persist upload to temp file
    temp_dir = tempfile.gettempdir()
    ext = os.path.splitext(audio_file.filename)[1] or ".wav"
    temp_path = os.path.join(temp_dir, f"audio_en_{uuid.uuid4().hex}{ext}")

    try:
        with open(temp_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save audio file: {str(exc)}",
        )

    background_tasks.add_task(cleanup_temp_file, temp_path)

    # ── Branch A: Read-Aloud ──
    if target_text and target_text.strip():
        logger.info(f"🔄 [EN] Read-Aloud mode. Target: '{target_text}'")
        try:
            result = await run_in_threadpool(
                scorer.score_audio, temp_path, target_text
            )
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"❌ [EN] Read-Aloud failed:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(exc)}")

    # ── Branch B: Free Decoding ──
    else:
        logger.info("🔄 [EN] Free Decoding mode")
        try:
            result = await run_in_threadpool(
                scorer.decode_and_score, temp_path
            )
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"❌ [EN] Free Decoding failed:\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(exc)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
