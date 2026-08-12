"""Tests for the application wiring: websocket protocol, blackout, callbacks."""
import pytest
from fastapi.testclient import TestClient

from backend import database as db_module
from backend import main as main_module
from backend.auth import get_current_user
from backend.database import Scene, SceneValue, get_db
from backend.dmx_interface import DMXInterface, DMXUniverse
from backend.websocket_manager import ConnectionManager


@pytest.fixture
def interface(monkeypatch):
    """Swap the global DMX interface for a private one with two universes."""
    dmx = DMXInterface()
    dmx.universes[1] = DMXUniverse(1)
    dmx.universes[2] = DMXUniverse(2)
    monkeypatch.setattr(main_module, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def ws_manager(monkeypatch):
    """A private connection manager so tests never touch real clients."""
    cm = ConnectionManager()
    monkeypatch.setattr(main_module, "manager", cm)
    return cm


@pytest.fixture
def client(interface, ws_manager, db_session):
    """A TestClient over the real app with auth and the database overridden.

    The client is *not* used as a context manager, so the lifespan (which
    would touch the real database and network) never runs.
    """
    app = main_module.app

    async def _user():
        return {"authenticated": True, "is_admin": True,
                "allowed_pages": [], "profile_name": "Test"}

    def _db():
        yield db_session

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Blackout endpoints
# ---------------------------------------------------------------------------
def test_blackout_status_endpoint(client, interface):
    assert client.get("/api/blackout/status").json() == {"blackout": False}


def test_blackout_endpoint_toggles(client, interface):
    interface.set_channel(1, 1, 200)

    assert client.post("/api/blackout").json() == {"status": "activated",
                                                   "blackout": True}
    assert interface.is_blackout_active() is True
    assert client.get("/api/blackout/status").json() == {"blackout": True}

    assert client.post("/api/blackout").json() == {"status": "released",
                                                   "blackout": False}
    assert interface.get_channel(1, 1) == 200


# ---------------------------------------------------------------------------
# dmx_callback
# ---------------------------------------------------------------------------
def test_dmx_callback_broadcasts_the_event(task_recorder):
    main_module.dmx_callback("channel_change", {"universe_id": 1})
    assert task_recorder.count == 1


# ---------------------------------------------------------------------------
# WebSocket protocol
# ---------------------------------------------------------------------------
def test_connect_receives_a_client_id(client):
    with client.websocket_connect("/ws") as ws:
        message = ws.receive_json()
        assert message["type"] == "connected"
        assert len(message["data"]["client_id"]) == 8


def test_set_channel_message(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channel", "universe_id": 1,
                      "channel": 3, "value": 200})
        ws.send_json({"type": "get_values", "universe_id": 1})
        values = ws.receive_json()["data"]["values"]

    assert values[2] == 200


def test_set_channel_tags_the_source_with_the_client_id(client, interface):
    with client.websocket_connect("/ws") as ws:
        client_id = ws.receive_json()["data"]["client_id"]
        ws.send_json({"type": "set_channel", "universe_id": 1,
                      "channel": 1, "value": 10})
        ws.send_json({"type": "get_values", "universe_id": 1})
        ws.receive_json()

    assert interface.get_channel_source(1, 1) == f"user_{client_id}"


def test_incomplete_set_channel_is_ignored(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channel", "universe_id": 1, "channel": 1})
        ws.send_json({"type": "get_values", "universe_id": 1})
        values = ws.receive_json()["data"]["values"]

    assert values[0] == 0


def test_set_channels_message(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channels", "universe_id": 1,
                      "values": {"1": 10, "2": 20}})
        ws.send_json({"type": "get_values", "universe_id": 1})
        values = ws.receive_json()["data"]["values"]

    assert values[:2] == [10, 20]


def test_get_all_universes_message(client, interface):
    interface.set_channel(2, 1, 55)

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "get_all_universes"})
        data = ws.receive_json()["data"]

    assert set(data) == {"1", "2"}
    assert data["2"][0] == 55


def test_get_input_values_messages(client, interface):
    interface.inputs[1] = object()
    interface._input_values[1] = [7] * 512

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()

        ws.send_json({"type": "get_input_values", "universe_id": 1})
        single = ws.receive_json()
        assert single["type"] == "input_values"
        assert single["data"]["values"][0] == 7

        ws.send_json({"type": "get_all_input_values"})
        everything = ws.receive_json()
        assert everything["type"] == "all_input_values"
        assert everything["data"]["1"][0] == 7


def test_grandmaster_messages(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_global_grandmaster", "value": 100})
        ws.send_json({"type": "set_universe_grandmaster", "universe_id": 1,
                      "value": 50})
        ws.send_json({"type": "get_grandmasters"})
        message = ws.receive_json()

    assert message["type"] == "grandmasters"
    assert message["data"] == {"global": 100, "universes": {"1": 50}}


@pytest.mark.parametrize("value", [-1, 256])
def test_out_of_range_grandmaster_values_are_ignored(client, interface, value):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_global_grandmaster", "value": value})
        ws.send_json({"type": "get_grandmasters"})
        message = ws.receive_json()

    assert message["data"]["global"] == 255


def test_set_active_scene_is_broadcast(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_active_scene", "scene_id": 7})
        message = ws.receive_json()

    assert message == {"type": "active_scene_changed", "data": {"scene_id": 7}}


def test_unknown_message_types_are_ignored(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "nonsense"})
        ws.send_json({"type": "get_values", "universe_id": 1})
        assert ws.receive_json()["type"] == "values"


def test_input_controlled_channels_snap_back(client, interface):
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 10}
    interface._input_values[1] = [0] * 512
    interface._input_values[1][0] = 42

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channel", "universe_id": 1,
                      "channel": 1, "value": 255})
        message = ws.receive_json()

    assert message["type"] == "input_to_ui"
    assert message["data"]["values"][0] == 42
    assert interface.get_channel(1, 1) == 0


def test_bulk_writes_split_blocked_and_allowed_channels(client, interface):
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 2}
    interface._input_values[1] = [0] * 512
    interface._input_values[1][0] = 42

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channels", "universe_id": 1,
                      "values": {"1": 255, "5": 128}})
        message = ws.receive_json()

    assert message["type"] == "input_to_ui"
    assert message["data"]["values"][0] == 42
    assert interface.get_channel(1, 1) == 0
    assert interface.get_channel(1, 5) == 128


def test_input_bypass_lets_writes_through(client, interface):
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 10}
    interface._input_values[1] = [0] * 512
    interface.set_input_bypass(True)

    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channel", "universe_id": 1,
                      "channel": 1, "value": 255})
        ws.send_json({"type": "set_channels", "universe_id": 1,
                      "values": {"2": 128}})
        ws.send_json({"type": "get_values", "universe_id": 1})
        values = ws.receive_json()["data"]["values"]

    assert values[0] == 255
    assert values[1] == 128


def test_disconnect_deregisters_the_client(client, ws_manager):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        assert len(ws_manager.active_connections) == 1

    assert ws_manager.active_connections == set()


# ---------------------------------------------------------------------------
# MIDI scene recall helper
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_midi_scene_recall_applies_scene_values(monkeypatch, db_session,
                                                      interface, ws_manager):
    scene = Scene(name="MIDI look")
    db_session.add(scene)
    db_session.commit()
    db_session.add(SceneValue(scene_id=scene.id, universe_id=1, channel=1,
                              value=222))
    db_session.commit()

    monkeypatch.setattr(db_module, "get_db", lambda: iter([db_session]))

    await main_module._recall_scene_from_midi(scene.id, 127)

    assert interface.get_channel(1, 1) == 222
    assert interface.get_channel_source(1, 1) == "midi_scene"


@pytest.mark.asyncio
async def test_midi_scene_recall_ignores_unknown_scenes(monkeypatch, db_session,
                                                        interface, ws_manager):
    monkeypatch.setattr(db_module, "get_db", lambda: iter([db_session]))
    await main_module._recall_scene_from_midi(999, 127)  # must not raise


# ---------------------------------------------------------------------------
# App wiring
# ---------------------------------------------------------------------------
def test_all_api_routers_are_mounted():
    paths = {route.path for route in main_module.app.routes}
    for expected in ("/api/auth/login", "/api/dmx/set", "/api/scenes",
                     "/api/patch", "/api/universes", "/api/fixtures",
                     "/api/backup/list", "/api/settings", "/api/io",
                     "/api/mapping", "/api/groups", "/api/remote/tokens",
                     "/api/help", "/api/monitor", "/api/midi/status",
                     "/api/blackout", "/ws"):
        assert expected in paths, expected


def test_cors_middleware_is_configured():
    assert any("CORSMiddleware" in str(m) for m in main_module.app.user_middleware)


# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------
@pytest.fixture
def lifespan_client(interface, ws_manager, db_session, monkeypatch):
    """A TestClient whose lifespan runs against the throw-away database."""
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    monkeypatch.setattr(main_module, "get_db", lambda: iter([db_session]))
    monkeypatch.setattr(db_module, "get_db", lambda: iter([db_session]))
    return TestClient(main_module.app)


def test_lifespan_loads_universes_and_outputs(lifespan_client, db_session,
                                              interface):
    from backend.database import Universe, UniverseOutput

    db_session.add(Universe(id=1, label="Main", device_type="mock",
                            config_json={}, enabled=True))
    db_session.add(Universe(id=2, label="Spare", device_type="mock",
                            config_json={}, enabled=False))
    db_session.commit()
    db_session.add(UniverseOutput(universe_id=1, device_type="mock",
                                  config_json={}, enabled=True, priority=0))
    db_session.commit()

    with lifespan_client:
        assert set(interface.universes) == {1, 2}
        assert len(interface.outputs[1]) == 1   # from UniverseOutput
        assert 2 not in interface.outputs       # disabled legacy output

    assert interface._running is False  # shutdown ran


def test_lifespan_registers_the_broadcast_callback(lifespan_client, interface):
    with lifespan_client:
        assert main_module.dmx_callback in interface._callbacks


def test_lifespan_loads_groups_mappings_and_parks(lifespan_client, db_session,
                                                  interface):
    from backend.database import (ChannelMapping, Group, GroupMember,
                                  MIDICCMapping, MIDITrigger, ParkedChannel,
                                  Universe)

    db_session.add(Universe(id=1, label="Main", device_type="mock",
                            config_json={}, enabled=False))
    group = Group(name="Warm", mode="follow", enabled=True)
    db_session.add(group)
    db_session.add(ChannelMapping(name="Desk", enabled=True,
                                  unmapped_behavior="ignore",
                                  mappings_json={"mappings": [
                                      {"src_universe": 1, "src_channel": 1,
                                       "dst_universe": 1, "dst_channel": 5}]}))
    db_session.add(MIDICCMapping(cc_number=7, input_channel=3, enabled=True))
    db_session.add(MIDITrigger(note=60, action="blackout", enabled=True))
    db_session.add(ParkedChannel(universe_id=1, channel=9, value=77))
    db_session.commit()
    db_session.add(GroupMember(group_id=group.id, universe_id=1, channel=1))
    db_session.commit()

    with lifespan_client:
        assert interface.get_group(group.id)["name"] == "Warm"
        assert interface.get_channel_mapping_status() == {
            "enabled": True, "unmapped_behavior": "ignore", "mapping_count": 1}
        assert len(interface._midi_cc_mappings) == 1
        assert len(interface._midi_triggers) == 1
        assert interface.get_parked_channels(1) == {9: 77}
        assert interface._scene_recall_callback is not None


def test_lifespan_starts_configured_inputs(lifespan_client, db_session,
                                           interface):
    from backend.database import Universe

    db_session.add(Universe(id=1, label="Main", device_type="mock",
                            config_json={}, enabled=False,
                            input_type="midi_input", input_config={},
                            input_enabled=True, passthrough_enabled=True,
                            passthrough_show_ui=True,
                            input_channel_start=5, input_channel_end=20))
    db_session.commit()

    with lifespan_client:
        assert 1 in interface.inputs
        config = interface._passthrough_config[1]
        assert config["passthrough_mode"] == "faders_output"
        assert (config["channel_start"], config["channel_end"]) == (5, 20)


# ---------------------------------------------------------------------------
# Malformed WebSocket writes (regression: these used to raise IndexError inside
# the handler, which the broad except caught by dropping the connection)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("channel", [0, 513, -5, 99999])
def test_out_of_range_channel_does_not_drop_the_connection(client, interface,
                                                           channel):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channel", "universe_id": 1,
                      "channel": channel, "value": 200})

        # The socket must still be usable afterwards
        ws.send_json({"type": "get_values", "universe_id": 1})
        message = ws.receive_json()

    assert message["type"] == "values"
    assert message["data"]["values"] == [0] * 512


def test_out_of_range_bulk_write_keeps_the_valid_channels(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channels", "universe_id": 1,
                      "values": {"1": 10, "513": 200, "0": 30}})
        ws.send_json({"type": "get_values", "universe_id": 1})
        values = ws.receive_json()["data"]["values"]

    assert values[0] == 10
    assert values[511] == 0   # channel 0 must not wrap onto channel 512
    assert sum(values) == 10


def test_out_of_range_value_does_not_drop_the_connection(client, interface):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "set_channel", "universe_id": 1,
                      "channel": 1, "value": 9999})
        ws.send_json({"type": "get_values", "universe_id": 1})
        values = ws.receive_json()["data"]["values"]

    assert values[0] == 0
