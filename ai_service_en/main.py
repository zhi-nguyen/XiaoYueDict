import os
import tempfile
import uuid
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

# Import the adaptive hardware scorer
from inference_pipeline import PronunciationScorer

# Global variable for the model to ensure single initialization
scorer = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event to load the ML models exactly ONCE when the server starts.
    This respects the hardware-adaptive logic in PronunciationScorer (CUDA vs CPU),
    prevents memory leaks, and drastically reduces request latency.
    """
    global scorer
    print("🚀 Starting FastAPI Server...")
    try:
        scorer = PronunciationScorer()
        print("✅ PronunciationScorer globally initialized successfully.")
    except Exception as e:
        print(f"❌ Failed to initialize PronunciationScorer: {e}")
        raise e
    
    yield
    
    # Cleanup on shutdown
    print("🛑 Shutting down FastAPI Server. Cleaning up ML resources...")
    scorer = None

# Initialize FastAPI application
app = FastAPI(
    title="English AI Pronunciation Service",
    description="Microservice for GOP scoring and Spontaneous Speech Decoding",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for Next.js frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to specific frontend domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def cleanup_temp_file(file_path: str):
    """
    Background task to securely delete temporary audio files after the response is sent,
    preventing server storage bloat over time.
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Deleted temporary file: {file_path}")
    except Exception as e:
        print(f"⚠️ Failed to delete temporary file {file_path}: {e}")

@app.post("/api/v1/score")
async def score_endpoint(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    target_text: str = Form(None)
):
    """
    Dual-Routing Endpoint handling multipart/form-data:
    - Branch A: If target_text is provided, runs strict GOP Read-Aloud scoring.
    - Branch B: If target_text is omitted, falls back to Free Decoding ASR.
    """
    if not audio_file.filename:
        raise HTTPException(status_code=400, detail="Audio file is required.")
        
    # Safely write the uploaded file to a temporary location on disk
    temp_dir = tempfile.gettempdir()
    file_ext = os.path.splitext(audio_file.filename)[1] or ".wav"
    temp_file_path = os.path.join(temp_dir, f"audio_{uuid.uuid4().hex}{file_ext}")
    
    try:
        with open(temp_file_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save audio file to disk: {str(e)}")
        
    # Queue the file deletion to run immediately AFTER the HTTP response is sent
    background_tasks.add_task(cleanup_temp_file, temp_file_path)
    
    # ==========================================
    # BRANCH A: Read Aloud (Forced Alignment + GOP)
    # ==========================================
    if target_text and target_text.strip():
        print(f"🔄 Routing to strict GOP Scorer. Target text: '{target_text}'")
        try:
            # Dispatch the heavy synchronous CPU/GPU inference to a background thread pool
            # This is critical to prevent the ML block from freezing FastAPI's async event loop
            result = await run_in_threadpool(scorer.score_audio, temp_file_path, target_text)
            
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
                
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"❌ GOP Scoring failed during inference:\n{err_msg}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(e)}")
            
    # ==========================================
    # BRANCH B: Spontaneous Speech (Free Decoding)
    # ==========================================
    else:
        print("🔄 Routing to Free Decoding ASR")
        try:
            result = await run_in_threadpool(scorer.decode_and_score, temp_file_path)
            
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
                
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            err_msg = traceback.format_exc()
            print(f"❌ Free Decoding failed during inference:\n{err_msg}")
            raise HTTPException(status_code=500, detail=f"ML Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    # Standalone execution for local testing
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
