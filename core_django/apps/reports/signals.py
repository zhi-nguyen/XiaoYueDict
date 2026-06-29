import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def trigger_guest_ticket_migration(sender, instance, created: bool, **kwargs) -> None:
    """
    Khi user mới được tạo và có email hợp lệ,
    dispatch Celery task để liên kết ticket cũ của Guest
    sang tài khoản mới (Guest-to-User migration).
    """
    if created and instance.email:
        from .tasks import link_guest_tickets_task
        link_guest_tickets_task.delay(str(instance.id), instance.email)
        logger.info(
            f"Dispatched guest ticket migration task for user {instance.id} "
            f"(email: {instance.email})"
        )
