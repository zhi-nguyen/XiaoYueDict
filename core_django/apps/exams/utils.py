import os
import json
import uuid
from django.conf import settings
from django.db import transaction
from django.core.cache import cache
from django.core.files.storage import default_storage
from .models import Exam, Section, Question, Option
from .tasks import process_exam_media_task

def import_full_exam_data(exam_json_file, audio_file=None, image_mapping_file=None, images=None):
    """
    Parses and imports an entire HSK exam from JSON, audio, and image files.
    Returns a dictionary of results or raises an exception.
    """
    if not exam_json_file:
        raise ValueError('Missing exam_json file')

    try:
        exam_data = json.loads(exam_json_file.read().decode('utf-8'))
    except json.JSONDecodeError as e:
        raise ValueError(f'Invalid exam JSON: {e}')

    exam_id = exam_data.get('exam_metadata', {}).get('exam_id')
    if not exam_id:
        raise ValueError('Missing exam_id in exam_metadata')

    # Base directories for media
    audio_dir = f'exams/audio/{exam_id}'
    images_dir = f'exams/images/{exam_id}'

    # Save audio file
    audio_url = ''
    if audio_file:
        audio_path = os.path.join(audio_dir, audio_file.name)
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
            raise ValueError(f'Invalid image mapping JSON: {e}')

    # Process and Save Data to DB
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

    # Evict cache for this exam and list caches
    cache.delete(f"exam:data:{exam_id}")
    if hasattr(cache, 'client'):
        try:
            redis_client = cache.client.get_client()
            keys = redis_client.keys("*exams:list:*")
            if keys:
                redis_client.delete(*keys)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to clear exam list cache: {e}")

    # Trigger background task to process and upload to GCS on commit
    transaction.on_commit(lambda: process_exam_media_task.delay(exam_id))

    return {
        'exam_id': exam_id,
        'audio_url': audio_url,
        'images_uploaded': len(saved_images)
    }
