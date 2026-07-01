import logging

logger = logging.getLogger(__name__)

class UserTierRouter:
    """
    Celery task router that dynamically routes tasks based on the user's subscription tier.
    Pops 'user_tier' from kwargs to prevent signature mismatch on workers.
    """
    def route_for_task(self, task, args=None, kwargs=None, client_config=None):
        # 1. System/Admin tasks always route to queue_core
        system_tasks = {
            'apps.gamification.tasks.calculate_daily_streaks',
            'apps.subscriptions.tasks.process_expired_subscriptions',
            'apps.notes.tasks.purge_old_pdf_exports_task',
            'apps.subscriptions.tasks.expire_pending_payment_orders',
        }
        if task in system_tasks:
            return {'queue': 'queue_core'}

        # 2. Extract user_tier from kwargs to route dynamically
        user_tier = None
        if kwargs and 'user_tier' in kwargs:
            # IMPORTANT: Pop the user_tier keyword argument to prevent unexpected argument error on worker execution
            user_tier = kwargs.pop('user_tier')

        if not user_tier:
            # Fallback to extract from rate_limit_user_id if present
            if kwargs and 'rate_limit_user_id' in kwargs:
                user_id_str = kwargs.get('rate_limit_user_id', '')
                if ':' in user_id_str:
                    prefix = user_id_str.split(':')[0].lower()
                    if prefix == 'guest':
                        user_tier = 'GUEST'
                    elif prefix == 'user':
                        user_tier = 'FREE'

        if not user_tier:
            return None # Fallback to default queue in settings.py (queue_core)

        # Normalize tier name
        user_tier = str(user_tier).upper()

        # Resource-heavy tasks that need QoS/SLA routing
        priority_tasks = {
            'apps.assessments.tasks.process_audio_task',
            'apps.notes.tasks.generate_pdf_task',
            'apps.media.tasks.generate_word_image_task',
            'apps.media.tasks.trigger_image_regeneration_task',
            'apps.dictionary_zh.tasks.translate_pure_text_task',
            'apps.media.tts_tasks.generate_tts_audio_task',
            'apps.flashcard_exercises.tasks.generate_exercises_task',
            'apps.flashcard_exercises.tasks.check_writing_task',
        }

        if task in priority_tasks:
            if user_tier in ('PLUS', 'PRO', 'PREMIUM', 'PAID'):
                return {'queue': 'queue_paid'}
            elif user_tier == 'FREE':
                return {'queue': 'queue_free'}
            elif user_tier in ('GUEST', 'ANONYMOUS'):
                return {'queue': 'queue_guest'}

        return None
