"""
Network Monitor API endpoints.
Provides REST and WebSocket endpoints for monitoring Art-Net and sACN traffic.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from ..auth import get_current_user
from ..network_monitor import network_monitor

router = APIRouter()


@router.get("")
async def get_monitor_status(user: dict = Depends(get_current_user)):
    """Get current monitor status and all detected sources."""
    return {
        "running": network_monitor.is_running(),
        "sources": network_monitor.get_all_sources(),
        "stats": network_monitor.get_stats()
    }


@router.post("/start")
async def start_monitor(user: dict = Depends(get_current_user)):
    """Start the network monitor."""
    success = await network_monitor.start()
    return {
        "status": "started" if success else "failed",
        "running": network_monitor.is_running()
    }


@router.post("/stop")
async def stop_monitor(user: dict = Depends(get_current_user)):
    """Stop the network monitor."""
    await network_monitor.stop()
    return {
        "status": "stopped",
        "running": network_monitor.is_running()
    }


@router.get("/source/{source_key:path}")
async def get_source_details(source_key: str, user: dict = Depends(get_current_user)):
    """Get detailed information about a specific source including all 512 channel values."""
    source = network_monitor.get_source(source_key)
    if source is None:
        return {"error": "Source not found"}
    return source


@router.get("/stats")
async def get_monitor_stats(user: dict = Depends(get_current_user)):
    """Get monitor statistics."""
    return network_monitor.get_stats()


@router.websocket("/ws")
async def monitor_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time monitor updates.

    Messages from server:
    - {"type": "monitor_status", "data": {"running": bool, "sources": {...}}}
    - {"type": "monitor_source_new", "data": {"key": str, "protocol": str, ...}}
    - {"type": "monitor_update", "data": {"sources": {...}}}
    - {"type": "monitor_source_timeout", "data": {"key": str, "last_seen": float}}
    - {"type": "monitor_source_removed", "data": {"key": str}}
    - {"type": "monitor_source_values", "data": {"key": str, "values": [...]}}

    Messages from client:
    - {"type": "subscribe_source", "source_key": str}
    - {"type": "unsubscribe_source", "source_key": str}
    """
    await network_monitor.connect_client(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "subscribe_source":
                source_key = data.get("source_key")
                if source_key:
                    await network_monitor.subscribe_source(websocket, source_key)

            elif msg_type == "unsubscribe_source":
                source_key = data.get("source_key")
                if source_key:
                    network_monitor.unsubscribe_source(websocket, source_key)

    except WebSocketDisconnect:
        network_monitor.disconnect_client(websocket)
    except Exception:
        network_monitor.disconnect_client(websocket)
