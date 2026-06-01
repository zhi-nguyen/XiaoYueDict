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

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "***REMOVED***")
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
