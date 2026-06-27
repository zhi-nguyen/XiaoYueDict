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

    @action(detail=True, methods=['get'])
    def full_exam(self, request, pk=None):
        """
        Alias for retrieve to explicitly fetch full exam with sections, questions and options.
        """
        exam = self.get_object()
        cache_key = f"exam:data:{exam.exam_id}"
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        serializer = ExamSerializer(exam)
        data = serializer.data
        cache.set(cache_key, data, timeout=24 * 60 * 60)  # 24 hours
        return Response(data)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_full_exam(self, request):
        """
        Upload an entire exam including JSON data, audio, and images.
        """
        from .utils import import_full_exam_data

        exam_json_file = request.FILES.get('exam_json')
        audio_file = request.FILES.get('audio_file')
        image_mapping_file = request.FILES.get('image_mapping')
        images = request.FILES.getlist('images')

        if not exam_json_file:
            return Response({'error': 'Missing exam_json file'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = import_full_exam_data(
                exam_json_file=exam_json_file,
                audio_file=audio_file,
                image_mapping_file=image_mapping_file,
                images=images
            )
            return Response({
                'message': 'Exam uploaded successfully. Media processing started in the background.',
                'exam_id': result['exam_id'],
                'audio_url': result['audio_url'],
                'images_uploaded': result['images_uploaded']
            })
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error("Failed to upload full exam via API", exc_info=True)
            return Response({'error': f'Database error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
