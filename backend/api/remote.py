"""Remote API endpoints with token authentication for external integrations."""
import secrets
from datetime import datetime
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from ..database import get_db, Scene, TriggerToken, Group, Universe
from ..auth import get_current_user
from ..dmx_interface import dmx_interface
from ..websocket_manager import manager
from .scenes import apply_fade

router = APIRouter()


# ============= Request/Response Models =============

class CreateTokenRequest(BaseModel):
    token_type: Literal["scene", "blackout", "group", "status"] = "scene"
    scene_id: Optional[int] = None  # Required for scene tokens
    group_id: Optional[int] = None  # Required for group tokens
    name: Optional[str] = None


class TokenResponse(BaseModel):
    id: int
    token: str
    token_type: str
    scene_id: Optional[int]
    scene_name: Optional[str]
    group_id: Optional[int]
    group_name: Optional[str]
    name: Optional[str]
    created_at: str
    last_used: Optional[str]
    trigger_url: str


class TriggerResponse(BaseModel):
    status: str
    message: str


class StatusResponse(BaseModel):
    blackout: bool
    groups: list
    universes: list


# ============= Token Management Endpoints (JWT authenticated) =============

@router.get("/tokens")
async def list_tokens(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all remote API tokens."""
    tokens = db.query(TriggerToken).options(
        joinedload(TriggerToken.scene),
        joinedload(TriggerToken.group)
    ).all()

    base_url = str(request.base_url).rstrip('/')

    def get_trigger_url(t):
        if t.token_type == "scene":
            return f"{base_url}/api/remote/scene/{t.scene_id}?token={t.token}"
        elif t.token_type == "blackout":
            return f"{base_url}/api/remote/blackout?token={t.token}"
        elif t.token_type == "group":
            return f"{base_url}/api/remote/group/{t.group_id}?token={t.token}&value=VALUE"
        elif t.token_type == "status":
            return f"{base_url}/api/remote/status?token={t.token}"
        return ""

    return {
        "tokens": [
            {
                "id": t.id,
                "token": t.token[:8] + "..." + t.token[-4:],  # Partially masked
                "full_token": t.token,
                "token_type": getattr(t, 'token_type', 'scene'),
                "scene_id": t.scene_id,
                "scene_name": t.scene.name if t.scene else None,
                "group_id": getattr(t, 'group_id', None),
                "group_name": t.group.name if hasattr(t, 'group') and t.group else None,
                "name": t.name,
                "created_at": t.created_at,
                "last_used": t.last_used,
                "trigger_url": get_trigger_url(t)
            }
            for t in tokens
        ]
    }


@router.post("/tokens")
async def create_token(
    data: CreateTokenRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new remote API token."""
    # Validate based on token type
    scene = None
    group = None

    if data.token_type == "scene":
        if not data.scene_id:
            raise HTTPException(status_code=400, detail="scene_id required for scene tokens")
        scene = db.query(Scene).filter(Scene.id == data.scene_id).first()
        if not scene:
            raise HTTPException(status_code=404, detail="Scene not found")
    elif data.token_type == "group":
        if not data.group_id:
            raise HTTPException(status_code=400, detail="group_id required for group tokens")
        group = db.query(Group).filter(Group.id == data.group_id).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

    # Generate secure token
    token = secrets.token_urlsafe(32)

    trigger_token = TriggerToken(
        token=token,
        token_type=data.token_type,
        scene_id=data.scene_id if data.token_type == "scene" else None,
        group_id=data.group_id if data.token_type == "group" else None,
        name=data.name,
        created_at=datetime.utcnow().isoformat()
    )
    db.add(trigger_token)
    db.commit()
    db.refresh(trigger_token)

    base_url = str(request.base_url).rstrip('/')

    # Build trigger URL based on type
    if data.token_type == "scene":
        trigger_url = f"{base_url}/api/remote/scene/{data.scene_id}?token={token}"
    elif data.token_type == "blackout":
        trigger_url = f"{base_url}/api/remote/blackout?token={token}"
    elif data.token_type == "group":
        trigger_url = f"{base_url}/api/remote/group/{data.group_id}?token={token}&value=VALUE"
    elif data.token_type == "status":
        trigger_url = f"{base_url}/api/remote/status?token={token}"
    else:
        trigger_url = ""

    return TokenResponse(
        id=trigger_token.id,
        token=token,
        token_type=data.token_type,
        scene_id=data.scene_id if data.token_type == "scene" else None,
        scene_name=scene.name if scene else None,
        group_id=data.group_id if data.token_type == "group" else None,
        group_name=group.name if group else None,
        name=trigger_token.name,
        created_at=trigger_token.created_at,
        last_used=None,
        trigger_url=trigger_url
    )


@router.delete("/tokens/{token_id}")
async def delete_token(
    token_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a remote API token."""
    token = db.query(TriggerToken).filter(TriggerToken.id == token_id).first()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    db.delete(token)
    db.commit()
    return {"status": "deleted"}


# ============= Remote Action Endpoints (token authenticated) =============

def validate_token(token: str, expected_type: str, db: Session, resource_id: int = None) -> TriggerToken:
    """Validate a token and update last_used timestamp."""
    query = db.query(TriggerToken).filter(TriggerToken.token == token)

    # Filter by token type
    query = query.filter(TriggerToken.token_type == expected_type)

    # For scene/group tokens, also verify the resource ID matches
    if expected_type == "scene" and resource_id is not None:
        query = query.filter(TriggerToken.scene_id == resource_id)
    elif expected_type == "group" and resource_id is not None:
        query = query.filter(TriggerToken.group_id == resource_id)

    trigger_token = query.first()

    if not trigger_token:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token or token not authorized for this {expected_type}"
        )

    # Update last_used
    trigger_token.last_used = datetime.utcnow().isoformat()
    db.commit()

    return trigger_token


# ----- Scene Trigger -----

@router.post("/scene/{scene_id}")
@router.get("/scene/{scene_id}")
async def trigger_scene(
    scene_id: int,
    token: str = Query(..., description="Scene trigger token"),
    db: Session = Depends(get_db)
):
    """Trigger a scene recall using a token."""
    validate_token(token, "scene", db, scene_id)

    scene = db.query(Scene).options(
        joinedload(Scene.values),
        joinedload(Scene.group_values)
    ).filter(Scene.id == scene_id).first()

    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Build target values by universe
    target_values = {}
    for sv in scene.values:
        if sv.universe_id not in target_values:
            target_values[sv.universe_id] = {}
        target_values[sv.universe_id][sv.channel] = sv.value

    # Filter out input-controlled channels if input is active
    filtered_values = {}
    for uid, channels in target_values.items():
        if uid in dmx_interface.inputs:
            # Input is active - filter out channels in the input range
            universe = db.query(Universe).filter(Universe.id == uid).first()
            input_start = universe.input_channel_start or 1 if universe else 1
            input_end = universe.input_channel_end or 512 if universe else 512
            filtered_values[uid] = {
                ch: val for ch, val in channels.items()
                if ch < input_start or ch > input_end
            }
        else:
            # No active input - use all channels
            filtered_values[uid] = channels

    # Apply transition
    if scene.transition_type == "instant" or scene.duration <= 0:
        for uid, channels in filtered_values.items():
            if channels:  # Only apply if there are channels to set
                dmx_interface.set_channels(uid, channels)
    elif scene.transition_type == "fade":
        await apply_fade(filtered_values, scene.duration, crossfade=False)
    elif scene.transition_type == "crossfade":
        await apply_fade(filtered_values, scene.duration, crossfade=True)

    # Restore group master values
    # Note: We only restore the master value, NOT apply to member channels
    # The scene already has the correct channel values - applying groups would overwrite them
    if scene.group_values:
        for gv in scene.group_values:
            group = db.query(Group).filter(Group.id == gv.group_id).first()
            if group:
                group.master_value = gv.master_value
                # Update runtime group master value (without applying to members)
                if gv.group_id in dmx_interface._groups:
                    dmx_interface._groups[gv.group_id]["master_value"] = gv.master_value
                # If physical master, set the channel but skip group member application
                if group.master_universe and group.master_channel:
                    dmx_interface.set_channel(group.master_universe, group.master_channel, gv.master_value, source="remote_api", _from_group=True)
                # For virtual masters, we've already updated the runtime value above
        db.commit()

        for gv in scene.group_values:
            await manager.broadcast_group_value_changed(gv.group_id, gv.master_value)

    # Broadcast active scene change to all WebSocket clients
    await manager.broadcast({
        "type": "active_scene_changed",
        "data": {"scene_id": scene_id}
    })

    return TriggerResponse(status="success", message=f"Scene '{scene.name}' triggered")


# ----- Blackout Toggle -----

@router.post("/blackout")
@router.get("/blackout")
async def trigger_blackout(
    token: str = Query(..., description="Blackout token"),
    state: Optional[str] = Query(None, description="Set state: 'on', 'off', or omit to toggle"),
    db: Session = Depends(get_db)
):
    """Toggle or set blackout state."""
    validate_token(token, "blackout", db)

    current_blackout = dmx_interface.is_blackout_active()

    if state is None:
        # Toggle
        new_state = not current_blackout
    elif state.lower() in ("on", "true", "1"):
        new_state = True
    elif state.lower() in ("off", "false", "0"):
        new_state = False
    else:
        raise HTTPException(status_code=400, detail="Invalid state. Use 'on', 'off', or omit to toggle.")

    # Apply blackout state
    if new_state:
        dmx_interface.blackout()
    else:
        dmx_interface.release_blackout()

    return TriggerResponse(
        status="success",
        message=f"Blackout {'enabled' if new_state else 'disabled'}"
    )


# ----- Group/Master Control -----

@router.post("/group/{group_id}")
@router.get("/group/{group_id}")
async def trigger_group(
    group_id: int,
    token: str = Query(..., description="Group token"),
    value: int = Query(..., description="Master value (0-255)", ge=0, le=255),
    db: Session = Depends(get_db)
):
    """Set a group's master fader value."""
    validate_token(token, "group", db, group_id)

    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Update group value
    group.master_value = value
    db.commit()

    # Apply to DMX
    if group.master_universe and group.master_channel:
        dmx_interface.set_channel(group.master_universe, group.master_channel, value, source="remote_api")
    else:
        dmx_interface.apply_group_direct(group_id, value)

    # Broadcast update
    await manager.broadcast_group_value_changed(group_id, value)

    return TriggerResponse(
        status="success",
        message=f"Group '{group.name}' set to {value}"
    )


# ----- Status Query -----

@router.get("/status")
async def get_status(
    token: str = Query(..., description="Status token"),
    db: Session = Depends(get_db)
):
    """Get current DMX system status (read-only)."""
    validate_token(token, "status", db)

    # Get groups
    groups = db.query(Group).filter(Group.enabled == True).all()
    group_list = [
        {
            "id": g.id,
            "name": g.name,
            "master_value": g.master_value
        }
        for g in groups
    ]

    # Get universes from database
    universes = db.query(Universe).all()
    universe_list = [
        {
            "id": u.id,
            "name": u.label,
            "enabled": u.enabled
        }
        for u in universes
    ]

    return StatusResponse(
        blackout=dmx_interface.is_blackout_active(),
        groups=group_list,
        universes=universe_list
    )
