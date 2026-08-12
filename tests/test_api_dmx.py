"""API tests for direct DMX control, parking and highlight."""
import pytest

from backend import database as db_module
from backend.api import dmx as dmx_api
from backend.database import ParkedChannel
from backend.dmx_interface import DMXInterface, DMXUniverse


@pytest.fixture
def interface(monkeypatch):
    """A private DMX interface with universes 1 and 2 for the router."""
    dmx = DMXInterface()
    dmx.universes[1] = DMXUniverse(1)
    dmx.universes[2] = DMXUniverse(2)
    monkeypatch.setattr(dmx_api, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def client(make_app, interface, db_sessionmaker, monkeypatch):
    # park/unpark open their own session via database.SessionLocal
    monkeypatch.setattr(db_module, "SessionLocal", db_sessionmaker)
    return make_app(dmx_api.router, prefix="/api/dmx")


def restricted_client(make_app, **permissions):
    return make_app(dmx_api.router, prefix="/api/dmx", user=permissions)


# ---------------------------------------------------------------------------
# Reading values
# ---------------------------------------------------------------------------
def test_get_values_for_a_universe(client, interface):
    interface.set_channel(1, 1, 200)

    body = client.get("/api/dmx/values/1").json()
    assert body["universe_id"] == 1
    assert len(body["values"]) == 512
    assert body["values"][0] == 200
    assert body["global_grandmaster"] == 255
    assert body["universe_grandmaster"] == 255


def test_values_are_grandmaster_scaled(client, interface):
    interface.set_channel(1, 1, 200)
    interface.set_global_grandmaster(0)

    body = client.get("/api/dmx/values/1").json()
    assert body["values"][0] == 0
    assert body["global_grandmaster"] == 0


def test_values_for_an_unknown_universe_are_zeros(client):
    assert client.get("/api/dmx/values/99").json()["values"] == [0] * 512


def test_get_all_values(client, interface):
    interface.set_channel(2, 5, 99)

    universes = client.get("/api/dmx/values").json()["universes"]
    assert set(universes) == {"1", "2"}
    assert universes["2"][4] == 99


def test_get_a_single_channel(client, interface):
    interface.set_channel(1, 7, 77)
    assert client.get("/api/dmx/channel/1/7").json() == {
        "universe_id": 1, "channel": 7, "value": 77}


@pytest.mark.parametrize("channel", [0, 513])
def test_get_channel_validates_the_range(client, channel):
    response = client.get(f"/api/dmx/channel/1/{channel}")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Setting values
# ---------------------------------------------------------------------------
def test_set_a_channel(client, interface):
    response = client.post("/api/dmx/set",
                           json={"universe_id": 1, "channel": 3, "value": 128})

    assert response.json() == {"status": "set", "universe_id": 1,
                               "channel": 3, "value": 128}
    assert interface.get_channel(1, 3) == 128


@pytest.mark.parametrize("channel", [0, 513, -1])
def test_set_validates_the_channel(client, channel):
    response = client.post("/api/dmx/set",
                           json={"universe_id": 1, "channel": channel, "value": 1})
    assert response.status_code == 400
    assert response.json()["detail"] == "Channel must be 1-512"


@pytest.mark.parametrize("value", [-1, 256])
def test_set_validates_the_value(client, value):
    response = client.post("/api/dmx/set",
                           json={"universe_id": 1, "channel": 1, "value": value})
    assert response.status_code == 400
    assert response.json()["detail"] == "Value must be 0-255"


def test_set_multiple_channels(client, interface):
    response = client.post("/api/dmx/set-multiple",
                           json={"universe_id": 1, "values": {"1": 10, "2": 20}})

    assert response.json() == {"status": "set", "universe_id": 1,
                               "channels_updated": 2}
    assert interface.get_channel(1, 1) == 10
    assert interface.get_channel(1, 2) == 20


def test_set_multiple_rejects_a_bad_channel(client, interface):
    response = client.post("/api/dmx/set-multiple",
                           json={"universe_id": 1, "values": {"600": 10}})
    assert response.status_code == 400
    assert "600" in response.json()["detail"]


def test_set_multiple_rejects_a_bad_value(client, interface):
    response = client.post("/api/dmx/set-multiple",
                           json={"universe_id": 1, "values": {"1": 999}})
    assert response.status_code == 400
    assert interface.get_channel(1, 1) == 0  # nothing applied


def test_set_multiple_with_no_values(client):
    assert client.post("/api/dmx/set-multiple",
                       json={"universe_id": 1,
                             "values": {}}).json()["channels_updated"] == 0


# ---------------------------------------------------------------------------
# Park
# ---------------------------------------------------------------------------
def test_park_a_channel(client, interface, db_session):
    response = client.post("/api/dmx/park",
                           json={"universe_id": 1, "channel": 5, "value": 128})

    assert response.json()["status"] == "parked"
    assert interface.is_channel_parked(1, 5) is True

    stored = db_session.query(ParkedChannel).all()
    assert [(p.universe_id, p.channel, p.value) for p in stored] == [(1, 5, 128)]


def test_parking_twice_keeps_one_row(client, db_session):
    client.post("/api/dmx/park", json={"universe_id": 1, "channel": 5, "value": 10})
    client.post("/api/dmx/park", json={"universe_id": 1, "channel": 5, "value": 20})

    stored = db_session.query(ParkedChannel).all()
    assert len(stored) == 1
    assert stored[0].value == 20


def test_unpark_a_channel(client, interface, db_session):
    client.post("/api/dmx/park", json={"universe_id": 1, "channel": 5, "value": 128})

    response = client.post("/api/dmx/unpark",
                           json={"universe_id": 1, "channel": 5})

    assert response.json()["status"] == "unparked"
    assert interface.is_channel_parked(1, 5) is False
    assert db_session.query(ParkedChannel).count() == 0


def test_list_parked_channels_for_a_universe(client):
    client.post("/api/dmx/park", json={"universe_id": 1, "channel": 5, "value": 10})

    assert client.get("/api/dmx/parked/1").json() == {"universe_id": 1,
                                                      "parked": {"5": 10}}


def test_list_all_parked_channels(client):
    client.post("/api/dmx/park", json={"universe_id": 1, "channel": 5, "value": 10})
    client.post("/api/dmx/park", json={"universe_id": 2, "channel": 6, "value": 20})

    assert client.get("/api/dmx/parked").json() == {
        "parked": {"1": {"5": 10}, "2": {"6": 20}}}


@pytest.mark.parametrize("payload,detail", [
    ({"universe_id": 1, "channel": 0, "value": 10}, "Channel must be 1-512"),
    ({"universe_id": 1, "channel": 5, "value": 300}, "Value must be 0-255"),
])
def test_park_validates_its_arguments(client, payload, detail):
    response = client.post("/api/dmx/park", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == detail


def test_unpark_validates_the_channel(client):
    assert client.post("/api/dmx/unpark",
                       json={"universe_id": 1, "channel": 999}).status_code == 400


def test_park_requires_the_permission(make_app, interface):
    client = restricted_client(make_app, can_park=False)
    response = client.post("/api/dmx/park",
                           json={"universe_id": 1, "channel": 1, "value": 1})

    assert response.status_code == 403
    assert interface.is_channel_parked(1, 1) is False


def test_unpark_requires_the_permission(make_app, interface):
    client = restricted_client(make_app, can_park=False)
    assert client.post("/api/dmx/unpark",
                       json={"universe_id": 1, "channel": 1}).status_code == 403


# ---------------------------------------------------------------------------
# Highlight
# ---------------------------------------------------------------------------
def test_start_highlight(client, interface):
    response = client.post("/api/dmx/highlight",
                           json={"universe_id": 1, "channels": [1, 2],
                                 "dim_level": 10})

    assert response.json()["status"] == "highlight_started"
    state = interface.get_highlight_state()
    assert state["active"] is True
    assert sorted(state["channels"][1]) == [1, 2]
    assert state["dim_level"] == 10


def test_highlight_state_endpoint(client, interface):
    interface.start_highlight(1, [3])
    body = client.get("/api/dmx/highlight").json()
    assert body["active"] is True
    assert body["channels"]["1"] == [3]


def test_add_and_remove_highlight_channels(client, interface):
    client.post("/api/dmx/highlight/add", json={"universe_id": 1, "channel": 4})
    assert interface.is_channel_highlighted(1, 4) is True

    client.post("/api/dmx/highlight/remove", json={"universe_id": 1, "channel": 4})
    assert interface.is_channel_highlighted(1, 4) is False


def test_stop_highlight(client, interface):
    interface.start_highlight(1, [1])
    assert client.post("/api/dmx/highlight/stop").json() == {
        "status": "highlight_stopped"}
    assert interface.get_highlight_state()["active"] is False


def test_highlight_validates_channels(client):
    response = client.post("/api/dmx/highlight",
                           json={"universe_id": 1, "channels": [1, 900]})
    assert response.status_code == 400
    assert "900" in response.json()["detail"]


def test_highlight_validates_the_dim_level(client):
    response = client.post("/api/dmx/highlight",
                           json={"universe_id": 1, "channels": [1],
                                 "dim_level": 999})
    assert response.status_code == 400


@pytest.mark.parametrize("path,payload", [
    ("/api/dmx/highlight/add", {"universe_id": 1, "channel": 0}),
    ("/api/dmx/highlight/remove", {"universe_id": 1, "channel": 513}),
])
def test_highlight_add_remove_validate_channels(client, path, payload):
    assert client.post(path, json=payload).status_code == 400


@pytest.mark.parametrize("path,payload", [
    ("/api/dmx/highlight", {"universe_id": 1, "channels": [1]}),
    ("/api/dmx/highlight/add", {"universe_id": 1, "channel": 1}),
    ("/api/dmx/highlight/remove", {"universe_id": 1, "channel": 1}),
    ("/api/dmx/highlight/stop", None),
])
def test_highlight_endpoints_require_the_permission(make_app, interface,
                                                    path, payload):
    client = restricted_client(make_app, can_highlight=False)
    response = client.post(path, json=payload) if payload else client.post(path)
    assert response.status_code == 403
