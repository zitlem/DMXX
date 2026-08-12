"""API tests for universe management and grand master endpoints."""
import pytest

from backend.api import universes as universes_api
from backend.database import Universe
from backend.dmx_interface import DMXInterface


@pytest.fixture
def dmx(monkeypatch):
    """Give the router a private DMX interface instead of the global one."""
    interface = DMXInterface()
    monkeypatch.setattr(universes_api, "dmx_interface", interface)
    return interface


@pytest.fixture
def client(make_app, dmx):
    return make_app(universes_api.router, prefix="/api/universes")


def add_universe(db, universe_id=1, label="Main", device_type="mock",
                 enabled=False):
    universe = Universe(id=universe_id, label=label, device_type=device_type,
                        config_json={}, enabled=enabled)
    db.add(universe)
    db.commit()
    db.refresh(universe)
    return universe


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def test_list_is_empty_initially(client):
    assert client.get("/api/universes").json() == {"universes": []}


def test_universe_payload_shape(client, db_session):
    add_universe(db_session, label="Stage", device_type="artnet")

    universe = client.get("/api/universes").json()["universes"][0]
    assert universe["id"] == 1
    assert universe["label"] == "Stage"
    assert universe["device_type"] == "artnet"
    assert universe["enabled"] is False
    assert universe["master_fader_color"] == "#00bcd4"
    assert universe["input"] == {"input_type": "none", "config": {},
                                 "enabled": False}
    assert universe["active"] is False


def test_active_flag_reflects_the_dmx_interface(client, db_session, dmx):
    add_universe(db_session)
    dmx.universes[1] = __import__(
        "backend.dmx_interface", fromlist=["DMXUniverse"]).DMXUniverse(1)
    dmx.universes[1].active = True

    assert client.get("/api/universes").json()["universes"][0]["active"] is True


def test_get_one_universe(client, db_session):
    add_universe(db_session, label="Stage")
    assert client.get("/api/universes/1").json()["label"] == "Stage"


def test_get_missing_universe_is_404(client):
    assert client.get("/api/universes/99").status_code == 404


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def test_create_universe_assigns_the_next_id(client, db_session):
    first = client.post("/api/universes", json={"label": "One"}).json()
    second = client.post("/api/universes", json={"label": "Two"}).json()

    assert first["id"] == 1
    assert second["id"] == 2
    assert db_session.query(Universe).count() == 2


def test_create_defaults(client):
    body = client.post("/api/universes", json={"label": "Defaults"}).json()
    assert body["device_type"] == "artnet"
    assert body["enabled"] is False
    assert body["config"] == {}


def test_create_with_a_custom_colour(client):
    body = client.post("/api/universes",
                       json={"label": "Coloured",
                             "master_fader_color": "#123456"}).json()
    assert body["master_fader_color"] == "#123456"


def test_creating_an_enabled_universe_registers_an_output(client, dmx):
    client.post("/api/universes",
                json={"label": "Live", "device_type": "mock", "enabled": True})

    assert 1 in dmx.universes
    assert len(dmx.outputs[1]) == 1


def test_creating_a_disabled_universe_does_not_register_output(client, dmx):
    client.post("/api/universes", json={"label": "Idle", "enabled": False})
    assert dmx.outputs == {}


def test_create_requires_a_label(client):
    assert client.post("/api/universes", json={}).status_code == 422


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def test_update_universe_fields(client, db_session):
    add_universe(db_session)

    body = client.put("/api/universes/1", json={
        "label": "Renamed", "device_type": "sacn",
        "config_json": {"universe": 4}, "master_fader_color": "#abcdef",
    }).json()

    assert body["label"] == "Renamed"
    assert body["device_type"] == "sacn"
    assert body["config"] == {"universe": 4}
    assert body["master_fader_color"] == "#abcdef"


def test_enabling_via_update_registers_an_output(client, db_session, dmx):
    add_universe(db_session, enabled=False)

    client.put("/api/universes/1", json={"enabled": True})
    assert 1 in dmx.outputs


def test_disabling_via_update_removes_the_universe(client, db_session, dmx):
    add_universe(db_session, enabled=True)
    client.post("/api/universes/1/enable")
    assert 1 in dmx.outputs

    client.put("/api/universes/1", json={"enabled": False})
    assert 1 not in dmx.universes


def test_config_changes_reconfigure_a_live_universe(client, db_session, dmx):
    add_universe(db_session, enabled=True)
    client.post("/api/universes/1/enable")
    first_output = dmx.outputs[1][0]

    client.put("/api/universes/1", json={"config_json": {"ip": "10.0.0.9"}})
    assert dmx.outputs[1][0] is not first_output


def test_update_missing_universe_is_404(client):
    assert client.put("/api/universes/99", json={"label": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# Enable / disable / delete
# ---------------------------------------------------------------------------
def test_enable_endpoint(client, db_session, dmx):
    add_universe(db_session)

    assert client.post("/api/universes/1/enable").json() == {
        "status": "enabled", "universe_id": 1}
    assert db_session.query(Universe).one().enabled is True
    assert 1 in dmx.outputs


def test_disable_endpoint(client, db_session, dmx):
    add_universe(db_session, enabled=True)
    client.post("/api/universes/1/enable")

    assert client.post("/api/universes/1/disable").json() == {
        "status": "disabled", "universe_id": 1}
    assert db_session.query(Universe).one().enabled is False
    assert 1 not in dmx.universes


def test_enable_and_disable_require_a_known_universe(client):
    assert client.post("/api/universes/99/enable").status_code == 404
    assert client.post("/api/universes/99/disable").status_code == 404


def test_delete_universe(client, db_session, dmx):
    add_universe(db_session, enabled=True)
    client.post("/api/universes/1/enable")

    assert client.delete("/api/universes/1").json() == {
        "status": "deleted", "universe_id": 1}
    assert db_session.query(Universe).count() == 0
    assert 1 not in dmx.universes


def test_delete_missing_universe_is_404(client):
    assert client.delete("/api/universes/99").status_code == 404


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------
def test_protocol_listing(client):
    protocols = client.get("/api/universes/protocols/list").json()["protocols"]
    assert [p["id"] for p in protocols] == ["artnet", "sacn", "mock"]


# ---------------------------------------------------------------------------
# Grand masters
# ---------------------------------------------------------------------------
def test_grandmaster_defaults(client):
    assert client.get("/api/universes/grandmaster").json() == {
        "global": 255, "universes": {}}


def test_set_global_grandmaster(client, dmx):
    response = client.post("/api/universes/grandmaster/global", json={"value": 128})

    assert response.json() == {"status": "ok", "global_grandmaster": 128}
    assert dmx.get_global_grandmaster() == 128


@pytest.mark.parametrize("value", [-1, 256, 1000])
def test_global_grandmaster_range_is_validated(client, dmx, value):
    response = client.post("/api/universes/grandmaster/global", json={"value": value})
    assert response.status_code == 400
    assert dmx.get_global_grandmaster() == 255


def test_set_universe_grandmaster(client, db_session, dmx):
    add_universe(db_session)

    response = client.post("/api/universes/1/grandmaster", json={"value": 100})

    assert response.json() == {"status": "ok", "universe_id": 1, "grandmaster": 100}
    assert dmx.get_universe_grandmaster(1) == 100
    assert client.get("/api/universes/1/grandmaster").json()["grandmaster"] == 100


def test_universe_grandmaster_requires_a_known_universe(client):
    assert client.post("/api/universes/99/grandmaster",
                       json={"value": 10}).status_code == 404
    assert client.get("/api/universes/99/grandmaster").status_code == 404


@pytest.mark.parametrize("value", [-1, 300])
def test_universe_grandmaster_range_is_validated(client, db_session, value):
    add_universe(db_session)
    assert client.post("/api/universes/1/grandmaster",
                       json={"value": value}).status_code == 400


def test_grandmaster_summary_includes_universes(client, db_session):
    add_universe(db_session)
    client.post("/api/universes/1/grandmaster", json={"value": 10})
    client.post("/api/universes/grandmaster/global", json={"value": 20})

    assert client.get("/api/universes/grandmaster").json() == {
        "global": 20, "universes": {"1": 10}}
