"""Fixture library API endpoints."""
import json
import os
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..database import get_db, Fixture
from ..auth import get_current_user
from ..websocket_manager import manager

router = APIRouter()

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


class CreateFixtureRequest(BaseModel):
    name: str
    manufacturer: str = ""
    definition_json: dict


class UpdateFixtureRequest(BaseModel):
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    definition_json: Optional[dict] = None


def fixture_to_dict(fixture: Fixture) -> dict:
    """Convert a Fixture model to dictionary."""
    definition = fixture.definition_json
    return {
        "id": fixture.id,
        "name": fixture.name,
        "manufacturer": fixture.manufacturer,
        "position": fixture.position,
        "channel_count": len(definition.get("channels", [])),
        "channels": definition.get("channels", []),
        "modes": definition.get("modes", []),
        "definition": definition,
        "definition_json": definition  # For edit form
    }


@router.get("")
async def list_fixtures(db: Session = Depends(get_db)):
    """List all fixtures in the library ordered by position."""
    fixtures = db.query(Fixture).order_by(Fixture.position).all()
    return {"fixtures": [fixture_to_dict(f) for f in fixtures]}


class ReorderFixturesRequest(BaseModel):
    fixture_ids: List[int]


@router.put("/reorder")
async def reorder_fixtures(
    request: ReorderFixturesRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Reorder fixtures by updating their positions."""
    for new_position, fixture_id in enumerate(request.fixture_ids):
        fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
        if fixture:
            fixture.position = new_position
    db.commit()
    await manager.broadcast({"type": "fixtures_changed"})
    return {"status": "reordered", "order": request.fixture_ids}


@router.get("/{fixture_id}")
async def get_fixture(fixture_id: int, db: Session = Depends(get_db)):
    """Get a specific fixture."""
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture_to_dict(fixture)


@router.post("")
async def create_fixture(
    request: CreateFixtureRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a custom fixture."""
    # Validate definition has channels
    if "channels" not in request.definition_json or not request.definition_json["channels"]:
        raise HTTPException(status_code=400, detail="Fixture must have at least one channel")

    # Get max position to place new fixture at end
    max_pos = db.query(func.max(Fixture.position)).scalar() or -1

    fixture = Fixture(
        name=request.name,
        manufacturer=request.manufacturer,
        definition_json=request.definition_json,
        position=max_pos + 1
    )
    db.add(fixture)
    db.commit()
    db.refresh(fixture)

    return fixture_to_dict(fixture)


@router.put("/{fixture_id}")
async def update_fixture(
    fixture_id: int,
    request: UpdateFixtureRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a fixture."""
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    if request.name is not None:
        fixture.name = request.name
    if request.manufacturer is not None:
        fixture.manufacturer = request.manufacturer
    if request.definition_json is not None:
        fixture.definition_json = request.definition_json

    db.commit()
    db.refresh(fixture)

    return fixture_to_dict(fixture)


@router.delete("/{fixture_id}")
async def delete_fixture(
    fixture_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a fixture."""
    fixture = db.query(Fixture).filter(Fixture.id == fixture_id).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Check if fixture is in use
    if fixture.patches:
        raise HTTPException(
            status_code=400,
            detail=f"Fixture is used in {len(fixture.patches)} patch(es). Remove patches first."
        )

    db.delete(fixture)
    db.commit()

    return {"status": "deleted", "fixture_id": fixture_id}


@router.post("/import/ofl")
async def import_ofl_fixture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Import a fixture from Open Fixture Library JSON file."""
    try:
        content = await file.read()
        ofl_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    # Parse OFL format
    name = ofl_data.get("name", file.filename.replace(".json", ""))
    manufacturer = ofl_data.get("manufacturerKey", "")

    # Convert OFL channels to our format
    channels = []
    available_channels = ofl_data.get("availableChannels", {})
    modes = ofl_data.get("modes", [])

    # Use first mode's channel order
    if modes and "channels" in modes[0]:
        mode_channels = modes[0]["channels"]
        for ch_ref in mode_channels:
            if ch_ref in available_channels:
                ch_data = available_channels[ch_ref]
                channels.append({
                    "name": ch_ref,
                    "type": ch_data.get("type", "intensity"),
                    "default": ch_data.get("defaultValue", 0)
                })
    else:
        # Fall back to available channels order
        for ch_name, ch_data in available_channels.items():
            channels.append({
                "name": ch_name,
                "type": ch_data.get("type", "intensity"),
                "default": ch_data.get("defaultValue", 0)
            })

    definition = {
        "channels": channels,
        "modes": modes,
        "ofl_data": ofl_data  # Store original for reference
    }

    fixture = Fixture(
        name=name,
        manufacturer=manufacturer,
        definition_json=definition
    )
    db.add(fixture)
    db.commit()
    db.refresh(fixture)

    return fixture_to_dict(fixture)


@router.get("/templates/generic")
async def get_generic_templates():
    """Get a list of generic fixture templates."""
    templates = [
        {
            "name": "Generic Dimmer",
            "manufacturer": "Generic",
            "definition_json": {
                "channels": [
                    {"name": "Dimmer", "type": "intensity", "default": 0}
                ]
            }
        },
        {
            "name": "Generic RGB",
            "manufacturer": "Generic",
            "definition_json": {
                "channels": [
                    {"name": "Red", "type": "color", "color": "#ff0000", "default": 0},
                    {"name": "Green", "type": "color", "color": "#00ff00", "default": 0},
                    {"name": "Blue", "type": "color", "color": "#0000ff", "default": 0}
                ]
            }
        },
        {
            "name": "Generic RGBW",
            "manufacturer": "Generic",
            "definition_json": {
                "channels": [
                    {"name": "Red", "type": "color", "color": "#ff0000", "default": 0},
                    {"name": "Green", "type": "color", "color": "#00ff00", "default": 0},
                    {"name": "Blue", "type": "color", "color": "#0000ff", "default": 0},
                    {"name": "White", "type": "color", "color": "#ffffff", "default": 0}
                ]
            }
        },
        {
            "name": "Generic RGBWA",
            "manufacturer": "Generic",
            "definition_json": {
                "channels": [
                    {"name": "Red", "type": "color", "color": "#ff0000", "default": 0},
                    {"name": "Green", "type": "color", "color": "#00ff00", "default": 0},
                    {"name": "Blue", "type": "color", "color": "#0000ff", "default": 0},
                    {"name": "White", "type": "color", "color": "#ffffff", "default": 0},
                    {"name": "Amber", "type": "color", "color": "#ffbf00", "default": 0}
                ]
            }
        },
        {
            "name": "Generic Moving Head",
            "manufacturer": "Generic",
            "definition_json": {
                "channels": [
                    {"name": "Pan", "type": "pan", "default": 128},
                    {"name": "Pan Fine", "type": "pan_fine", "default": 0},
                    {"name": "Tilt", "type": "tilt", "default": 128},
                    {"name": "Tilt Fine", "type": "tilt_fine", "default": 0},
                    {"name": "Dimmer", "type": "intensity", "default": 0},
                    {"name": "Shutter", "type": "shutter", "default": 0},
                    {"name": "Color Wheel", "type": "color_wheel", "default": 0},
                    {"name": "Gobo Wheel", "type": "gobo", "default": 0}
                ]
            }
        }
    ]
    return {"templates": templates}
