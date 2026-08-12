"""API tests for the fixture library endpoints."""
import io
import json

import pytest

from backend.api import fixtures as fixtures_api
from backend.database import Fixture, Patch, Universe


DIMMER = {"channels": [{"name": "Dimmer", "type": "intensity"}]}
RGB = {"channels": [{"name": "Red"}, {"name": "Green"}, {"name": "Blue"}]}


@pytest.fixture
def client(make_app):
    return make_app(fixtures_api.router, prefix="/api/fixtures")


def add_fixture(db, name="PAR", definition=None, position=0):
    fixture = Fixture(name=name, manufacturer="Acme",
                      definition_json=definition or DIMMER, position=position)
    db.add(fixture)
    db.commit()
    db.refresh(fixture)
    return fixture


# ---------------------------------------------------------------------------
# Listing & retrieval
# ---------------------------------------------------------------------------
def test_list_is_empty_initially(client):
    assert client.get("/api/fixtures").json() == {"fixtures": []}


def test_list_returns_fixtures_in_position_order(client, db_session):
    add_fixture(db_session, "Second", position=1)
    add_fixture(db_session, "First", position=0)

    names = [f["name"] for f in client.get("/api/fixtures").json()["fixtures"]]
    assert names == ["First", "Second"]


def test_fixture_payload_shape(client, db_session):
    add_fixture(db_session, "RGB Par", definition=RGB)

    fixture = client.get("/api/fixtures").json()["fixtures"][0]
    assert fixture["name"] == "RGB Par"
    assert fixture["manufacturer"] == "Acme"
    assert fixture["channel_count"] == 3
    assert len(fixture["channels"]) == 3
    assert fixture["definition"] == RGB


def test_get_one_fixture(client, db_session):
    fixture = add_fixture(db_session)
    assert client.get(f"/api/fixtures/{fixture.id}").json()["id"] == fixture.id


def test_get_missing_fixture_is_404(client):
    response = client.get("/api/fixtures/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Fixture not found"


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------
def test_create_fixture(client, db_session):
    response = client.post("/api/fixtures", json={
        "name": "LED Bar", "manufacturer": "Chauvet", "definition_json": RGB,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "LED Bar"
    assert body["channel_count"] == 3
    assert db_session.query(Fixture).count() == 1


def test_create_appends_to_the_end_of_the_order(client, db_session):
    add_fixture(db_session, "Existing", position=4)

    body = client.post("/api/fixtures",
                       json={"name": "New", "definition_json": DIMMER}).json()
    assert body["position"] == 5


def test_the_second_fixture_gets_the_next_position(client):
    client.post("/api/fixtures", json={"name": "First",
                                       "definition_json": DIMMER})
    second = client.post("/api/fixtures", json={"name": "Second",
                                                "definition_json": DIMMER}).json()
    assert second["position"] == 1


def test_create_rejects_a_definition_without_channels(client):
    response = client.post("/api/fixtures",
                           json={"name": "Empty", "definition_json": {}})
    assert response.status_code == 400
    assert "at least one channel" in response.json()["detail"]


def test_create_rejects_an_empty_channel_list(client):
    response = client.post("/api/fixtures",
                           json={"name": "Empty", "definition_json": {"channels": []}})
    assert response.status_code == 400


def test_create_requires_a_name(client):
    assert client.post("/api/fixtures",
                       json={"definition_json": DIMMER}).status_code == 422


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def test_update_fixture_fields(client, db_session):
    fixture = add_fixture(db_session)

    body = client.put(f"/api/fixtures/{fixture.id}", json={
        "name": "Renamed", "manufacturer": "New Co", "definition_json": RGB,
    }).json()

    assert body["name"] == "Renamed"
    assert body["manufacturer"] == "New Co"
    assert body["channel_count"] == 3


def test_partial_update_leaves_other_fields_alone(client, db_session):
    fixture = add_fixture(db_session, "Keep")

    body = client.put(f"/api/fixtures/{fixture.id}",
                      json={"manufacturer": "Only this"}).json()
    assert body["name"] == "Keep"
    assert body["manufacturer"] == "Only this"


def test_update_missing_fixture_is_404(client):
    assert client.put("/api/fixtures/999", json={"name": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def test_delete_fixture(client, db_session):
    fixture = add_fixture(db_session)

    response = client.delete(f"/api/fixtures/{fixture.id}")
    assert response.json() == {"status": "deleted", "fixture_id": fixture.id}
    assert db_session.query(Fixture).count() == 0


def test_delete_missing_fixture_is_404(client):
    assert client.delete("/api/fixtures/999").status_code == 404


def test_delete_is_blocked_while_patched(client, db_session):
    fixture = add_fixture(db_session)
    universe = Universe(label="U", device_type="mock")
    db_session.add(universe)
    db_session.commit()
    db_session.add(Patch(fixture_id=fixture.id, universe_id=universe.id,
                         start_channel=1))
    db_session.commit()

    response = client.delete(f"/api/fixtures/{fixture.id}")
    assert response.status_code == 400
    assert "patch(es)" in response.json()["detail"]
    assert db_session.query(Fixture).count() == 1


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------
def test_reorder_fixtures(client, db_session):
    a = add_fixture(db_session, "A", position=0)
    b = add_fixture(db_session, "B", position=1)
    c = add_fixture(db_session, "C", position=2)

    response = client.put("/api/fixtures/reorder",
                          json={"fixture_ids": [c.id, a.id, b.id]})

    assert response.json()["status"] == "reordered"
    names = [f["name"] for f in client.get("/api/fixtures").json()["fixtures"]]
    assert names == ["C", "A", "B"]


def test_reorder_ignores_unknown_ids(client, db_session):
    fixture = add_fixture(db_session, "A")
    response = client.put("/api/fixtures/reorder",
                          json={"fixture_ids": [999, fixture.id]})
    assert response.status_code == 200


def test_reorder_with_an_empty_list(client):
    assert client.put("/api/fixtures/reorder",
                      json={"fixture_ids": []}).status_code == 200


# ---------------------------------------------------------------------------
# OFL import
# ---------------------------------------------------------------------------
def test_import_ofl_fixture(client, db_session):
    ofl = {
        "name": "Mini Spot",
        "manufacturerKey": "generic",
        "availableChannels": {
            "Dimmer": {"type": "intensity", "defaultValue": 5},
            "Pan": {"type": "pan"},
        },
        "modes": [{"name": "8ch", "channels": ["Pan", "Dimmer"]}],
    }
    files = {"file": ("mini.json", io.BytesIO(json.dumps(ofl).encode()),
                      "application/json")}

    body = client.post("/api/fixtures/import/ofl", files=files).json()

    assert body["name"] == "Mini Spot"
    assert body["manufacturer"] == "generic"
    assert [c["name"] for c in body["channels"]] == ["Pan", "Dimmer"]
    assert body["channels"][1]["default"] == 5


def test_import_ofl_falls_back_to_available_channel_order(client):
    ofl = {"name": "NoModes",
           "availableChannels": {"A": {"type": "intensity"},
                                 "B": {"type": "color"}}}
    files = {"file": ("x.json", io.BytesIO(json.dumps(ofl).encode()),
                      "application/json")}

    body = client.post("/api/fixtures/import/ofl", files=files).json()
    assert [c["name"] for c in body["channels"]] == ["A", "B"]


def test_import_ofl_uses_the_filename_when_unnamed(client):
    files = {"file": ("my-light.json", io.BytesIO(b"{}"), "application/json")}
    body = client.post("/api/fixtures/import/ofl", files=files).json()
    assert body["name"] == "my-light"


def test_import_ofl_rejects_invalid_json(client):
    files = {"file": ("bad.json", io.BytesIO(b"not json"), "application/json")}
    response = client.post("/api/fixtures/import/ofl", files=files)
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSON file"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def test_generic_templates(client):
    templates = client.get("/api/fixtures/templates/generic").json()["templates"]

    names = [t["name"] for t in templates]
    assert "Generic Dimmer" in names
    assert "Generic RGB" in names

    for template in templates:
        assert template["definition_json"]["channels"]
        for channel in template["definition_json"]["channels"]:
            assert "name" in channel and "type" in channel


def test_rgb_template_has_three_colour_channels(client):
    templates = client.get("/api/fixtures/templates/generic").json()["templates"]
    rgb = next(t for t in templates if t["name"] == "Generic RGB")
    assert len(rgb["definition_json"]["channels"]) == 3
