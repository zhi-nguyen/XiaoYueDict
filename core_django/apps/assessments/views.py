from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from .models import AssessmentTask
from .serializers import AssessmentTaskSerializer
from .tasks import process_audio_task, process_refund_task
from rest_framework.permissions import AllowAny
import subprocess
import os
import logging
from apps.subscriptions.middleware import refund_volume_limit
from .utils import is_service_available

logger = logging.getLogger(__name__)

class SubmitAssessmentView(APIView):
    """
    POST /api/v1/assessments/submit/
    Accepts audio + optional target_text + language (en/zh).
    Saves audio to disk, enqueues a Celery task, returns task_id immediately.
    """
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        # 0. Kiểm tra bảo trì
        if not is_service_available():
            return Response(
                {
                    'error': 'Service Unavailable',
                    'message': 'Dịch vụ chấm điểm hiện đang bảo trì hoặc tạm ngưng hoạt động. Vui lòng quay lại sau.'
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response(
                {'error': 'No audio file provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Chặn cứng tệp tin > 2MB
        if audio_file.size > 2 * 1024 * 1024:
            guest_id = request.data.get('guest_id')
            rate_limit_user_id = getattr(request, 'rate_limit_user_id', None)
            if not rate_limit_user_id:
                if request.user and request.user.is_authenticated:
                    rate_limit_user_id = f"user:{request.user.id}"
                else:
                    identifier = guest_id if guest_id else request.META.get('REMOTE_ADDR', 'anonymous')
                    rate_limit_user_id = f"guest:{identifier}"
            
            refund_volume_limit(rate_limit_user_id, audio_file.size)
            return Response(
                {'error': 'Dung lượng tệp ghi âm vượt quá giới hạn tối đa cho phép (2MB).'},
                status=status.HTTP_400_BAD_REQUEST
            )

        target_text = request.data.get('target_text', '')
        language = request.data.get('language', 'en')

        # Validate language choice
        if language not in ('en', 'zh'):
            return Response(
                {'error': f'Invalid language: {language}. Must be "en" or "zh".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine the subscription tier and route to the correct physical queue
        if request.user and request.user.is_authenticated:
            tier = getattr(request.user.subscription, 'tier', 'Free') if hasattr(request.user, 'subscription') else 'Free'
            if tier in ('Plus', 'Premium', 'Pro'):
                target_queue = 'queue_paid'
            else:
                target_queue = 'queue_free'
        else:
            target_queue = 'queue_guest'

        task = AssessmentTask.objects.create(
            user=request.user if request.user.is_authenticated else None,
            audio_file=audio_file,
            target_text=target_text,
            language=language,
            status='PENDING',
            queue_name=target_queue,
        )

        guest_id = request.data.get('guest_id')
        user_id = str(request.user.id) if request.user.is_authenticated else guest_id

        # Lấy rate_limit_user_id từ middleware hoặc tự sinh làm phương án dự phòng
        rate_limit_user_id = getattr(request, 'rate_limit_user_id', None)
        if not rate_limit_user_id:
            if request.user and request.user.is_authenticated:
                rate_limit_user_id = f"user:{request.user.id}"
            else:
                identifier = guest_id if guest_id else request.META.get('REMOTE_ADDR', 'anonymous')
                rate_limit_user_id = f"guest:{identifier}"

        # Đo thời lượng bằng ffprobe có timeout
        duration = 0
        has_error = False
        error_msg = ''
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', task.audio_file.path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if result.returncode == 0:
                duration = float(result.stdout.strip())
                if duration > 45:
                    has_error = True
                    error_msg = 'Thời lượng tệp ghi âm vượt quá giới hạn tối đa cho phép (45 giây).'
            else:
                has_error = True
                error_msg = 'Tệp âm thanh không hợp lệ hoặc không thể phân tích.'
        except subprocess.TimeoutExpired:
            has_error = True
            error_msg = 'Quá thời gian phân tích thời lượng tệp ghi âm (Metadata Timeout).'
        except Exception as e:
            has_error = True
            error_msg = f'Lỗi phân tích cú pháp tệp tin: {str(e)}'

        if has_error:
            try:
                if task.audio_file and os.path.exists(task.audio_file.path):
                    task.audio_file.delete()
                task.delete()
            finally:
                refund_volume_limit(rate_limit_user_id, audio_file.size)
            return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

        process_audio_task.apply_async(
            args=[
                str(task.id),
                task.audio_file.path,
                target_text,
                language,
                user_id,
            ],
            kwargs={
                'rate_limit_user_id': rate_limit_user_id,
            },
            queue=target_queue
        )

        # Return initial queue position relative to its specific physical queue
        pending_ahead = AssessmentTask.objects.filter(
            status__in=['PENDING', 'PROCESSING'],
            queue_name=target_queue,
            created_at__lt=task.created_at,
        ).count()
        queue_position = pending_ahead + 1

        # Calculate estimated wait time based on normalized EWT formula:
        # EWT = ceil(queue_position / concurrency) * processing_time_per_task
        import math
        concurrency = 2 if target_queue == 'queue_paid' else 1
        processing_time_per_task = 7  # seconds
        estimated_wait_seconds = math.ceil(queue_position / concurrency) * processing_time_per_task

        return Response(
            {
                'task_id': str(task.id),
                'queue_position': queue_position,
                'estimated_wait_seconds': estimated_wait_seconds,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AssessmentStatusView(APIView):
    """
    GET /api/v1/assessments/status/<task_id>/
    Returns current status, queue position, and result data when completed.
    """
    throttle_classes = []

    def get(self, request, task_id, *args, **kwargs):
        try:
            task = AssessmentTask.objects.get(id=task_id)
        except AssessmentTask.DoesNotExist:
            return Response(
                {'error': 'Task not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # IDOR Protection
        if task.user is not None:
            if not request.user.is_authenticated or task.user != request.user:
                return Response(
                    {'error': 'Permission denied. This task belongs to another user.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = AssessmentTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SpellCheckView(APIView):
    """
    POST /api/v1/assessments/spellcheck/
    Accepts {"text": "some English text"} and returns misspelled words
    with suggestions. Used by the frontend to validate text BEFORE
    submitting for pronunciation scoring.

    Response:
        {
            "is_valid": true/false,
            "misspelled": [
                {"word": "helo", "index": 0, "suggestions": ["hello", "help"]},
            ],
            "clean_text": "original text"
        }
    """

    def post(self, request, *args, **kwargs):
        text = request.data.get('text', '')

        if not text or not text.strip():
            return Response(
                {'error': 'No text provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .spellcheck import check_english_text
        result = check_english_text(text)

        return Response(result, status=status.HTTP_200_OK)


class RefundAssessmentView(APIView):
    """
    POST /api/v1/assessments/refund/
    Allows the client to request a rate limit refund if a task times out (e.g. after 60s).
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        task_id = request.data.get('task_id')
        if not task_id:
            return Response(
                {'error': 'Missing task_id parameter.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            task = AssessmentTask.objects.get(id=task_id)
        except (AssessmentTask.DoesNotExist, ValueError):
            return Response(
                {'error': 'Task not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # IDOR Protection
        if task.user is not None:
            if not request.user.is_authenticated or task.user != request.user:
                return Response(
                    {'error': 'Permission denied.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Check if the task is already completed
        if task.status == 'COMPLETED':
            return Response(
                {'error': 'Cannot refund a completed task.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Preliminary check: check if already refunded or currently processing refund
        if task.refund_status in ('PENDING', 'SUCCESS'):
            return Response(
                {'status': 'already_failed', 'message': 'Task already timed out and refunded.'},
                status=status.HTTP_200_OK,
            )

        # Process Refund
        guest_id = request.data.get('guest_id') or request.headers.get('X-Guest-ID')
        if task.user:
            rate_limit_user_id = f"user:{task.user.id}"
        else:
            identifier = guest_id if guest_id else request.META.get('REMOTE_ADDR', 'anonymous')
            rate_limit_user_id = f"guest:{identifier}"

        file_size = task.audio_file.size if task.audio_file else 0

        # Trigger refund asynchronously via Celery
        process_refund_task.delay(str(task.id), rate_limit_user_id)
        logger.info(f"Triggered asynchronous refund task for task {task_id}.")

        return Response(
            {
                'status': 'refunded',
                'task_id': str(task.id),
                'refunded_bytes': file_size,
                'message': 'Refund request accepted and is processing asynchronously.',
            },
            status=status.HTTP_202_ACCEPTED,
        )

