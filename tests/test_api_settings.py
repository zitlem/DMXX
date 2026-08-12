"""API tests for settings, theme presets and the destructive reset endpoint."""
import json

import pytest

from backend.api import settings as settings_api
from backend.api.settings import (
    DEFAULT_SETTINGS,
    THEME_PRESETS,
    get_setting,
    set_setting,
)
from backend.database import Fixture, Group, Profile, Scene, Setting, Universe


@pytest.fixture
def client(make_app):
    return make_app(settings_api.router, prefix="/api/settings")


# ---------------------------------------------------------------------------
# get_setting / set_setting helpers
# ---------------------------------------------------------------------------
def test_get_setting_falls_back_to_the_default(db_session):
    assert get_setting("dmx_refresh_rate", db_session) == "40"


def test_get_unknown_setting_is_an_empty_string(db_session):
    assert get_setting("nope", db_session) == ""


def test_set_setting_creates_then_updates(db_session):
    set_setting("theme", "dark", db_session)
    assert get_setting("theme", db_session) == "dark"

    set_setting("theme", "light", db_session)
    assert get_setting("theme", db_session) == "light"
    assert db_session.query(Setting).filter_by(key="theme").count() == 1


# ---------------------------------------------------------------------------
# Reading settings
# ---------------------------------------------------------------------------
def test_get_all_returns_the_defaults(client):
    settings = client.get("/api/settings").json()["settings"]
    for key, value in DEFAULT_SETTINGS.items():
        assert settings[key] == value


def test_stored_values_override_the_defaults(client, db_session):
    set_setting("dmx_refresh_rate", "25", db_session)
    assert client.get("/api/settings").json()["settings"]["dmx_refresh_rate"] == "25"


def test_custom_keys_are_included(client, db_session):
    set_setting("my_custom_key", "hello", db_session)
    assert client.get("/api/settings").json()["settings"]["my_custom_key"] == "hello"


def test_get_a_single_setting(client, db_session):
    set_setting("theme", "custom", db_session)
    assert client.get("/api/settings/theme").json() == {"key": "theme",
                                                        "value": "custom"}


def test_get_a_single_unset_setting_uses_the_default(client):
    assert client.get("/api/settings/websocket_update_rate").json()["value"] == "30"


# ---------------------------------------------------------------------------
# Writing settings
# ---------------------------------------------------------------------------
def test_update_a_single_setting(client, db_session):
    response = client.post("/api/settings",
                           json={"key": "dmx_refresh_rate", "value": "44"})

    assert response.json() == {"key": "dmx_refresh_rate", "value": "44"}
    assert get_setting("dmx_refresh_rate", db_session) == "44"


def test_update_multiple_settings(client, db_session):
    response = client.put("/api/settings", json={"settings": {
        "dmx_refresh_rate": "30", "websocket_update_rate": 15}})

    assert response.json() == {"status": "updated", "count": 2}
    assert get_setting("dmx_refresh_rate", db_session) == "30"
    assert get_setting("websocket_update_rate", db_session) == "15"  # coerced


def test_update_multiple_with_nothing_to_do(client):
    assert client.put("/api/settings", json={"settings": {}}).json()["count"] == 0


def test_update_requires_key_and_value(client):
    assert client.post("/api/settings", json={"key": "x"}).status_code == 422


# ---------------------------------------------------------------------------
# Defaults & themes
# ---------------------------------------------------------------------------
def test_defaults_endpoint(client):
    assert client.get("/api/settings/defaults/all").json() == {
        "defaults": DEFAULT_SETTINGS}


def test_default_theme_is_valid_json():
    theme = json.loads(DEFAULT_SETTINGS["theme"])
    assert theme["type"] == "preset"
    assert theme["presetName"] == "dark"
    assert theme["colors"] == THEME_PRESETS["dark"]


def test_theme_presets_endpoint(client):
    presets = client.get("/api/settings/theme/presets").json()["presets"]
    assert set(presets) == {"dark", "light"}


def test_theme_presets_share_the_same_colour_keys():
    assert set(THEME_PRESETS["dark"]) == set(THEME_PRESETS["light"])


def test_theme_colours_are_hex_strings():
    for preset in THEME_PRESETS.values():
        for value in preset.values():
            assert value.startswith("#") and len(value) == 7


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------
def test_reset_clears_data_and_recreates_the_admin_profile(client, db_session):
    db_session.add_all([
        Universe(id=1, label="U", device_type="mock"),
        Fixture(name="F", definition_json={}),
        Scene(name="S"),
        Group(name="G"),
        Profile(name="Tech", allowed_pages=["faders"]),
        Setting(key="theme", value="custom"),
    ])
    db_session.commit()

    response = client.post("/api/settings/reset")

    assert response.json()["status"] == "reset"
    assert db_session.query(Universe).count() == 0
    assert db_session.query(Fixture).count() == 0
    assert db_session.query(Scene).count() == 0
    assert db_session.query(Group).count() == 0
    assert db_session.query(Setting).count() == 0

    profiles = db_session.query(Profile).all()
    assert len(profiles) == 1
    assert profiles[0].name == "Admin"
    assert profiles[0].is_admin is True


def test_reset_returns_the_defaults(client):
    assert client.post("/api/settings/reset").json()["defaults"] == DEFAULT_SETTINGS


def test_reset_on_an_empty_database(client, db_session):
    client.post("/api/settings/reset")
    assert db_session.query(Profile).count() == 1
