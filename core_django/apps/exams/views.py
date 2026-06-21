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

        exam_json_file = request.FILES.get('exam_json')
        audio_file = request.FILES.get('audio_file')
        image_mapping_file = request.FILES.get('image_mapping')
        images = request.FILES.getlist('images')

        if not exam_json_file:
            return Response({'error': 'Missing exam_json file'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exam_data = json.loads(exam_json_file.read().decode('utf-8'))
        except json.JSONDecodeError as e:
            return Response({'error': f'Invalid exam JSON: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        exam_id = exam_data.get('exam_metadata', {}).get('exam_id')
        if not exam_id:
            return Response({'error': 'Missing exam_id in exam_metadata'}, status=status.HTTP_400_BAD_REQUEST)

        # Base directories for media
        audio_dir = f'exams/audio/{exam_id}'
        images_dir = f'exams/images/{exam_id}'

        # Save audio file
        audio_url = ''
        if audio_file:
            audio_path = os.path.join(audio_dir, audio_file.name)
            # Remove old file if exists
            if default_storage.exists(audio_path):
                default_storage.delete(audio_path)
            saved_audio_path = default_storage.save(audio_path, audio_file)
            audio_url = settings.MEDIA_URL + saved_audio_path

        # Save images
        saved_images = {}
        if images:
            for img in images:
                img_path = os.path.join(images_dir, img.name)
                if default_storage.exists(img_path):
                    default_storage.delete(img_path)
                saved_img_path = default_storage.save(img_path, img)
                saved_images[img.name] = settings.MEDIA_URL + saved_img_path

        # Parse image mapping
        image_mapping_by_desc = {}
        if image_mapping_file:
            try:
                mapping_data = json.loads(image_mapping_file.read().decode('utf-8'))
                for desc, val in mapping_data.items():
                    filename = val.get('filename')
                    if filename and filename in saved_images:
                        image_mapping_by_desc[desc.strip()] = saved_images[filename]
            except Exception as e:
                return Response({'error': f'Invalid image mapping JSON: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        # Process and Save Data to DB
        try:
            with transaction.atomic():
                metadata = exam_data.get('exam_metadata', {})
                settings_data = exam_data.get('exam_settings', {})
                
                exam, _ = Exam.objects.update_or_create(
                    exam_id=exam_id,
                    defaults={
                        'exam_name': metadata.get('exam_name', ''),
                        'exam_version': metadata.get('exam_version', '1.0'),
                        'level': metadata.get('level', ''),
                        'language': metadata.get('language', 'zh'),
                        'total_questions': metadata.get('total_questions', 0),
                        'total_time_minutes': metadata.get('total_time_minutes', 0),
                        'total_score': metadata.get('total_score', 0),
                        'passing_score': metadata.get('passing_score', 0),
                        'allow_resume': settings_data.get('allow_resume', True),
                        'max_attempts': settings_data.get('max_attempts', -1),
                        'shuffle_questions': settings_data.get('shuffle_questions', False),
                        'shuffle_options': settings_data.get('shuffle_options', False),
                        'show_explanation_after': settings_data.get('show_explanation_after', 'exam_submitted'),
                        'status': 1
                    }
                )
                
                sections_data = exam_data.get('sections', [])
                for s_idx, sec_data in enumerate(sections_data):
                    section_name = sec_data.get('section_name', '')
                    # Apply audio URL if this is listening section
                    s_audio_url = audio_url if section_name == 'Listening' else sec_data.get('section_audio_url', '')
                    
                    section, _ = Section.objects.update_or_create(
                        exam=exam,
                        section_id=sec_data.get('section_id'),
                        defaults={
                            'section_name': section_name,
                            'part_number': sec_data.get('part_number', 0),
                            'instruction': sec_data.get('instruction', ''),
                            'section_audio_url': s_audio_url,
                            'ordering': s_idx
                        }
                    )
                    
                    for q_idx, q_data in enumerate(sec_data.get('questions', [])):
                        q_id = q_data.get('question_id')
                        # Check image mapping by description
                        q_desc = q_data.get('image_description', '').strip()
                        q_image_url = q_data.get('image_url', '')
                        if not q_image_url and q_desc in image_mapping_by_desc:
                            q_image_url = image_mapping_by_desc[q_desc]
                                    
                        question, _ = Question.objects.update_or_create(
                            section=section,
                            question_id=q_id,
                            defaults={
                                'question_type': q_data.get('question_type', 'multiple_choice'),
                                'difficulty': q_data.get('difficulty', 'easy'),
                                'points': q_data.get('points', 5),
                                'tags': q_data.get('tags', []),
                                'audio_url': q_data.get('audio_url', ''),
                                'audio_start_time': q_data.get('audio_start_time', ''),
                                'audio_end_time': q_data.get('audio_end_time', ''),
                                'audio_script': q_data.get('audio_script', ''),
                                'question_text': q_data.get('question_text', ''),
                                'image_url': q_image_url,
                                'image_description': q_data.get('image_description', ''),
                                'correct_answer': q_data.get('correct_answer', ''),
                                'explanation': q_data.get('explanation', ''),
                                'ordering': q_idx
                            }
                        )
                        
                        for o_idx, o_data in enumerate(q_data.get('options', [])):
                            o_id = o_data.get('option_id')
                            o_image_url = o_data.get('image_url', '')
                            
                            o_desc = o_data.get('image_description', '').strip()
                            if not o_image_url and o_desc in image_mapping_by_desc:
                                o_image_url = image_mapping_by_desc[o_desc]
                                        
                            Option.objects.update_or_create(
                                question=question,
                                option_id=o_id,
                                defaults={
                                    'text': o_data.get('text', ''),
                                    'image_url': o_image_url,
                                    'image_description': o_data.get('image_description', ''),
                                    'ordering': o_idx
                                }
                            )

            # Evict cache for this exam
            cache.delete(f"exam:data:{exam_id}")

            # Trigger background task to process and upload to GCS on commit
            transaction.on_commit(lambda: process_exam_media_task.delay(exam_id))

            return Response({
                'message': 'Exam uploaded successfully. Media processing started in the background.',
                'exam_id': exam_id,
                'audio_url': audio_url,
                'images_uploaded': len(saved_images)
            })

        except Exception as e:
            return Response({'error': f'Database error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
