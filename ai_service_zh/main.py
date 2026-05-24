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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from inference_pipeline import ChinesePronunciationScorer

# Global variable for the model to ensure single initialization
scorer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event to load the ML models exactly ONCE when the server starts.
    """
    global scorer
    print("🚀 Starting Chinese AI Service...")
    try:
        scorer = ChinesePronunciationScorer()
        print("✅ ChinesePronunciationScorer globally initialized.")
    except Exception as e:
        print(f"❌ Failed to initialize ChinesePronunciationScorer: {e}")
        raise e

    yield

    print("🛑 Shutting down Chinese AI Service.")
    scorer = None


# Initialize FastAPI application
app = FastAPI(
    title="Chinese AI Pronunciation Service",
    description="Microservice for Chinese Mandarin pronunciation scoring using FunASR Paraformer-zh",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def cleanup_temp_file(file_path: str):
    """Background task to delete temporary audio files after response is sent."""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Deleted temporary file: {file_path}")
    except Exception as e:
        print(f"⚠️ Failed to delete temporary file {file_path}: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker orchestration."""
    cuda_active = False
    if scorer is not None and scorer.model_loaded and scorer.model is not None:
        cuda_active = getattr(scorer.model, "device", "") == "cuda"

    return {
        "status": "healthy",
        "service": "ai_service_zh",
        "model_loaded": scorer is not None and scorer.model_loaded,
        "device": "cuda" if cuda_active else "cpu",
    }


@app.post("/api/v1/score")
async def score_endpoint(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    target_text: str = Form(None),
):
    """
    Dual-Routing Endpoint (mirrors ai_service_en API contract):
    - Branch A: If target_text is provided → Read-Aloud scoring (character-level)
    - Branch B: If target_text is omitted → Free Decoding ASR
    """
    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required.")

    # Save uploaded file to temp location
    temp_dir = tempfile.gettempdir()
    file_ext = os.path.splitext(audio_file.filename)[1] or ".wav"
    temp_file_path = os.path.join(temp_dir, f"audio_zh_{uuid.uuid4().hex}{file_ext}")

    try:
        with open(temp_file_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save audio file: {str(e)}",
        )

    background_tasks.add_task(cleanup_temp_file, temp_file_path)

    # ── BRANCH A: Read Aloud ──
    if target_text and target_text.strip():
        print(f"🔄 [ZH] Read-Aloud mode. Target: '{target_text}'")
        try:
            result = await run_in_threadpool(
                scorer.score_audio, temp_file_path, target_text
            )
            if "error" in result:
                code = result.get("error_code", "")
                http_code = 503 if code in ("oom_error", "model_error") else 400
                raise HTTPException(status_code=http_code, detail=result["error"])
            return result

        except HTTPException:
            raise
        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"❌ [ZH] Read-Aloud scoring failed:\n{err_msg}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(e)}")

    # ── BRANCH B: Free Decoding ──
    else:
        print("🔄 [ZH] Free Decoding mode")
        try:
            result = await run_in_threadpool(
                scorer.decode_and_score, temp_file_path
            )
            if "error" in result:
                code = result.get("error_code", "")
                http_code = 503 if code in ("oom_error", "model_error") else 400
                raise HTTPException(status_code=http_code, detail=result["error"])
            return result

        except HTTPException:
            raise
        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"❌ [ZH] Free Decoding failed:\n{err_msg}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
