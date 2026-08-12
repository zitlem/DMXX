"""API tests for MIDI devices, CC mappings, triggers and feedback."""
import pytest

from backend.api import midi as midi_api
from backend.database import MIDICCMapping, MIDITrigger
from backend.dmx_interface import DMXInterface


class FakeHandler:
    """Minimal MIDI handler stand-in for the router's test endpoints."""

    def __init__(self, ok=True):
        self.ok = ok
        self.cc = []
        self.notes = []

    def send_cc(self, channel, control, value):
        self.cc.append((channel, control, value))
        return self.ok

    def send_note_on(self, channel, note, velocity=127):
        self.notes.append((channel, note, velocity))
        return self.ok


@pytest.fixture
def interface(monkeypatch):
    dmx = DMXInterface()
    monkeypatch.setattr(midi_api, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def client(make_app, interface):
    return make_app(midi_api.router, prefix="/api/midi")


def with_output_running(interface, handler):
    """Make get_midi_status() report a running output backed by `handler`."""
    interface._midi_handler = handler
    handler.get_status = lambda: {
        "available": True,
        "input": {"running": False, "device": None, "devices": [],
                  "messages_received": 0},
        "output": {"running": True, "device": "Fake", "messages_sent": 0},
        "learn_mode": False,
        "last_message": None,
        "network": {"server_running": False, "port": None, "peers": []},
    }


# ---------------------------------------------------------------------------
# Devices & status
# ---------------------------------------------------------------------------
def test_device_listing(client):
    body = client.get("/api/midi/devices").json()
    assert set(body) == {"inputs", "outputs"}
    assert isinstance(body["inputs"], list)


def test_status_without_a_handler(client):
    body = client.get("/api/midi/status").json()
    assert body["input"]["running"] is False
    assert body["output"]["running"] is False


def test_stop_input_and_output_are_safe(client):
    assert client.post("/api/midi/input/stop").json() == {"status": "stopped"}
    assert client.post("/api/midi/output/stop").json() == {"status": "stopped"}


def test_start_input_reports_unavailable_midi(client, monkeypatch):
    from backend import midi_handler

    monkeypatch.setattr(midi_handler, "MIDO_AVAILABLE", False)
    response = client.post("/api/midi/input/start", json={})
    assert response.status_code == 503
    assert "not available" in response.json()["detail"]


def test_start_output_reports_unavailable_midi(client, monkeypatch):
    from backend import midi_handler

    monkeypatch.setattr(midi_handler, "MIDO_AVAILABLE", False)
    assert client.post("/api/midi/output/start", json={}).status_code == 503


def test_start_input_reports_a_failed_device(client, interface, monkeypatch):
    async def _fail(device_name=None):
        return False

    monkeypatch.setattr(interface, "start_midi_input", _fail)
    response = client.post("/api/midi/input/start",
                           json={"device_name": "Nope"})
    assert response.status_code == 400
    assert "Check device name" in response.json()["detail"]


def test_start_input_success(client, interface, monkeypatch):
    async def _ok(device_name=None):
        return True

    monkeypatch.setattr(interface, "start_midi_input", _ok)
    assert client.post("/api/midi/input/start",
                       json={"device_name": "APC"}).json()["status"] == "started"


def test_start_output_success(client, interface, monkeypatch):
    async def _ok(device_name=None):
        return True

    monkeypatch.setattr(interface, "start_midi_output", _ok)
    assert client.post("/api/midi/output/start",
                       json={}).json()["status"] == "started"


# ---------------------------------------------------------------------------
# Learn mode
# ---------------------------------------------------------------------------
def test_learn_mode_endpoints(client):
    assert client.post("/api/midi/learn/start").json() == {"status": "learning"}

    body = client.post("/api/midi/learn/stop").json()
    assert body["status"] == "stopped"
    assert body["last_message"] is None


def test_last_learned_message_is_empty_without_a_handler(client):
    assert client.get("/api/midi/learn/last").json() == {"message": None}


def test_last_learned_note_gets_a_note_name(client, interface):
    class Handler:
        def get_last_learned_message(self):
            return {"type": "note_on", "note": 60}

    interface._midi_handler = Handler()
    body = client.get("/api/midi/learn/last").json()
    assert body["message"]["note_name"] == "C4"


# ---------------------------------------------------------------------------
# Test send endpoints
# ---------------------------------------------------------------------------
def test_test_cc_requires_a_running_output(client):
    response = client.post("/api/midi/test/cc")
    assert response.status_code == 400
    assert response.json()["detail"] == "MIDI output not running"


def test_test_cc_sends_a_message(client, interface):
    handler = FakeHandler()
    with_output_running(interface, handler)

    body = client.post("/api/midi/test/cc?channel=1&control=7&value=100").json()

    assert body == {"status": "sent", "channel": 1, "control": 7, "value": 100}
    assert handler.cc == [(1, 7, 100)]


def test_test_cc_reports_send_failures(client, interface):
    with_output_running(interface, FakeHandler(ok=False))
    response = client.post("/api/midi/test/cc")
    assert response.status_code == 400
    assert response.json()["detail"] == "Failed to send MIDI CC"


def test_test_note_sends_a_message(client, interface):
    handler = FakeHandler()
    with_output_running(interface, handler)

    body = client.post("/api/midi/test/note?note=60&velocity=100").json()

    assert body["note_name"] == "C4"
    assert handler.notes == [(0, 60, 100)]


def test_test_note_requires_a_running_output(client):
    assert client.post("/api/midi/test/note").status_code == 400


# ---------------------------------------------------------------------------
# CC mappings
# ---------------------------------------------------------------------------
def test_cc_mapping_list_is_empty_initially(client):
    assert client.get("/api/midi/cc-mappings").json() == []


def test_create_a_cc_mapping(client, db_session, interface):
    body = client.post("/api/midi/cc-mappings", json={
        "cc_number": 7, "input_channel": 3, "label": "Fader 1"}).json()

    assert body["cc_number"] == 7
    assert body["input_channel"] == 3
    assert body["midi_channel"] == -1
    assert body["enabled"] is True
    assert db_session.query(MIDICCMapping).count() == 1
    assert len(interface._midi_cc_mappings) == 1


def test_create_a_device_specific_cc_mapping(client):
    body = client.post("/api/midi/cc-mappings", json={
        "cc_number": 1, "input_channel": 1, "device_name": "APC"}).json()
    assert body["device_name"] == "APC"


def test_update_a_cc_mapping(client, interface):
    created = client.post("/api/midi/cc-mappings",
                          json={"cc_number": 7, "input_channel": 3}).json()

    body = client.put(f"/api/midi/cc-mappings/{created['id']}", json={
        "cc_number": 8, "midi_channel": 2, "input_channel": 4,
        "label": "Renamed"}).json()

    assert body["cc_number"] == 8
    assert body["midi_channel"] == 2
    assert body["input_channel"] == 4
    assert body["label"] == "Renamed"
    assert interface._midi_cc_mappings[0]["cc_number"] == 8


def test_clearing_the_device_name_with_an_empty_string(client):
    created = client.post("/api/midi/cc-mappings", json={
        "cc_number": 7, "input_channel": 3, "device_name": "APC"}).json()

    body = client.put(f"/api/midi/cc-mappings/{created['id']}",
                      json={"device_name": ""}).json()
    assert body["device_name"] is None


def test_disabling_a_cc_mapping_drops_it_from_the_runtime(client, interface):
    created = client.post("/api/midi/cc-mappings",
                          json={"cc_number": 7, "input_channel": 3}).json()

    client.put(f"/api/midi/cc-mappings/{created['id']}", json={"enabled": False})
    assert interface._midi_cc_mappings == []


def test_update_missing_cc_mapping_is_404(client):
    assert client.put("/api/midi/cc-mappings/99",
                      json={"cc_number": 1}).status_code == 404


def test_delete_a_cc_mapping(client, db_session, interface):
    created = client.post("/api/midi/cc-mappings",
                          json={"cc_number": 7, "input_channel": 3}).json()

    assert client.delete(f"/api/midi/cc-mappings/{created['id']}").json() == {
        "status": "deleted"}
    assert db_session.query(MIDICCMapping).count() == 0
    assert interface._midi_cc_mappings == []


def test_delete_missing_cc_mapping_is_404(client):
    assert client.delete("/api/midi/cc-mappings/99").status_code == 404


def test_create_cc_mapping_requires_its_fields(client):
    assert client.post("/api/midi/cc-mappings",
                       json={"cc_number": 7}).status_code == 422


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------
def test_trigger_list_is_empty_initially(client):
    assert client.get("/api/midi/triggers").json() == []


def test_create_a_trigger(client, db_session, interface):
    body = client.post("/api/midi/triggers", json={
        "note": 60, "action": "scene", "target_id": 4,
        "label": "Look 1"}).json()

    assert body["note"] == 60
    assert body["action"] == "scene"
    assert body["target_id"] == 4
    assert db_session.query(MIDITrigger).count() == 1
    assert len(interface._midi_triggers) == 1


def test_create_a_blackout_trigger(client):
    body = client.post("/api/midi/triggers",
                       json={"note": 61, "action": "blackout"}).json()
    assert body["target_id"] is None


def test_update_a_trigger(client, interface):
    created = client.post("/api/midi/triggers",
                          json={"note": 60, "action": "scene"}).json()

    body = client.put(f"/api/midi/triggers/{created['id']}", json={
        "note": 62, "action": "group", "target_id": 2,
        "midi_channel": 3}).json()

    assert body["note"] == 62
    assert body["action"] == "group"
    assert body["target_id"] == 2
    assert interface._midi_triggers[0]["note"] == 62


def test_disabling_a_trigger_drops_it_from_the_runtime(client, interface):
    created = client.post("/api/midi/triggers",
                          json={"note": 60, "action": "blackout"}).json()

    client.put(f"/api/midi/triggers/{created['id']}", json={"enabled": False})
    assert interface._midi_triggers == []


def test_update_missing_trigger_is_404(client):
    assert client.put("/api/midi/triggers/99", json={"note": 1}).status_code == 404


def test_delete_a_trigger(client, db_session, interface):
    created = client.post("/api/midi/triggers",
                          json={"note": 60, "action": "blackout"}).json()

    assert client.delete(f"/api/midi/triggers/{created['id']}").json() == {
        "status": "deleted"}
    assert db_session.query(MIDITrigger).count() == 0
    assert interface._midi_triggers == []


def test_delete_missing_trigger_is_404(client):
    assert client.delete("/api/midi/triggers/99").status_code == 404


def test_create_trigger_requires_an_action(client):
    assert client.post("/api/midi/triggers", json={"note": 60}).status_code == 422


# ---------------------------------------------------------------------------
# Input integration
# ---------------------------------------------------------------------------
def test_input_status_endpoint(client, interface):
    body = client.get("/api/midi/input/status").json()
    assert body["type"] == "midi"
    assert body["enabled"] is False
    assert body["active_channels"] == 0


def test_input_values_endpoint(client):
    assert client.get("/api/midi/input/values").json() == {"values": [0] * 512}


def test_enable_and_disable_input_integration(client, interface):
    client.post("/api/midi/cc-mappings", json={"cc_number": 1,
                                               "input_channel": 1})
    interface.load_midi_cc_mappings([])  # simulate runtime drift

    assert client.post("/api/midi/input/enable").json() == {"status": "enabled"}
    assert interface._midi_input_enabled is True
    assert len(interface._midi_cc_mappings) == 1  # reloaded from the database

    assert client.post("/api/midi/input/disable").json() == {"status": "disabled"}
    assert interface._midi_input_enabled is False


def test_connected_devices_listing(client, interface):
    body = client.get("/api/midi/input/connected-devices").json()
    assert body == {"usb_devices": [], "network_devices": [], "all_devices": []}


def test_connect_reports_a_failure(client, interface, monkeypatch):
    async def _fail(device_name=None):
        return False

    monkeypatch.setattr(interface, "start_midi_input", _fail)
    response = client.post("/api/midi/input/connect",
                           json={"device_name": "Ghost"})
    assert response.status_code == 400
    assert "Ghost" in response.json()["detail"]


def test_connect_success_reloads_mappings(client, interface, monkeypatch):
    async def _ok(device_name=None):
        return True

    monkeypatch.setattr(interface, "start_midi_input", _ok)
    client.post("/api/midi/cc-mappings", json={"cc_number": 1,
                                               "input_channel": 1})
    interface.load_midi_cc_mappings([])

    body = client.post("/api/midi/input/connect",
                       json={"device_name": "APC"}).json()

    assert body == {"status": "connected", "device": "APC"}
    assert len(interface._midi_cc_mappings) == 1


# ---------------------------------------------------------------------------
# Network MIDI
# ---------------------------------------------------------------------------
def test_network_status_without_a_handler(client):
    """No handler yet, so only the availability flag is reported."""
    body = client.get("/api/midi/network/status").json()
    assert set(body) == {"available"}
    assert isinstance(body["available"], bool)


def test_network_status_with_a_handler(client, interface):
    class Handler:
        def get_status(self):
            return {"network": {"server_running": True, "port": 5004,
                                "peers": []}}

    interface._midi_handler = Handler()
    body = client.get("/api/midi/network/status").json()
    assert body["server_running"] is True
    assert body["port"] == 5004


def test_network_peers_listing(client):
    assert client.get("/api/midi/network/peers").json() == {"peers": []}


def test_starting_the_network_server_without_pymidi(client, monkeypatch):
    from backend import midi_handler

    monkeypatch.setattr(midi_handler, "PYMIDI_AVAILABLE", False)
    response = client.post("/api/midi/network/server/start", json={})
    assert response.status_code == 503
    assert "pymidi" in response.json()["detail"]


def test_stopping_the_network_server_is_safe(client):
    assert client.post("/api/midi/network/server/stop").json() == {
        "status": "stopped"}


# ---------------------------------------------------------------------------
# Output feedback
# ---------------------------------------------------------------------------
def test_feedback_toggle(client, interface):
    assert client.get("/api/midi/output/feedback/status").json() == {
        "enabled": False}

    assert client.post("/api/midi/output/feedback/enable").json() == {
        "status": "enabled"}
    assert interface._midi_output_enabled is True
    assert client.get("/api/midi/output/feedback/status").json() == {
        "enabled": True}

    assert client.post("/api/midi/output/feedback/disable").json() == {
        "status": "disabled"}
    assert interface._midi_output_enabled is False
