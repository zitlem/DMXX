"""Patch management API endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, Patch, Fixture, Universe, ChannelLabel
from ..auth import get_current_user
from ..websocket_manager import manager

router = APIRouter()


class CreatePatchRequest(BaseModel):
    fixture_id: int
    universe_id: int
    start_channel: int
    label: Optional[str] = ""
    group_color: Optional[str] = ""


class UpdatePatchRequest(BaseModel):
    fixture_id: Optional[int] = None
    universe_id: Optional[int] = None
    start_channel: Optional[int] = None
    label: Optional[str] = None
    group_color: Optional[str] = None


class ChannelLabelRequest(BaseModel):
    universe_id: int
    channel: int
    label: str


def patch_to_dict(patch: Patch) -> dict:
    """Convert a Patch model to dictionary."""
    fixture_def = patch.fixture.definition_json if patch.fixture else {}
    channel_count = len(fixture_def.get("channels", []))

    return {
        "id": patch.id,
        "fixture_id": patch.fixture_id,
        "fixture_name": patch.fixture.name if patch.fixture else "Unknown",
        "manufacturer": patch.fixture.manufacturer if patch.fixture else "",
        "universe_id": patch.universe_id,
        "universe_label": patch.universe.label if patch.universe else "",
        "start_channel": patch.start_channel,
        "end_channel": patch.start_channel + channel_count - 1,
        "channel_count": channel_count,
        "label": patch.label,
        "group_color": patch.group_color or "",
        "channels": fixture_def.get("channels", [])
    }


@router.get("")
async def list_patches(
    universe_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List all patches, optionally filtered by universe."""
    query = db.query(Patch)
    if universe_id is not None:
        query = query.filter(Patch.universe_id == universe_id)

    patches = query.all()
    return {"patches": [patch_to_dict(p) for p in patches]}


@router.get("/{patch_id}")
async def get_patch(patch_id: int, db: Session = Depends(get_db)):
    """Get a specific patch."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")
    return patch_to_dict(patch)


@router.post("")
async def create_patch(
    request: CreatePatchRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new patch."""
    # Validate fixture exists
    fixture = db.query(Fixture).filter(Fixture.id == request.fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Validate universe exists
    universe = db.query(Universe).filter(Universe.id == request.universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    # Validate channel range
    channel_count = len(fixture.definition_json.get("channels", []))
    if request.start_channel < 1 or request.start_channel + channel_count - 1 > 512:
        raise HTTPException(
            status_code=400,
            detail=f"Fixture requires channels {request.start_channel}-{request.start_channel + channel_count - 1}, which exceeds DMX range"
        )

    # Check for channel conflicts
    existing = db.query(Patch).filter(
        Patch.universe_id == request.universe_id
    ).all()

    new_start = request.start_channel
    new_end = request.start_channel + channel_count - 1

    for p in existing:
        p_count = len(p.fixture.definition_json.get("channels", []))
        p_start = p.start_channel
        p_end = p.start_channel + p_count - 1

        if not (new_end < p_start or new_start > p_end):
            raise HTTPException(
                status_code=400,
                detail=f"Channel conflict with existing patch '{p.label or p.fixture.name}' (channels {p_start}-{p_end})"
            )

    # Create patch
    patch = Patch(
        fixture_id=request.fixture_id,
        universe_id=request.universe_id,
        start_channel=request.start_channel,
        label=request.label or "",
        group_color=request.group_color or ""
    )
    db.add(patch)
    db.commit()
    db.refresh(patch)
    await manager.broadcast_patches_changed()

    return patch_to_dict(patch)


@router.put("/{patch_id}")
async def update_patch(
    patch_id: int,
    request: UpdatePatchRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update an existing patch."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    if request.fixture_id is not None:
        fixture = db.query(Fixture).filter(Fixture.id == request.fixture_id).first()
        if not fixture:
            raise HTTPException(status_code=404, detail="Fixture not found")
        patch.fixture_id = request.fixture_id

    if request.universe_id is not None:
        universe = db.query(Universe).filter(Universe.id == request.universe_id).first()
        if not universe:
            raise HTTPException(status_code=404, detail="Universe not found")
        patch.universe_id = request.universe_id

    if request.start_channel is not None:
        patch.start_channel = request.start_channel

    if request.label is not None:
        patch.label = request.label

    if request.group_color is not None:
        patch.group_color = request.group_color

    db.commit()
    db.refresh(patch)
    await manager.broadcast_patches_changed()

    return patch_to_dict(patch)


@router.delete("/{patch_id}")
async def delete_patch(
    patch_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a patch."""
    patch = db.query(Patch).filter(Patch.id == patch_id).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    db.delete(patch)
    db.commit()
    await manager.broadcast_patches_changed()
    return {"status": "deleted", "patch_id": patch_id}


@router.get("/labels/{universe_id}")
async def get_channel_labels(
    universe_id: int,
    db: Session = Depends(get_db)
):
    """Get all channel labels for a universe (from patches and custom labels)."""
    labels = {}

    # Get labels from patches
    patches = db.query(Patch).filter(Patch.universe_id == universe_id).all()
    for patch in patches:
        fixture_def = patch.fixture.definition_json
        channels = fixture_def.get("channels", [])
        # Use patch.group_color (per-patch setting)
        group_color = patch.group_color if patch.group_color else None
        for i, ch in enumerate(channels):
            channel_num = patch.start_channel + i
            label = f"{patch.label or patch.fixture.name}: {ch.get('name', f'Ch{i+1}')}"
            labels[channel_num] = {
                "label": label,
                "type": ch.get("type", "intensity"),
                "color": ch.get("color"),
                "faderName": ch.get("faderName", ""),
                "groupColor": group_color,
                "patch_id": patch.id
            }

    # Get custom labels (override patch labels)
    custom_labels = db.query(ChannelLabel).filter(ChannelLabel.universe_id == universe_id).all()
    for cl in custom_labels:
        if cl.channel in labels:
            labels[cl.channel]["custom_label"] = cl.label
        else:
            labels[cl.channel] = {"label": cl.label, "type": "custom"}

    return {"universe_id": universe_id, "labels": labels}


@router.post("/labels")
async def set_channel_label(
    request: ChannelLabelRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Set a custom label for a channel."""
    existing = db.query(ChannelLabel).filter(
        ChannelLabel.universe_id == request.universe_id,
        ChannelLabel.channel == request.channel
    ).first()

    if existing:
        existing.label = request.label
    else:
        label = ChannelLabel(
            universe_id=request.universe_id,
            channel=request.channel,
            label=request.label
        )
        db.add(label)

    db.commit()
    return {"status": "set", "universe_id": request.universe_id, "channel": request.channel, "label": request.label}


@router.delete("/labels/{universe_id}/{channel}")
async def delete_channel_label(
    universe_id: int,
    channel: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a custom channel label."""
    label = db.query(ChannelLabel).filter(
        ChannelLabel.universe_id == universe_id,
        ChannelLabel.channel == channel
    ).first()

    if label:
        db.delete(label)
        db.commit()

    return {"status": "deleted"}
