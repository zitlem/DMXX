"""Settings API endpoints."""
import json
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import (
    get_db, Setting, Universe, UniverseOutput, Fixture, Patch,
    Scene, SceneValue, SceneGroupValue, Group, GroupMember,
    Profile, ChannelMapping, ChannelLabel, TriggerToken
)
from ..auth import get_current_user

router = APIRouter()


class SettingRequest(BaseModel):
    key: str
    value: str


class SettingsUpdateRequest(BaseModel):
    settings: dict


# Theme presets
THEME_PRESETS = {
    "dark": {
        "bgPrimary": "#1a1a2e",
        "bgSecondary": "#16213e",
        "bgTertiary": "#0f3460",
        "textPrimary": "#eeeeee",
        "textSecondary": "#aaaaaa",
        "accent": "#e94560",
        "accentHover": "#ff6b6b",
        "success": "#4ade80",
        "warning": "#fbbf24",
        "error": "#f87171",
        "border": "#2a2a4a",
        "faderBg": "#2a2a4a",
        "faderFill": "#e94560",
        "indicatorRemote": "#00bcd4",
        "indicatorLocal": "#4caf50",
        "indicatorGroup": "#4ade80"
    },
    "light": {
        "bgPrimary": "#f5f5f5",
        "bgSecondary": "#ffffff",
        "bgTertiary": "#e0e0e0",
        "textPrimary": "#212121",
        "textSecondary": "#666666",
        "accent": "#e94560",
        "accentHover": "#ff6b6b",
        "success": "#22c55e",
        "warning": "#f59e0b",
        "error": "#ef4444",
        "border": "#d0d0d0",
        "faderBg": "#c0c0c0",
        "faderFill": "#e94560",
        "indicatorRemote": "#00bcd4",
        "indicatorLocal": "#4caf50",
        "indicatorGroup": "#22c55e"
    }
}

# Default theme as JSON string
DEFAULT_THEME = json.dumps({
    "type": "preset",
    "presetName": "dark",
    "colors": THEME_PRESETS["dark"]
})

# Default settings
DEFAULT_SETTINGS = {
    "default_transition_type": "instant",
    "default_transition_duration": "0",
    "dmx_refresh_rate": "40",  # Hz
    "websocket_update_rate": "30",  # Hz
    "theme": DEFAULT_THEME,
    "global_master_fader_color": "#f59e0b"  # Gold/amber default for global master
}


def get_setting(key: str, db: Session) -> str:
    """Get a setting value, with default fallback."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        return setting.value
    return DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str, db: Session) -> None:
    """Set a setting value."""
    setting = db.query(Setting).filter(Setting.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.add(setting)
    db.commit()


@router.get("")
async def get_all_settings(db: Session = Depends(get_db)):
    """Get all settings."""
    settings = {}

    # Load defaults first
    for key, default in DEFAULT_SETTINGS.items():
        settings[key] = default

    # Override with stored values
    stored = db.query(Setting).all()
    for s in stored:
        settings[s.key] = s.value

    return {"settings": settings}


@router.get("/{key}")
async def get_setting_value(key: str, db: Session = Depends(get_db)):
    """Get a specific setting."""
    value = get_setting(key, db)
    return {"key": key, "value": value}


@router.post("")
async def update_setting(
    request: SettingRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update a single setting."""
    set_setting(request.key, request.value, db)
    return {"key": request.key, "value": request.value}


@router.put("")
async def update_multiple_settings(
    request: SettingsUpdateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Update multiple settings at once."""
    for key, value in request.settings.items():
        set_setting(key, str(value), db)

    return {"status": "updated", "count": len(request.settings)}


@router.post("/reset")
async def reset_settings(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Reset all settings and delete all data (except backups)."""
    # Delete in order respecting foreign keys
    db.query(TriggerToken).delete()
    db.query(SceneGroupValue).delete()
    db.query(SceneValue).delete()
    db.query(Scene).delete()
    db.query(GroupMember).delete()
    db.query(Group).delete()
    db.query(Patch).delete()
    db.query(UniverseOutput).delete()
    db.query(Universe).delete()
    db.query(Fixture).delete()
    db.query(Profile).delete()
    db.query(ChannelMapping).delete()
    db.query(ChannelLabel).delete()
    db.query(Setting).delete()
    db.commit()

    # Recreate default admin profile from config.json
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.json")
    default_password = "dmxx"
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = json.load(f)
                default_password = config.get("password", "dmxx")
        except:
            pass

    admin_profile = Profile(
        name="Admin",
        password=default_password,
        allowed_pages=["faders", "scenes", "fixtures", "patch", "io", "groups", "settings"],
        is_admin=True
    )
    db.add(admin_profile)
    db.commit()

    return {"status": "reset", "defaults": DEFAULT_SETTINGS}


@router.get("/defaults/all")
async def get_default_settings():
    """Get default settings values."""
    return {"defaults": DEFAULT_SETTINGS}


@router.get("/theme/presets")
async def get_theme_presets():
    """Get available theme presets."""
    return {"presets": THEME_PRESETS}
