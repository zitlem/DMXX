"""DMX control API endpoints."""
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..auth import get_current_user
from ..dmx_interface import dmx_interface

router = APIRouter()


class SetChannelRequest(BaseModel):
    universe_id: int
    channel: int
    value: int


class SetChannelsRequest(BaseModel):
    universe_id: int
    values: Dict[int, int]  # channel: value


class FadeRequest(BaseModel):
    universe_id: int
    channel: int
    start_value: int
    end_value: int
    duration_ms: int


@router.get("/values/{universe_id}")
async def get_dmx_values(
    universe_id: int,
    user: dict = Depends(get_current_user)
):
    """Get all DMX values for a universe."""
    values = dmx_interface.get_all_values(universe_id)
    return {
        "universe_id": universe_id,
        "values": values
    }


@router.get("/values")
async def get_all_dmx_values(user: dict = Depends(get_current_user)):
    """Get DMX values for all universes."""
    all_values = {}
    for uid in dmx_interface.universes:
        all_values[uid] = dmx_interface.get_all_values(uid)
    return {"universes": all_values}


@router.post("/set")
async def set_channel(
    request: SetChannelRequest,
    user: dict = Depends(get_current_user)
):
    """Set a single DMX channel value."""
    if not 1 <= request.channel <= 512:
        raise HTTPException(status_code=400, detail="Channel must be 1-512")
    if not 0 <= request.value <= 255:
        raise HTTPException(status_code=400, detail="Value must be 0-255")

    dmx_interface.set_channel(request.universe_id, request.channel, request.value)
    return {
        "status": "set",
        "universe_id": request.universe_id,
        "channel": request.channel,
        "value": request.value
    }


@router.post("/set-multiple")
async def set_channels(
    request: SetChannelsRequest,
    user: dict = Depends(get_current_user)
):
    """Set multiple DMX channel values at once."""
    for channel, value in request.values.items():
        if not 1 <= channel <= 512:
            raise HTTPException(status_code=400, detail=f"Channel {channel} must be 1-512")
        if not 0 <= value <= 255:
            raise HTTPException(status_code=400, detail=f"Value for channel {channel} must be 0-255")

    dmx_interface.set_channels(request.universe_id, request.values)
    return {
        "status": "set",
        "universe_id": request.universe_id,
        "channels_updated": len(request.values)
    }


@router.get("/channel/{universe_id}/{channel}")
async def get_channel(
    universe_id: int,
    channel: int,
    user: dict = Depends(get_current_user)
):
    """Get a single DMX channel value."""
    if not 1 <= channel <= 512:
        raise HTTPException(status_code=400, detail="Channel must be 1-512")

    value = dmx_interface.get_channel(universe_id, channel)
    return {
        "universe_id": universe_id,
        "channel": channel,
        "value": value
    }
