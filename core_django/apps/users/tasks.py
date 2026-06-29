import logging
import requests
import socket
from urllib.parse import urlparse
from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def sync_firebase_avatar_task(self, user_id, picture_url):
    """
    Task chạy ngầm để tải ảnh đại diện từ Firebase/Google và cập nhật cho User.
    """
    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning(f"User {user_id} not found. Skipping avatar sync.")
        return

    try:
        parsed_url = urlparse(picture_url)
        allowed_domains = ['googleusercontent.com', 'firebaseapp.com', 'secure.gravatar.com', 'google.com']
        is_valid_domain = any(parsed_url.netloc.endswith(domain) for domain in allowed_domains)

        # Kiểm tra IP Private để chống SSRF
        is_private_ip = False
        if parsed_url.hostname:
            try:
                ip = socket.gethostbyname(parsed_url.hostname)
                octets = [int(o) for o in ip.split('.')]
                if (octets[0] == 127 or
                    octets[0] == 10 or
                    (octets[0] == 172 and 16 <= octets[1] <= 31) or
                    (octets[0] == 192 and octets[1] == 168) or
                    ip == '255.255.255.255'):
                    is_private_ip = True
            except Exception as e:
                logger.error(f"SSRF DNS check error: {e}", exc_info=True)
                is_private_ip = True

        if is_valid_domain and parsed_url.scheme in ('http', 'https') and not is_private_ip:
            avatar_response = requests.get(picture_url, timeout=10)
            if avatar_response.status_code == 200:
                filename = f"avatar_{user.firebase_uid}.jpg"
                user.avatar.save(filename, ContentFile(avatar_response.content), save=True)
                logger.info(f"Successfully synced Firebase avatar for user {user.id}")
            else:
                logger.warning(f"Failed to fetch avatar from {picture_url}, status code: {avatar_response.status_code}")
        else:
            logger.warning(f"Blocked untrusted or private profile picture URL: {picture_url}")
    except Exception as exc:
        logger.error(f"Error syncing Firebase avatar for user {user.id}: {exc}")
        # Retry task nếu gặp sự cố kết nối mạng tạm thời
        raise self.retry(exc=exc)
