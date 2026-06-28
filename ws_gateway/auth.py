"""
JWT Authentication for WebSocket handshake.

Verifies short-lived tokens (2-minute lifetime) issued by Django's
/api/v1/users/ws-token/ endpoint. Uses the same SECRET_KEY as Django
to ensure token compatibility.
"""

import os
import logging
import jwt

logger = logging.getLogger(__name__)

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "replace-this-in-production")
if JWT_SECRET_KEY == "replace-this-in-production":
    # Raise error if not explicitly in development mode
    is_dev = os.environ.get("ENV", "").lower() in ("dev", "development") or os.environ.get("DEBUG", "False").lower() in ("true", "1", "t")
    if not is_dev:
        raise ValueError("JWT_SECRET_KEY must be set to a secure value in production!")

JWT_ALGORITHM = "HS256"


def verify_ws_token(token: str) -> dict | None:
    """
    Verify a short-lived WebSocket token.

    Returns the decoded payload dict on success, or None on failure.
    Expected payload: {"user_id": "123", "purpose": "websocket", ...}
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # Ensure this token was specifically issued for WebSocket
        if payload.get("purpose") != "websocket":
            logger.warning("Token rejected: purpose is not 'websocket'")
            return None

        # Ensure user_id is present
        if "user_id" not in payload:
            logger.warning("Token rejected: missing user_id")
            return None

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("WebSocket token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid WebSocket token: {e}")
        return None
