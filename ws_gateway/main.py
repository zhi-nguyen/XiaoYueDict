"""
WebSocket Gateway — FastAPI entry point.

Provides a persistent WebSocket endpoint for real-time communication
between the XiaoYue backend (Django/Celery) and frontend (Next.js).

Endpoints:
  GET  /health      → Health check for Docker orchestration
  WS   /ws/{user_id} → WebSocket connection with JWT auth via query param
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse

from connection_manager import ConnectionManager
from auth import verify_ws_token
from redis_listener import redis_listener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Global connection manager instance
manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the Redis listener as a background task on startup."""
    logger.info("🚀 Starting WebSocket Gateway...")
    listener_task = asyncio.create_task(redis_listener(manager))
    logger.info("✅ Redis Pub/Sub listener started.")

    yield

    logger.info("🛑 Shutting down WebSocket Gateway...")
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="XiaoYue WebSocket Gateway",
    description="Real-time WebSocket server for live scoring and notifications.",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Health Check ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ws_gateway",
        "connected_users": manager.user_count,
        "total_connections": manager.connection_count,
    }


# ── WebSocket Endpoint ──────────────────────────────────────
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint with JWT authentication.

    Client connects: ws://host/ws/{user_id}?token=<short-lived-jwt>

    Protocol:
      - Client sends "ping" → Server responds "pong" (heartbeat)
      - Server pushes JSON messages from Redis Pub/Sub
    """

    # ── Step 1: Verify JWT token ──
    payload = verify_ws_token(token)
    if payload is None:
        await websocket.close(code=4003, reason="Invalid or expired token")
        return

    # Ensure token user_id matches the URL path
    token_user_id = str(payload.get("user_id", ""))
    if token_user_id != user_id:
        await websocket.close(code=4003, reason="Token user_id mismatch")
        return

    # ── Step 2: Register connection ──
    await manager.connect(user_id, websocket)

    try:
        # ── Step 3: Heartbeat loop ──
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        logger.info(f"User {user_id} disconnected (WebSocketDisconnect)")
    except Exception as e:
        logger.warning(f"User {user_id} connection error: {e}")
    finally:
        manager.disconnect(user_id, websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8005, reload=True)
