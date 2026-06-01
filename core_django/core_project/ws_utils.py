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

logger = logging.getLogger(__name__)

_redis_client = None


def get_redis_client():
    """Lazy-initialized Redis client singleton."""
    global _redis_client
    if _redis_client is None:
        url = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
        _redis_client = redis.Redis.from_url(url)
    return _redis_client


def ws_notify(user_id, event_type: str, title: str, payload: dict = None):
    """
    Send a notification to a user via WebSocket.

    1. Saves the notification to PostgreSQL (apps.notifications.Notification)
    2. Publishes to Redis Pub/Sub channel 'ws:notifications'

    Args:
        user_id: The user's database PK (int or str). If None, skip.
        event_type: One of the Notification.NOTIFICATION_TYPES values.
        title: Human-readable notification title.
        payload: Additional JSON data for the frontend.
    """
    if not user_id:
        return  # No user to notify

    if payload is None:
        payload = {}

    is_guest = str(user_id).startswith('guest_')

    # Step 1: Persist to database (Only for registered users)
    if not is_guest:
        try:
            from apps.notifications.models import Notification
            Notification.objects.create(
                user_id=user_id,
                notification_type=event_type,
                title=title,
                payload=payload,
            )
        except Exception as e:
            logger.error(f"Failed to save notification to DB: {e}")

    # Step 2: Publish to Redis Pub/Sub for real-time delivery
    try:
        message = json.dumps({
            "user_id": str(user_id),
            "type": event_type,
            "title": title,
            "payload": payload,
        })
        get_redis_client().publish("ws:notifications", message)
    except Exception as e:
        logger.error(f"Failed to publish WS notification to Redis: {e}")
