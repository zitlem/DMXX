"""Scenes API endpoints."""
import asyncio
import time
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from ..database import get_db, Scene, SceneValue, SceneGroupValue, SceneMasterValue, Setting, Group, Universe
from ..auth import get_current_user
from ..dmx_interface import dmx_interface
from ..websocket_manager import manager

router = APIRouter()


class SceneValueModel(BaseModel):
    universe_id: int
    channel: int
    value: int


class SceneGroupValueModel(BaseModel):
    group_id: int
    master_value: int
    color_state_h: Optional[float] = None
    color_state_s: Optional[float] = None
    color_state_l: Optional[float] = None


class SceneMasterValueModel(BaseModel):
    master_type: str  # "global" or "universe"
    universe_id: Optional[int] = None  # Only for master_type="universe"
    value: int


class CreateSceneRequest(BaseModel):
    name: str
    transition_type: str = "instant"  # instant, fade, crossfade
    duration: int = 0  # milliseconds
    values: Optional[List[SceneValueModel]] = None  # If None, capture current
    universe_ids: Optional[List[int]] = None  # If None, capture all universes
    group_ids: Optional[List[int]] = None  # If None, capture all enabled groups
    include_global_master: bool = False  # Include global grandmaster in scene
    include_universe_masters: bool = False  # Include universe grandmasters in scene


class UpdateSceneRequest(BaseModel):
    name: Optional[str] = None
    transition_type: Optional[str] = None
    duration: Optional[int] = None
    values: Optional[List[SceneValueModel]] = None
    group_values: Optional[List[SceneGroupValueModel]] = None
    master_values: Optional[List[SceneMasterValueModel]] = None


class RecallOptions(BaseModel):
    override_transition: Optional[str] = None
    override_duration: Optional[int] = None


class UpdateCurrentRequest(BaseModel):
    universe_ids: Optional[List[int]] = None  # If None, capture all universes
    merge_mode: str = "replace_all"  # "replace_all" or "replace"
    group_ids: Optional[List[int]] = None  # If None, capture all enabled groups
    include_global_master: bool = False  # Include global grandmaster in scene
    include_universe_masters: bool = False  # Include universe grandmasters in scene


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
                "master_value": gv.master_value,
                "color_state_h": gv.color_state_h,
                "color_state_s": gv.color_state_s,
                "color_state_l": gv.color_state_l
            })

    master_values = []
    if hasattr(scene, 'master_values') and scene.master_values:
        for mv in scene.master_values:
            master_values.append({
                "master_type": mv.master_type,
                "universe_id": mv.universe_id,
                "value": mv.value
            })

    return {
        "id": scene.id,
        "name": scene.name,
        "transition_type": scene.transition_type,
        "duration": scene.duration,
        "position": scene.position,
        "values": values,
        "group_values": group_values,
        "master_values": master_values
    }


@router.get("")
async def list_scenes(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all scenes ordered by position, filtered by user's allowed_scenes."""
    scenes = db.query(Scene).options(
        joinedload(Scene.values),
        joinedload(Scene.group_values),
        joinedload(Scene.master_values)
    ).order_by(Scene.position).all()

    # Filter by allowed_scenes if user is not admin and has restrictions
    allowed_scenes = user.get("allowed_scenes")
    if not user.get("is_admin") and allowed_scenes and len(allowed_scenes) > 0:
        scenes = [s for s in scenes if s.id in allowed_scenes]

    return {"scenes": [scene_to_dict(s) for s in scenes]}


class ReorderScenesRequest(BaseModel):
    scene_ids: List[int]


@router.put("/reorder")
async def reorder_scenes(
    request: ReorderScenesRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Reorder scenes by updating their positions."""
    for new_position, scene_id in enumerate(request.scene_ids):
        scene = db.query(Scene).filter(Scene.id == scene_id).first()
        if scene:
            scene.position = new_position
    db.commit()
    await manager.broadcast_scenes_changed()
    return {"status": "reordered", "order": request.scene_ids}


@router.get("/{scene_id}")
async def get_scene(scene_id: int, db: Session = Depends(get_db)):
    """Get a specific scene."""
    scene = db.query(Scene).options(
        joinedload(Scene.values),
        joinedload(Scene.group_values),
        joinedload(Scene.master_values)
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
    # Get max position to place new scene at end
    max_pos = db.query(func.max(Scene.position)).scalar() or -1

    # Create the scene
    scene = Scene(
        name=request.name,
        transition_type=request.transition_type,
        duration=request.duration,
        position=max_pos + 1
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
        # Use get_all_values() to capture actual output values (including group contributions)
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

    # Capture current group master values (filtered by group_ids if provided)
    groups_query = db.query(Group).filter(Group.enabled == True)
    if request.group_ids is not None:
        groups_query = groups_query.filter(Group.id.in_(request.group_ids))
    groups = groups_query.all()
    for group in groups:
        # Get actual master value from runtime (most reliable source)
        runtime_group = dmx_interface.get_group(group.id)
        if runtime_group:
            actual_master_value = runtime_group.get("master_value", 0)
        elif group.master_universe and group.master_channel:
            actual_master_value = dmx_interface.get_channel(group.master_universe, group.master_channel)
        else:
            actual_master_value = group.master_value
        scene_group_value = SceneGroupValue(
            scene_id=scene.id,
            group_id=group.id,
            master_value=actual_master_value,
            color_state_h=group.color_state_h,
            color_state_s=group.color_state_s,
            color_state_l=group.color_state_l
        )
        db.add(scene_group_value)

    # Capture grandmaster values if requested
    if request.include_global_master:
        global_master = dmx_interface.get_global_grandmaster()
        scene_master_value = SceneMasterValue(
            scene_id=scene.id,
            master_type="global",
            universe_id=None,
            value=global_master
        )
        db.add(scene_master_value)

    if request.include_universe_masters:
        # Capture universe grandmasters only for selected universes (none if no selection)
        universes_to_capture = request.universe_ids if request.universe_ids else []
        for uid in universes_to_capture:
            if uid in dmx_interface.universes:
                universe_master = dmx_interface.get_universe_grandmaster(uid)
                scene_master_value = SceneMasterValue(
                    scene_id=scene.id,
                    master_type="universe",
                    universe_id=uid,
                    value=universe_master
                )
                db.add(scene_master_value)

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

    if request.group_values is not None:
        # Delete existing group values
        db.query(SceneGroupValue).filter(SceneGroupValue.scene_id == scene_id).delete()
        # Add new group values
        for gv in request.group_values:
            scene_group_value = SceneGroupValue(
                scene_id=scene.id,
                group_id=gv.group_id,
                master_value=gv.master_value,
                color_state_h=gv.color_state_h,
                color_state_s=gv.color_state_s,
                color_state_l=gv.color_state_l
            )
            db.add(scene_group_value)

    if request.master_values is not None:
        # Delete existing master values
        db.query(SceneMasterValue).filter(SceneMasterValue.scene_id == scene_id).delete()
        # Add new master values
        for mv in request.master_values:
            scene_master_value = SceneMasterValue(
                scene_id=scene.id,
                master_type=mv.master_type,
                universe_id=mv.universe_id,
                value=mv.value
            )
            db.add(scene_master_value)

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
    group_ids = request.group_ids if request else None

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
    # Use get_all_values() to capture actual output values (including group contributions)
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
    groups_query = db.query(Group).filter(Group.enabled == True)
    if group_ids is not None:
        groups_query = groups_query.filter(Group.id.in_(group_ids))
    groups = groups_query.all()
    for group in groups:
        # Get actual master value from runtime (most reliable source)
        runtime_group = dmx_interface.get_group(group.id)
        if runtime_group:
            actual_master_value = runtime_group.get("master_value", 0)
        elif group.master_universe and group.master_channel:
            actual_master_value = dmx_interface.get_channel(group.master_universe, group.master_channel)
        else:
            actual_master_value = group.master_value
        scene_group_value = SceneGroupValue(
            scene_id=scene.id,
            group_id=group.id,
            master_value=actual_master_value,
            color_state_h=group.color_state_h,
            color_state_s=group.color_state_s,
            color_state_l=group.color_state_l
        )
        db.add(scene_group_value)

    # Capture grandmaster values if requested
    include_global_master = request.include_global_master if request else False
    include_universe_masters = request.include_universe_masters if request else False

    # Delete existing master values before adding new ones
    if include_global_master or include_universe_masters:
        db.query(SceneMasterValue).filter(SceneMasterValue.scene_id == scene_id).delete()

    if include_global_master:
        global_master = dmx_interface.get_global_grandmaster()
        scene_master_value = SceneMasterValue(
            scene_id=scene.id,
            master_type="global",
            universe_id=None,
            value=global_master
        )
        db.add(scene_master_value)

    if include_universe_masters:
        # Capture universe grandmasters only for selected universes (none if no selection)
        master_universes = universe_ids if universe_ids else []
        for uid in master_universes:
            if uid in dmx_interface.universes:
                universe_master = dmx_interface.get_universe_grandmaster(uid)
                scene_master_value = SceneMasterValue(
                    scene_id=scene.id,
                    master_type="universe",
                    universe_id=uid,
                    value=universe_master
                )
                db.add(scene_master_value)

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
    duration_sec = duration_ms / 1000
    start_time = time.monotonic()

    for step in range(1, steps + 1):
        progress = step / steps

        for uid, channels in target_values.items():
            new_values = {}
            # Only iterate over channels that are in target_values (respects input filtering)
            for channel, target_value in channels.items():
                start = start_values[uid].get(channel, 0)
                new_values[channel] = int(start + (target_value - start) * progress)

            # Use silent mode during fade - no per-channel callbacks
            dmx_interface.set_channels_silent(uid, new_values)

        # Calculate how long we should have elapsed by now
        target_elapsed = (step / steps) * duration_sec
        actual_elapsed = time.monotonic() - start_time
        sleep_time = max(0, target_elapsed - actual_elapsed)

        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

    # Send final values notification after fade completes
    for uid in target_values.keys():
        await manager.broadcast({
            "type": "values",
            "data": {
                "universe_id": uid,
                "values": dmx_interface.get_all_values(uid)
            }
        })


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
        joinedload(Scene.group_values),
        joinedload(Scene.master_values)
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

    # Filter out input-controlled channels if input is active (unless bypass is ON)
    filtered_values: Dict[int, Dict[int, int]] = {}
    bypass_active = dmx_interface.get_input_bypass()

    for uid, channels in target_values.items():
        if bypass_active:
            # Bypass ON - allow all scene values
            filtered_values[uid] = channels
        elif uid in dmx_interface.inputs:
            # Input active, bypass OFF - filter out input-controlled channels
            controlled = dmx_interface.get_input_controlled_channels(uid)

            # Also filter out indirectly controlled channels (group members whose master is input-controlled)
            for group_id, group in dmx_interface._groups.items():
                if not group.get("enabled"):
                    continue
                master_universe = group.get("master_universe")
                master_channel = group.get("master_channel")
                if master_universe and master_channel:
                    # Check if this group's master is input-controlled
                    master_controlled = dmx_interface.get_input_controlled_channels(master_universe)
                    if master_channel in master_controlled:
                        # Add all member channels in this universe to controlled set
                        for member in group.get("members", []):
                            if member["universe_id"] == uid:
                                controlled.add(member["channel"])

            filtered_values[uid] = {
                ch: val for ch, val in channels.items()
                if ch not in controlled
            }
        else:
            # No active input - use all channels
            filtered_values[uid] = channels

    # Flash indicators immediately to show which channels will change
    for uid, channels in filtered_values.items():
        if channels:
            current_values = dmx_interface.get_all_values(uid)
            preview_values = current_values.copy()
            for ch, val in channels.items():
                preview_values[ch - 1] = val
            await manager.broadcast({
                "type": "values",
                "data": {
                    "universe_id": uid,
                    "values": preview_values
                }
            })

    # Apply transition
    if transition_type == "instant" or duration <= 0:
        for uid, channels in filtered_values.items():
            if channels:  # Only apply if there are channels to set
                dmx_interface.set_channels(uid, channels)
    elif transition_type == "fade":
        await apply_fade(filtered_values, duration, crossfade=False)
    elif transition_type == "crossfade":
        await apply_fade(filtered_values, duration, crossfade=True)

    # Restore group master values
    # Note: We only restore the master value, NOT apply to member channels
    # The scene already has the correct channel values - applying groups would overwrite them
    restored_groups = []  # Track which groups were restored
    if scene.group_values:
        for gv in scene.group_values:
            # Update database
            group = db.query(Group).filter(Group.id == gv.group_id).first()
            if group:
                # Check if this group's master is input-controlled (unless bypass is active)
                skip_restore = False
                if not bypass_active and group.master_universe and group.master_channel:
                    master_controlled = dmx_interface.get_input_controlled_channels(group.master_universe)
                    if group.master_channel in master_controlled:
                        skip_restore = True

                if skip_restore:
                    # Don't restore - master is controlled by input
                    continue

                restored_groups.append(gv.group_id)
                group.master_value = gv.master_value

                # Restore color_state for color_mixer groups
                if gv.color_state_h is not None:
                    group.color_state_h = gv.color_state_h
                    group.color_state_s = gv.color_state_s
                    group.color_state_l = gv.color_state_l

                # Update runtime group
                if gv.group_id in dmx_interface._groups:
                    dmx_interface._groups[gv.group_id]["master_value"] = gv.master_value
                    # Restore color_state to runtime group
                    if gv.color_state_h is not None:
                        dmx_interface._groups[gv.group_id]["color_state"] = {
                            "h": gv.color_state_h,
                            "s": gv.color_state_s,
                            "l": gv.color_state_l
                        }
                    # Re-apply color_mixer groups to update output channels with restored color
                    if group.mode == "color_mixer":
                        dmx_interface._apply_group(gv.group_id, gv.master_value)

                # If physical master, set the channel but skip group member application
                if group.master_universe and group.master_channel:
                    dmx_interface.set_channel(group.master_universe, group.master_channel, gv.master_value, source="scene_recall", _from_group=True)
                # For virtual masters, we've already updated the runtime value above
        db.commit()

        # Broadcast updated universe values for groups with physical masters (DMX Input Link)
        affected_universes = set()
        for gv in scene.group_values:
            if gv.group_id in restored_groups:
                group = db.query(Group).filter(Group.id == gv.group_id).first()
                if group and group.master_universe:
                    affected_universes.add(group.master_universe)

        for uid in affected_universes:
            values = dmx_interface.get_all_values(uid)
            await manager.broadcast({
                "type": "values",
                "data": {"universe_id": uid, "values": values}
            })

        # Broadcast group value changes to update UI (only for restored groups)
        for gv in scene.group_values:
            if gv.group_id in restored_groups:
                await manager.broadcast_group_value_changed(gv.group_id, gv.master_value)

        # Broadcast groups_changed so frontend reloads color_state
        await manager.broadcast_groups_changed()

    # Restore grandmaster values (unless input bypass would block them)
    if scene.master_values:
        for mv in scene.master_values:
            if mv.master_type == "global":
                dmx_interface.set_global_grandmaster(mv.value)
                # Broadcast grandmaster change
                await manager.broadcast({
                    "type": "grandmaster_changed",
                    "data": {"type": "global", "value": mv.value}
                })
            elif mv.master_type == "universe" and mv.universe_id is not None:
                dmx_interface.set_universe_grandmaster(mv.universe_id, mv.value)
                # Broadcast grandmaster change
                await manager.broadcast({
                    "type": "grandmaster_changed",
                    "data": {"type": "universe", "universe_id": mv.universe_id, "value": mv.value}
                })

    # Update active scene and send MIDI feedback
    dmx_interface.set_active_scene(scene_id)

    # Broadcast active scene change to all WebSocket clients
    await manager.broadcast({
        "type": "active_scene_changed",
        "data": {"scene_id": scene_id}
    })

    return {
        "status": "recalled",
        "scene_id": scene_id,
        "transition": transition_type,
        "duration": duration
    }
