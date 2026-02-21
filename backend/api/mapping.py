"""Channel mapping API endpoints.

Custom Channel Mapping System
=============================

This module provides API endpoints for configuring custom input-to-output
channel mappings. Mappings allow routing any input channel to any output
channel, including across different universes.

How Mapping Works
-----------------

When mapping is enabled, input DMX values are routed according to the mapping
configuration before being sent to output:

1. **Mapped Source Channels**: If an input channel has a mapping defined,
   its value is sent ONLY to the mapped destination(s). It does NOT also
   pass through 1:1 to its original channel number.

   Example: If Input Ch1 -> Output Ch7 is defined:
   - Input Ch1 value (say 200) goes to Output Ch7
   - Output Ch1 gets 0 (or local fader value), NOT 200
   - Input Ch1 is "consumed" by the mapping

2. **One-to-Many Mapping**: A single source channel can map to multiple
   destinations. Each destination receives the same value.

3. **Mapped Destination Protection**: When a channel is a mapped destination,
   unmapped input channels cannot overwrite it.

   Example: If Ch1 -> Ch7 is defined:
   - Input Ch7 is BLOCKED because Ch7 is already a mapped destination
   - This prevents Input Ch7 from conflicting with the mapped Ch1 value

Unmapped Channel Behavior
-------------------------

The `unmapped_behavior` setting controls what happens to input channels
that have NO mapping defined:

- **"passthrough"** (default): Unmapped channels pass through 1:1 to the
  same channel number. However, if that channel is already a mapped
  destination, the unmapped input is blocked.

- **"ignore"**: Unmapped channels are ignored entirely. Only explicitly
  mapped source channels produce output.

Cross-Universe Mapping
----------------------

Mappings can route input from one universe to output on a different universe.
Example: Universe 1 Input Ch1 -> Universe 2 Output Ch7

HTP/LTP Merge Modes
-------------------

After mapping is applied, the HTP or LTP merge mode combines mapped input
with local fader values. Merge mode is configured per-universe in I/O settings.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, ChannelMapping
from ..auth import get_current_user
from ..dmx_interface import dmx_interface

router = APIRouter()


class ChannelMappingEntry(BaseModel):
    src_universe: int
    src_channel: int  # 1-512
    dst_universe: Optional[int] = None  # For channel targets
    dst_channel: Optional[int] = None   # For channel targets (1-512)
    dst_target_type: str = "channel"    # "channel", "universe_master", "global_master"
    dst_target_universe_id: Optional[int] = None  # For universe_master target


class ChannelMappingConfig(BaseModel):
    name: str
    enabled: bool = False
    unmapped_behavior: str = "passthrough"  # "passthrough" or "ignore"
    mappings: List[ChannelMappingEntry]


class BulkMappingRequest(BaseModel):
    src_universe: int
    src_start: int  # 1-512
    src_end: int  # 1-512
    dst_universe: int
    dst_start: int  # 1-512


def mapping_to_dict(mapping: ChannelMapping) -> Optional[dict]:
    """Convert a ChannelMapping model to dictionary."""
    if not mapping:
        return None
    return {
        "id": mapping.id,
        "name": mapping.name,
        "enabled": mapping.enabled,
        "unmapped_behavior": mapping.unmapped_behavior,
        "mappings": mapping.mappings_json.get("mappings", []) if mapping.mappings_json else []
    }


def apply_mapping_to_runtime(mapping: ChannelMapping) -> None:
    """Apply a mapping configuration to the DMX interface."""
    import logging
    logger = logging.getLogger(__name__)
    mappings_data = mapping.mappings_json.get("mappings", []) if mapping.mappings_json else []
    logger.info(f"apply_mapping_to_runtime: name={mapping.name}, unmapped_behavior={mapping.unmapped_behavior}, mappings_count={len(mappings_data)}")
    dmx_interface.set_channel_mapping(mappings_data, mapping.unmapped_behavior)


@router.get("")
async def get_mappings(db: Session = Depends(get_db)):
    """Get all channel mapping configurations.

    Returns a list of all saved mapping configs plus the current runtime status.
    Only one mapping can be enabled at a time.
    """
    mappings = db.query(ChannelMapping).all()
    return {
        "mappings": [mapping_to_dict(m) for m in mappings],
        "status": dmx_interface.get_channel_mapping_status()
    }


@router.get("/active")
async def get_active_mapping(db: Session = Depends(get_db)):
    """Get the currently active mapping configuration."""
    mapping = db.query(ChannelMapping).filter(ChannelMapping.enabled == True).first()
    return {
        "mapping": mapping_to_dict(mapping),
        "status": dmx_interface.get_channel_mapping_status()
    }


@router.get("/{mapping_id}")
async def get_mapping(mapping_id: int, db: Session = Depends(get_db)):
    """Get a specific mapping configuration."""
    mapping = db.query(ChannelMapping).filter(ChannelMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return mapping_to_dict(mapping)


@router.post("")
async def create_mapping(
    config: ChannelMappingConfig,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new channel mapping configuration.

    Args:
        config.name: Display name for this mapping config
        config.enabled: If True, enables this mapping (disables all others)
        config.unmapped_behavior: "passthrough" or "ignore"
            - passthrough: Unmapped input channels pass 1:1 to same output channel
              (unless that channel is already a mapped destination)
            - ignore: Unmapped input channels are discarded (output = 0)
        config.mappings: List of channel mappings, each with:
            - src_universe: Source universe ID
            - src_channel: Source channel (1-512)
            - dst_universe: Destination universe ID
            - dst_channel: Destination channel (1-512)

    Note: Mapped source channels do NOT pass through 1:1. If you map Ch1->Ch7,
    Input Ch1 only goes to Output Ch7, not also to Output Ch1.
    """
    # Validate mappings
    for m in config.mappings:
        if not (1 <= m.src_channel <= 512):
            raise HTTPException(status_code=400, detail="Source channel must be between 1 and 512")
        # Validate based on target type
        if m.dst_target_type == "channel":
            if m.dst_channel is None or not (1 <= m.dst_channel <= 512):
                raise HTTPException(status_code=400, detail="Destination channel must be between 1 and 512 for channel targets")
        elif m.dst_target_type == "universe_master":
            if m.dst_target_universe_id is None:
                raise HTTPException(status_code=400, detail="Universe ID required for universe_master target")
        elif m.dst_target_type == "global_master":
            pass  # No additional params needed
        else:
            raise HTTPException(status_code=400, detail=f"Invalid target type: {m.dst_target_type}")

    # If enabling this mapping, disable all others
    if config.enabled:
        db.query(ChannelMapping).update({ChannelMapping.enabled: False})

    mapping = ChannelMapping(
        name=config.name,
        enabled=config.enabled,
        unmapped_behavior=config.unmapped_behavior,
        mappings_json={"mappings": [m.dict() for m in config.mappings]}
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    if config.enabled:
        apply_mapping_to_runtime(mapping)

    return mapping_to_dict(mapping)


@router.put("/{mapping_id}")
async def update_mapping(
    mapping_id: int,
    config: ChannelMappingConfig,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a channel mapping configuration."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"=== UPDATE MAPPING START ===")
    logger.info(f"update_mapping called: id={mapping_id}, enabled={config.enabled}, unmapped_behavior={config.unmapped_behavior}")
    logger.info(f"Config object: name={config.name}, mappings_count={len(config.mappings)}")

    mapping = db.query(ChannelMapping).filter(ChannelMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # Validate mappings
    for m in config.mappings:
        if not (1 <= m.src_channel <= 512):
            raise HTTPException(status_code=400, detail="Source channel must be between 1 and 512")
        # Validate based on target type
        if m.dst_target_type == "channel":
            if m.dst_channel is None or not (1 <= m.dst_channel <= 512):
                raise HTTPException(status_code=400, detail="Destination channel must be between 1 and 512 for channel targets")
        elif m.dst_target_type == "universe_master":
            if m.dst_target_universe_id is None:
                raise HTTPException(status_code=400, detail="Universe ID required for universe_master target")
        elif m.dst_target_type == "global_master":
            pass  # No additional params needed
        else:
            raise HTTPException(status_code=400, detail=f"Invalid target type: {m.dst_target_type}")

    # If enabling this mapping, disable all others
    if config.enabled and not mapping.enabled:
        db.query(ChannelMapping).filter(ChannelMapping.id != mapping_id).update({ChannelMapping.enabled: False})

    mapping.name = config.name
    mapping.enabled = config.enabled
    mapping.unmapped_behavior = config.unmapped_behavior
    mapping.mappings_json = {"mappings": [m.dict() for m in config.mappings]}
    db.commit()
    db.refresh(mapping)

    if config.enabled:
        logger.info(f"Mapping is enabled, applying to runtime: unmapped_behavior={mapping.unmapped_behavior}")
        apply_mapping_to_runtime(mapping)
        logger.info(f"Runtime status after apply: {dmx_interface.get_channel_mapping_status()}")
    else:
        # Check if any other mapping is enabled
        other_enabled = db.query(ChannelMapping).filter(ChannelMapping.enabled == True).first()
        if other_enabled:
            apply_mapping_to_runtime(other_enabled)
        else:
            logger.info("No enabled mapping, clearing runtime mapping")
            dmx_interface.set_channel_mapping([], "passthrough")

    return mapping_to_dict(mapping)


@router.delete("/{mapping_id}")
async def delete_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a channel mapping configuration."""
    mapping = db.query(ChannelMapping).filter(ChannelMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    was_enabled = mapping.enabled
    db.delete(mapping)
    db.commit()

    # If the deleted mapping was enabled, clear runtime mapping
    if was_enabled:
        dmx_interface.set_channel_mapping([], "passthrough")

    return {"status": "deleted", "mapping_id": mapping_id}


@router.post("/{mapping_id}/enable")
async def enable_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Enable a specific mapping (disables others)."""
    mapping = db.query(ChannelMapping).filter(ChannelMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    # Disable all other mappings
    db.query(ChannelMapping).update({ChannelMapping.enabled: False})

    mapping.enabled = True
    db.commit()

    apply_mapping_to_runtime(mapping)
    return {"status": "enabled", "mapping_id": mapping_id}


@router.post("/disable")
async def disable_all_mappings(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Disable all channel mappings (revert to 1:1 passthrough).

    When disabled, input channels pass through 1:1 to output without any
    remapping. The passthrough mode (off/view_only/faders_output) still
    applies from the I/O settings.
    """
    db.query(ChannelMapping).update({ChannelMapping.enabled: False})
    db.commit()

    dmx_interface.set_channel_mapping([], "passthrough")
    return {"status": "disabled"}


@router.post("/sync")
async def sync_mapping_to_runtime(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Force sync the active mapping from database to runtime.

    Use this if the runtime state doesn't match the database (e.g., after
    direct database edits or if there was a sync issue).
    """
    active_mapping = db.query(ChannelMapping).filter(ChannelMapping.enabled == True).first()
    if active_mapping:
        apply_mapping_to_runtime(active_mapping)
        return {
            "status": "synced",
            "mapping_id": active_mapping.id,
            "unmapped_behavior": active_mapping.unmapped_behavior
        }
    else:
        dmx_interface.set_channel_mapping([], "passthrough")
        return {"status": "no_active_mapping"}


@router.post("/bulk")
async def generate_bulk_mapping(bulk: BulkMappingRequest):
    """Generate bulk range mappings (helper for UI - does not save).

    Creates a contiguous range of channel mappings. For example:
    - src_start=1, src_end=16, dst_start=17
    - Results in: Ch1->Ch17, Ch2->Ch18, ..., Ch16->Ch32

    Returns the mapping entries which can be added to a mapping config.
    """
    # Validate inputs
    if not (1 <= bulk.src_start <= 512) or not (1 <= bulk.src_end <= 512):
        raise HTTPException(status_code=400, detail="Source channels must be between 1 and 512")
    if bulk.src_end < bulk.src_start:
        raise HTTPException(status_code=400, detail="Source end must be >= start")

    range_size = bulk.src_end - bulk.src_start + 1
    dst_end = bulk.dst_start + range_size - 1

    if not (1 <= bulk.dst_start <= 512) or not (1 <= dst_end <= 512):
        raise HTTPException(status_code=400, detail="Destination channels must be between 1 and 512")

    mappings = []
    for i in range(range_size):
        mappings.append({
            "src_universe": bulk.src_universe,
            "src_channel": bulk.src_start + i,
            "dst_universe": bulk.dst_universe,
            "dst_channel": bulk.dst_start + i
        })

    return {"mappings": mappings, "count": len(mappings)}
