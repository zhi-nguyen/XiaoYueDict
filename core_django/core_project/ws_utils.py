"""
WebSocket notification utility — provides a single function for Django/Celery
to send real-time notifications to connected WebSocket clients.

Architecture: Save to PostgreSQL first (persistence), then publish to Redis
Pub/Sub (real-time delivery). This ensures no notification is lost when
the user is offline.
"""

import os
import json
import logging
import redis
import uuid

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis_client():
    """Lazy-initialized Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
        _redis_client = redis.Redis.from_url(url)
    return _redis_client


def _serialize_uuids(data):
    """Recursively convert UUID objects to their string representation."""
    if isinstance(data, dict):
        return {k: _serialize_uuids(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_serialize_uuids(x) for x in data]
    elif isinstance(data, uuid.UUID):
        return str(data)
    return data


def ws_notify(user_id, event_type: str, title: str, payload: dict = None, persist: bool = True, expires_at=None):
    """
    Send a notification to a user via WebSocket.

    1. Saves the notification to PostgreSQL (apps.notifications.Notification)
    2. Publishes to Redis Pub/Sub channel 'ws:notifications'

    ⚠️  USAGE CONTRACT:
        Hàm này thực hiện BLOCKING I/O (DB write + Redis publish).
        CHỈ được gọi từ Celery tasks hoặc management commands.
        TUYỆT ĐỐI KHÔNG gọi trực tiếp từ Django views/serializers
        vì sẽ block Gunicorn worker thread và giảm throughput hệ thống.

    Args:
        user_id: The user's database PK (int or str). If None, skip.
        event_type: One of the Notification.NOTIFICATION_TYPES values.
        title: Human-readable notification title.
        payload: Additional JSON data for the frontend.
        persist: Boolean whether to save to DB.
        expires_at: Expiration datetime for the notification interaction.
    """
    if not user_id:
        return  # No user to notify

    # Guard: Cảnh báo nếu gọi từ ngoài Celery worker context
    try:
        from celery import current_task
        if current_task is None:
            logger.warning(
                "⚠️ ws_notify() được gọi từ NGOÀI Celery worker context. "
                "Điều này có thể block request thread. "
                f"Event: {event_type}, User: {user_id}"
            )
    except ImportError:
        pass

    if payload is None:
        payload = {}
    else:
        payload = _serialize_uuids(payload)

    is_guest = str(user_id).startswith('guest_')
    notification_id = None

    # Step 1: Persist to database (Only for registered users)
    if not is_guest and persist:
        try:
            from apps.notifications.models import Notification
            notification = Notification.objects.create(
                user_id=user_id,
                notification_type=event_type,
                title=title,
                payload=payload,
                expires_at=expires_at,
            )
            notification_id = str(notification.id)
        except Exception as e:
            logger.error(f"Failed to save notification to DB: {e}")

    # Transient ID generation for un-persisted notification events
    if notification_id is None:
        notification_id = str(uuid.uuid4())

    # Step 2: Publish to Redis Pub/Sub for real-time delivery
    try:
        message = json.dumps({
            "id": notification_id,
            "user_id": str(user_id),
            "type": event_type,
            "title": title,
            "payload": payload,
        })
        get_redis_client().publish("ws:notifications", message)
    except Exception as e:
        logger.error(f"Failed to publish WS notification to Redis: {e}")

