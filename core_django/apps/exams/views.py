import json
import os
from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.throttling import ScopedRateThrottle
from django.core.cache import cache
from google.cloud import storage
from .models import Exam, Section, Question, Option
from .serializers import ExamSerializer, ExamListSerializer
from .throttles import UniqueExamAccessThrottle
from .tasks import process_exam_media_task


class ExamViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API viewset for viewing Exams.
    """
    queryset = Exam.objects.filter(status=1).order_by('level', 'created_at')
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle, UniqueExamAccessThrottle]

    @property
    def throttle_scope(self):
        if self.action == 'list':
            return 'user'
        return 'exam_fetch'

    def get_serializer_class(self):
        # List view uses a lightweight serializer (no sections/questions included)
        if self.action == 'list':
            return ExamListSerializer
        # Detail view includes the full nested structure
        return ExamSerializer

    def list(self, request, *args, **kwargs):
        level = request.query_params.get('level', '')
        language = request.query_params.get('language', '')

        cache_key = f"exams:list:{level}:{language}"
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            import random
            ttl = 24 * 3600 + random.randint(0, 1800)  # 24 hours + jitter
            cache.set(cache_key, response.data, timeout=ttl)
        return response

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ['retrieve', 'full_exam']:
            queryset = queryset.prefetch_related('sections__questions__options')
        level = self.request.query_params.get('level', None)
        if level is not None:
            queryset = queryset.filter(level__iexact=level)
        language = self.request.query_params.get('language', None)
        if language is not None:
            queryset = queryset.filter(language=language)
        return queryset

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get('pk')
        # Fast indexed query to fetch only the exam_id field
        exam_id = Exam.objects.filter(pk=pk).values_list('exam_id', flat=True).first()
        if not exam_id:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        cache_key = f"exam:data:{exam_id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        # Cache miss: fetch full object and run the prefetch JOINs
        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == 200:
            import random
            ttl = 24 * 3600 + random.randint(0, 1800)  # 24 hours + jitter
            cache.set(cache_key, response.data, timeout=ttl)
        return response

    @action(detail=True, methods=['get'])
    def full_exam(self, request, pk=None):
        """
        Alias for retrieve to explicitly fetch full exam with sections, questions and options.
        """
        return self.retrieve(request, pk=pk)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser], permission_classes=[permissions.IsAdminUser])
    def upload_full_exam(self, request):
        """
        Upload an entire exam including JSON data, audio, and images.
        Processes asynchronously in background via Celery.
        """
        import uuid
        import os
        from django.core.files.storage import default_storage
        from .tasks import import_full_exam_task

        exam_json_file = request.FILES.get('exam_json')
        audio_file = request.FILES.get('audio_file')
        image_mapping_file = request.FILES.get('image_mapping')
        images = request.FILES.getlist('images')

        if not exam_json_file:
            return Response({'error': 'Missing exam_json file'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Create a unique temp directory inside media root
        import_id = str(uuid.uuid4())
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_exam_imports', import_id)
        os.makedirs(os.path.join(temp_dir, 'images'), exist_ok=True)

        try:
            # 2. Save JSON file
            json_name = exam_json_file.name
            json_path = os.path.join(temp_dir, json_name)
            with open(json_path, 'wb') as f:
                for chunk in exam_json_file.chunks():
                    f.write(chunk)

            # 3. Save Audio file (if provided)
            audio_name = None
            if audio_file:
                audio_name = audio_file.name
                audio_path = os.path.join(temp_dir, audio_name)
                with open(audio_path, 'wb') as f:
                    for chunk in audio_file.chunks():
                        f.write(chunk)

            # 4. Save Image Mapping file (if provided)
            mapping_name = None
            if image_mapping_file:
                mapping_name = image_mapping_file.name
                mapping_path = os.path.join(temp_dir, mapping_name)
                with open(mapping_path, 'wb') as f:
                    for chunk in image_mapping_file.chunks():
                        f.write(chunk)

            # 5. Save images (if provided)
            images_names = []
            for img in images:
                img_name = img.name
                images_names.append(img_name)
                img_path = os.path.join(temp_dir, 'images', img_name)
                with open(img_path, 'wb') as f:
                    for chunk in img.chunks():
                        f.write(chunk)

            # 6. Trigger background task
            task = import_full_exam_task.delay(
                temp_dir=temp_dir,
                exam_json_name=json_name,
                audio_name=audio_name,
                image_mapping_name=mapping_name,
                images_names=images_names
            )

            return Response({
                'message': 'Đã nhận yêu cầu tải lên đề thi. Tiến trình nhập dữ liệu đang chạy ngầm.',
                'task_id': task.id
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            # Cleanup temp directory if saving files failed
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            import logging
            logging.getLogger(__name__).error(f"Failed to initiate background exam import: {e}", exc_info=True)
            return Response({'error': f'Lỗi hệ thống: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

