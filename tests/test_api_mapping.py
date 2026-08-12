"""API tests for channel mapping configuration."""
import pytest

from backend.api import mapping as mapping_api
from backend.database import ChannelMapping
from backend.dmx_interface import DMXInterface


def entry(src_channel=1, dst_channel=7, src_universe=1, dst_universe=1, **extra):
    data = {"src_universe": src_universe, "src_channel": src_channel,
            "dst_universe": dst_universe, "dst_channel": dst_channel}
    data.update(extra)
    return data


def config(name="Desk", enabled=False, mappings=None,
           unmapped_behavior="passthrough"):
    return {"name": name, "enabled": enabled,
            "unmapped_behavior": unmapped_behavior,
            "mappings": mappings if mappings is not None else [entry()]}


@pytest.fixture
def interface(monkeypatch):
    dmx = DMXInterface()
    monkeypatch.setattr(mapping_api, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def client(make_app, interface):
    return make_app(mapping_api.router, prefix="/api/mapping")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def test_list_is_empty_initially(client):
    body = client.get("/api/mapping").json()
    assert body["mappings"] == []
    assert body["status"] == {"enabled": False,
                              "unmapped_behavior": "passthrough",
                              "mapping_count": 0}


def test_created_mappings_are_listed(client):
    client.post("/api/mapping", json=config(name="Show A"))
    names = [m["name"] for m in client.get("/api/mapping").json()["mappings"]]
    assert names == ["Show A"]


def test_get_one_mapping(client):
    created = client.post("/api/mapping", json=config()).json()
    assert client.get(f"/api/mapping/{created['id']}").json() == created


def test_get_missing_mapping_is_404(client):
    assert client.get("/api/mapping/99").status_code == 404


def test_active_mapping_is_none_when_nothing_is_enabled(client):
    client.post("/api/mapping", json=config(enabled=False))
    assert client.get("/api/mapping/active").json()["mapping"] is None


def test_active_mapping_reports_the_enabled_one(client):
    client.post("/api/mapping", json=config(name="Off", enabled=False))
    client.post("/api/mapping", json=config(name="On", enabled=True))

    body = client.get("/api/mapping/active").json()
    assert body["mapping"]["name"] == "On"
    assert body["status"]["enabled"] is True


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def test_create_mapping(client, db_session):
    body = client.post("/api/mapping", json=config(name="Show")).json()

    assert body["name"] == "Show"
    assert body["enabled"] is False
    assert body["unmapped_behavior"] == "passthrough"
    assert body["mappings"][0]["src_channel"] == 1
    assert db_session.query(ChannelMapping).count() == 1


def test_creating_an_enabled_mapping_applies_it_to_the_runtime(client, interface):
    client.post("/api/mapping", json=config(enabled=True))

    assert interface.get_channel_mapping_status()["enabled"] is True
    assert interface.get_mapped_destination(1, 1)[0]["channel"] == 7


def test_creating_a_disabled_mapping_leaves_the_runtime_alone(client, interface):
    client.post("/api/mapping", json=config(enabled=False))
    assert interface.get_channel_mapping_status()["enabled"] is False


def test_enabling_a_new_mapping_disables_the_others(client):
    first = client.post("/api/mapping", json=config(name="A", enabled=True)).json()
    client.post("/api/mapping", json=config(name="B", enabled=True))

    assert client.get(f"/api/mapping/{first['id']}").json()["enabled"] is False


def test_virtual_targets_are_accepted(client, interface):
    client.post("/api/mapping", json=config(enabled=True, mappings=[
        {"src_universe": 1, "src_channel": 1,
         "dst_target_type": "global_master"},
        {"src_universe": 1, "src_channel": 2,
         "dst_target_type": "universe_master", "dst_target_universe_id": 2},
    ]))

    assert interface.get_mapped_destination(1, 1)[0]["target_type"] == "global_master"
    assert interface.get_mapped_destination(1, 2)[0]["target_universe_id"] == 2


@pytest.mark.parametrize("bad,detail", [
    (entry(src_channel=0), "Source channel must be between 1 and 512"),
    (entry(src_channel=513), "Source channel must be between 1 and 512"),
    (entry(dst_channel=0), "Destination channel must be between 1 and 512 "
                           "for channel targets"),
    ({"src_universe": 1, "src_channel": 1, "dst_target_type": "channel"},
     "Destination channel must be between 1 and 512 for channel targets"),
    ({"src_universe": 1, "src_channel": 1,
      "dst_target_type": "universe_master"},
     "Universe ID required for universe_master target"),
    ({"src_universe": 1, "src_channel": 1, "dst_target_type": "nonsense"},
     "Invalid target type: nonsense"),
])
def test_create_validates_entries(client, db_session, bad, detail):
    response = client.post("/api/mapping", json=config(mappings=[bad]))
    assert response.status_code == 400
    assert response.json()["detail"] == detail
    assert db_session.query(ChannelMapping).count() == 0


def test_create_accepts_an_empty_mapping_list(client):
    body = client.post("/api/mapping", json=config(mappings=[])).json()
    assert body["mappings"] == []


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def test_update_mapping(client):
    created = client.post("/api/mapping", json=config(name="Old")).json()

    body = client.put(f"/api/mapping/{created['id']}",
                      json=config(name="New", unmapped_behavior="ignore",
                                  mappings=[entry(2, 9)])).json()

    assert body["name"] == "New"
    assert body["unmapped_behavior"] == "ignore"
    assert body["mappings"][0]["dst_channel"] == 9


def test_updating_to_enabled_applies_the_runtime_mapping(client, interface):
    created = client.post("/api/mapping", json=config()).json()

    client.put(f"/api/mapping/{created['id']}",
               json=config(enabled=True, unmapped_behavior="ignore"))

    status = interface.get_channel_mapping_status()
    assert status["enabled"] is True
    assert status["unmapped_behavior"] == "ignore"


def test_disabling_the_last_mapping_clears_the_runtime(client, interface):
    created = client.post("/api/mapping", json=config(enabled=True)).json()

    client.put(f"/api/mapping/{created['id']}", json=config(enabled=False))

    assert interface.get_channel_mapping_status()["enabled"] is False


def test_disabling_one_mapping_activates_another_enabled_one(client, interface,
                                                             db_session):
    a = client.post("/api/mapping", json=config(name="A", enabled=True)).json()
    # force a second enabled row directly in the database
    row = ChannelMapping(name="B", enabled=True, unmapped_behavior="ignore",
                         mappings_json={"mappings": [entry(3, 4)]})
    db_session.add(row)
    db_session.commit()

    client.put(f"/api/mapping/{a['id']}", json=config(name="A", enabled=False))

    assert interface.get_channel_mapping_status()["unmapped_behavior"] == "ignore"
    assert interface.get_mapped_destination(1, 3)[0]["channel"] == 4


def test_update_missing_mapping_is_404(client):
    assert client.put("/api/mapping/99", json=config()).status_code == 404


def test_update_validates_entries(client):
    created = client.post("/api/mapping", json=config()).json()
    response = client.put(f"/api/mapping/{created['id']}",
                          json=config(mappings=[entry(src_channel=900)]))
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Enable / disable / delete / sync
# ---------------------------------------------------------------------------
def test_enable_endpoint(client, interface):
    a = client.post("/api/mapping", json=config(name="A", enabled=True)).json()
    b = client.post("/api/mapping", json=config(name="B",
                                                mappings=[entry(5, 6)])).json()

    assert client.post(f"/api/mapping/{b['id']}/enable").json() == {
        "status": "enabled", "mapping_id": b["id"]}
    assert client.get(f"/api/mapping/{a['id']}").json()["enabled"] is False
    assert interface.get_mapped_destination(1, 5)[0]["channel"] == 6


def test_enable_missing_mapping_is_404(client):
    assert client.post("/api/mapping/99/enable").status_code == 404


def test_disable_all(client, interface, db_session):
    client.post("/api/mapping", json=config(enabled=True))

    assert client.post("/api/mapping/disable").json() == {"status": "disabled"}
    assert interface.get_channel_mapping_status()["enabled"] is False
    assert all(not m.enabled for m in db_session.query(ChannelMapping).all())


def test_delete_mapping(client, db_session):
    created = client.post("/api/mapping", json=config()).json()

    assert client.delete(f"/api/mapping/{created['id']}").json() == {
        "status": "deleted", "mapping_id": created["id"]}
    assert db_session.query(ChannelMapping).count() == 0


def test_deleting_the_active_mapping_clears_the_runtime(client, interface):
    created = client.post("/api/mapping", json=config(enabled=True)).json()

    client.delete(f"/api/mapping/{created['id']}")
    assert interface.get_channel_mapping_status()["enabled"] is False


def test_delete_missing_mapping_is_404(client):
    assert client.delete("/api/mapping/99").status_code == 404


def test_sync_applies_the_active_mapping(client, interface):
    created = client.post("/api/mapping", json=config(enabled=True)).json()
    interface.set_channel_mapping([], "passthrough")  # simulate runtime drift

    response = client.post("/api/mapping/sync")

    assert response.json()["status"] == "synced"
    assert response.json()["mapping_id"] == created["id"]
    assert interface.get_channel_mapping_status()["enabled"] is True


def test_sync_without_an_active_mapping(client, interface):
    assert client.post("/api/mapping/sync").json() == {"status": "no_active_mapping"}
    assert interface.get_channel_mapping_status()["enabled"] is False


# ---------------------------------------------------------------------------
# Bulk generation helper
# ---------------------------------------------------------------------------
def test_bulk_generates_a_contiguous_range(client):
    body = client.post("/api/mapping/bulk", json={
        "src_universe": 1, "src_start": 1, "src_end": 4,
        "dst_universe": 2, "dst_start": 17}).json()

    assert body["count"] == 4
    assert body["mappings"][0] == {"src_universe": 1, "src_channel": 1,
                                   "dst_universe": 2, "dst_channel": 17}
    assert body["mappings"][-1] == {"src_universe": 1, "src_channel": 4,
                                    "dst_universe": 2, "dst_channel": 20}


def test_bulk_single_channel_range(client):
    body = client.post("/api/mapping/bulk", json={
        "src_universe": 1, "src_start": 5, "src_end": 5,
        "dst_universe": 1, "dst_start": 10}).json()
    assert body["count"] == 1


def test_bulk_does_not_persist_anything(client, db_session):
    client.post("/api/mapping/bulk", json={
        "src_universe": 1, "src_start": 1, "src_end": 2,
        "dst_universe": 1, "dst_start": 3})
    assert db_session.query(ChannelMapping).count() == 0


@pytest.mark.parametrize("payload,detail", [
    ({"src_universe": 1, "src_start": 0, "src_end": 4, "dst_universe": 1,
      "dst_start": 1}, "Source channels must be between 1 and 512"),
    ({"src_universe": 1, "src_start": 1, "src_end": 600, "dst_universe": 1,
      "dst_start": 1}, "Source channels must be between 1 and 512"),
    ({"src_universe": 1, "src_start": 5, "src_end": 2, "dst_universe": 1,
      "dst_start": 1}, "Source end must be >= start"),
    ({"src_universe": 1, "src_start": 1, "src_end": 10, "dst_universe": 1,
      "dst_start": 510}, "Destination channels must be between 1 and 512"),
])
def test_bulk_validation(client, payload, detail):
    response = client.post("/api/mapping/bulk", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == detail
