"""API tests for the token-authenticated remote control endpoints."""
import pytest

from backend.api import remote as remote_api
from backend.database import Group, Scene, SceneGroupValue, SceneValue, TriggerToken, Universe
from backend.dmx_interface import DMXInterface, DMXUniverse


@pytest.fixture
def interface(monkeypatch):
    dmx = DMXInterface()
    dmx.universes[1] = DMXUniverse(1)
    monkeypatch.setattr(remote_api, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def client(make_app, interface):
    return make_app(remote_api.router, prefix="/api/remote")


@pytest.fixture
def scene(db_session):
    scene = Scene(name="Look 1", transition_type="instant", duration=0)
    db_session.add(scene)
    db_session.commit()
    db_session.add(SceneValue(scene_id=scene.id, universe_id=1, channel=1,
                              value=200))
    db_session.commit()
    db_session.refresh(scene)
    return scene


@pytest.fixture
def group(db_session):
    group = Group(name="Warm", mode="follow", master_value=0, enabled=True)
    db_session.add(group)
    db_session.commit()
    db_session.refresh(group)
    return group


def make_token(client, **payload):
    return client.post("/api/remote/tokens", json=payload).json()


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------
def test_token_list_is_empty_initially(client):
    assert client.get("/api/remote/tokens").json() == {"tokens": []}


def test_create_a_scene_token(client, scene, db_session):
    body = make_token(client, token_type="scene", scene_id=scene.id,
                      name="Home Assistant")

    assert body["token_type"] == "scene"
    assert body["scene_id"] == scene.id
    assert body["scene_name"] == "Look 1"
    assert body["name"] == "Home Assistant"
    assert f"/api/remote/scene/{scene.id}?token=" in body["trigger_url"]
    assert db_session.query(TriggerToken).count() == 1


def test_create_a_blackout_token(client):
    body = make_token(client, token_type="blackout")
    assert body["token_type"] == "blackout"
    assert body["scene_id"] is None
    assert "/api/remote/blackout?token=" in body["trigger_url"]


def test_create_a_group_token(client, group):
    body = make_token(client, token_type="group", group_id=group.id)
    assert body["group_id"] == group.id
    assert body["group_name"] == "Warm"
    assert "value=VALUE" in body["trigger_url"]


def test_create_a_status_token(client):
    body = make_token(client, token_type="status")
    assert "/api/remote/status?token=" in body["trigger_url"]


def test_tokens_are_unique(client, scene):
    a = make_token(client, token_type="scene", scene_id=scene.id)
    b = make_token(client, token_type="scene", scene_id=scene.id)
    assert a["token"] != b["token"]
    assert len(a["token"]) >= 32


def test_scene_token_requires_a_scene_id(client):
    response = client.post("/api/remote/tokens", json={"token_type": "scene"})
    assert response.status_code == 400
    assert response.json()["detail"] == "scene_id required for scene tokens"


def test_scene_token_requires_an_existing_scene(client):
    response = client.post("/api/remote/tokens",
                           json={"token_type": "scene", "scene_id": 99})
    assert response.status_code == 404


def test_group_token_requires_a_group_id(client):
    response = client.post("/api/remote/tokens", json={"token_type": "group"})
    assert response.status_code == 400
    assert response.json()["detail"] == "group_id required for group tokens"


def test_group_token_requires_an_existing_group(client):
    response = client.post("/api/remote/tokens",
                           json={"token_type": "group", "group_id": 99})
    assert response.status_code == 404


def test_unknown_token_types_are_rejected(client):
    assert client.post("/api/remote/tokens",
                       json={"token_type": "nonsense"}).status_code == 422


def test_listed_tokens_are_masked(client, scene):
    created = make_token(client, token_type="scene", scene_id=scene.id)

    listed = client.get("/api/remote/tokens").json()["tokens"][0]
    assert listed["full_token"] == created["token"]
    assert listed["token"] != created["token"]
    assert "..." in listed["token"]


def test_delete_a_token(client, scene, db_session):
    created = make_token(client, token_type="scene", scene_id=scene.id)

    assert client.delete(f"/api/remote/tokens/{created['id']}").json() == {
        "status": "deleted"}
    assert db_session.query(TriggerToken).count() == 0


def test_delete_missing_token_is_404(client):
    assert client.delete("/api/remote/tokens/99").status_code == 404


# ---------------------------------------------------------------------------
# Scene trigger
# ---------------------------------------------------------------------------
def test_trigger_a_scene(client, scene, interface):
    token = make_token(client, token_type="scene", scene_id=scene.id)["token"]

    response = client.get(f"/api/remote/scene/{scene.id}?token={token}")

    assert response.json()["status"] == "success"
    assert "Look 1" in response.json()["message"]
    assert interface.get_channel(1, 1) == 200


def test_scene_trigger_works_over_post_too(client, scene, interface):
    token = make_token(client, token_type="scene", scene_id=scene.id)["token"]
    assert client.post(f"/api/remote/scene/{scene.id}?token={token}").status_code == 200


def test_scene_trigger_rejects_an_unknown_token(client, scene):
    response = client.get(f"/api/remote/scene/{scene.id}?token=nope")
    assert response.status_code == 401


def test_scene_trigger_rejects_a_token_for_another_scene(client, db_session,
                                                         scene):
    other = Scene(name="Other")
    db_session.add(other)
    db_session.commit()
    token = make_token(client, token_type="scene", scene_id=other.id)["token"]

    response = client.get(f"/api/remote/scene/{scene.id}?token={token}")
    assert response.status_code == 401


def test_scene_trigger_rejects_a_token_of_the_wrong_type(client, scene):
    token = make_token(client, token_type="blackout")["token"]
    assert client.get(
        f"/api/remote/scene/{scene.id}?token={token}").status_code == 401


def test_scene_trigger_requires_a_token(client, scene):
    assert client.get(f"/api/remote/scene/{scene.id}").status_code == 422


def test_triggering_updates_last_used(client, scene, db_session):
    token = make_token(client, token_type="scene", scene_id=scene.id)["token"]
    assert db_session.query(TriggerToken).one().last_used is None

    client.get(f"/api/remote/scene/{scene.id}?token={token}")
    db_session.expire_all()
    assert db_session.query(TriggerToken).one().last_used is not None


def test_scene_trigger_skips_input_controlled_channels(client, scene, interface,
                                                       db_session):
    db_session.add(Universe(id=1, label="U", device_type="mock",
                            input_channel_start=1, input_channel_end=10))
    db_session.commit()
    interface.inputs[1] = object()  # pretend an input is live

    token = make_token(client, token_type="scene", scene_id=scene.id)["token"]
    client.get(f"/api/remote/scene/{scene.id}?token={token}")

    assert interface.get_channel(1, 1) == 0


def test_scene_trigger_restores_group_master_values(client, scene, group,
                                                    interface, db_session):
    db_session.add(SceneGroupValue(scene_id=scene.id, group_id=group.id,
                                   master_value=180))
    db_session.commit()
    interface.load_groups([{"id": group.id, "name": "Warm", "mode": "follow",
                            "master_universe": None, "master_channel": None,
                            "master_value": 0, "enabled": True, "members": []}])

    token = make_token(client, token_type="scene", scene_id=scene.id)["token"]
    client.get(f"/api/remote/scene/{scene.id}?token={token}")

    db_session.expire_all()
    assert db_session.query(Group).one().master_value == 180
    assert interface.get_group(group.id)["master_value"] == 180


# ---------------------------------------------------------------------------
# Blackout trigger
# ---------------------------------------------------------------------------
def test_blackout_toggles_by_default(client, interface):
    token = make_token(client, token_type="blackout")["token"]

    client.get(f"/api/remote/blackout?token={token}")
    assert interface.is_blackout_active() is True

    client.get(f"/api/remote/blackout?token={token}")
    assert interface.is_blackout_active() is False


@pytest.mark.parametrize("state", ["on", "true", "1", "ON"])
def test_blackout_can_be_forced_on(client, interface, state):
    token = make_token(client, token_type="blackout")["token"]
    client.get(f"/api/remote/blackout?token={token}&state={state}")
    assert interface.is_blackout_active() is True


@pytest.mark.parametrize("state", ["off", "false", "0"])
def test_blackout_can_be_forced_off(client, interface, state):
    token = make_token(client, token_type="blackout")["token"]
    interface.blackout()

    client.get(f"/api/remote/blackout?token={token}&state={state}")
    assert interface.is_blackout_active() is False


def test_blackout_rejects_an_unknown_state(client):
    token = make_token(client, token_type="blackout")["token"]
    response = client.get(f"/api/remote/blackout?token={token}&state=maybe")
    assert response.status_code == 400


def test_blackout_rejects_a_bad_token(client):
    assert client.get("/api/remote/blackout?token=nope").status_code == 401


# ---------------------------------------------------------------------------
# Group trigger
# ---------------------------------------------------------------------------
def test_group_trigger_sets_the_master_value(client, group, interface,
                                             db_session):
    interface.load_groups([{"id": group.id, "name": "Warm", "mode": "follow",
                            "master_universe": None, "master_channel": None,
                            "master_value": 0, "enabled": True,
                            "members": [{"universe_id": 1, "channel": 1,
                                         "base_value": 255,
                                         "target_type": "channel"}]}])
    token = make_token(client, token_type="group", group_id=group.id)["token"]

    response = client.get(f"/api/remote/group/{group.id}?token={token}&value=128")

    assert response.json()["status"] == "success"
    assert interface.get_channel(1, 1) == 128
    db_session.expire_all()
    assert db_session.query(Group).one().master_value == 128


def test_group_trigger_uses_the_physical_master_channel(client, db_session,
                                                        interface):
    group = Group(name="Physical", mode="follow", master_universe=1,
                  master_channel=10, enabled=True)
    db_session.add(group)
    db_session.commit()
    token = make_token(client, token_type="group", group_id=group.id)["token"]

    client.get(f"/api/remote/group/{group.id}?token={token}&value=90")
    assert interface.get_channel(1, 10) == 90


@pytest.mark.parametrize("value", [-1, 256])
def test_group_trigger_validates_the_value(client, group, value):
    token = make_token(client, token_type="group", group_id=group.id)["token"]
    response = client.get(f"/api/remote/group/{group.id}?token={token}&value={value}")
    assert response.status_code == 422


def test_group_trigger_requires_a_value(client, group):
    token = make_token(client, token_type="group", group_id=group.id)["token"]
    assert client.get(
        f"/api/remote/group/{group.id}?token={token}").status_code == 422


def test_group_trigger_rejects_a_token_for_another_group(client, db_session,
                                                         group):
    other = Group(name="Other")
    db_session.add(other)
    db_session.commit()
    token = make_token(client, token_type="group", group_id=other.id)["token"]

    assert client.get(
        f"/api/remote/group/{group.id}?token={token}&value=1").status_code == 401


# ---------------------------------------------------------------------------
# Status query
# ---------------------------------------------------------------------------
def test_status_reports_groups_and_universes(client, db_session, interface):
    db_session.add_all([
        Group(name="Enabled", master_value=100, enabled=True),
        Group(name="Disabled", master_value=50, enabled=False),
        Universe(id=1, label="Main", device_type="mock", enabled=True),
    ])
    db_session.commit()
    token = make_token(client, token_type="status")["token"]

    body = client.get(f"/api/remote/status?token={token}").json()

    assert body["blackout"] is False
    assert [g["name"] for g in body["groups"]] == ["Enabled"]
    assert body["groups"][0]["master_value"] == 100
    assert body["universes"] == [{"id": 1, "name": "Main", "enabled": True}]


def test_status_reflects_blackout(client, interface):
    token = make_token(client, token_type="status")["token"]
    interface.blackout()
    assert client.get(f"/api/remote/status?token={token}").json()["blackout"] is True


def test_status_rejects_a_bad_token(client):
    assert client.get("/api/remote/status?token=nope").status_code == 401
