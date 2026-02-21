"""Input/Output configuration API endpoints."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db, Universe, UniverseOutput, Patch, Fixture, SceneValue
from ..auth import get_current_user
from ..dmx_interface import dmx_interface
from ..websocket_manager import manager

router = APIRouter()


class InputConfigRequest(BaseModel):
    input_type: str = "none"  # none, artnet_input, sacn_input, midi_input
    input_config: dict = {}
    input_enabled: bool = False
    input_channel_start: Optional[int] = None  # Start of input-controlled channel range
    input_channel_end: Optional[int] = None  # End of input-controlled channel range


class PassthroughConfigRequest(BaseModel):
    # New unified passthrough mode: "off", "view_only", "faders_output"
    passthrough_mode: str = "off"
    merge_mode: str = "htp"  # htp, ltp (only applies when passthrough_mode != "off")
    # Legacy fields for backwards compatibility
    passthrough_enabled: Optional[bool] = None
    passthrough_show_ui: Optional[bool] = None


class UniverseIOConfig(BaseModel):
    # Output settings (legacy - for single output compatibility)
    device_type: Optional[str] = None
    config_json: Optional[dict] = None
    enabled: Optional[bool] = None
    # Input settings
    input_type: Optional[str] = None
    input_config: Optional[dict] = None
    input_enabled: Optional[bool] = None
    # Passthrough settings
    passthrough_enabled: Optional[bool] = None
    passthrough_mode: Optional[str] = None
    passthrough_show_ui: Optional[bool] = None


class OutputConfigRequest(BaseModel):
    device_type: str
    config_json: dict = {}
    enabled: bool = True


def _get_passthrough_mode_dict(universe: Universe) -> dict:
    """Convert universe passthrough settings to new format."""
    # Check if using new passthrough_mode field (stored in passthrough_mode column)
    # or old enabled/show_ui format
    enabled = universe.passthrough_enabled or False
    show_ui = universe.passthrough_show_ui or False
    merge_mode = universe.passthrough_mode or "htp"

    # Determine passthrough_mode from old fields
    if not enabled and not show_ui:
        passthrough_mode = "off"
    elif show_ui and not enabled:
        passthrough_mode = "view_only"
    elif enabled and show_ui:
        passthrough_mode = "faders_output"
    elif enabled and not show_ui:
        passthrough_mode = "output_only"
    else:
        passthrough_mode = "off"

    return {
        "passthrough_mode": passthrough_mode,
        "merge_mode": merge_mode,
        # Legacy fields for backwards compatibility
        "enabled": enabled,
        "mode": merge_mode,
        "show_ui": show_ui
    }


def universe_io_to_dict(universe: Universe, db: Session = None) -> dict:
    """Convert a Universe model to I/O dictionary."""
    # Get runtime status for all outputs
    output_statuses = dmx_interface.get_output_status(universe.id) or []
    input_status = dmx_interface.get_input_status(universe.id)

    # Get outputs from database
    outputs_list = []
    if db:
        db_outputs = db.query(UniverseOutput).filter(
            UniverseOutput.universe_id == universe.id
        ).order_by(UniverseOutput.priority).all()

        for i, db_output in enumerate(db_outputs):
            output_dict = {
                "id": db_output.id,
                "device_type": db_output.device_type,
                "config": db_output.config_json or {},
                "enabled": db_output.enabled,
                "priority": db_output.priority,
                "status": output_statuses[i] if i < len(output_statuses) else None
            }
            outputs_list.append(output_dict)

    # Fallback to legacy single output if no outputs in new table
    if not outputs_list:
        outputs_list = [{
            "id": None,  # Legacy output has no ID
            "device_type": universe.device_type,
            "config": universe.config_json or {},
            "enabled": universe.enabled,
            "priority": 0,
            "status": output_statuses[0] if output_statuses else None
        }]

    return {
        "id": universe.id,
        "label": universe.label,
        "master_fader_color": universe.master_fader_color or "#00bcd4",
        # Multiple outputs
        "outputs": outputs_list,
        # Legacy single output for backwards compatibility
        "output": {
            "device_type": universe.device_type,
            "config": universe.config_json or {},
            "enabled": universe.enabled,
            "status": output_statuses[0] if output_statuses else None
        },
        # Input info
        "input": {
            "input_type": universe.input_type or "none",
            "config": universe.input_config or {},
            "enabled": universe.input_enabled or False,
            "channel_start": universe.input_channel_start or 1,
            "channel_end": universe.input_channel_end or 512,
            "status": input_status
        },
        # Passthrough info - convert old format to new passthrough_mode
        "passthrough": _get_passthrough_mode_dict(universe)
    }


@router.get("")
async def get_io_config(db: Session = Depends(get_db)):
    """Get full I/O configuration for all universes."""
    universes = db.query(Universe).all()
    return {
        "universes": [universe_io_to_dict(u, db) for u in universes],
        "input_protocols": dmx_interface.get_input_protocols(),
        "output_protocols": dmx_interface.get_protocols()
    }


# Input bypass endpoints - must be before /{universe_id} routes
class InputBypassRequest(BaseModel):
    bypass: bool


@router.put("/bypass")
async def set_input_bypass(
    config: InputBypassRequest,
    user: dict = Depends(get_current_user)
):
    """Toggle global input bypass.

    When enabled, DMX input is received but not applied to output.
    This is useful for temporarily taking manual control without
    reconfiguring passthrough settings.
    """
    if not user.get("can_bypass", True):
        raise HTTPException(status_code=403, detail="Permission denied: cannot toggle input bypass")
    dmx_interface.set_input_bypass(config.bypass)

    # Broadcast bypass state to all connected clients
    await manager.broadcast({
        "type": "input_bypass_changed",
        "data": {"bypass": config.bypass}
    })

    return {"bypass": config.bypass}


@router.get("/bypass")
async def get_input_bypass():
    """Get current input bypass state."""
    return {"bypass": dmx_interface.get_input_bypass()}


@router.get("/{universe_id}")
async def get_universe_io(universe_id: int, db: Session = Depends(get_db)):
    """Get I/O configuration for a specific universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")
    return universe_io_to_dict(universe, db)


@router.put("/{universe_id}")
async def update_universe_io(
    universe_id: int,
    config: UniverseIOConfig,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update I/O configuration for a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    # Track what changed
    output_changed = False
    input_changed = False

    # Update output settings
    if config.device_type is not None:
        universe.device_type = config.device_type
        output_changed = True
    if config.config_json is not None:
        universe.config_json = config.config_json
        output_changed = True
    if config.enabled is not None:
        universe.enabled = config.enabled
        output_changed = True

    # Update input settings
    if config.input_type is not None:
        universe.input_type = config.input_type
        input_changed = True
    if config.input_config is not None:
        universe.input_config = config.input_config
        input_changed = True
    if config.input_enabled is not None:
        universe.input_enabled = config.input_enabled
        input_changed = True

    # Update passthrough settings
    if config.passthrough_enabled is not None:
        universe.passthrough_enabled = config.passthrough_enabled
    if config.passthrough_mode is not None:
        universe.passthrough_mode = config.passthrough_mode
    if config.passthrough_show_ui is not None:
        universe.passthrough_show_ui = config.passthrough_show_ui

    db.commit()
    db.refresh(universe)

    # Apply changes to runtime
    if output_changed and universe.enabled:
        await dmx_interface.add_universe(
            universe.id,
            device_type=universe.device_type,
            config=universe.config_json or {}
        )

    if input_changed or config.passthrough_enabled is not None or config.passthrough_mode is not None or config.passthrough_show_ui is not None:
        if universe.input_enabled and universe.input_type != "none":
            # Include channel range in config for input handling
            input_config = universe.input_config or {}
            input_config["channel_start"] = universe.input_channel_start or 1
            input_config["channel_end"] = universe.input_channel_end or 512
            await dmx_interface.add_input(
                universe.id,
                input_type=universe.input_type,
                config=input_config,
                passthrough_enabled=universe.passthrough_enabled or False,
                passthrough_mode=universe.passthrough_mode or "htp",
                passthrough_show_ui=universe.passthrough_show_ui or False
            )
        else:
            await dmx_interface.remove_input(universe.id)
            dmx_interface.set_passthrough(universe.id, False)

    # Update passthrough runtime config
    dmx_interface.set_passthrough(
        universe.id,
        universe.passthrough_enabled or False,
        universe.passthrough_mode or "htp",
        universe.passthrough_show_ui or False
    )

    return universe_io_to_dict(universe, db)


# =========================================================================
# Multiple Outputs endpoints
# =========================================================================

@router.get("/{universe_id}/outputs")
async def get_universe_outputs(universe_id: int, db: Session = Depends(get_db)):
    """Get all outputs for a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    outputs = db.query(UniverseOutput).filter(
        UniverseOutput.universe_id == universe_id
    ).order_by(UniverseOutput.priority).all()

    output_statuses = dmx_interface.get_output_status(universe_id) or []

    return {
        "outputs": [
            {
                "id": o.id,
                "device_type": o.device_type,
                "config": o.config_json or {},
                "enabled": o.enabled,
                "priority": o.priority,
                "status": output_statuses[i] if i < len(output_statuses) else None
            }
            for i, o in enumerate(outputs)
        ]
    }


@router.post("/{universe_id}/outputs")
async def add_universe_output(
    universe_id: int,
    config: OutputConfigRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Add a new output to a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    # Get max priority for ordering
    max_priority = db.query(UniverseOutput).filter(
        UniverseOutput.universe_id == universe_id
    ).count()

    # Create new output in database
    new_output = UniverseOutput(
        universe_id=universe_id,
        device_type=config.device_type,
        config_json=config.config_json,
        enabled=config.enabled,
        priority=max_priority
    )
    db.add(new_output)
    db.commit()
    db.refresh(new_output)

    # Add to runtime
    await dmx_interface.add_output(
        universe_id,
        config.device_type,
        config.config_json,
        output_id=new_output.id,
        enabled=config.enabled
    )

    return {
        "id": new_output.id,
        "device_type": new_output.device_type,
        "config": new_output.config_json or {},
        "enabled": new_output.enabled,
        "priority": new_output.priority
    }


@router.put("/{universe_id}/outputs/{output_id}")
async def update_universe_output(
    universe_id: int,
    output_id: int,
    config: OutputConfigRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a specific output."""
    output = db.query(UniverseOutput).filter(
        UniverseOutput.id == output_id,
        UniverseOutput.universe_id == universe_id
    ).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    # Update database
    output.device_type = config.device_type
    output.config_json = config.config_json
    output.enabled = config.enabled
    db.commit()
    db.refresh(output)

    # Update runtime - remove old and add new
    await dmx_interface.remove_output(universe_id, output_id)
    await dmx_interface.add_output(
        universe_id,
        config.device_type,
        config.config_json,
        output_id=output.id,
        enabled=config.enabled
    )

    return {
        "id": output.id,
        "device_type": output.device_type,
        "config": output.config_json or {},
        "enabled": output.enabled,
        "priority": output.priority
    }


@router.delete("/{universe_id}/outputs/{output_id}")
async def delete_universe_output(
    universe_id: int,
    output_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a specific output."""
    output = db.query(UniverseOutput).filter(
        UniverseOutput.id == output_id,
        UniverseOutput.universe_id == universe_id
    ).first()
    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    # Remove from runtime
    await dmx_interface.remove_output(universe_id, output_id)

    # Remove from database
    db.delete(output)
    db.commit()

    return {"status": "deleted", "output_id": output_id}


@router.put("/{universe_id}/input")
async def configure_input(
    universe_id: int,
    config: InputConfigRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Configure input for a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    universe.input_type = config.input_type
    universe.input_config = config.input_config
    universe.input_enabled = config.input_enabled
    if config.input_channel_start is not None:
        universe.input_channel_start = config.input_channel_start
    if config.input_channel_end is not None:
        universe.input_channel_end = config.input_channel_end
    db.commit()
    db.refresh(universe)

    # Apply to runtime
    if config.input_enabled and config.input_type != "none":
        # Include channel range in config for input handling
        input_config = config.input_config or {}
        input_config["channel_start"] = universe.input_channel_start or 1
        input_config["channel_end"] = universe.input_channel_end or 512
        await dmx_interface.add_input(
            universe.id,
            input_type=config.input_type,
            config=input_config,
            passthrough_enabled=universe.passthrough_enabled or False,
            passthrough_mode=universe.passthrough_mode or "htp",
            passthrough_show_ui=universe.passthrough_show_ui or False
        )
    else:
        await dmx_interface.remove_input(universe.id)

    return universe_io_to_dict(universe, db)


@router.put("/{universe_id}/passthrough")
async def configure_passthrough(
    universe_id: int,
    config: PassthroughConfigRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Configure passthrough for a universe.

    New passthrough_mode values: "off", "view_only", "faders_output"
    """
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    # Convert new passthrough_mode to old database fields for storage
    passthrough_mode = config.passthrough_mode

    if passthrough_mode == "off":
        universe.passthrough_enabled = False
        universe.passthrough_show_ui = False
    elif passthrough_mode == "view_only":
        universe.passthrough_enabled = False
        universe.passthrough_show_ui = True
    elif passthrough_mode == "faders_output":
        universe.passthrough_enabled = True
        universe.passthrough_show_ui = True
    elif passthrough_mode == "output_only":
        universe.passthrough_enabled = True
        universe.passthrough_show_ui = False
    else:
        # Legacy support: use old fields if provided
        if config.passthrough_enabled is not None:
            universe.passthrough_enabled = config.passthrough_enabled
        if config.passthrough_show_ui is not None:
            universe.passthrough_show_ui = config.passthrough_show_ui

    universe.passthrough_mode = config.merge_mode  # HTP/LTP merge mode
    db.commit()
    db.refresh(universe)

    # Apply to runtime with new passthrough_mode
    dmx_interface.set_passthrough(
        universe.id,
        passthrough_mode=passthrough_mode,
        mode=config.merge_mode
    )

    return universe_io_to_dict(universe, db)


@router.post("/{universe_id}/input/enable")
async def enable_input(
    universe_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Enable input for a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    if not universe.input_type or universe.input_type == "none":
        raise HTTPException(status_code=400, detail="No input type configured")

    universe.input_enabled = True
    db.commit()

    # Include channel range in config for input handling
    input_config = universe.input_config or {}
    input_config["channel_start"] = universe.input_channel_start or 1
    input_config["channel_end"] = universe.input_channel_end or 512
    await dmx_interface.add_input(
        universe.id,
        input_type=universe.input_type,
        config=input_config,
        passthrough_enabled=universe.passthrough_enabled or False,
        passthrough_mode=universe.passthrough_mode or "htp",
        passthrough_show_ui=universe.passthrough_show_ui or False
    )

    return {"status": "enabled", "universe_id": universe_id}


@router.post("/{universe_id}/input/disable")
async def disable_input(
    universe_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Disable input for a universe."""
    universe = db.query(Universe).filter(Universe.id == universe_id).first()
    if not universe:
        raise HTTPException(status_code=404, detail="Universe not found")

    universe.input_enabled = False
    db.commit()

    await dmx_interface.remove_input(universe.id)

    return {"status": "disabled", "universe_id": universe_id}


@router.get("/protocols/input")
async def list_input_protocols():
    """List available input protocols."""
    return {"protocols": dmx_interface.get_input_protocols()}


@router.get("/protocols/output")
async def list_output_protocols():
    """List available output protocols."""
    return {"protocols": dmx_interface.get_protocols()}


@router.get("/network/interfaces")
async def get_network_interfaces():
    """Get list of network interfaces and their IP addresses for subnet calculator."""
    import socket
    interfaces = []

    try:
        # Try to use netifaces if available (more reliable)
        import netifaces
        for iface_name in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface_name)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr")
                    netmask = addr.get("netmask")
                    broadcast = addr.get("broadcast")
                    # Skip localhost
                    if ip and not ip.startswith("127."):
                        interfaces.append({
                            "interface": iface_name,
                            "ip": ip,
                            "netmask": netmask,
                            "broadcast": broadcast
                        })
    except ImportError:
        # Fallback: try to get hostname-based IP
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and not ip.startswith("127."):
                interfaces.append({
                    "interface": "default",
                    "ip": ip,
                    "netmask": "255.255.255.0",  # Assume /24
                    "broadcast": None
                })
        except Exception:
            pass

        # Also try to get all IPs via getaddrinfo
        try:
            hostname = socket.gethostname()
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                ip = info[4][0]
                if ip and not ip.startswith("127."):
                    # Check if not already added
                    if not any(i["ip"] == ip for i in interfaces):
                        interfaces.append({
                            "interface": "unknown",
                            "ip": ip,
                            "netmask": "255.255.255.0",
                            "broadcast": None
                        })
        except Exception:
            pass

    return {"interfaces": interfaces}


@router.get("/channel-usage")
async def get_channel_usage(db: Session = Depends(get_db)):
    """Get channel usage information for all universes.

    Returns the highest used channel per universe, calculated from:
    - Patched fixtures (start_channel + channel_count)
    - Saved scenes (highest channel with non-zero value)
    """
    universes = db.query(Universe).all()
    result = {}

    for universe in universes:
        # Get all patches for this universe with their fixtures
        patches = db.query(Patch).filter(
            Patch.universe_id == universe.id
        ).join(Fixture).all()

        highest_patched = 0
        patched_channels = set()

        for patch in patches:
            # Get channel count from fixture definition - try multiple sources
            fixture_def = patch.fixture.definition_json or {}

            # Try "channels" array first
            channels_array = fixture_def.get("channels", [])
            channel_count = len(channels_array) if channels_array else 0

            # Fallback: try "channelCount" or "channel_count" fields
            if channel_count == 0:
                channel_count = fixture_def.get("channelCount", 0) or fixture_def.get("channel_count", 0)

            # Fallback: try "numChannels" or "totalChannels"
            if channel_count == 0:
                channel_count = fixture_def.get("numChannels", 0) or fixture_def.get("totalChannels", 0)

            # Fallback: try to infer from modes
            if channel_count == 0:
                modes = fixture_def.get("modes", [])
                if modes and len(modes) > 0:
                    # Use first mode's channel count
                    first_mode = modes[0]
                    if isinstance(first_mode, dict):
                        channel_count = first_mode.get("channels", 0) or first_mode.get("channelCount", 0) or len(first_mode.get("channelList", []))

            # Ensure at least 1 channel
            if channel_count == 0:
                channel_count = 1

            end_channel = patch.start_channel + channel_count - 1

            # Track highest channel
            if end_channel > highest_patched:
                highest_patched = end_channel

            # Track all patched channels
            for ch in range(patch.start_channel, end_channel + 1):
                patched_channels.add(ch)

        # Find highest channel with non-zero value in any saved scene
        highest_scene = db.query(func.max(SceneValue.channel)).filter(
            SceneValue.universe_id == universe.id,
            SceneValue.value > 0
        ).scalar() or 0

        # Highest used is the max of patched and scene channels
        highest_used = max(highest_patched, highest_scene)

        result[str(universe.id)] = {
            "universe_id": universe.id,
            "label": universe.label,
            "highest_patched": highest_patched,
            "highest_scene": highest_scene,
            "highest_used": highest_used,
            "patched_count": len(patched_channels),
            "patch_count": len(patches),
            "patched_channels": sorted(list(patched_channels))
        }

    return {"universes": result}
