from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from .models import AssessmentTask
from .serializers import AssessmentTaskSerializer
from .tasks import process_audio_task


class SubmitAssessmentView(APIView):
    """
    POST /api/v1/assessments/submit/
    Accepts audio + optional target_text + language (en/zh).
    Saves audio to disk, enqueues a Celery task, returns task_id immediately.
    """
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response(
                {'error': 'No audio file provided.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_text = request.data.get('target_text', '')
        language = request.data.get('language', 'en')

        # Validate language choice
        if language not in ('en', 'zh'):
            return Response(
                {'error': f'Invalid language: {language}. Must be "en" or "zh".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = AssessmentTask.objects.create(
            user=request.user if request.user.is_authenticated else None,
            audio_file=audio_file,
            target_text=target_text,
            language=language,
            status='PENDING',
        )

        # Trigger Celery task — language determines which AI service to call
        target_queue = 'queue_ai_zh' if language == 'zh' else 'queue_ai_en'
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

        # Return initial queue position
        pending_ahead = AssessmentTask.objects.filter(
            status__in=['PENDING', 'PROCESSING'],
            created_at__lt=task.created_at,
        ).count()
        queue_position = pending_ahead + 1

        return Response(
            {
                'task_id': str(task.id),
                'queue_position': queue_position,
                'estimated_wait_seconds': queue_position * 7,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class AssessmentStatusView(APIView):
    """
    GET /api/v1/assessments/status/<task_id>/
    Returns current status, queue position, and result data when completed.
    """
    def get(self, request, task_id, *args, **kwargs):
        try:
            task = AssessmentTask.objects.get(id=task_id)
        except AssessmentTask.DoesNotExist:
            return Response(
                {'error': 'Task not found.'},
                status=status.HTTP_404_NOT_FOUND,
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

