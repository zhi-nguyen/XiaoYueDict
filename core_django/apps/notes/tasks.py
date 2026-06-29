import os
import logging
import requests
import datetime
from django.utils import timezone
from django.core.cache import cache
from django.core.files import File
from tempfile import NamedTemporaryFile
from celery import shared_task
from core_project.ws_utils import ws_notify
from .models import PDFExportTask

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def generate_pdf_task(self, task_id, notebook_id, user_id, words_data, safe_options, rate_limit_key):
    logger.info(f"Starting PDF generation task: {task_id}")
    
    try:
        task = PDFExportTask.objects.get(id=task_id)
    except PDFExportTask.DoesNotExist:
        logger.error(f"PDFExportTask {task_id} not found.")
        return {"error": "Task not found"}

    task.status = 'PROCESSING'
    task.save(update_fields=['status'])

    # FastAPI URL for PDF generation
    fastapi_url = "http://pdf-service:8082/generate"
    payload = {
        "title": task.notebook.name,
        "words": words_data,
        "options": safe_options
    }

    try:
        # Communicate with PDF generation service with streaming enabled to prevent RAM bloat
        upstream_response = requests.post(fastapi_url, json=payload, stream=True, timeout=60)
        upstream_response.raise_for_status()

        # Write to NamedTemporaryFile chunks to prevent OOM
        # delete=False is used for Windows compatibility to avoid permission sharing violations
        with NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            for chunk in upstream_response.iter_content(chunk_size=8192):
                if chunk:
                    temp_pdf.write(chunk)
            temp_pdf.flush()
            temp_pdf_path = temp_pdf.name
        
        # Open and save file to task.pdf_file
        with open(temp_pdf_path, 'rb') as f:
            task.pdf_file.save(f"notebook_{notebook_id}_{str(task_id)[:8]}.pdf", File(f))
        
        # Clean up temporary physical file
        try:
            os.remove(temp_pdf_path)
        except OSError as e:
            logger.warning(f"Failed to delete temp file {temp_pdf_path}: {e}")

        task.status = 'COMPLETED'
        task.save(update_fields=['status', 'pdf_file'])
        
        logger.info(f"Successfully generated PDF for task: {task_id}")

        # Send WebSocket notification
        from django.utils import timezone
        from datetime import timedelta
        
        pdf_expires_at = timezone.now() + timedelta(hours=1)

        ws_notify(
            user_id=user_id,
            event_type='pdf_complete',
            title='Xuất vở tập viết PDF thành công!',
            payload={
                'task_id': str(task_id),
                'notebook_id': notebook_id,
                'status': 'COMPLETED',
                'download_url': f'/notes/notebooks/export-pdf/download/{task_id}/',
                'expires_at': pdf_expires_at.isoformat(),
            },
            expires_at=pdf_expires_at,
        )

        return {"status": "success", "task_id": str(task_id)}

    except Exception as exc:
        logger.error(f"Error generating PDF for task {task_id}: {exc}")
        
        # Check if the rate limit key exists before decrementing to prevent negative OOM/bypass values
        if rate_limit_key and cache.get(rate_limit_key) is not None:
            cache.decr(rate_limit_key)

        task.status = 'FAILED'
        task.error_message = str(exc)
        task.save(update_fields=['status', 'error_message'])

        # Send WebSocket notification
        ws_notify(
            user_id=user_id,
            event_type='pdf_failed',
            title='Xuất vở tập viết PDF thất bại',
            payload={
                'task_id': str(task_id),
                'notebook_id': notebook_id,
                'status': 'FAILED',
                'error': str(exc)
            }
        )

        # Retry logic if appropriate, otherwise return
        try:
            if isinstance(exc, requests.RequestException):
                raise self.retry(exc=exc, countdown=10)
        except Exception as retry_exc:
            if type(retry_exc).__name__ in ['MaxRetriesExceededError', 'Retry']:
                raise retry_exc

        return {"status": "failed", "error": str(exc)}


@shared_task(name="apps.notes.tasks.purge_old_pdf_exports_task")
def purge_old_pdf_exports_task():
    """
    Tự động rà soát và giải phóng không gian lưu trữ bằng cách xóa các tệp PDF 
    và bản ghi tác vụ đã hoàn tất hoặc thất bại có vòng đời quá 24 giờ.
    """
    expiry_time = timezone.now() - datetime.timedelta(hours=24)
    
    # Truy xuất các tác vụ cũ thuộc nhóm trạng thái kết thúc (Terminal states)
    old_tasks = PDFExportTask.objects.filter(
        created_at__lt=expiry_time,
        status__in=['COMPLETED', 'FAILED']
    )
    
    count = 0
    for task in old_tasks:
        if task.pdf_file:
            # THAO TÁC BẮT BUỘC (CRITICAL): 
            # Gọi lệnh xóa tệp vật lý trên ổ đĩa với tham số save=False 
            # nhằm tránh kích hoạt ngược luồng lưu trữ (save) không mong muốn.
            task.pdf_file.delete(save=False) 
            
        task.delete() # Giải phóng bản ghi khỏi cơ sở dữ liệu PostgreSQL
        count += 1
        
    return f"Tiến trình hoàn tất: Đã giải phóng {count} tệp PDF quá hạn."
