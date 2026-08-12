"""API tests for the I/O configuration endpoints."""
import pytest

from backend.api import io as io_api
from backend.database import Fixture, Patch, Scene, SceneValue, Universe, UniverseOutput
from backend.dmx_interface import DMXInterface


@pytest.fixture
def interface(monkeypatch):
    dmx = DMXInterface()
    monkeypatch.setattr(io_api, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def client(make_app, interface):
    return make_app(io_api.router, prefix="/api/io")


@pytest.fixture
def universe(db_session):
    universe = Universe(id=1, label="Main", device_type="mock", config_json={},
                        enabled=True)
    db_session.add(universe)
    db_session.commit()
    db_session.refresh(universe)
    return universe


# ---------------------------------------------------------------------------
# Reading configuration
# ---------------------------------------------------------------------------
def test_io_config_of_an_empty_system(client):
    body = client.get("/api/io").json()
    assert body["universes"] == []
    assert [p["id"] for p in body["output_protocols"]] == ["artnet", "sacn", "mock"]
    assert body["input_protocols"][0]["id"] == "none"


def test_universe_io_payload_shape(client, universe):
    body = client.get("/api/io/1").json()

    assert body["id"] == 1
    assert body["label"] == "Main"
    assert body["master_fader_color"] == "#00bcd4"
    assert body["input"] == {"input_type": "none", "config": {},
                             "enabled": False, "channel_start": 1,
                             "channel_end": 512, "status": None}
    assert body["passthrough"]["passthrough_mode"] == "off"
    assert body["passthrough"]["merge_mode"] == "htp"


def test_legacy_output_is_reported_when_no_output_rows_exist(client, universe):
    outputs = client.get("/api/io/1").json()["outputs"]
    assert outputs == [{"id": None, "device_type": "mock", "config": {},
                        "enabled": True, "priority": 0, "status": None}]


def test_get_io_for_a_missing_universe_is_404(client):
    assert client.get("/api/io/99").status_code == 404


@pytest.mark.parametrize("enabled,show_ui,expected", [
    (False, False, "off"),
    (False, True, "view_only"),
    (True, True, "faders_output"),
    (True, False, "output_only"),
])
def test_passthrough_mode_is_derived_from_legacy_flags(client, db_session,
                                                       universe, enabled,
                                                       show_ui, expected):
    universe.passthrough_enabled = enabled
    universe.passthrough_show_ui = show_ui
    db_session.commit()

    body = client.get("/api/io/1").json()
    assert body["passthrough"]["passthrough_mode"] == expected
    assert body["passthrough"]["enabled"] is enabled
    assert body["passthrough"]["show_ui"] is show_ui


# ---------------------------------------------------------------------------
# Updating the combined configuration
# ---------------------------------------------------------------------------
def test_update_output_settings(client, db_session, universe, interface):
    body = client.put("/api/io/1", json={
        "device_type": "artnet", "config_json": {"ip": "10.0.0.5"},
        "enabled": True}).json()

    assert body["output"]["device_type"] == "artnet"
    assert body["output"]["config"] == {"ip": "10.0.0.5"}
    assert 1 in interface.outputs


def test_update_enables_an_input(client, universe, interface):
    client.put("/api/io/1", json={
        "input_type": "midi_input", "input_config": {"device_name": "X"},
        "input_enabled": True})

    assert 1 in interface.inputs


def test_update_removes_a_disabled_input(client, universe, interface):
    client.put("/api/io/1", json={"input_type": "midi_input",
                                  "input_enabled": True})
    assert 1 in interface.inputs

    client.put("/api/io/1", json={"input_enabled": False})
    assert interface.inputs == {}


def test_update_stores_passthrough_flags(client, universe):
    body = client.put("/api/io/1", json={
        "passthrough_enabled": True, "passthrough_show_ui": True,
        "passthrough_mode": "ltp"}).json()

    assert body["passthrough"]["passthrough_mode"] == "faders_output"
    assert body["passthrough"]["merge_mode"] == "ltp"


def test_update_missing_universe_is_404(client):
    assert client.put("/api/io/99", json={"enabled": True}).status_code == 404


# ---------------------------------------------------------------------------
# Multiple outputs
# ---------------------------------------------------------------------------
def test_output_list_is_empty_initially(client, universe):
    assert client.get("/api/io/1/outputs").json() == {"outputs": []}


def test_add_an_output(client, db_session, universe, interface):
    body = client.post("/api/io/1/outputs", json={
        "device_type": "mock", "config_json": {"log_level": "debug"},
        "enabled": True}).json()

    assert body["device_type"] == "mock"
    assert body["priority"] == 0
    assert db_session.query(UniverseOutput).count() == 1
    assert len(interface.outputs[1]) == 1


def test_outputs_get_increasing_priorities(client, universe):
    first = client.post("/api/io/1/outputs",
                        json={"device_type": "mock"}).json()
    second = client.post("/api/io/1/outputs",
                         json={"device_type": "mock"}).json()

    assert (first["priority"], second["priority"]) == (0, 1)


def test_added_outputs_are_listed(client, universe):
    client.post("/api/io/1/outputs", json={"device_type": "mock"})
    outputs = client.get("/api/io/1/outputs").json()["outputs"]

    assert len(outputs) == 1
    assert outputs[0]["status"]["protocol"] == "mock"


def test_a_disabled_output_is_not_started(client, universe, interface):
    client.post("/api/io/1/outputs",
                json={"device_type": "mock", "enabled": False})
    assert interface.outputs[1][0].running is False


def test_update_an_output(client, universe, interface):
    created = client.post("/api/io/1/outputs",
                          json={"device_type": "mock"}).json()

    body = client.put(f"/api/io/1/outputs/{created['id']}", json={
        "device_type": "mock", "config_json": {"log_level": "debug"},
        "enabled": True}).json()

    assert body["config"] == {"log_level": "debug"}
    assert len(interface.outputs[1]) == 1  # replaced, not duplicated


def test_delete_an_output(client, db_session, universe, interface):
    created = client.post("/api/io/1/outputs",
                          json={"device_type": "mock"}).json()

    assert client.delete(f"/api/io/1/outputs/{created['id']}").json() == {
        "status": "deleted", "output_id": created["id"]}
    assert db_session.query(UniverseOutput).count() == 0
    assert interface.outputs[1] == []


def test_output_endpoints_validate_the_universe(client):
    assert client.get("/api/io/99/outputs").status_code == 404
    assert client.post("/api/io/99/outputs",
                       json={"device_type": "mock"}).status_code == 404


def test_output_endpoints_validate_the_output_id(client, universe):
    assert client.put("/api/io/1/outputs/99",
                      json={"device_type": "mock"}).status_code == 404
    assert client.delete("/api/io/1/outputs/99").status_code == 404


# ---------------------------------------------------------------------------
# Input configuration
# ---------------------------------------------------------------------------
def test_configure_an_input(client, db_session, universe, interface):
    body = client.put("/api/io/1/input", json={
        "input_type": "midi_input", "input_config": {"device_name": "APC"},
        "input_enabled": True, "input_channel_start": 10,
        "input_channel_end": 20}).json()

    assert body["input"]["input_type"] == "midi_input"
    assert body["input"]["channel_start"] == 10
    assert body["input"]["channel_end"] == 20
    assert 1 in interface.inputs
    assert interface._passthrough_config[1]["channel_start"] == 10


def test_configuring_input_none_removes_the_runtime_input(client, universe,
                                                          interface):
    client.put("/api/io/1/input", json={"input_type": "midi_input",
                                        "input_enabled": True})
    client.put("/api/io/1/input", json={"input_type": "none",
                                        "input_enabled": False})
    assert interface.inputs == {}


def test_configure_input_missing_universe_is_404(client):
    assert client.put("/api/io/99/input",
                      json={"input_type": "none"}).status_code == 404


def test_enable_and_disable_input_endpoints(client, db_session, universe,
                                            interface):
    universe.input_type = "midi_input"
    db_session.commit()

    assert client.post("/api/io/1/input/enable").json() == {
        "status": "enabled", "universe_id": 1}
    assert 1 in interface.inputs

    assert client.post("/api/io/1/input/disable").json() == {
        "status": "disabled", "universe_id": 1}
    assert interface.inputs == {}


def test_enable_input_requires_a_configured_type(client, universe):
    response = client.post("/api/io/1/input/enable")
    assert response.status_code == 400
    assert response.json()["detail"] == "No input type configured"


def test_input_enable_disable_validate_the_universe(client):
    assert client.post("/api/io/99/input/enable").status_code == 404
    assert client.post("/api/io/99/input/disable").status_code == 404


# ---------------------------------------------------------------------------
# Passthrough configuration
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode,enabled,show_ui", [
    ("off", False, False),
    ("view_only", False, True),
    ("faders_output", True, True),
    ("output_only", True, False),
])
def test_configure_passthrough_modes(client, db_session, universe, interface,
                                     mode, enabled, show_ui):
    body = client.put("/api/io/1/passthrough", json={
        "passthrough_mode": mode, "merge_mode": "ltp"}).json()

    assert body["passthrough"]["passthrough_mode"] == mode
    db_session.expire_all()
    stored = db_session.query(Universe).one()
    assert stored.passthrough_enabled is enabled
    assert stored.passthrough_show_ui is show_ui
    assert interface._passthrough_config[1]["passthrough_mode"] == mode
    assert interface._passthrough_config[1]["mode"] == "ltp"


def test_passthrough_legacy_fields_still_work(client, db_session, universe):
    client.put("/api/io/1/passthrough", json={
        "passthrough_mode": "legacy", "passthrough_enabled": True,
        "passthrough_show_ui": False, "merge_mode": "htp"})

    db_session.expire_all()
    stored = db_session.query(Universe).one()
    assert stored.passthrough_enabled is True
    assert stored.passthrough_show_ui is False


def test_configure_passthrough_missing_universe_is_404(client):
    assert client.put("/api/io/99/passthrough",
                      json={"passthrough_mode": "off"}).status_code == 404


# ---------------------------------------------------------------------------
# Input bypass
# ---------------------------------------------------------------------------
def test_bypass_round_trip(client, interface):
    assert client.get("/api/io/bypass").json() == {"bypass": False}

    assert client.put("/api/io/bypass", json={"bypass": True}).json() == {
        "bypass": True}
    assert interface.get_input_bypass() is True
    assert client.get("/api/io/bypass").json() == {"bypass": True}


def test_bypass_requires_the_permission(make_app, interface):
    restricted = make_app(io_api.router, prefix="/api/io",
                          user={"can_bypass": False})
    response = restricted.put("/api/io/bypass", json={"bypass": True})

    assert response.status_code == 403
    assert interface.get_input_bypass() is False


# ---------------------------------------------------------------------------
# Protocol listings & interfaces
# ---------------------------------------------------------------------------
def test_protocol_listings(client):
    assert [p["id"] for p in client.get("/api/io/protocols/output").json()["protocols"]] \
        == ["artnet", "sacn", "mock"]
    assert [p["id"] for p in client.get("/api/io/protocols/input").json()["protocols"]] \
        == ["none", "artnet_input", "sacn_input", "midi_input"]


def test_network_interfaces_listing(client):
    interfaces = client.get("/api/io/network/interfaces").json()["interfaces"]
    assert isinstance(interfaces, list)
    for iface in interfaces:
        assert {"interface", "ip", "netmask", "broadcast"} == set(iface)
        assert not iface["ip"].startswith("127.")


# ---------------------------------------------------------------------------
# Channel usage
#
# `/channel-usage` must stay declared ahead of the dynamic `/{universe_id}`
# route, otherwise the literal path is parsed as a universe ID and 422s.
# ---------------------------------------------------------------------------
def test_channel_usage_route_is_not_shadowed_by_the_universe_route(client,
                                                                   universe):
    response = client.get("/api/io/channel-usage")
    assert response.status_code == 200
    assert "universes" in response.json()


def test_channel_usage_is_declared_before_the_dynamic_route():
    paths = [route.path for route in io_api.router.routes]
    assert paths.index("/channel-usage") < paths.index("/{universe_id}")


def test_channel_usage_for_an_empty_universe(client, universe):
    usage = client.get("/api/io/channel-usage").json()["universes"]["1"]

    assert usage["highest_patched"] == 0
    assert usage["highest_scene"] == 0
    assert usage["highest_used"] == 0
    assert usage["patch_count"] == 0
    assert usage["patched_channels"] == []


def test_channel_usage_counts_patched_channels(client, db_session, universe):
    fixture = Fixture(name="RGB", definition_json={
        "channels": [{"name": "R"}, {"name": "G"}, {"name": "B"}]})
    db_session.add(fixture)
    db_session.commit()
    db_session.add(Patch(fixture_id=fixture.id, universe_id=1, start_channel=10))
    db_session.commit()

    usage = client.get("/api/io/channel-usage").json()["universes"]["1"]

    assert usage["highest_patched"] == 12
    assert usage["patched_count"] == 3
    assert usage["patched_channels"] == [10, 11, 12]


def test_channel_usage_infers_a_count_when_absent(client, db_session, universe):
    fixture = Fixture(name="Odd", definition_json={"channelCount": 4})
    db_session.add(fixture)
    db_session.commit()
    db_session.add(Patch(fixture_id=fixture.id, universe_id=1, start_channel=1))
    db_session.commit()

    usage = client.get("/api/io/channel-usage").json()["universes"]["1"]
    assert usage["highest_patched"] == 4


def test_channel_usage_defaults_to_one_channel(client, db_session, universe):
    fixture = Fixture(name="Mystery", definition_json={})
    db_session.add(fixture)
    db_session.commit()
    db_session.add(Patch(fixture_id=fixture.id, universe_id=1, start_channel=7))
    db_session.commit()

    usage = client.get("/api/io/channel-usage").json()["universes"]["1"]
    assert usage["highest_patched"] == 7
    assert usage["patched_channels"] == [7]


def test_channel_usage_includes_scene_values(client, db_session, universe):
    scene = Scene(name="Look")
    db_session.add(scene)
    db_session.commit()
    db_session.add_all([
        SceneValue(scene_id=scene.id, universe_id=1, channel=50, value=255),
        SceneValue(scene_id=scene.id, universe_id=1, channel=90, value=0),
    ])
    db_session.commit()

    usage = client.get("/api/io/channel-usage").json()["universes"]["1"]
    assert usage["highest_scene"] == 50  # zero-valued channel 90 is ignored
    assert usage["highest_used"] == 50
