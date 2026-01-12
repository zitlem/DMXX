"""Scenes API endpoints."""
import asyncio
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from ..database import get_db, Scene, SceneValue, SceneGroupValue, Setting, Group
from ..auth import get_current_user
from ..dmx_interface import dmx_interface
from ..websocket_manager import manager

router = APIRouter()


class SceneValueModel(BaseModel):
    universe_id: int
    channel: int
    value: int


class CreateSceneRequest(BaseModel):
    name: str
    transition_type: str = "instant"  # instant, fade, crossfade
    duration: int = 0  # milliseconds
    values: Optional[List[SceneValueModel]] = None  # If None, capture current
    universe_ids: Optional[List[int]] = None  # If None, capture all universes


class UpdateSceneRequest(BaseModel):
    name: Optional[str] = None
    transition_type: Optional[str] = None
    duration: Optional[int] = None
    values: Optional[List[SceneValueModel]] = None


class RecallOptions(BaseModel):
    override_transition: Optional[str] = None
    override_duration: Optional[int] = None


class UpdateCurrentRequest(BaseModel):
    universe_ids: Optional[List[int]] = None  # If None, capture all universes
    merge_mode: str = "replace_all"  # "replace_all" or "replace"


def scene_to_dict(scene: Scene) -> dict:
    """Convert a Scene model to dictionary."""
    values = []
    for sv in scene.values:
        values.append({
            "universe_id": sv.universe_id,
            "channel": sv.channel,
            "value": sv.value
        })

    group_values = []
    if hasattr(scene, 'group_values') and scene.group_values:
        for gv in scene.group_values:
            group_values.append({
                "group_id": gv.group_id,
                "master_value": gv.master_value
            })

    return {
        "id": scene.id,
        "name": scene.name,
        "transition_type": scene.transition_type,
        "duration": scene.duration,
        "values": values,
        "group_values": group_values
    }


@router.get("")
async def list_scenes(db: Session = Depends(get_db)):
    """List all scenes."""
    scenes = db.query(Scene).options(
        joinedload(Scene.values),
        joinedload(Scene.group_values)
    ).all()
    return {"scenes": [scene_to_dict(s) for s in scenes]}


@router.get("/{scene_id}")
async def get_scene(scene_id: int, db: Session = Depends(get_db)):
    """Get a specific scene."""
    scene = db.query(Scene).options(
        joinedload(Scene.values),
        joinedload(Scene.group_values)
    ).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene_to_dict(scene)


@router.post("/save")
async def save_scene(
    request: CreateSceneRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Save current fader values as a new scene."""
    # Create the scene
    scene = Scene(
        name=request.name,
        transition_type=request.transition_type,
        duration=request.duration
    )
    db.add(scene)
    db.flush()  # Get the scene ID

    # Get values - either from request or capture current values
    if request.values:
        for v in request.values:
            # Filter by universe_ids if specified
            if request.universe_ids is None or v.universe_id in request.universe_ids:
                scene_value = SceneValue(
                    scene_id=scene.id,
                    universe_id=v.universe_id,
                    channel=v.channel,
                    value=v.value
                )
                db.add(scene_value)
    else:
        # Capture current values - filter by universe_ids if specified
        universes_to_capture = request.universe_ids if request.universe_ids else list(dmx_interface.universes.keys())
        for uid in universes_to_capture:
            if uid in dmx_interface.universes:
                values = dmx_interface.get_all_values(uid)
                for channel, value in enumerate(values, 1):
                    scene_value = SceneValue(
                        scene_id=scene.id,
                        universe_id=uid,
                        channel=channel,
                        value=value
                    )
                    db.add(scene_value)

    # Capture current group master values (all enabled groups)
    groups = db.query(Group).filter(Group.enabled == True).all()
    for group in groups:
        scene_group_value = SceneGroupValue(
            scene_id=scene.id,
            group_id=group.id,
            master_value=group.master_value
        )
        db.add(scene_group_value)

    db.commit()
    await manager.broadcast_scenes_changed()
    return scene_to_dict(scene)


@router.put("/update/{scene_id}")
async def update_scene(
    scene_id: int,
    request: UpdateSceneRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update an existing scene."""
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    if request.name is not None:
        scene.name = request.name
    if request.transition_type is not None:
        scene.transition_type = request.transition_type
    if request.duration is not None:
        scene.duration = request.duration

    if request.values is not None:
        # Delete existing values
        db.query(SceneValue).filter(SceneValue.scene_id == scene_id).delete()
        # Add new values
        for v in request.values:
            scene_value = SceneValue(
                scene_id=scene.id,
                universe_id=v.universe_id,
                channel=v.channel,
                value=v.value
            )
            db.add(scene_value)

    db.commit()
    await manager.broadcast_scenes_changed()
    return scene_to_dict(scene)


@router.post("/update-current/{scene_id}")
async def update_scene_with_current(
    scene_id: int,
    request: Optional[UpdateCurrentRequest] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update scene with current fader values."""
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    universe_ids = request.universe_ids if request else None
    merge_mode = request.merge_mode if request else "replace_all"

    if merge_mode == "replace_all" or universe_ids is None:
        # Delete all existing values
        db.query(SceneValue).filter(SceneValue.scene_id == scene_id).delete()
        universes_to_capture = universe_ids if universe_ids else list(dmx_interface.universes.keys())
    else:
        # Delete only values for specified universes (merge mode)
        db.query(SceneValue).filter(
            SceneValue.scene_id == scene_id,
            SceneValue.universe_id.in_(universe_ids)
        ).delete(synchronize_session=False)
        universes_to_capture = universe_ids

    # Capture current values for specified universes
    for uid in universes_to_capture:
        if uid in dmx_interface.universes:
            values = dmx_interface.get_all_values(uid)
            for channel, value in enumerate(values, 1):
                scene_value = SceneValue(
                    scene_id=scene.id,
                    universe_id=uid,
                    channel=channel,
                    value=value
                )
                db.add(scene_value)

    # Also update group values
    db.query(SceneGroupValue).filter(SceneGroupValue.scene_id == scene_id).delete()
    groups = db.query(Group).filter(Group.enabled == True).all()
    for group in groups:
        scene_group_value = SceneGroupValue(
            scene_id=scene.id,
            group_id=group.id,
            master_value=group.master_value
        )
        db.add(scene_group_value)

    db.commit()
    db.refresh(scene)
    await manager.broadcast_scenes_changed()
    return scene_to_dict(scene)


@router.delete("/{scene_id}")
async def delete_scene(
    scene_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a scene."""
    scene = db.query(Scene).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    db.delete(scene)
    db.commit()
    await manager.broadcast_scenes_changed()
    return {"status": "deleted", "scene_id": scene_id}


async def apply_fade(
    target_values: Dict[int, Dict[int, int]],
    duration_ms: int,
    crossfade: bool = False
):
    """Apply a fade transition to target values."""
    if duration_ms <= 0:
        # Instant transition
        for uid, channels in target_values.items():
            dmx_interface.set_channels(uid, channels)
        return

    # Get current values
    start_values = {}
    for uid in target_values:
        current = dmx_interface.get_all_values(uid)
        start_values[uid] = {ch: current[ch - 1] for ch in range(1, 513)}

    # Calculate steps (aim for ~30fps)
    steps = max(1, duration_ms // 33)
    step_delay = duration_ms / 1000 / steps

    for step in range(1, steps + 1):
        progress = step / steps

        for uid, channels in target_values.items():
            new_values = {}
            for channel in range(1, 513):
                start = start_values[uid].get(channel, 0)
                end = channels.get(channel, 0 if crossfade else start)
                new_values[channel] = int(start + (end - start) * progress)

            dmx_interface.set_channels(uid, new_values)

        await asyncio.sleep(step_delay)


@router.post("/recall/{scene_id}")
async def recall_scene(
    scene_id: int,
    options: Optional[RecallOptions] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Recall a scene and apply its values."""
    scene = db.query(Scene).options(
        joinedload(Scene.values),
        joinedload(Scene.group_values)
    ).filter(Scene.id == scene_id).first()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Determine transition settings
    transition_type = options.override_transition if options and options.override_transition else scene.transition_type
    duration = options.override_duration if options and options.override_duration is not None else scene.duration

    # Build target values by universe
    target_values: Dict[int, Dict[int, int]] = {}
    for sv in scene.values:
        if sv.universe_id not in target_values:
            target_values[sv.universe_id] = {}
        target_values[sv.universe_id][sv.channel] = sv.value

    # Apply transition
    if transition_type == "instant" or duration <= 0:
        for uid, channels in target_values.items():
            dmx_interface.set_channels(uid, channels)
    elif transition_type == "fade":
        await apply_fade(target_values, duration, crossfade=False)
    elif transition_type == "crossfade":
        await apply_fade(target_values, duration, crossfade=True)

    # Restore group master values
    if scene.group_values:
        for gv in scene.group_values:
            # Update database
            group = db.query(Group).filter(Group.id == gv.group_id).first()
            if group:
                group.master_value = gv.master_value
                # Apply group to update member channels
                if group.master_universe and group.master_channel:
                    dmx_interface.set_channel(group.master_universe, group.master_channel, gv.master_value, source="scene_recall")
                else:
                    dmx_interface.apply_group_direct(gv.group_id, gv.master_value)
        db.commit()

        # Broadcast group value changes to update UI
        for gv in scene.group_values:
            await manager.broadcast_group_value_changed(gv.group_id, gv.master_value)

    return {
        "status": "recalled",
        "scene_id": scene_id,
        "transition": transition_type,
        "duration": duration
    }
