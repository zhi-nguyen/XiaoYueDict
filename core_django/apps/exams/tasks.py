import os
import shutil
import logging
from celery import shared_task
from django.conf import settings
from django.db import transaction
from google.cloud import storage
from PIL import Image
from .models import Exam, Section, Question, Option

logger = logging.getLogger(__name__)


@shared_task
def process_exam_media_task(exam_id):
    """
    Background task to compress exam images to WebP, upload all media to GCS,
    update database records with GCS URLs, and delete local temp files.
    """
    logger.info(f"🚀 Starting background media processing for exam: {exam_id}")
    bucket_name = os.environ.get('GS_BUCKET_NAME', 'cnen-bucket')
    
    try:
        exam = Exam.objects.get(exam_id=exam_id)
    except Exam.DoesNotExist:
        logger.error(f"❌ Exam {exam_id} not found in database.")
        return f"Exam {exam_id} not found"

    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
    except Exception as e:
        logger.error(f"❌ Failed to initialize GCS client: {e}")
        return str(e)

    # Dictionary to keep track of already uploaded local files to GCS URLs
    uploaded_files = {}

    def upload_to_gcs(local_path, target_blob_name, content_type=None):
        if local_path in uploaded_files:
            return uploaded_files[local_path]
            
        if not os.path.exists(local_path):
            logger.warning(f"⚠️ Local file not found for upload: {local_path}")
            return None
            
        try:
            blob = bucket.blob(target_blob_name)
            blob.upload_from_filename(local_path, content_type=content_type)
            logger.info(f"☁️ Uploaded to GCS: gs://{bucket_name}/{target_blob_name}")
            uploaded_files[local_path] = blob.public_url
            return blob.public_url
        except Exception as err:
            logger.error(f"❌ GCS upload failed for {local_path}: {err}")
            return None

    # We will fetch and update URLs inside an atomic transaction
    try:
        with transaction.atomic():
            # 1. Process Section Audios
            for sec in exam.sections.all():
                url_path = sec.section_audio_url
                if url_path and url_path.startswith(settings.MEDIA_URL):
                    relative_path = url_path[len(settings.MEDIA_URL):]
                    local_path = os.path.join(settings.MEDIA_ROOT, relative_path)
                    
                    gcs_blob_name = relative_path.replace("\\", "/")
                    new_url = upload_to_gcs(local_path, gcs_blob_name, content_type="audio/mpeg")
                    if new_url:
                        sec.section_audio_url = new_url
                        sec.save(update_fields=['section_audio_url'])

            # 2. Process Question Audios & Images
            for sec in exam.sections.all():
                for q in sec.questions.all():
                    updated_fields = []
                    
                    # Audio
                    audio_url = q.audio_url
                    if audio_url and audio_url.startswith(settings.MEDIA_URL):
                        relative_path = audio_url[len(settings.MEDIA_URL):]
                        local_path = os.path.join(settings.MEDIA_ROOT, relative_path)
                        gcs_blob_name = relative_path.replace("\\", "/")
                        new_url = upload_to_gcs(local_path, gcs_blob_name, content_type="audio/mpeg")
                        if new_url:
                            q.audio_url = new_url
                            updated_fields.append('audio_url')
                            
                    # Image
                    image_url = q.image_url
                    if image_url and image_url.startswith(settings.MEDIA_URL):
                        relative_path = image_url[len(settings.MEDIA_URL):]
                        local_path = os.path.join(settings.MEDIA_ROOT, relative_path)
                        
                        if os.path.exists(local_path):
                            # Compress to WebP
                            webp_relative = os.path.splitext(relative_path)[0] + '.webp'
                            webp_local_path = os.path.join(settings.MEDIA_ROOT, webp_relative)
                            
                            try:
                                with Image.open(local_path) as img:
                                    img.save(webp_local_path, 'WEBP', quality=80)
                                    
                                gcs_blob_name = webp_relative.replace("\\", "/")
                                new_url = upload_to_gcs(webp_local_path, gcs_blob_name, content_type="image/webp")
                                if new_url:
                                    q.image_url = new_url
                                    updated_fields.append('image_url')
                                    
                                # Clean up compressed webp temp file
                                if os.path.exists(webp_local_path):
                                    os.remove(webp_local_path)
                            except Exception as img_err:
                                logger.error(f"❌ Failed to compress image {local_path}: {img_err}")
                                
                    if updated_fields:
                        q.save(update_fields=updated_fields)

            # 3. Process Option Images
            for sec in exam.sections.all():
                for q in sec.questions.all():
                    for opt in q.options.all():
                        image_url = opt.image_url
                        if image_url and image_url.startswith(settings.MEDIA_URL):
                            relative_path = image_url[len(settings.MEDIA_URL):]
                            local_path = os.path.join(settings.MEDIA_ROOT, relative_path)
                            
                            if os.path.exists(local_path):
                                # Compress to WebP
                                webp_relative = os.path.splitext(relative_path)[0] + '.webp'
                                webp_local_path = os.path.join(settings.MEDIA_ROOT, webp_relative)
                                
                                try:
                                    with Image.open(local_path) as img:
                                        img.save(webp_local_path, 'WEBP', quality=80)
                                        
                                    gcs_blob_name = webp_relative.replace("\\", "/")
                                    new_url = upload_to_gcs(webp_local_path, gcs_blob_name, content_type="image/webp")
                                    if new_url:
                                        opt.image_url = new_url
                                        opt.save(update_fields=['image_url'])
                                        
                                    # Clean up compressed webp temp file
                                    if os.path.exists(webp_local_path):
                                        os.remove(webp_local_path)
                                except Exception as img_err:
                                    logger.error(f"❌ Failed to compress option image {local_path}: {img_err}")

        # Evict cache for this exam and exam lists
        from django.core.cache import cache
        cache.delete(f"exam:data:{exam_id}")
        if hasattr(cache, 'client'):
            try:
                redis_client = cache.client.get_client()
                keys = redis_client.keys("*exams:list:*")
                if keys:
                    redis_client.delete(*keys)
            except Exception as e:
                logger.warning(f"Failed to clear exam list cache: {e}")
        logger.info(f"✅ Finished database updates and GCS uploads for exam: {exam_id}")

    except Exception as tx_err:
        logger.error(f"❌ Transaction failed during GCS media processing: {tx_err}")
        return str(tx_err)

    # 4. Clean up temporary local media folders
    local_audio_dir = os.path.join(settings.MEDIA_ROOT, 'exams', 'audio', exam_id)
    local_images_dir = os.path.join(settings.MEDIA_ROOT, 'exams', 'images', exam_id)
    
    for local_dir in [local_audio_dir, local_images_dir]:
        if os.path.exists(local_dir):
            try:
                shutil.rmtree(local_dir)
                logger.info(f"🗑️ Cleaned up local directory: {local_dir}")
            except Exception as cleanup_err:
                logger.warning(f"⚠️ Failed to delete local directory {local_dir}: {cleanup_err}")

    return f"Exam {exam_id} media processed and uploaded successfully"


@shared_task
def import_full_exam_task(temp_dir, exam_json_name, audio_name=None, image_mapping_name=None, images_names=None):
    from django.core.files import File
    from .utils import import_full_exam_data
    import shutil

    images_names = images_names or []
    
    # Construct full paths
    json_path = os.path.join(temp_dir, exam_json_name)
    audio_path = os.path.join(temp_dir, audio_name) if audio_name else None
    image_mapping_path = os.path.join(temp_dir, image_mapping_name) if image_mapping_name else None
    
    # Open files and wrap with django File
    f_json = File(open(json_path, 'rb'), name=exam_json_name)
    f_audio = File(open(audio_path, 'rb'), name=audio_name) if audio_path else None
    f_mapping = File(open(image_mapping_path, 'rb'), name=image_mapping_name) if image_mapping_path else None
    
    f_images = []
    for img_name in images_names:
        img_path = os.path.join(temp_dir, 'images', img_name)
        if os.path.exists(img_path):
            f_images.append(File(open(img_path, 'rb'), name=img_name))
            
    try:
        result = import_full_exam_data(
            exam_json_file=f_json,
            audio_file=f_audio,
            image_mapping_file=f_mapping,
            images=f_images
        )
        logger.info(f"Import full exam task finished successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Error running import_full_exam_task: {e}", exc_info=True)
        raise e
    finally:
        # Clean up files
        f_json.close()
        if f_audio: f_audio.close()
        if f_mapping: f_mapping.close()
        for f_img in f_images:
            f_img.close()
            
        # Remove temp directory
        try:
            shutil.rmtree(temp_dir)
        except Exception as cleanup_err:
            logger.warning(f"Failed to delete temp dir {temp_dir}: {cleanup_err}")

