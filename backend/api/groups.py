"""Groups/Masters API endpoints for controlling multiple channels with a single master."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, Group, GroupMember
from ..auth import get_current_user
from ..dmx_interface import dmx_interface
from ..websocket_manager import manager

router = APIRouter()


class GroupMemberRequest(BaseModel):
    universe_id: int
    channel: int
    base_value: int = 255


class BulkMemberRequest(BaseModel):
    members: List[GroupMemberRequest]


class GroupCreateRequest(BaseModel):
    name: str
    mode: str = "proportional"  # "proportional" or "follow"
    master_universe: Optional[int] = None  # Optional - for DMX-linked masters
    master_channel: Optional[int] = None   # Optional - for DMX-linked masters
    enabled: bool = True
    color: Optional[str] = None  # Custom fader color (hex)
    members: List[GroupMemberRequest] = []


class GroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    master_universe: Optional[int] = None
    master_channel: Optional[int] = None
    enabled: Optional[bool] = None
    color: Optional[str] = None


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


@router.get("")
async def list_groups(db: Session = Depends(get_db)):
    """Get all groups."""
    groups = db.query(Group).all()
    return {"groups": [group_to_dict(g) for g in groups]}


@router.post("")
async def create_group(
    request: GroupCreateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new group."""
    # Create the group
    group = Group(
        name=request.name,
        mode=request.mode,
        master_universe=request.master_universe,
        master_channel=request.master_channel,
        enabled=request.enabled,
        color=request.color
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
            base_value=member_req.base_value
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

    # Handle color, master_universe and master_channel specially to allow clearing them
    # These are explicitly set (including to null) via the request body
    # We check if the key exists in the raw request data
    request_data = request.model_dump(exclude_unset=True)
    if 'color' in request_data:
        group.color = request.color
    if 'master_universe' in request_data:
        group.master_universe = request.master_universe
    if 'master_channel' in request_data:
        group.master_channel = request.master_channel

    db.commit()
    db.refresh(group)

    # Update runtime
    dmx_interface.update_group(group_to_dict(group))

    # Broadcast to all clients
    await manager.broadcast_groups_changed()

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

    # Check if member already exists
    existing = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.universe_id == request.universe_id,
        GroupMember.channel == request.channel
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Member already exists in group")

    # Add member
    member = GroupMember(
        group_id=group_id,
        universe_id=request.universe_id,
        channel=request.channel,
        base_value=request.base_value
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
        "base_value": member.base_value
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
        # Check if member already exists
        existing = db.query(GroupMember).filter(
            GroupMember.group_id == group_id,
            GroupMember.universe_id == member_req.universe_id,
            GroupMember.channel == member_req.channel
        ).first()

        if existing:
            skipped.append({"universe_id": member_req.universe_id, "channel": member_req.channel})
            continue

        # Add member
        member = GroupMember(
            group_id=group_id,
            universe_id=member_req.universe_id,
            channel=member_req.channel,
            base_value=member_req.base_value
        )
        db.add(member)
        added.append({
            "universe_id": member_req.universe_id,
            "channel": member_req.channel,
            "base_value": member_req.base_value
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
