"""MIDI control API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db, MIDICCMapping, MIDITrigger
from ..dmx_interface import dmx_interface
from ..midi_handler import note_to_name

router = APIRouter()


# Request/Response models
class MIDIDeviceResponse(BaseModel):
    inputs: List[str]
    outputs: List[str]


class MIDIStartRequest(BaseModel):
    device_name: Optional[str] = None


def _reload_cc_mappings(db: Session) -> None:
    """Reload enabled MIDI CC -> Input Channel mappings (apply to all MIDI-input universes)."""
    cc_mappings = db.query(MIDICCMapping).filter(MIDICCMapping.enabled == True).all()
    mappings = [
        {
            "id": m.id,
            "cc_number": m.cc_number,
            "midi_channel": m.midi_channel,
            "input_channel": m.input_channel,
            "label": m.label,
            "enabled": m.enabled,
            "device_name": m.device_name  # For multi-device filtering
        }
        for m in cc_mappings
    ]
    dmx_interface.load_midi_cc_mappings(mappings)


def _reload_triggers(db: Session) -> None:
    """Reload enabled MIDI Note -> Action triggers."""
    triggers = db.query(MIDITrigger).filter(MIDITrigger.enabled == True).all()
    trigger_list = [
        {
            "id": t.id,
            "note": t.note,
            "midi_channel": t.midi_channel,
            "action": t.action,
            "target_id": t.target_id,
            "label": t.label,
            "enabled": t.enabled,
            "device_name": t.device_name  # For multi-device filtering
        }
        for t in triggers
    ]
    dmx_interface.load_midi_triggers(trigger_list)


# Device discovery endpoints
@router.get("/devices", response_model=MIDIDeviceResponse)
async def list_devices(user: dict = Depends(get_current_user)):
    """List available MIDI input and output devices."""
    return dmx_interface.get_midi_devices()


# Input control endpoints
@router.post("/input/start")
async def start_input(
    request: MIDIStartRequest,
    user: dict = Depends(get_current_user)
):
    """Start MIDI input on specified device."""
    from ..midi_handler import MIDIHandler

    if not MIDIHandler.is_available():
        raise HTTPException(
            status_code=503,
            detail="MIDI support not available. Install mido[rtmidi]."
        )

    success = await dmx_interface.start_midi_input(request.device_name)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to start MIDI input. Check device name."
        )

    status = dmx_interface.get_midi_status()
    return {"status": "started", "device": status["input"]["device"]}


@router.post("/input/stop")
async def stop_input(user: dict = Depends(get_current_user)):
    """Stop MIDI input."""
    await dmx_interface.stop_midi_input()
    return {"status": "stopped"}


# Output control endpoints
@router.post("/output/start")
async def start_output(
    request: MIDIStartRequest,
    user: dict = Depends(get_current_user)
):
    """Start MIDI output on specified device."""
    from ..midi_handler import MIDIHandler

    if not MIDIHandler.is_available():
        raise HTTPException(
            status_code=503,
            detail="MIDI support not available. Install mido[rtmidi]."
        )

    success = await dmx_interface.start_midi_output(request.device_name)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to start MIDI output. Check device name."
        )

    status = dmx_interface.get_midi_status()
    return {"status": "started", "device": status["output"]["device"]}


@router.post("/output/stop")
async def stop_output(user: dict = Depends(get_current_user)):
    """Stop MIDI output."""
    await dmx_interface.stop_midi_output()
    return {"status": "stopped"}


# Status endpoint
@router.get("/status")
async def get_status(user: dict = Depends(get_current_user)):
    """Get MIDI handler status."""
    return dmx_interface.get_midi_status()


# Learn mode endpoints
@router.post("/learn/start")
async def start_learn(user: dict = Depends(get_current_user)):
    """Start MIDI learn mode to capture incoming messages."""
    dmx_interface.start_midi_learn()
    return {"status": "learning"}


@router.post("/learn/stop")
async def stop_learn(user: dict = Depends(get_current_user)):
    """Stop MIDI learn mode."""
    dmx_interface.stop_midi_learn()
    return {"status": "stopped", "last_message": dmx_interface.get_midi_last_message()}


@router.get("/learn/last")
async def get_last_learned(user: dict = Depends(get_current_user)):
    """Get the last learned MIDI message."""
    msg = dmx_interface.get_midi_last_message()
    if msg and msg.get("type") == "note_on":
        msg["note_name"] = note_to_name(msg.get("note", 0))
    return {"message": msg}


# Test endpoints for manual MIDI output
@router.post("/test/cc")
async def test_send_cc(
    channel: int = 0,
    control: int = 0,
    value: int = 127,
    user: dict = Depends(get_current_user)
):
    """Send a test MIDI CC message."""
    status = dmx_interface.get_midi_status()
    if not status["output"]["running"]:
        raise HTTPException(status_code=400, detail="MIDI output not running")

    handler = dmx_interface._midi_handler
    if not handler:
        raise HTTPException(status_code=400, detail="MIDI handler not initialized")

    success = handler.send_cc(channel, control, value)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to send MIDI CC")
    return {"status": "sent", "channel": channel, "control": control, "value": value}


@router.post("/test/note")
async def test_send_note(
    channel: int = 0,
    note: int = 60,
    velocity: int = 127,
    user: dict = Depends(get_current_user)
):
    """Send a test MIDI Note On message."""
    status = dmx_interface.get_midi_status()
    if not status["output"]["running"]:
        raise HTTPException(status_code=400, detail="MIDI output not running")

    handler = dmx_interface._midi_handler
    if not handler:
        raise HTTPException(status_code=400, detail="MIDI handler not initialized")

    success = handler.send_note_on(channel, note, velocity)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to send MIDI Note")
    return {
        "status": "sent",
        "channel": channel,
        "note": note,
        "note_name": note_to_name(note),
        "velocity": velocity
    }


# =============================================================================
# CC Mapping endpoints (CC -> Input Channel for I/O integration)
# =============================================================================

class CCMappingCreate(BaseModel):
    cc_number: int
    midi_channel: int = -1
    input_channel: int
    label: str = ""
    enabled: bool = True
    device_name: Optional[str] = None  # None = all devices


class CCMappingUpdate(BaseModel):
    cc_number: Optional[int] = None
    midi_channel: Optional[int] = None
    input_channel: Optional[int] = None
    label: Optional[str] = None
    enabled: Optional[bool] = None
    device_name: Optional[str] = None


class CCMappingResponse(BaseModel):
    id: int
    cc_number: int
    midi_channel: int
    input_channel: int
    label: str
    enabled: bool
    device_name: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/cc-mappings", response_model=List[CCMappingResponse])
async def list_cc_mappings(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all MIDI CC -> Input Channel mappings."""
    mappings = db.query(MIDICCMapping).all()
    return mappings


@router.post("/cc-mappings", response_model=CCMappingResponse)
async def create_cc_mapping(
    mapping: CCMappingCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new MIDI CC -> Input Channel mapping (applies to all MIDI-input universes)."""
    db_mapping = MIDICCMapping(
        cc_number=mapping.cc_number,
        midi_channel=mapping.midi_channel,
        input_channel=mapping.input_channel,
        label=mapping.label,
        enabled=mapping.enabled,
        device_name=mapping.device_name
    )
    db.add(db_mapping)
    db.commit()
    db.refresh(db_mapping)

    # Reload CC mappings
    _reload_cc_mappings(db)

    return db_mapping


@router.put("/cc-mappings/{mapping_id}", response_model=CCMappingResponse)
async def update_cc_mapping(
    mapping_id: int,
    update: CCMappingUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a MIDI CC mapping."""
    mapping = db.query(MIDICCMapping).filter(MIDICCMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="CC mapping not found")

    if update.cc_number is not None:
        mapping.cc_number = update.cc_number
    if update.midi_channel is not None:
        mapping.midi_channel = update.midi_channel
    if update.input_channel is not None:
        mapping.input_channel = update.input_channel
    if update.label is not None:
        mapping.label = update.label
    if update.enabled is not None:
        mapping.enabled = update.enabled
    if update.device_name is not None:
        # Allow clearing device_name by setting to empty string -> None
        mapping.device_name = update.device_name if update.device_name else None

    db.commit()
    db.refresh(mapping)

    # Reload CC mappings
    _reload_cc_mappings(db)

    return mapping


@router.delete("/cc-mappings/{mapping_id}")
async def delete_cc_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a MIDI CC mapping."""
    mapping = db.query(MIDICCMapping).filter(MIDICCMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="CC mapping not found")

    db.delete(mapping)
    db.commit()

    # Reload CC mappings
    _reload_cc_mappings(db)

    return {"status": "deleted"}


# =============================================================================
# Trigger endpoints (Note -> Action for direct actions)
# =============================================================================

class TriggerCreate(BaseModel):
    note: int
    midi_channel: int = -1
    action: str  # "scene", "blackout", "group"
    target_id: Optional[int] = None
    label: str = ""
    enabled: bool = True
    device_name: Optional[str] = None  # None = all devices


class TriggerUpdate(BaseModel):
    note: Optional[int] = None
    midi_channel: Optional[int] = None
    action: Optional[str] = None
    target_id: Optional[int] = None
    label: Optional[str] = None
    enabled: Optional[bool] = None
    device_name: Optional[str] = None


class TriggerResponse(BaseModel):
    id: int
    note: int
    midi_channel: int
    action: str
    target_id: Optional[int]
    label: str
    enabled: bool
    device_name: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/triggers", response_model=List[TriggerResponse])
async def list_triggers(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """List all MIDI Note -> Action triggers."""
    triggers = db.query(MIDITrigger).all()
    return triggers


@router.post("/triggers", response_model=TriggerResponse)
async def create_trigger(
    trigger: TriggerCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new MIDI Note -> Action trigger."""
    db_trigger = MIDITrigger(
        note=trigger.note,
        midi_channel=trigger.midi_channel,
        action=trigger.action,
        target_id=trigger.target_id,
        label=trigger.label,
        enabled=trigger.enabled,
        device_name=trigger.device_name
    )
    db.add(db_trigger)
    db.commit()
    db.refresh(db_trigger)

    # Reload triggers
    _reload_triggers(db)

    return db_trigger


@router.put("/triggers/{trigger_id}", response_model=TriggerResponse)
async def update_trigger(
    trigger_id: int,
    update: TriggerUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a MIDI trigger."""
    trigger = db.query(MIDITrigger).filter(MIDITrigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    if update.note is not None:
        trigger.note = update.note
    if update.midi_channel is not None:
        trigger.midi_channel = update.midi_channel
    if update.action is not None:
        trigger.action = update.action
    if update.target_id is not None:
        trigger.target_id = update.target_id
    if update.label is not None:
        trigger.label = update.label
    if update.enabled is not None:
        trigger.enabled = update.enabled
    if update.device_name is not None:
        # Allow clearing device_name by setting to empty string -> None
        trigger.device_name = update.device_name if update.device_name else None

    db.commit()
    db.refresh(trigger)

    # Reload triggers
    _reload_triggers(db)

    return trigger


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(
    trigger_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a MIDI trigger."""
    trigger = db.query(MIDITrigger).filter(MIDITrigger.id == trigger_id).first()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    db.delete(trigger)
    db.commit()

    # Reload triggers
    _reload_triggers(db)

    return {"status": "deleted"}


# =============================================================================
# MIDI Input Status endpoint (for I/O page)
# =============================================================================

@router.get("/input/status")
async def get_midi_input_status(user: dict = Depends(get_current_user)):
    """Get MIDI input status for I/O page display."""
    return dmx_interface.get_midi_input_status()


@router.get("/input/values")
async def get_midi_input_values(user: dict = Depends(get_current_user)):
    """Get current MIDI input channel values."""
    return {"values": dmx_interface.get_midi_input_values()}


@router.post("/input/enable")
async def enable_midi_input_integration(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Enable MIDI input integration with I/O system."""
    dmx_interface.set_midi_input_enabled(True)
    # Reload CC mappings and triggers
    _reload_cc_mappings(db)
    _reload_triggers(db)
    return {"status": "enabled"}


@router.post("/input/disable")
async def disable_midi_input_integration(user: dict = Depends(get_current_user)):
    """Disable MIDI input integration with I/O system."""
    dmx_interface.set_midi_input_enabled(False)
    return {"status": "disabled"}


# =============================================================================
# Multi-Device Management endpoints
# =============================================================================

@router.get("/input/connected-devices")
async def get_connected_devices(user: dict = Depends(get_current_user)):
    """Get list of currently connected MIDI input devices."""
    status = dmx_interface.get_midi_status()
    network_status = status.get("network", {})

    # Get USB devices
    usb_devices = status.get("input", {}).get("devices", [])

    # Get network peers (format as device names)
    network_peers = network_status.get("peers", [])
    network_devices = [f"network:{p.get('name', p)}" for p in network_peers]

    return {
        "usb_devices": usb_devices,
        "network_devices": network_devices,
        "all_devices": usb_devices + network_devices
    }


class DeviceConnectRequest(BaseModel):
    device_name: str


@router.post("/input/connect")
async def connect_device(
    request: DeviceConnectRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Connect to a specific MIDI input device (additive - can have multiple)."""
    success = await dmx_interface.start_midi_input(request.device_name)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to connect to {request.device_name}")

    # Reload mappings for the new device
    _reload_cc_mappings(db)
    _reload_triggers(db)

    return {"status": "connected", "device": request.device_name}


@router.post("/input/disconnect")
async def disconnect_device(
    request: DeviceConnectRequest,
    user: dict = Depends(get_current_user)
):
    """Disconnect a specific MIDI input device."""
    await dmx_interface.stop_midi_input(request.device_name)
    return {"status": "disconnected", "device": request.device_name}


# =============================================================================
# Network MIDI (rtpMIDI) endpoints
# =============================================================================

class NetworkServerRequest(BaseModel):
    port: int = 5004
    name: str = "DMXX"


class NetworkConnectRequest(BaseModel):
    host: str
    port: int = 5004


@router.get("/network/status")
async def get_network_status(user: dict = Depends(get_current_user)):
    """Get Network MIDI (rtpMIDI) status."""
    from ..midi_handler import MIDIHandler
    status = dmx_interface.get_midi_status()
    return {
        "available": MIDIHandler.is_network_available(),
        **status.get("network", {})
    }


@router.post("/network/server/start")
async def start_network_server(
    request: NetworkServerRequest,
    user: dict = Depends(get_current_user)
):
    """Start rtpMIDI server to accept incoming connections."""
    from ..midi_handler import MIDIHandler

    if not MIDIHandler.is_network_available():
        raise HTTPException(
            status_code=503,
            detail="Network MIDI not available. Install pymidi: pip install pymidi"
        )

    success = await dmx_interface.start_midi_network_server(request.port, request.name)
    if not success:
        raise HTTPException(
            status_code=400,
            detail="Failed to start network MIDI server. Port may be in use."
        )

    return {
        "status": "started",
        "port": request.port,
        "name": request.name
    }


@router.post("/network/server/stop")
async def stop_network_server(user: dict = Depends(get_current_user)):
    """Stop the rtpMIDI server."""
    await dmx_interface.stop_midi_network_server()
    return {"status": "stopped"}


@router.get("/network/peers")
async def get_network_peers(user: dict = Depends(get_current_user)):
    """Get list of connected network MIDI peers."""
    return {"peers": dmx_interface.get_midi_network_peers()}


# =============================================================================
# MIDI Output Feedback endpoints
# =============================================================================

@router.post("/output/feedback/enable")
async def enable_midi_feedback(user: dict = Depends(get_current_user)):
    """Enable MIDI output feedback.

    When enabled, channel value changes and scene/blackout state changes
    will send MIDI CC and Note messages back to the controller.
    """
    dmx_interface.set_midi_output_enabled(True)
    return {"status": "enabled"}


@router.post("/output/feedback/disable")
async def disable_midi_feedback(user: dict = Depends(get_current_user)):
    """Disable MIDI output feedback."""
    dmx_interface.set_midi_output_enabled(False)
    return {"status": "disabled"}


@router.get("/output/feedback/status")
async def get_midi_feedback_status(user: dict = Depends(get_current_user)):
    """Get MIDI output feedback status."""
    return {"enabled": dmx_interface._midi_output_enabled}
