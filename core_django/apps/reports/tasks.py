import logging

from celery import shared_task
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def link_guest_tickets_task(self, user_id: str, email: str) -> dict[str, int]:
    """
    Liên kết SupportRequest của Guest sang tài khoản User mới
    khi email trùng khớp (case-insensitive).

    Được trigger bởi post_save signal khi User mới được tạo.
    """
    User = get_user_model()
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for guest ticket migration.")
        return {"error": "User not found"}

    from .models import SupportRequest

    # Liên kết SupportRequest dựa trên guest_email (case-insensitive)
    support_count = SupportRequest.objects.filter(
        guest_email__iexact=email,
        reporter__isnull=True
    ).update(reporter=user)

    if support_count > 0:
        logger.info(
            f"Guest ticket migration for {email}: "
            f"linked {support_count} support request(s) to user {user_id}."
        )
    else:
        logger.debug(
            f"Guest ticket migration for {email}: no matching tickets found."
        )

    return {"support_linked": support_count}
