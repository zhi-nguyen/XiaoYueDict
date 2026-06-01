"""
Redis Pub/Sub Listener — subscribes to 'ws:notifications' channel
and forwards messages to connected WebSocket clients.

Runs as a background asyncio task during the FastAPI lifespan.
"""

import os
import json
import asyncio
import logging
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CHANNEL_NAME = "ws:notifications"


async def redis_listener(manager):
    """
    Subscribe to Redis Pub/Sub and forward messages to WebSocket clients.

    Expected message format:
    {
        "user_id": "123",
        "type": "score_complete",
        "payload": { ... }
    }
    """
    while True:
        try:
            redis_client = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_timeout=None,        # Pub/Sub waits indefinitely for messages
                socket_keepalive=True,       # Keep TCP connection alive
            )
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(CHANNEL_NAME)
            logger.info(f"Subscribed to Redis channel: {CHANNEL_NAME}")

            async for raw_message in pubsub.listen():
                if raw_message["type"] != "message":
                    continue

                try:
                    data = json.loads(raw_message["data"])
                    user_id = data.get("user_id")
                    if not user_id:
                        logger.warning(f"Message missing user_id: {data}")
                        continue

                    # Forward to all WebSocket connections of this user
                    await manager.send_personal_message(data, str(user_id))

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from Redis: {raw_message['data']}")
                except Exception as e:
                    logger.error(f"Error forwarding message: {e}")

        except Exception as e:
            logger.error(f"Redis connection error: {e}. Reconnecting in 3s...")
            await asyncio.sleep(3)
