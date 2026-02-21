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
    """Get all DMX values for a universe (with grandmaster scaling applied)."""
    values = dmx_interface.get_scaled_values(universe_id)
    gm_info = dmx_interface.get_grandmaster_info()
    return {
        "universe_id": universe_id,
        "values": values,
        "global_grandmaster": gm_info["global"],
        "universe_grandmaster": gm_info["universes"].get(universe_id, 255)
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


# =========================================================================
# Park Channels
# =========================================================================

class ParkChannelRequest(BaseModel):
    universe_id: int
    channel: int
    value: int


@router.post("/park")
async def park_channel(
    request: ParkChannelRequest,
    user: dict = Depends(get_current_user)
):
    """Park a channel at a fixed value, ignoring all other input."""
    if not user.get("can_park", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot park channels")
    if not 1 <= request.channel <= 512:
        raise HTTPException(status_code=400, detail="Channel must be 1-512")
    if not 0 <= request.value <= 255:
        raise HTTPException(status_code=400, detail="Value must be 0-255")

    dmx_interface.park_channel(request.universe_id, request.channel, request.value)

    # Persist to database
    from ..database import SessionLocal, ParkedChannel
    db = SessionLocal()
    try:
        # Remove any existing park for this channel
        db.query(ParkedChannel).filter(
            ParkedChannel.universe_id == request.universe_id,
            ParkedChannel.channel == request.channel
        ).delete()
        # Add new park
        db.add(ParkedChannel(
            universe_id=request.universe_id,
            channel=request.channel,
            value=request.value
        ))
        db.commit()
    finally:
        db.close()

    return {
        "status": "parked",
        "universe_id": request.universe_id,
        "channel": request.channel,
        "value": request.value
    }


class UnparkChannelRequest(BaseModel):
    universe_id: int
    channel: int


@router.post("/unpark")
async def unpark_channel(
    request: UnparkChannelRequest,
    user: dict = Depends(get_current_user)
):
    """Unpark a channel, restoring normal control."""
    if not user.get("can_park", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot unpark channels")
    if not 1 <= request.channel <= 512:
        raise HTTPException(status_code=400, detail="Channel must be 1-512")

    dmx_interface.unpark_channel(request.universe_id, request.channel)

    # Remove from database
    from ..database import SessionLocal, ParkedChannel
    db = SessionLocal()
    try:
        db.query(ParkedChannel).filter(
            ParkedChannel.universe_id == request.universe_id,
            ParkedChannel.channel == request.channel
        ).delete()
        db.commit()
    finally:
        db.close()

    return {
        "status": "unparked",
        "universe_id": request.universe_id,
        "channel": request.channel
    }


@router.get("/parked/{universe_id}")
async def get_parked_channels(
    universe_id: int,
    user: dict = Depends(get_current_user)
):
    """Get all parked channels for a universe."""
    parked = dmx_interface.get_parked_channels(universe_id)
    return {
        "universe_id": universe_id,
        "parked": parked
    }


@router.get("/parked")
async def get_all_parked_channels(user: dict = Depends(get_current_user)):
    """Get all parked channels for all universes."""
    parked = dmx_interface.get_all_parked_channels()
    return {"parked": parked}


# =========================================================================
# Highlight/Solo
# =========================================================================

class HighlightRequest(BaseModel):
    universe_id: int
    channels: List[int]
    dim_level: int = 0


@router.post("/highlight")
async def start_highlight(
    request: HighlightRequest,
    user: dict = Depends(get_current_user)
):
    """Start highlight mode for specified channels."""
    if not user.get("can_highlight", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot use highlight mode")
    for ch in request.channels:
        if not 1 <= ch <= 512:
            raise HTTPException(status_code=400, detail=f"Channel {ch} must be 1-512")
    if not 0 <= request.dim_level <= 255:
        raise HTTPException(status_code=400, detail="Dim level must be 0-255")

    dmx_interface.start_highlight(request.universe_id, request.channels, request.dim_level)
    return {
        "status": "highlight_started",
        "universe_id": request.universe_id,
        "channels": request.channels,
        "dim_level": request.dim_level
    }


class AddHighlightRequest(BaseModel):
    universe_id: int
    channel: int


@router.post("/highlight/add")
async def add_to_highlight(
    request: AddHighlightRequest,
    user: dict = Depends(get_current_user)
):
    """Add a channel to the highlight set."""
    if not user.get("can_highlight", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot use highlight mode")
    if not 1 <= request.channel <= 512:
        raise HTTPException(status_code=400, detail="Channel must be 1-512")

    dmx_interface.add_to_highlight(request.universe_id, request.channel)
    return {
        "status": "added_to_highlight",
        "universe_id": request.universe_id,
        "channel": request.channel
    }


class RemoveHighlightRequest(BaseModel):
    universe_id: int
    channel: int


@router.post("/highlight/remove")
async def remove_from_highlight(
    request: RemoveHighlightRequest,
    user: dict = Depends(get_current_user)
):
    """Remove a channel from the highlight set."""
    if not user.get("can_highlight", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot use highlight mode")
    if not 1 <= request.channel <= 512:
        raise HTTPException(status_code=400, detail="Channel must be 1-512")

    dmx_interface.remove_from_highlight(request.universe_id, request.channel)
    return {
        "status": "removed_from_highlight",
        "universe_id": request.universe_id,
        "channel": request.channel
    }


@router.post("/highlight/stop")
async def stop_highlight(user: dict = Depends(get_current_user)):
    """Stop highlight mode."""
    if not user.get("can_highlight", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot use highlight mode")
    dmx_interface.stop_highlight()
    return {"status": "highlight_stopped"}


@router.get("/highlight")
async def get_highlight_state(user: dict = Depends(get_current_user)):
    """Get current highlight state."""
    return dmx_interface.get_highlight_state()
