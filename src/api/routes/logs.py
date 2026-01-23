"""Server-sent events for real-time logs."""

import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.utils.logging import get_log_buffer, subscribe_to_logs

router = APIRouter()


async def _event_generator() -> AsyncGenerator[str, None]:
    """Generate server-sent events for logs."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    
    def on_log(entry: dict):
        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            pass
    
    unsubscribe = subscribe_to_logs(on_log)
    
    try:
        # Send recent logs first
        for entry in get_log_buffer()[-30:]:
            yield f"data: {json.dumps(entry)}\n\n"
        
        # Stream new logs
        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {json.dumps(entry)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        unsubscribe()


@router.get("/logs/stream")
async def stream_logs():
    """Stream logs via Server-Sent Events.
    
    Connect to this endpoint to receive real-time log updates.
    Logs are sent as JSON objects with timestamp, level, and message.
    """
    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/logs/recent")
async def get_recent_logs(limit: int = 50):
    """Get recent log entries.
    
    Args:
        limit: Maximum number of entries to return (default: 50)
    """
    logs = get_log_buffer()
    return {"logs": logs[-limit:], "total": len(logs)}
