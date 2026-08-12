"""API tests for patching fixtures into universes and channel labels."""
import pytest

from backend.api import patch as patch_api
from backend.database import ChannelLabel, Fixture, Patch, Universe


RGB = {"channels": [
    {"name": "Red", "type": "color", "color": "#ff0000"},
    {"name": "Green", "type": "color"},
    {"name": "Blue", "type": "color"},
]}


@pytest.fixture
def client(make_app):
    return make_app(patch_api.router, prefix="/api/patch")


@pytest.fixture
def rig(db_session):
    """A fixture and a universe to patch it into."""
    fixture = Fixture(name="RGB Par", manufacturer="Acme", definition_json=RGB)
    universe = Universe(id=1, label="Main", device_type="mock")
    db_session.add_all([fixture, universe])
    db_session.commit()
    db_session.refresh(fixture)
    return fixture, universe


def add_patch(db, fixture, universe, start_channel=1, label="", position=0):
    patch = Patch(fixture_id=fixture.id, universe_id=universe.id,
                  start_channel=start_channel, label=label, position=position)
    db.add(patch)
    db.commit()
    db.refresh(patch)
    return patch


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def test_list_is_empty_initially(client):
    assert client.get("/api/patch").json() == {"patches": []}


def test_list_returns_patches_in_position_order(client, db_session, rig):
    fixture, universe = rig
    add_patch(db_session, fixture, universe, 10, label="Second", position=1)
    add_patch(db_session, fixture, universe, 1, label="First", position=0)

    labels = [p["label"] for p in client.get("/api/patch").json()["patches"]]
    assert labels == ["First", "Second"]


def test_list_can_filter_by_universe(client, db_session, rig):
    fixture, universe = rig
    other = Universe(id=2, label="Second", device_type="mock")
    db_session.add(other)
    db_session.commit()

    add_patch(db_session, fixture, universe, 1)
    add_patch(db_session, fixture, other, 1)

    assert len(client.get("/api/patch?universe_id=1").json()["patches"]) == 1


def test_patch_payload_shape(client, db_session, rig):
    fixture, universe = rig
    patch = add_patch(db_session, fixture, universe, start_channel=10,
                      label="Front L")

    body = client.get(f"/api/patch/{patch.id}").json()
    assert body["fixture_name"] == "RGB Par"
    assert body["manufacturer"] == "Acme"
    assert body["universe_label"] == "Main"
    assert body["start_channel"] == 10
    assert body["end_channel"] == 12
    assert body["channel_count"] == 3
    assert body["label"] == "Front L"


def test_get_missing_patch_is_404(client):
    assert client.get("/api/patch/999").status_code == 404


# ---------------------------------------------------------------------------
# Creation & validation
# ---------------------------------------------------------------------------
def test_create_patch(client, db_session, rig):
    fixture, universe = rig

    response = client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": universe.id,
        "start_channel": 1, "label": "Front",
    })

    assert response.status_code == 200
    assert response.json()["end_channel"] == 3
    assert db_session.query(Patch).count() == 1


def test_create_requires_a_known_fixture(client, rig):
    _, universe = rig
    response = client.post("/api/patch", json={
        "fixture_id": 999, "universe_id": universe.id, "start_channel": 1})
    assert response.status_code == 404
    assert response.json()["detail"] == "Fixture not found"


def test_create_requires_a_known_universe(client, rig):
    fixture, _ = rig
    response = client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": 99, "start_channel": 1})
    assert response.status_code == 404
    assert response.json()["detail"] == "Universe not found"


@pytest.mark.parametrize("start_channel", [0, -1, 511])
def test_create_rejects_out_of_range_channels(client, rig, start_channel):
    fixture, universe = rig
    response = client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": universe.id,
        "start_channel": start_channel})
    assert response.status_code == 400
    assert "DMX range" in response.json()["detail"]


def test_a_fixture_may_end_exactly_on_channel_512(client, rig):
    fixture, universe = rig
    response = client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": universe.id,
        "start_channel": 510})
    assert response.status_code == 200
    assert response.json()["end_channel"] == 512


def test_overlapping_patches_are_rejected(client, db_session, rig):
    fixture, universe = rig
    add_patch(db_session, fixture, universe, start_channel=5)  # occupies 5-7

    for start in (5, 6, 7, 4, 3):
        response = client.post("/api/patch", json={
            "fixture_id": fixture.id, "universe_id": universe.id,
            "start_channel": start})
        assert response.status_code == 400, start
        assert "conflict" in response.json()["detail"].lower()


def test_adjacent_patches_are_allowed(client, db_session, rig):
    fixture, universe = rig
    add_patch(db_session, fixture, universe, start_channel=5)  # 5-7

    assert client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": universe.id,
        "start_channel": 8}).status_code == 200
    assert client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": universe.id,
        "start_channel": 2}).status_code == 200


def test_the_same_channels_may_be_used_in_another_universe(client, db_session, rig):
    fixture, universe = rig
    db_session.add(Universe(id=2, label="Second", device_type="mock"))
    db_session.commit()
    add_patch(db_session, fixture, universe, start_channel=5)

    assert client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": 2,
        "start_channel": 5}).status_code == 200


def test_create_appends_to_the_end_of_the_order(client, db_session, rig):
    fixture, universe = rig
    add_patch(db_session, fixture, universe, start_channel=1, position=7)

    body = client.post("/api/patch", json={
        "fixture_id": fixture.id, "universe_id": universe.id,
        "start_channel": 20}).json()
    assert body["position"] == 8


def test_the_second_patch_gets_the_next_position(client, rig):
    fixture, universe = rig
    client.post("/api/patch", json={"fixture_id": fixture.id,
                                    "universe_id": universe.id,
                                    "start_channel": 1})
    second = client.post("/api/patch", json={"fixture_id": fixture.id,
                                             "universe_id": universe.id,
                                             "start_channel": 10}).json()
    assert second["position"] == 1


# ---------------------------------------------------------------------------
# Update & delete
# ---------------------------------------------------------------------------
def test_update_patch_fields(client, db_session, rig):
    fixture, universe = rig
    patch = add_patch(db_session, fixture, universe, start_channel=1)

    body = client.put(f"/api/patch/{patch.id}", json={
        "start_channel": 100, "label": "Moved", "group_color": "#ff0000"}).json()

    assert body["start_channel"] == 100
    assert body["label"] == "Moved"
    assert body["group_color"] == "#ff0000"


def test_update_rejects_unknown_references(client, db_session, rig):
    fixture, universe = rig
    patch = add_patch(db_session, fixture, universe)

    assert client.put(f"/api/patch/{patch.id}",
                      json={"fixture_id": 999}).status_code == 404
    assert client.put(f"/api/patch/{patch.id}",
                      json={"universe_id": 999}).status_code == 404


def test_update_missing_patch_is_404(client):
    assert client.put("/api/patch/999", json={"label": "x"}).status_code == 404


def test_delete_patch(client, db_session, rig):
    fixture, universe = rig
    patch = add_patch(db_session, fixture, universe)

    assert client.delete(f"/api/patch/{patch.id}").json() == {
        "status": "deleted", "patch_id": patch.id}
    assert db_session.query(Patch).count() == 0


def test_delete_missing_patch_is_404(client):
    assert client.delete("/api/patch/999").status_code == 404


def test_reorder_patches(client, db_session, rig):
    fixture, universe = rig
    a = add_patch(db_session, fixture, universe, 1, label="A", position=0)
    b = add_patch(db_session, fixture, universe, 10, label="B", position=1)

    client.put("/api/patch/reorder", json={"patch_ids": [b.id, a.id]})

    labels = [p["label"] for p in client.get("/api/patch").json()["patches"]]
    assert labels == ["B", "A"]


# ---------------------------------------------------------------------------
# Channel labels
# ---------------------------------------------------------------------------
def test_labels_are_derived_from_patches(client, db_session, rig):
    fixture, universe = rig
    add_patch(db_session, fixture, universe, start_channel=5, label="Front")

    labels = client.get("/api/patch/labels/1").json()["labels"]

    assert labels["5"]["label"] == "Front: Red"
    assert labels["6"]["label"] == "Front: Green"
    assert labels["7"]["label"] == "Front: Blue"
    assert labels["5"]["type"] == "color"
    assert labels["5"]["color"] == "#ff0000"


def test_labels_fall_back_to_the_fixture_name(client, db_session, rig):
    fixture, universe = rig
    add_patch(db_session, fixture, universe, start_channel=1, label="")

    labels = client.get("/api/patch/labels/1").json()["labels"]
    assert labels["1"]["label"] == "RGB Par: Red"


def test_labels_include_the_group_colour(client, db_session, rig):
    fixture, universe = rig
    patch = add_patch(db_session, fixture, universe, start_channel=1)
    patch.group_color = "#00ff00"
    db_session.commit()

    labels = client.get("/api/patch/labels/1").json()["labels"]
    assert labels["1"]["groupColor"] == "#00ff00"


def test_custom_label_is_merged_into_a_patched_channel(client, db_session, rig):
    fixture, universe = rig
    add_patch(db_session, fixture, universe, start_channel=1)
    db_session.add(ChannelLabel(universe_id=1, channel=1, label="House left"))
    db_session.commit()

    labels = client.get("/api/patch/labels/1").json()["labels"]
    assert labels["1"]["custom_label"] == "House left"
    assert labels["1"]["label"] == "RGB Par: Red"


def test_custom_label_on_an_unpatched_channel(client, db_session):
    db_session.add(ChannelLabel(universe_id=1, channel=100, label="Smoke"))
    db_session.commit()

    labels = client.get("/api/patch/labels/1").json()["labels"]
    assert labels["100"] == {"label": "Smoke", "type": "custom"}


def test_set_channel_label_creates_then_updates(client, db_session):
    client.post("/api/patch/labels",
                json={"universe_id": 1, "channel": 3, "label": "First"})
    response = client.post("/api/patch/labels",
                           json={"universe_id": 1, "channel": 3, "label": "Second"})

    assert response.json()["label"] == "Second"
    assert db_session.query(ChannelLabel).count() == 1
    assert db_session.query(ChannelLabel).one().label == "Second"


def test_delete_channel_label(client, db_session):
    db_session.add(ChannelLabel(universe_id=1, channel=3, label="Gone"))
    db_session.commit()

    assert client.delete("/api/patch/labels/1/3").json() == {"status": "deleted"}
    assert db_session.query(ChannelLabel).count() == 0


def test_delete_missing_label_still_reports_success(client):
    assert client.delete("/api/patch/labels/1/99").json() == {"status": "deleted"}


def test_labels_for_an_empty_universe(client):
    assert client.get("/api/patch/labels/7").json() == {"universe_id": 7,
                                                        "labels": {}}
