"""Groups/Masters API endpoints for controlling multiple channels with a single master."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db, Group, GroupMember, GroupGrid, ParkedChannel
from ..auth import get_current_user
from ..dmx_interface import dmx_interface
from ..websocket_manager import manager

router = APIRouter()


class GroupMemberRequest(BaseModel):
    # For channel targets
    universe_id: Optional[int] = None
    channel: Optional[int] = None
    base_value: int = 255
    # Virtual target support
    target_type: str = "channel"  # "channel", "universe_master", "global_master"
    target_universe_id: Optional[int] = None  # For universe_master target
    # Color mixer support
    color_role: Optional[str] = None  # red, green, blue, white, amber, uv, lime, cyan, magenta, yellow, orange


class BulkMemberRequest(BaseModel):
    members: List[GroupMemberRequest]


class GroupCreateRequest(BaseModel):
    name: str
    mode: str = "proportional"  # "proportional" or "follow"
    master_universe: Optional[int] = None  # Optional - for DMX-linked masters
    master_channel: Optional[int] = None   # Optional - for DMX-linked masters
    enabled: bool = True
    color: Optional[str] = None  # Custom fader color (hex)
    grid_id: Optional[int] = None  # Which grid this group belongs to
    members: List[GroupMemberRequest] = []


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    master_universe: Optional[int] = None
    master_channel: Optional[int] = None
    enabled: Optional[bool] = None
    color: Optional[str] = None
    grid_id: Optional[int] = None  # Move group to different grid


class GroupGridCreateRequest(BaseModel):
    name: str
    color: Optional[str] = None


class GroupGridUpdateRequest(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class ReorderGridsRequest(BaseModel):
    grid_ids: List[int]


def group_to_dict(group: Group) -> dict:
    """Convert a Group model to dictionary."""
    return {
        "id": group.id,
        "name": group.name,
        "mode": group.mode,
        "master_universe": group.master_universe,
        "master_channel": group.master_channel,
        "master_value": group.master_value,
        "enabled": group.enabled,
        "color": group.color,
        "color_state": {
            "h": group.color_state_h or 0,
            "s": group.color_state_s or 0,
            "l": group.color_state_l if group.color_state_l is not None else 100
        },
        "position": group.position,
        "grid_id": group.grid_id,
        "members": [
            {
                "id": m.id,
                "universe_id": m.universe_id,
                "channel": m.channel,
                "base_value": m.base_value,
                "target_type": m.target_type or "channel",
                "target_universe_id": m.target_universe_id,
                "color_role": m.color_role
            }
            for m in group.members
        ]
    }


def grid_to_dict(grid: GroupGrid, include_groups: bool = True) -> dict:
    """Convert a GroupGrid model to dictionary."""
    result = {
        "id": grid.id,
        "name": grid.name,
        "position": grid.position,
        "color": grid.color,
    }
    if include_groups:
        result["groups"] = [group_to_dict(g) for g in sorted(grid.groups, key=lambda x: x.position)]
    return result


@router.get("")
async def list_groups(db: Session = Depends(get_db)):
    """Get all groups ordered by position."""
    groups = db.query(Group).order_by(Group.position).all()
    return {"groups": [group_to_dict(g) for g in groups]}


# ========== Grid Endpoints ==========

@router.get("/grids")
async def list_grids(db: Session = Depends(get_db)):
    """Get all group grids with their groups."""
    grids = db.query(GroupGrid).order_by(GroupGrid.position).all()
    return {"grids": [grid_to_dict(g) for g in grids]}


@router.post("/grids")
async def create_grid(
    request: GroupGridCreateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new group grid."""
    # Get max position to place new grid at end
    max_pos = db.query(func.max(GroupGrid.position)).scalar() or -1

    grid = GroupGrid(
        name=request.name,
        color=request.color,
        position=max_pos + 1
    )
    db.add(grid)
    db.commit()
    db.refresh(grid)

    await manager.broadcast_grids_changed()
    return grid_to_dict(grid)


@router.put("/grids/reorder")
async def reorder_grids(
    request: ReorderGridsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Reorder grids by updating their positions."""
    for new_position, grid_id in enumerate(request.grid_ids):
        grid = db.query(GroupGrid).filter(GroupGrid.id == grid_id).first()
        if grid:
            grid.position = new_position
    db.commit()
    await manager.broadcast_grids_changed()
    return {"status": "reordered", "order": request.grid_ids}


@router.get("/grids/{grid_id}")
async def get_grid(grid_id: int, db: Session = Depends(get_db)):
    """Get a specific grid with its groups."""
    grid = db.query(GroupGrid).filter(GroupGrid.id == grid_id).first()
    if not grid:
        raise HTTPException(status_code=404, detail="Grid not found")
    return grid_to_dict(grid)


@router.put("/grids/{grid_id}")
async def update_grid(
    grid_id: int,
    request: GroupGridUpdateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a grid's properties."""
    grid = db.query(GroupGrid).filter(GroupGrid.id == grid_id).first()
    if not grid:
        raise HTTPException(status_code=404, detail="Grid not found")

    if request.name is not None:
        grid.name = request.name

    request_data = request.model_dump(exclude_unset=True)
    if 'color' in request_data:
        grid.color = request.color

    db.commit()
    db.refresh(grid)

    await manager.broadcast_grids_changed()
    return grid_to_dict(grid)


@router.delete("/grids/{grid_id}")
async def delete_grid(
    grid_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a grid. Groups in this grid are moved to the first remaining grid."""
    grid = db.query(GroupGrid).filter(GroupGrid.id == grid_id).first()
    if not grid:
        raise HTTPException(status_code=404, detail="Grid not found")

    # Find another grid to move groups to (or create default if this is the last one)
    other_grid = db.query(GroupGrid).filter(GroupGrid.id != grid_id).order_by(GroupGrid.position).first()
    if not other_grid:
        # Create a default grid if deleting the last one
        other_grid = GroupGrid(name="Groups", position=0)
        db.add(other_grid)
        db.commit()
        db.refresh(other_grid)

    # Move all groups from the deleted grid to the other grid
    for group in grid.groups:
        group.grid_id = other_grid.id
    db.commit()

    # Delete the grid
    db.delete(grid)
    db.commit()

    await manager.broadcast_grids_changed()
    await manager.broadcast_groups_changed()
    return {"status": "deleted", "grid_id": grid_id, "groups_moved_to": other_grid.id}


@router.get("/runtime-values")
async def get_runtime_group_values():
    """Get current runtime group values from dmx_interface."""
    values = {}
    for group_id, group_data in dmx_interface._groups.items():
        values[group_id] = group_data.get("master_value", 0)
    return {"values": values}


class ReorderGroupsRequest(BaseModel):
    group_ids: List[int]


@router.put("/reorder")
async def reorder_groups(
    request: ReorderGroupsRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Reorder groups by updating their positions."""
    for new_position, group_id in enumerate(request.group_ids):
        group = db.query(Group).filter(Group.id == group_id).first()
        if group:
            group.position = new_position
    db.commit()
    await manager.broadcast_groups_changed()
    return {"status": "reordered", "order": request.group_ids}


@router.post("")
async def create_group(
    request: GroupCreateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new group."""
    # Get max position within the target grid (or globally if no grid specified)
    if request.grid_id:
        max_pos = db.query(func.max(Group.position)).filter(Group.grid_id == request.grid_id).scalar() or -1
    else:
        max_pos = db.query(func.max(Group.position)).scalar() or -1

    # If no grid_id specified, use the first grid (or create default)
    grid_id = request.grid_id
    if not grid_id:
        first_grid = db.query(GroupGrid).order_by(GroupGrid.position).first()
        if first_grid:
            grid_id = first_grid.id
        else:
            # Create default grid
            default_grid = GroupGrid(name="Groups", position=0)
            db.add(default_grid)
            db.commit()
            db.refresh(default_grid)
            grid_id = default_grid.id

    # Create the group
    group = Group(
        name=request.name,
        mode=request.mode,
        master_universe=request.master_universe,
        master_channel=request.master_channel,
        enabled=request.enabled,
        color=request.color,
        grid_id=grid_id,
        position=max_pos + 1
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    # Add members
    for member_req in request.members:
        member = GroupMember(
            group_id=group.id,
            universe_id=member_req.universe_id,
            channel=member_req.channel,
            base_value=member_req.base_value,
            target_type=member_req.target_type,
            target_universe_id=member_req.target_universe_id,
            color_role=member_req.color_role
        )
        db.add(member)

    db.commit()
    db.refresh(group)

    # Update runtime
    dmx_interface.add_group(group_to_dict(group))

    # Broadcast to all clients
    await manager.broadcast_groups_changed()

    return group_to_dict(group)


@router.get("/{group_id}")
async def get_group(group_id: int, db: Session = Depends(get_db)):
    """Get a specific group."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group_to_dict(group)


@router.put("/{group_id}")
async def update_group(
    group_id: int,
    request: GroupUpdateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a group's properties."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if request.name is not None:
        group.name = request.name
    if request.mode is not None:
        group.mode = request.mode
    if request.enabled is not None:
        group.enabled = request.enabled

    # Handle color, master_universe, master_channel, and grid_id specially to allow clearing them
    # These are explicitly set (including to null) via the request body
    # We check if the key exists in the raw request data
    request_data = request.model_dump(exclude_unset=True)
    if 'color' in request_data:
        group.color = request.color
    if 'master_universe' in request_data:
        group.master_universe = request.master_universe
    if 'master_channel' in request_data:
        group.master_channel = request.master_channel
    if 'grid_id' in request_data:
        group.grid_id = request.grid_id

    db.commit()
    db.refresh(group)

    # Update runtime
    dmx_interface.update_group(group_to_dict(group))

    # Broadcast to all clients
    await manager.broadcast_groups_changed()
    if 'grid_id' in request_data:
        await manager.broadcast_grids_changed()

    return group_to_dict(group)


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a group."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Remove from runtime
    dmx_interface.remove_group(group_id)

    # Delete from database (cascade deletes members)
    db.delete(group)
    db.commit()

    # Broadcast to all clients
    await manager.broadcast_groups_changed()

    return {"status": "deleted", "group_id": group_id}


@router.post("/{group_id}/members")
async def add_member(
    group_id: int,
    request: GroupMemberRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Add a member to a group."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Check if member already exists - need to account for virtual targets
    if request.target_type == "channel":
        existing = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.target_type == "channel",
            GroupMember.universe_id == request.universe_id,
            GroupMember.channel == request.channel
        ).first()
    elif request.target_type == "universe_master":
        existing = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.target_type == "universe_master",
            GroupMember.target_universe_id == request.target_universe_id
        ).first()
    elif request.target_type == "global_master":
        existing = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.target_type == "global_master"
        ).first()
    else:
        existing = None

    if existing:
        raise HTTPException(status_code=400, detail="Member already exists in group")

    # Add member
    member = GroupMember(
        group_id=group_id,
        universe_id=request.universe_id,
        channel=request.channel,
        base_value=request.base_value,
        target_type=request.target_type,
        target_universe_id=request.target_universe_id,
        color_role=request.color_role
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    db.refresh(group)

    # Update runtime with full group
    dmx_interface.update_group(group_to_dict(group))

    # Broadcast to all clients
    await manager.broadcast_groups_changed()

    return {
        "id": member.id,
        "universe_id": member.universe_id,
        "channel": member.channel,
        "base_value": member.base_value
    }


@router.put("/{group_id}/members/{member_id}")
async def update_member(
    group_id: int,
    member_id: int,
    request: GroupMemberRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a group member's properties."""
    member = db.query(GroupMember).filter(
        GroupMember.id == member_id,
        GroupMember.group_id == group_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Clear effective base for old channel (before updating)
    dmx_interface.clear_group_contribution(group_id, member.universe_id, member.channel)

    member.universe_id = request.universe_id
    member.channel = request.channel
    member.base_value = request.base_value
    member.color_role = request.color_role

    db.commit()
    db.refresh(member)

    # Get full group and update runtime
    group = db.query(Group).filter(Group.id == group_id).first()
    dmx_interface.update_group(group_to_dict(group))

    # Broadcast to all clients
    await manager.broadcast_groups_changed()

    return {
        "id": member.id,
        "universe_id": member.universe_id,
        "channel": member.channel,
        "base_value": member.base_value,
        "color_role": member.color_role
    }


@router.delete("/{group_id}/members/{member_id}")
async def remove_member(
    group_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Remove a member from a group."""
    member = db.query(GroupMember).filter(
        GroupMember.id == member_id,
        GroupMember.group_id == group_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    # Clear effective base for removed member
    dmx_interface.clear_group_contribution(group_id, member.universe_id, member.channel)

    db.delete(member)
    db.commit()

    # Get full group and update runtime
    group = db.query(Group).filter(Group.id == group_id).first()
    dmx_interface.update_group(group_to_dict(group))

    # Broadcast to all clients
    await manager.broadcast_groups_changed()

    return {"status": "deleted", "member_id": member_id}


@router.post("/{group_id}/members/bulk")
async def add_members_bulk(
    group_id: int,
    request: BulkMemberRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Add multiple members to a group in a single operation."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    added = []
    skipped = []

    for member_req in request.members:
        # Check if member already exists - need to account for virtual targets
        if member_req.target_type == "channel":
            existing = db.query(GroupMember).filter(
                GroupMember.group_id == group_id,
                GroupMember.target_type == "channel",
                GroupMember.universe_id == member_req.universe_id,
                GroupMember.channel == member_req.channel
            ).first()
        elif member_req.target_type == "universe_master":
            existing = db.query(GroupMember).filter(
                GroupMember.group_id == group_id,
                GroupMember.target_type == "universe_master",
                GroupMember.target_universe_id == member_req.target_universe_id
            ).first()
        elif member_req.target_type == "global_master":
            existing = db.query(GroupMember).filter(
                GroupMember.group_id == group_id,
                GroupMember.target_type == "global_master"
            ).first()
        else:
            existing = None

        if existing:
            skipped.append({"universe_id": member_req.universe_id, "channel": member_req.channel})
            continue

        # Add member
        member = GroupMember(
            group_id=group_id,
            universe_id=member_req.universe_id,
            channel=member_req.channel,
            base_value=member_req.base_value,
            target_type=member_req.target_type,
            target_universe_id=member_req.target_universe_id,
            color_role=member_req.color_role
        )
        db.add(member)
        added.append({
            "universe_id": member_req.universe_id,
            "channel": member_req.channel,
            "base_value": member_req.base_value,
            "color_role": member_req.color_role
        })

    db.commit()
    db.refresh(group)

    # Update runtime with full group
    dmx_interface.update_group(group_to_dict(group))

    # Broadcast to all clients
    await manager.broadcast_groups_changed()

    return {
        "added": len(added),
        "skipped": len(skipped),
        "added_members": added,
        "skipped_members": skipped
    }


@router.get("/{group_id}/trigger")
async def get_group_master_value(group_id: int, db: Session = Depends(get_db)):
    """Get the current value of a group's master (virtual or DMX-linked)."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # For virtual masters, return stored master_value
    # For DMX-linked masters, return the current channel value
    if group.master_universe and group.master_channel:
        value = dmx_interface.get_channel(group.master_universe, group.master_channel)
    else:
        value = group.master_value

    return {
        "group_id": group_id,
        "master_universe": group.master_universe,
        "master_channel": group.master_channel,
        "value": value
    }


@router.post("/{group_id}/trigger")
async def trigger_group(
    group_id: int,
    value: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Trigger a group by setting its master value (virtual or DMX-linked)."""
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if not 0 <= value <= 255:
        raise HTTPException(status_code=400, detail="Value must be 0-255")

    # Check if group master is input-controlled (unless bypass is active)
    if group.master_universe and group.master_channel:
        if not dmx_interface.get_input_bypass():
            controlled = dmx_interface.get_input_controlled_channels(group.master_universe)
            if group.master_channel in controlled:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change group while its master is controlled by input. Enable Input Bypass to override."
                )

    # Check if any member channel is input-controlled (unless bypass is active)
    members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.target_type == "channel"
    ).all()
    channel_members = [m for m in members if m.universe_id and m.channel]

    if not dmx_interface.get_input_bypass():
        for member in channel_members:
            controlled = dmx_interface.get_input_controlled_channels(member.universe_id)
            if member.channel in controlled:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change group while member channels are controlled by input. Enable Input Bypass to override."
                )

    # Check if all channel members are parked (group is effectively locked)
    if channel_members:
        all_parked = all(
            dmx_interface.is_channel_parked(m.universe_id, m.channel)
            for m in channel_members
        )
        if all_parked:
            raise HTTPException(
                status_code=400,
                detail="Cannot change group while all members are parked"
            )

        # Also check if all members are highlighted
        all_highlighted = all(
            dmx_interface.is_channel_highlighted(m.universe_id, m.channel)
            for m in channel_members
        )
        if all_highlighted:
            raise HTTPException(
                status_code=400,
                detail="Cannot change group while all members are highlighted"
            )

    # Update stored master value for persistence
    group.master_value = value
    db.commit()

    if group.master_universe and group.master_channel:
        # DMX-linked master - set the DMX channel (triggers group via set_channel)
        dmx_interface.set_channel(group.master_universe, group.master_channel, value, source="group_api")
    else:
        # Virtual master - apply group directly
        dmx_interface.apply_group_direct(group_id, value)

    # Broadcast value change to all connected clients
    await manager.broadcast_group_value_changed(group_id, value)

    return {
        "group_id": group_id,
        "master_universe": group.master_universe,
        "master_channel": group.master_channel,
        "value": value
    }


class ColorUpdateRequest(BaseModel):
    h: float  # Hue 0-360
    s: float  # Saturation 0-100
    l: float  # Lightness 0-100


@router.put("/{group_id}/color")
async def update_group_color(
    group_id: int,
    color: ColorUpdateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a color_mixer group's color state (HSL values).

    This triggers immediate recalculation of RGB channel values
    using the stored brightness (master_value).
    """
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if group.mode != "color_mixer":
        raise HTTPException(status_code=400, detail="Group is not a color_mixer")

    # Validate HSL values
    if not (0 <= color.h <= 360):
        raise HTTPException(status_code=400, detail="Hue must be 0-360")
    if not (0 <= color.s <= 100):
        raise HTTPException(status_code=400, detail="Saturation must be 0-100")
    if not (0 <= color.l <= 100):
        raise HTTPException(status_code=400, detail="Lightness must be 0-100")

    # Persist to database
    group.color_state_h = color.h
    group.color_state_s = color.s
    group.color_state_l = color.l
    db.commit()

    # Update color in DMX interface (this also triggers reapply)
    success = dmx_interface.set_group_color(group_id, color.h, color.s, color.l)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update color state")

    return {
        "group_id": group_id,
        "color_state": {"h": color.h, "s": color.s, "l": color.l}
    }


@router.post("/{group_id}/highlight")
async def highlight_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Highlight all channel members of a group (excludes universe/global masters)."""
    if not user.get("can_highlight", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot use highlight mode")
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get all channel members (exclude universe_master and global_master targets)
    members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.target_type == "channel"
    ).all()

    if not members:
        raise HTTPException(status_code=400, detail="Group has no channel members to highlight")

    # Add each channel to highlight
    for member in members:
        if member.universe_id and member.channel:
            dmx_interface.add_to_highlight(member.universe_id, member.channel)

    return {
        "group_id": group_id,
        "highlighted_channels": len(members)
    }


@router.post("/{group_id}/highlight/stop")
async def stop_highlight_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Remove highlight from all channel members of a group."""
    if not user.get("can_highlight", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot use highlight mode")
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get all channel members
    members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.target_type == "channel"
    ).all()

    # Remove each channel from highlight
    for member in members:
        if member.universe_id and member.channel:
            dmx_interface.remove_from_highlight(member.universe_id, member.channel)

    return {
        "group_id": group_id,
        "unhighlighted_channels": len(members)
    }


@router.post("/{group_id}/park")
async def park_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Park all channel members of a group at their current output values."""
    if not user.get("can_park", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot park channels")
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get all channel members
    members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.target_type == "channel"
    ).all()

    if not members:
        raise HTTPException(status_code=400, detail="Group has no channel members to park")

    # Park each channel at its current output value and persist to database
    parked_count = 0
    for member in members:
        if member.universe_id and member.channel:
            # Get current output value for this channel
            current_value = dmx_interface.get_channel(member.universe_id, member.channel)
            dmx_interface.park_channel(member.universe_id, member.channel, current_value)

            # Persist to database
            db.query(ParkedChannel).filter(
                ParkedChannel.universe_id == member.universe_id,
                ParkedChannel.channel == member.channel
            ).delete()
            db.add(ParkedChannel(
                universe_id=member.universe_id,
                channel=member.channel,
                value=current_value
            ))
            parked_count += 1

    db.commit()

    return {
        "group_id": group_id,
        "parked_channels": parked_count
    }


@router.post("/{group_id}/unpark")
async def unpark_group(
    group_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Unpark all channel members of a group."""
    if not user.get("can_park", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot unpark channels")
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get all channel members
    members = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.target_type == "channel"
    ).all()

    # Unpark each channel and remove from database
    unparked_count = 0
    for member in members:
        if member.universe_id and member.channel:
            dmx_interface.unpark_channel(member.universe_id, member.channel)

            # Remove from database
            db.query(ParkedChannel).filter(
                ParkedChannel.universe_id == member.universe_id,
                ParkedChannel.channel == member.channel
            ).delete()
            unparked_count += 1

    db.commit()

    return {
        "group_id": group_id,
        "unparked_channels": unparked_count
    }


class BulkInputLinkRequest(BaseModel):
    group_ids: List[int]
    start_universe: int
    start_channel: int


@router.post("/bulk-input-link")
async def bulk_input_link(
    request: BulkInputLinkRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Assign sequential input links to multiple groups.

    Example: group_ids=[1,2,3], start_universe=1, start_channel=500
    Result: Group 1 → ch 500, Group 2 → ch 501, Group 3 → ch 502
    """
    if not request.group_ids:
        raise HTTPException(status_code=400, detail="No group IDs provided")

    if not 1 <= request.start_channel <= 512:
        raise HTTPException(status_code=400, detail="Start channel must be 1-512")

    # Check if we have enough channels
    end_channel = request.start_channel + len(request.group_ids) - 1
    if end_channel > 512:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough channels: need {len(request.group_ids)} starting at {request.start_channel}, but only {512 - request.start_channel + 1} available"
        )

    updated = []
    not_found = []

    for i, group_id in enumerate(request.group_ids):
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            not_found.append(group_id)
            continue

        channel = request.start_channel + i
        group.master_universe = request.start_universe
        group.master_channel = channel

        updated.append({
            "group_id": group_id,
            "name": group.name,
            "master_universe": request.start_universe,
            "master_channel": channel
        })

    db.commit()

    # Update runtime for all updated groups
    for item in updated:
        group = db.query(Group).filter(Group.id == item["group_id"]).first()
        if group:
            dmx_interface.update_group(group_to_dict(group))

    # Broadcast changes
    await manager.broadcast_groups_changed()

    return {
        "updated": len(updated),
        "not_found": len(not_found),
        "updated_groups": updated,
        "not_found_ids": not_found
    }
