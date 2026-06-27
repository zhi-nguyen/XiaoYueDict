import os
import re
import hashlib
import logging
import asyncio
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import edge_tts
from google.cloud import storage

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("tts_service")

app = FastAPI(title="XiaoYueDict Standalone TTS Service", version="1.0.0")

# Directories
CACHE_DIR = "/app/cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Environment Configurations
BUCKET_NAME = os.environ.get("GS_BUCKET_NAME", "cnen-bucket")
DEFAULT_ZH_VOICE = os.environ.get("DEFAULT_ZH_VOICE", "zh-CN-XiaoxiaoNeural")
DEFAULT_EN_VOICE = os.environ.get("DEFAULT_EN_VOICE", "en-US-AriaNeural")

# Voice Mapping Table for reference/validation
VOICE_MAPPING = {
    "zh": {
        "female": "zh-CN-XiaoxiaoNeural",
        "male": "zh-CN-YunxiNeural"
    },
    "en": {
        "female": "en-US-AriaNeural",
        "male": "en-US-GuyNeural"
    }
}

# GCS Client Initialization Helper
def get_gcs_bucket():
    # If credentials are not set or fail, return None so we can degrade gracefully
    try:
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and os.path.exists(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")):
            client = storage.Client()
            return client.bucket(BUCKET_NAME)
        else:
            logger.warning("GCS credentials not found. Cloud storage operations will be skipped.")
            return None
    except Exception as e:
        logger.error(f"Failed to initialize GCS client: {e}")
        return None

bucket_instance = get_gcs_bucket()

def generate_text_cache_key(text: str, voice: str) -> str:
    # 1. Strip whitespace
    clean_text = text.strip()
    
    # 2. Lowercase if English/Latin characters (avoiding re \p{P} syntax error)
    if not re.search(r'[\u4e00-\u9fa5]', clean_text):
        clean_text = clean_text.lower()
        
    # 3. MD5 hash
    payload = f"{clean_text}_{voice}"
    return hashlib.md5(payload.encode('utf-8')).hexdigest()

async def upload_to_gcs_background(local_path: str, blob_name: str):
    """
    Asynchronously uploads a file to GCS in a thread pool.
    Exceptions are isolated to protect the HTTP request thread.
    """
    try:
        bucket = get_gcs_bucket()
        if not bucket:
            logger.warning(f"GCS Bucket not available. Skipping background upload for {blob_name}")
            return
        
        blob = bucket.blob(blob_name)
        logger.info(f"☁️ Starting upload of {local_path} to GCS as {blob_name}")
        await asyncio.to_thread(blob.upload_from_filename, local_path)
        logger.info(f"✅ Successfully uploaded {blob_name} to GCS.")
    except Exception as e:
        logger.error(f"[GCS-Leak] Failed to upload {blob_name} to Cloud Storage: {e}")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "tts_service",
        "gcs_bucket_connected": bucket_instance is not None
    }

@app.get("/api/v1/tts")
async def get_tts(
    text: str = Query(..., description="Text to convert to speech"),
    lang: str = Query("zh", description="Language code (zh or en)"),
    voice: str = Query(None, description="Exact voice model name (optional)"),
    background_tasks: BackgroundTasks = None
):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    # Determine target voice
    target_voice = voice
    if not target_voice:
        if lang.lower() == "en":
            target_voice = DEFAULT_EN_VOICE
        else:
            target_voice = DEFAULT_ZH_VOICE

    # Generate Cache Key and paths
    cache_key = generate_text_cache_key(text, target_voice)
    filename = f"{cache_key}.mp3"
    local_path = os.path.join(CACHE_DIR, filename)
    blob_name = f"tts/{filename}"

    logger.info(f"🔊 Request for text='{text}' voice='{target_voice}' key='{cache_key}'")

    # 1. Local Cache Hit Check
    if os.path.exists(local_path):
        logger.info(f"🎯 Local Cache Hit: {filename}")
        return FileResponse(local_path, media_type="audio/mpeg", filename=filename)

    # 2. GCS Bucket Check
    bucket = get_gcs_bucket()
    if bucket:
        try:
            blob = bucket.blob(blob_name)
            blob_exists = await asyncio.to_thread(blob.exists)
            if blob_exists:
                logger.info(f"☁️ GCS Bucket Hit: {blob_name}. Downloading...")
                await asyncio.to_thread(blob.download_to_filename, local_path)
                return FileResponse(local_path, media_type="audio/mpeg", filename=filename)
        except Exception as e:
            logger.error(f"Failed checking/downloading from GCS: {e}")
            # Degrade gracefully and proceed to edge-tts generation

    # 3. Cache Miss & Bucket Miss -> Generate via Edge-TTS
    logger.info(f"⚡ Cache Miss. Generating via Edge-TTS using voice '{target_voice}'...")
    try:
        communicate = edge_tts.Communicate(text, target_voice)
        await communicate.save(local_path)
        logger.info(f"✨ Successfully generated local file: {local_path}")
    except Exception as e:
        logger.error(f"❌ Edge-TTS generation failed: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"TTS Generation failed or service is unavailable: {str(e)}"
        )

    # 4. Trigger Background Upload to GCS
    if bucket and background_tasks:
        background_tasks.add_task(upload_to_gcs_background, local_path, blob_name)

    return FileResponse(local_path, media_type="audio/mpeg", filename=filename)
