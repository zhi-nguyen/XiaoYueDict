import os
import json
import logging
import asyncio
import shutil
from fastapi import FastAPI, Query, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from google.cloud import storage
from google import genai
from google.genai import types

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("image_service")

app = FastAPI(title="XiaoYueDict Standalone Image Service", version="1.0.0")

# Directories
CACHE_DIR = "/app/cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Environment Configurations
BUCKET_NAME = os.environ.get("GS_BUCKET_NAME", "cnen-bucket")

# Mock Mode Configuration — $0 cost local development
IS_DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("true", "1", "t")
MOCK_IMAGE_PATH = os.path.join(CACHE_DIR, "mock_sample.png")


def _create_mock_placeholder(output_path):
    """
    Sinh ảnh giả lập (Programmatic Image Generation) tại runtime.
    Tạo file PNG 512x512 với text "MOCK IMAGE" — loại bỏ binary blobs khỏi Git.
    Yêu cầu: Pillow trong requirements.txt
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (512, 512), color=(240, 240, 245))
        draw = ImageDraw.Draw(img)

        # Draw grid pattern for visual identification
        for i in range(0, 512, 32):
            draw.line([(i, 0), (i, 512)], fill=(220, 220, 230), width=1)
            draw.line([(0, i), (512, i)], fill=(220, 220, 230), width=1)

        # Draw center text
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except (IOError, OSError):
            font = ImageFont.load_default()
            font_sm = font

        # "MOCK IMAGE" label
        draw.text((256, 220), "MOCK IMAGE", fill=(100, 100, 120), font=font, anchor="mm")
        draw.text((256, 270), "Debug Mode · No API Cost", fill=(150, 150, 170), font=font_sm, anchor="mm")

        # Border
        draw.rectangle([(4, 4), (507, 507)], outline=(180, 180, 200), width=2)

        img.save(output_path, "PNG")
        logger.info(f"🧪 Created mock placeholder image: {output_path}")
    except ImportError:
        # Pillow not installed — create minimal 1x1 PNG fallback
        import struct
        import zlib
        def _minimal_png(path):
            """Create a minimal valid 1x1 white PNG without Pillow."""
            signature = b'\x89PNG\r\n\x1a\n'
            ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
            ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xFFFFFFFF
            ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
            raw = zlib.compress(b'\x00\xff\xff\xff')
            idat_crc = zlib.crc32(b'IDAT' + raw) & 0xFFFFFFFF
            idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
            iend_crc = zlib.crc32(b'IEND') & 0xFFFFFFFF
            iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
            with open(path, 'wb') as f:
                f.write(signature + ihdr + idat + iend)
        _minimal_png(path)
        logger.warning(f"⚠️ Pillow not available, created minimal PNG: {output_path}")


# Initialize mock placeholder at startup if in debug mode
if IS_DEBUG:
    if not os.path.exists(MOCK_IMAGE_PATH):
        _create_mock_placeholder(MOCK_IMAGE_PATH)
    logger.info("🧪 Mock mode ENABLED — will use placeholder images instead of Vertex AI")

# Helper to extract project ID from service account credentials
def get_project_id():
    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if key_path and os.path.exists(key_path):
        try:
            with open(key_path, 'r') as f:
                key_data = json.load(f)
                return key_data.get("project_id")
        except Exception as e:
            logger.error(f"Failed to read GCS key file for project_id: {e}")
    return None

# Initialize Google GenAI Client (Vertex AI backend)
project_id = get_project_id()
genai_client = None
if project_id:
    try:
        genai_client = genai.Client(
            vertexai=True,
            project=project_id,
            location="us-central1",
        )
        logger.info(f"Google GenAI client initialized with project: {project_id}")
    except Exception as e:
        logger.error(f"Google GenAI client initialization failed: {e}")
else:
    logger.warning("Google GenAI client could not be initialized. Project ID not found.")

# GCS Client Initialization Helper
def get_gcs_bucket():
    try:
        key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if key_path and os.path.exists(key_path):
            client = storage.Client()
            return client.bucket(BUCKET_NAME)
        else:
            logger.warning("GCS credentials not found. Cloud storage operations will be skipped.")
            return None
    except Exception as e:
        logger.error(f"Failed to initialize GCS client: {e}")
        return None

bucket_instance = get_gcs_bucket()

# Request schemas
class GenerateRequest(BaseModel):
    word_id: str
    lang: str
    prompt: str

class DeleteRequest(BaseModel):
    word_id: str
    lang: str

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "image_service",
        "gcs_bucket_connected": bucket_instance is not None,
        "vertex_ai_initialized": genai_client is not None
    }

@app.post("/api/v1/image/generate")
async def generate_image(req: GenerateRequest):
    word_id = req.word_id
    lang = req.lang
    prompt = req.prompt

    if not word_id or not lang or not prompt:
        raise HTTPException(status_code=400, detail="Missing required parameters")

    filename = f"{word_id}.png"
    local_path = os.path.join(CACHE_DIR, filename)
    blob_name = f"images/{lang}/{filename}"

    bucket = get_gcs_bucket()
    if not bucket:
        raise HTTPException(status_code=500, detail="GCS Bucket is not configured or authenticated")

    logger.info(f"🎨 Generating image for word_id={word_id}, lang={lang}, prompt='{prompt}'")
    
    # 1. Generate image — Mock mode or Production mode
    try:
        if IS_DEBUG:
            # Mock mode: copy local placeholder instead of calling Vertex AI ($0 cost)
            logger.info(f"🧪 [MOCK] Using placeholder image for word_id={word_id}")
            shutil.copy(MOCK_IMAGE_PATH, local_path)
        else:
            # Production: call Vertex AI Imagen
            if not genai_client:
                raise HTTPException(status_code=500, detail="Google GenAI client is not initialized")

            def genai_generate():
                response = genai_client.models.generate_images(
                    model="gemini-2.5-flash-image",
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="1:1",
                        output_mime_type="image/png",
                    ),
                )
                if not response or not response.generated_images:
                    raise Exception("Google GenAI returned no images.")
                
                # Save locally by writing raw image bytes
                image_bytes = response.generated_images[0].image.image_bytes
                with open(local_path, "wb") as f:
                    f.write(image_bytes)

            await asyncio.to_thread(genai_generate)

        logger.info(f"✨ Successfully generated image locally: {local_path}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Image generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image generation failed: {str(e)}")

    # 2. Upload to GCS
    try:
        blob = bucket.blob(blob_name)
        await asyncio.to_thread(blob.upload_from_filename, local_path)
        logger.info(f"☁️ Uploaded to GCS as {blob_name}")
        gcs_url = blob.public_url
        
        # Clean up local file
        if os.path.exists(local_path):
            os.remove(local_path)
            
        return {"status": "success", "image_url": gcs_url}
    except Exception as e:
        logger.error(f"❌ Failed to upload image to GCS: {e}")
        if os.path.exists(local_path):
            os.remove(local_path)
        raise HTTPException(status_code=500, detail=f"GCS upload failed: {str(e)}")

@app.delete("/api/v1/image/delete")
async def delete_image(req: DeleteRequest):
    word_id = req.word_id
    lang = req.lang

    if not word_id or not lang:
        raise HTTPException(status_code=400, detail="Missing required parameters")

    filename = f"{word_id}.png"
    blob_name = f"images/{lang}/{filename}"

    bucket = get_gcs_bucket()
    if not bucket:
        raise HTTPException(status_code=500, detail="GCS Bucket is not configured or authenticated")

    try:
        blob = bucket.blob(blob_name)
        blob_exists = await asyncio.to_thread(blob.exists)
        if blob_exists:
            await asyncio.to_thread(blob.delete)
            logger.info(f"🗑️ Deleted GCS image: {blob_name}")
            return {"status": "success", "detail": "Image deleted from GCS"}
        else:
            # Safe recovery: trả success để Celery không bị gãy mạch khi file chưa tồn tại
            logger.warning(f"⚠️ Image not found on GCS (already clean): {blob_name}")
            return {"status": "success", "detail": "Image not found on GCS (already clean)"}
    except Exception as e:
        logger.error(f"❌ Failed to delete GCS image: {e}")
        raise HTTPException(status_code=500, detail=f"GCS deletion failed: {str(e)}")
