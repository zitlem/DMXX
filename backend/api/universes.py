"""Universe management API endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, Universe
from ..auth import get_current_user
from ..dmx_interface import dmx_interface

router = APIRouter()


class CreateUniverseRequest(BaseModel):
    label: str
    device_type: str = "artnet"  # artnet, sacn, dmx_usb, etc.
    config_json: dict = {}
    enabled: bool = False
    master_fader_color: Optional[str] = None  # Hex color for universe master fader


class UpdateUniverseRequest(BaseModel):
    label: Optional[str] = None
    device_type: Optional[str] = None
    config_json: Optional[dict] = None
    enabled: Optional[bool] = None
    master_fader_color: Optional[str] = None  # Hex color for universe master fader


def universe_to_dict(universe: Universe, include_activity: bool = True) -> dict:
    """Convert a Universe model to dictionary."""
    result = {
        "id": universe.id,
        "label": universe.label,
        "device_type": universe.device_type,
        "config": universe.config_json,
        "enabled": universe.enabled,
        "master_fader_color": universe.master_fader_color or "#00bcd4",
        "input": {
            "input_type": universe.input_type,
            "config": universe.input_config if isinstance(universe.input_config, dict) else {},
            "enabled": universe.input_enabled
        }
    }

    if include_activity:
        ola_universe = dmx_interface.get_universe(universe.id)
        result["active"] = ola_universe.active if ola_universe else False

    return result


@router.get("")
async def list_universes(db: Session = Depends(get_db)):
    """List all universes."""
    universes = db.query(Universe).all()
    return {"universes": [universe_to_dict(u) for u in universes]}


# ============= Static routes must come BEFORE /{universe_id} =============

@router.get("/protocols/list")
async def list_protocols():
    """List available DMX output protocols and their configuration schemas."""
    return {"protocols": dmx_interface.get_protocols()}


# ============= Grand Master Endpoints =============

class GrandmasterRequest(BaseModel):
    value: int  # 0-255


@router.get("/grandmaster")
async def get_grandmasters():
    """Get all grand master values (global and per-universe)."""
    return dmx_interface.get_all_grandmasters()


@router.post("/grandmaster/global")
async def set_global_grandmaster(
    request: GrandmasterRequest,
    user: dict = Depends(get_current_user)
):
    """Set the global grand master value (0-255)."""
    if not 0 <= request.value <= 255:
        raise HTTPException(status_code=400, detail="Value must be 0-255")
    dmx_interface.set_global_grandmaster(request.value)
    return {"status": "ok", "global_grandmaster": request.value}


# ============= Dynamic /{universe_id} routes =============

@router.get("/{universe_id}")
async def get_universe(universe_id: int, db: Session = Depends(get_db)):
    """Get a specific universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")
    return universe_to_dict(universe)


@router.post("")
async def create_universe(
    request: CreateUniverseRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new universe."""
    # Find the next available ID
    max_id = db.query(Universe).order_by(Universe.id.desc()).first()
    next_id = (max_id.id + 1) if max_id else 1

    # Limit check (Art-Net supports up to 32768 universes)
    if next_id > 32768:
        raise HTTPException(status_code=400, detail="Maximum universe limit reached (32768)")

    universe = Universe(
        id=next_id,
        label=request.label,
        device_type=request.device_type,
        config_json=request.config_json,
        enabled=request.enabled,
        master_fader_color=request.master_fader_color or "#00bcd4"
    )
    db.add(universe)
    db.commit()
    db.refresh(universe)

    # Add to DMX interface if enabled
    if universe.enabled:
        await dmx_interface.add_universe(
            universe.id,
            device_type=universe.device_type,
            config=universe.config_json or {}
        )

    return universe_to_dict(universe)


@router.put("/{universe_id}")
async def update_universe(
    universe_id: int,
    request: UpdateUniverseRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update an existing universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    was_enabled = universe.enabled

    if request.label is not None:
        universe.label = request.label
    if request.device_type is not None:
        universe.device_type = request.device_type
    if request.config_json is not None:
        universe.config_json = request.config_json
    if request.enabled is not None:
        universe.enabled = request.enabled
    if request.master_fader_color is not None:
        universe.master_fader_color = request.master_fader_color

    db.commit()
    db.refresh(universe)

    # Update DMX interface - reconfigure if device_type or config changed
    config_changed = request.device_type is not None or request.config_json is not None

    if universe.enabled:
        if not was_enabled or config_changed:
            # Add or reconfigure the universe
            await dmx_interface.add_universe(
                universe.id,
                device_type=universe.device_type,
                config=universe.config_json or {}
            )
    elif was_enabled:
        # Was enabled, now disabled
        await dmx_interface.remove_universe(universe.id)

    return universe_to_dict(universe)


@router.delete("/{universe_id}")
async def delete_universe(
    universe_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    # Remove from DMX interface
    await dmx_interface.remove_universe(universe.id)

    db.delete(universe)
    db.commit()

    return {"status": "deleted", "universe_id": universe_id}


@router.post("/{universe_id}/enable")
async def enable_universe(
    universe_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Enable a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    universe.enabled = True
    db.commit()

    await dmx_interface.add_universe(
        universe.id,
        device_type=universe.device_type,
        config=universe.config_json or {}
    )

    return {"status": "enabled", "universe_id": universe_id}


@router.post("/{universe_id}/disable")
async def disable_universe(
    universe_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Disable a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    universe.enabled = False
    db.commit()

    await dmx_interface.remove_universe(universe.id)

    return {"status": "disabled", "universe_id": universe_id}


@router.post("/{universe_id}/grandmaster")
async def set_universe_grandmaster(
    universe_id: int,
    request: GrandmasterRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Set per-universe grand master value (0-255)."""
    # Verify universe exists
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    if not 0 <= request.value <= 255:
        raise HTTPException(status_code=400, detail="Value must be 0-255")

    dmx_interface.set_universe_grandmaster(universe_id, request.value)
    return {"status": "ok", "universe_id": universe_id, "grandmaster": request.value}


@router.get("/{universe_id}/grandmaster")
async def get_universe_grandmaster(universe_id: int, db: Session = Depends(get_db)):
    """Get per-universe grand master value."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    return {"universe_id": universe_id, "grandmaster": dmx_interface.get_universe_grandmaster(universe_id)}
