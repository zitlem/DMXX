"""
DMXX - DMX Lighting Controller
FastAPI application with WebSocket support for real-time DMX control.
"""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Dict, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
import os

from .database import init_db, get_db, Universe, ChannelMapping, Group, UniverseOutput
from .dmx_interface import dmx_interface
from .auth import get_current_user
from .websocket_manager import manager

# Import API routers
from .api.auth import router as auth_router
from .api.dmx import router as dmx_router
from .api.scenes import router as scenes_router
from .api.patch import router as patch_router
from .api.universes import router as universes_router
from .api.fixtures import router as fixtures_router
from .api.backup import router as backup_router
from .api.settings import router as settings_router
from .api.io import router as io_router
from .api.mapping import router as mapping_router
from .api.groups import router as groups_router
from .api.remote import router as remote_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def dmx_callback(event_type: str, data: dict):
    """Callback for DMX events - queues broadcast."""
    asyncio.create_task(manager.broadcast({
        "type": event_type,
        "data": data
    }))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting DMXX...")
    init_db()

    # Initialize DMX interface
    await dmx_interface.connect()
    dmx_interface.register_callback(dmx_callback)
    logger.info("DMX interface initialized")

    # Load ALL universes from database for state tracking
    # The enabled flag controls DMX output, not whether the universe exists in memory
    db = next(get_db())
    universes = db.query(Universe).all()
    for universe in universes:
        # Create universe in memory
        if universe.id not in dmx_interface.universes:
            from .dmx_interface import DMXUniverse
            dmx_interface.universes[universe.id] = DMXUniverse(universe.id)

        # Load outputs from new UniverseOutput table
        outputs = db.query(UniverseOutput).filter(
            UniverseOutput.universe_id == universe.id
        ).order_by(UniverseOutput.priority).all()

        if outputs:
            # Use new multi-output system
            for output in outputs:
                await dmx_interface.add_output(
                    universe.id,
                    output.device_type,
                    output.config_json or {},
                    output_id=output.id,
                    enabled=output.enabled
                )
            output_status = f"outputs: {len(outputs)}"
        else:
            # Fallback to legacy single output
            if universe.enabled:
                await dmx_interface.add_output(
                    universe.id,
                    universe.device_type,
                    universe.config_json or {},
                    enabled=True
                )
            output_status = f"output: {universe.device_type}" if universe.enabled else "output: disabled"

        logger.info(f"Loaded universe {universe.id}: {universe.label} ({output_status})")

        # Load input configuration if enabled
        if universe.input_enabled and universe.input_type and universe.input_type != "none":
            success = await dmx_interface.add_input(
                universe.id,
                input_type=universe.input_type,
                config=universe.input_config or {},
                passthrough_enabled=universe.passthrough_enabled or False,
                passthrough_mode=universe.passthrough_mode or "htp",
                passthrough_show_ui=universe.passthrough_show_ui or False
            )
            if success:
                logger.info(f"  -> Input: {universe.input_type} started (passthrough: {universe.passthrough_enabled}, show_ui: {universe.passthrough_show_ui})")
            else:
                logger.error(f"  -> Input: {universe.input_type} FAILED TO START")

    # Load active channel mapping if one exists
    active_mapping = db.query(ChannelMapping).filter(ChannelMapping.enabled == True).first()
    if active_mapping:
        mappings_data = active_mapping.mappings_json.get("mappings", []) if active_mapping.mappings_json else []
        dmx_interface.set_channel_mapping(mappings_data, active_mapping.unmapped_behavior)
        logger.info(f"Loaded channel mapping: {active_mapping.name} ({len(mappings_data)} mappings, unmapped_behavior={active_mapping.unmapped_behavior})")

    # Load groups
    groups = db.query(Group).all()
    if groups:
        groups_data = []
        for group in groups:
            group_dict = {
                "id": group.id,
                "name": group.name,
                "mode": group.mode,
                "master_universe": group.master_universe,
                "master_channel": group.master_channel,
                "enabled": group.enabled,
                "members": [
                    {
                        "id": m.id,
                        "universe_id": m.universe_id,
                        "channel": m.channel,
                        "base_value": m.base_value
                    }
                    for m in group.members
                ]
            }
            groups_data.append(group_dict)
        dmx_interface.load_groups(groups_data)
        logger.info(f"Loaded {len(groups)} groups")

    db.close()

    yield

    # Shutdown
    logger.info("Shutting down DMXX...")
    await dmx_interface.disconnect()


app = FastAPI(
    title="DMXX",
    description="Web-based DMX Lighting Controller",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(dmx_router, prefix="/api/dmx", tags=["DMX"])
app.include_router(scenes_router, prefix="/api/scenes", tags=["Scenes"])
app.include_router(patch_router, prefix="/api/patch", tags=["Patch"])
app.include_router(universes_router, prefix="/api/universes", tags=["Universes"])
app.include_router(fixtures_router, prefix="/api/fixtures", tags=["Fixtures"])
app.include_router(backup_router, prefix="/api/backup", tags=["Backup"])
app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
app.include_router(io_router, prefix="/api/io", tags=["Input/Output"])
app.include_router(mapping_router, prefix="/api/mapping", tags=["Channel Mapping"])
app.include_router(groups_router, prefix="/api/groups", tags=["Groups"])
app.include_router(remote_router, prefix="/api/remote", tags=["Remote API"])


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time DMX updates.

    Messages from client:
    - {"type": "subscribe", "universes": [1, 2, 3]} - Subscribe to specific universes
    - {"type": "set_channel", "universe_id": 1, "channel": 1, "value": 255}
    - {"type": "set_channels", "universe_id": 1, "values": {1: 255, 2: 128}}
    - {"type": "get_values", "universe_id": 1}

    Messages to client:
    - {"type": "channel_change", "data": {"universe_id": 1, "channel": 1, "value": 255}}
    - {"type": "blackout", "data": {"active": true}}
    - {"type": "values", "data": {"universe_id": 1, "values": [...]}}
    """
    client_id = await manager.connect(websocket)

    try:
        # Send client their ID so they can identify their own messages
        await manager.send_personal(websocket, {
            "type": "connected",
            "data": {"client_id": client_id}
        })

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "set_channel":
                universe_id = data.get("universe_id")
                channel = data.get("channel")
                value = data.get("value")
                if all(v is not None for v in [universe_id, channel, value]):
                    # Include client_id as source for tracking
                    dmx_interface.set_channel(universe_id, channel, value, source=f"user_{client_id}")

            elif msg_type == "set_channels":
                universe_id = data.get("universe_id")
                values = data.get("values", {})
                if universe_id is not None:
                    # Convert string keys to int if needed
                    int_values = {int(k): v for k, v in values.items()}
                    dmx_interface.set_channels(universe_id, int_values, source=f"user_{client_id}")

            elif msg_type == "get_values":
                universe_id = data.get("universe_id")
                if universe_id is not None:
                    values = dmx_interface.get_all_values(universe_id)
                    await manager.send_personal(websocket, {
                        "type": "values",
                        "data": {
                            "universe_id": universe_id,
                            "values": values
                        }
                    })

            elif msg_type == "get_all_universes":
                all_data = {}
                for uid in dmx_interface.universes:
                    all_data[uid] = dmx_interface.get_all_values(uid)
                await manager.send_personal(websocket, {
                    "type": "all_values",
                    "data": all_data
                })

            elif msg_type == "get_input_values":
                universe_id = data.get("universe_id")
                if universe_id is not None:
                    values = dmx_interface.get_input_values(universe_id)
                    await manager.send_personal(websocket, {
                        "type": "input_values",
                        "data": {
                            "universe_id": universe_id,
                            "values": values
                        }
                    })

            elif msg_type == "get_all_input_values":
                all_input_data = {}
                for uid in dmx_interface.inputs:
                    all_input_data[uid] = dmx_interface.get_input_values(uid)
                await manager.send_personal(websocket, {
                    "type": "all_input_values",
                    "data": all_input_data
                })

            elif msg_type == "set_active_scene":
                scene_id = data.get("scene_id")  # Can be int or None
                # Broadcast to ALL clients so they stay in sync
                await manager.broadcast({
                    "type": "active_scene_changed",
                    "data": {"scene_id": scene_id}
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.post("/api/blackout")
async def trigger_blackout(user: dict = Depends(get_current_user)):
    """Trigger global blackout."""
    if dmx_interface.is_blackout_active():
        dmx_interface.release_blackout()
        return {"status": "released", "blackout": False}
    else:
        dmx_interface.blackout()
        return {"status": "activated", "blackout": True}


@app.get("/api/blackout/status")
async def get_blackout_status():
    """Get current blackout status."""
    return {"blackout": dmx_interface.is_blackout_active()}


# Serve static frontend files
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the Vue.js frontend."""
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    from .auth import load_config
    config = load_config()
    uvicorn.run(app, host=config.get("host", "0.0.0.0"), port=config.get("port", 8000))
