from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from .models import AssessmentTask
from .serializers import AssessmentTaskSerializer
from .tasks import process_audio_task

class SubmitAssessmentView(APIView):
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, *args, **kwargs):
        audio_file = request.FILES.get('audio')
        if not audio_file:
            return Response({'error': 'No audio file provided'}, status=status.HTTP_400_BAD_REQUEST)

        target_text = request.data.get('target_text', '')

        task = AssessmentTask.objects.create(
            audio_file=audio_file,
            target_text=target_text,
            status='PENDING'
        )
        
        # Trigger Celery task with target_text for GOP scoring
        process_audio_task.delay(str(task.id), task.audio_file.path, target_text)

        return Response({'task_id': str(task.id)}, status=status.HTTP_202_ACCEPTED)


class AssessmentStatusView(APIView):
    def get(self, request, task_id, *args, **kwargs):
        try:
            task = AssessmentTask.objects.get(id=task_id)
        except AssessmentTask.DoesNotExist:
            return Response({'error': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssessmentTaskSerializer(task)
        return Response(serializer.data, status=status.HTTP_200_OK)
