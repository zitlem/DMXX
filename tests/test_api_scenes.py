"""API tests for scene save/update/recall."""
import pytest

from backend.api import scenes as scenes_api
from backend.api.scenes import apply_fade
from backend.database import (
    Group,
    Scene,
    SceneGroupValue,
    SceneMasterValue,
    SceneValue,
)
from backend.dmx_interface import DMXInterface, DMXUniverse


@pytest.fixture
def interface(monkeypatch):
    dmx = DMXInterface()
    dmx.universes[1] = DMXUniverse(1)
    dmx.universes[2] = DMXUniverse(2)
    monkeypatch.setattr(scenes_api, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def client(make_app, interface):
    return make_app(scenes_api.router, prefix="/api/scenes")


def add_scene(db, name="Look", transition_type="instant", duration=0,
              position=0, values=None):
    scene = Scene(name=name, transition_type=transition_type,
                  duration=duration, position=position)
    db.add(scene)
    db.commit()
    for universe_id, channel, value in values or []:
        db.add(SceneValue(scene_id=scene.id, universe_id=universe_id,
                          channel=channel, value=value))
    db.commit()
    db.refresh(scene)
    return scene


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
def test_list_is_empty_initially(client):
    assert client.get("/api/scenes").json() == {"scenes": []}


def test_scenes_are_listed_in_position_order(client, db_session):
    add_scene(db_session, "Second", position=1)
    add_scene(db_session, "First", position=0)

    names = [s["name"] for s in client.get("/api/scenes").json()["scenes"]]
    assert names == ["First", "Second"]


def test_scene_payload_shape(client, db_session):
    scene = add_scene(db_session, "Look 1", transition_type="fade",
                      duration=2000, values=[(1, 5, 128)])
    db_session.add(SceneGroupValue(scene_id=scene.id, group_id=3,
                                   master_value=200))
    db_session.add(SceneMasterValue(scene_id=scene.id, master_type="global",
                                    value=180))
    db_session.commit()

    body = client.get(f"/api/scenes/{scene.id}").json()

    assert body["name"] == "Look 1"
    assert body["transition_type"] == "fade"
    assert body["duration"] == 2000
    assert body["values"] == [{"universe_id": 1, "channel": 5, "value": 128}]
    assert body["group_values"][0]["group_id"] == 3
    assert body["master_values"][0]["value"] == 180


def test_get_missing_scene_is_404(client):
    assert client.get("/api/scenes/99").status_code == 404


def test_non_admins_only_see_their_allowed_scenes(make_app, interface,
                                                  db_session):
    allowed = add_scene(db_session, "Allowed")
    add_scene(db_session, "Hidden")

    client = make_app(scenes_api.router, prefix="/api/scenes",
                      user={"is_admin": False, "allowed_scenes": [allowed.id]})

    names = [s["name"] for s in client.get("/api/scenes").json()["scenes"]]
    assert names == ["Allowed"]


def test_admins_see_every_scene(make_app, interface, db_session):
    add_scene(db_session, "A")
    add_scene(db_session, "B")

    client = make_app(scenes_api.router, prefix="/api/scenes",
                      user={"is_admin": True, "allowed_scenes": [999]})
    assert len(client.get("/api/scenes").json()["scenes"]) == 2


def test_an_empty_allow_list_means_no_restriction(make_app, interface,
                                                  db_session):
    add_scene(db_session, "A")
    client = make_app(scenes_api.router, prefix="/api/scenes",
                      user={"is_admin": False, "allowed_scenes": []})
    assert len(client.get("/api/scenes").json()["scenes"]) == 1


def test_reorder_scenes(client, db_session):
    a = add_scene(db_session, "A", position=0)
    b = add_scene(db_session, "B", position=1)

    client.put("/api/scenes/reorder", json={"scene_ids": [b.id, a.id]})

    names = [s["name"] for s in client.get("/api/scenes").json()["scenes"]]
    assert names == ["B", "A"]


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------
def test_save_with_explicit_values(client, db_session):
    body = client.post("/api/scenes/save", json={
        "name": "Manual", "transition_type": "fade", "duration": 1500,
        "values": [{"universe_id": 1, "channel": 1, "value": 255}],
    }).json()

    assert body["name"] == "Manual"
    assert body["duration"] == 1500
    assert body["values"] == [{"universe_id": 1, "channel": 1, "value": 255}]
    assert db_session.query(Scene).count() == 1


def test_save_filters_explicit_values_by_universe(client):
    body = client.post("/api/scenes/save", json={
        "name": "Filtered",
        "universe_ids": [1],
        "values": [{"universe_id": 1, "channel": 1, "value": 10},
                   {"universe_id": 2, "channel": 1, "value": 20}],
    }).json()

    assert body["values"] == [{"universe_id": 1, "channel": 1, "value": 10}]


def test_save_captures_the_current_output(client, interface):
    interface.set_channel(1, 1, 111)

    body = client.post("/api/scenes/save",
                       json={"name": "Snapshot", "universe_ids": [1]}).json()

    assert len(body["values"]) == 512
    assert body["values"][0] == {"universe_id": 1, "channel": 1, "value": 111}


def test_save_captures_every_universe_by_default(client, interface):
    body = client.post("/api/scenes/save", json={"name": "All"}).json()
    assert len(body["values"]) == 1024


def test_save_ignores_unknown_universes(client):
    body = client.post("/api/scenes/save",
                       json={"name": "Ghost", "universe_ids": [99]}).json()
    assert body["values"] == []


def test_save_appends_to_the_end_of_the_order(client, db_session):
    add_scene(db_session, "Existing", position=3)
    body = client.post("/api/scenes/save",
                       json={"name": "New", "universe_ids": []}).json()
    assert body["position"] == 4


def test_the_second_scene_gets_the_next_position(client):
    client.post("/api/scenes/save", json={"name": "First", "universe_ids": []})
    second = client.post("/api/scenes/save",
                         json={"name": "Second", "universe_ids": []}).json()
    assert second["position"] == 1


def test_save_captures_group_master_values(client, db_session, interface):
    group = Group(name="Warm", master_value=77, enabled=True)
    db_session.add(group)
    db_session.commit()

    body = client.post("/api/scenes/save",
                       json={"name": "WithGroups", "universe_ids": []}).json()

    assert body["group_values"] == [{"group_id": group.id, "master_value": 77,
                                     "color_state_h": 0.0,
                                     "color_state_s": 0.0,
                                     "color_state_l": 100.0}]


def test_save_prefers_the_runtime_group_value(client, db_session, interface):
    group = Group(name="Warm", master_value=10, enabled=True)
    db_session.add(group)
    db_session.commit()
    interface.load_groups([{"id": group.id, "name": "Warm", "mode": "follow",
                            "master_universe": None, "master_channel": None,
                            "master_value": 240, "enabled": True,
                            "members": []}])

    body = client.post("/api/scenes/save",
                       json={"name": "Runtime", "universe_ids": []}).json()
    assert body["group_values"][0]["master_value"] == 240


def test_save_reads_a_physical_master_channel(client, db_session, interface):
    group = Group(name="Physical", master_universe=1, master_channel=5,
                  master_value=0, enabled=True)
    db_session.add(group)
    db_session.commit()
    interface.set_channel(1, 5, 199)

    body = client.post("/api/scenes/save",
                       json={"name": "Phys", "universe_ids": []}).json()
    assert body["group_values"][0]["master_value"] == 199


def test_save_skips_disabled_groups(client, db_session):
    db_session.add(Group(name="Off", enabled=False))
    db_session.commit()

    body = client.post("/api/scenes/save",
                       json={"name": "NoGroups", "universe_ids": []}).json()
    assert body["group_values"] == []


def test_save_can_select_specific_groups(client, db_session):
    keep = Group(name="Keep", enabled=True)
    skip = Group(name="Skip", enabled=True)
    db_session.add_all([keep, skip])
    db_session.commit()

    body = client.post("/api/scenes/save", json={
        "name": "Selected", "universe_ids": [], "group_ids": [keep.id]}).json()

    assert [gv["group_id"] for gv in body["group_values"]] == [keep.id]


def test_save_can_include_the_global_master(client, interface):
    interface.set_global_grandmaster(123)

    body = client.post("/api/scenes/save", json={
        "name": "GM", "universe_ids": [], "include_global_master": True}).json()

    assert body["master_values"] == [{"master_type": "global",
                                      "universe_id": None, "value": 123}]


def test_save_can_include_universe_masters(client, interface):
    interface.set_universe_grandmaster(1, 55)

    body = client.post("/api/scenes/save", json={
        "name": "UM", "universe_ids": [1],
        "include_universe_masters": True}).json()

    assert {"master_type": "universe", "universe_id": 1, "value": 55} in \
        body["master_values"]


def test_universe_masters_need_an_explicit_universe_selection(client):
    body = client.post("/api/scenes/save", json={
        "name": "UM", "include_universe_masters": True}).json()
    assert body["master_values"] == []


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------
def test_update_scene_metadata(client, db_session):
    scene = add_scene(db_session, "Old")

    body = client.put(f"/api/scenes/update/{scene.id}", json={
        "name": "New", "transition_type": "crossfade", "duration": 500}).json()

    assert body["name"] == "New"
    assert body["transition_type"] == "crossfade"
    assert body["duration"] == 500


def test_update_replaces_values(client, db_session):
    scene = add_scene(db_session, "Look", values=[(1, 1, 10), (1, 2, 20)])

    body = client.put(f"/api/scenes/update/{scene.id}", json={
        "values": [{"universe_id": 1, "channel": 9, "value": 90}]}).json()

    assert body["values"] == [{"universe_id": 1, "channel": 9, "value": 90}]


def test_update_replaces_group_and_master_values(client, db_session):
    scene = add_scene(db_session, "Look")
    db_session.add(SceneGroupValue(scene_id=scene.id, group_id=1,
                                   master_value=1))
    db_session.commit()

    body = client.put(f"/api/scenes/update/{scene.id}", json={
        "group_values": [{"group_id": 7, "master_value": 200,
                          "color_state_h": 180.0, "color_state_s": 100.0,
                          "color_state_l": 50.0}],
        "master_values": [{"master_type": "global", "value": 90}],
    }).json()

    assert body["group_values"][0]["group_id"] == 7
    assert body["group_values"][0]["color_state_h"] == 180.0
    assert body["master_values"][0]["value"] == 90


def test_partial_update_keeps_untouched_fields(client, db_session):
    scene = add_scene(db_session, "Keep", values=[(1, 1, 10)])

    body = client.put(f"/api/scenes/update/{scene.id}",
                      json={"name": "Renamed"}).json()
    assert body["values"] == [{"universe_id": 1, "channel": 1, "value": 10}]


def test_update_missing_scene_is_404(client):
    assert client.put("/api/scenes/update/99", json={"name": "x"}).status_code == 404


# ---------------------------------------------------------------------------
# Update with current values
# ---------------------------------------------------------------------------
def test_update_current_replaces_everything(client, db_session, interface):
    scene = add_scene(db_session, "Look", values=[(1, 1, 5)])
    interface.set_channel(1, 1, 250)

    body = client.post(f"/api/scenes/update-current/{scene.id}",
                       json={"universe_ids": [1]}).json()

    assert len(body["values"]) == 512
    assert body["values"][0]["value"] == 250


def test_update_current_merge_mode_keeps_other_universes(client, db_session,
                                                         interface):
    scene = add_scene(db_session, "Look", values=[(2, 7, 42)])
    interface.set_channel(1, 1, 100)

    body = client.post(f"/api/scenes/update-current/{scene.id}", json={
        "universe_ids": [1], "merge_mode": "merge"}).json()

    universe_two = [v for v in body["values"] if v["universe_id"] == 2]
    assert universe_two == [{"universe_id": 2, "channel": 7, "value": 42}]


def test_update_current_without_a_body(client, db_session, interface):
    scene = add_scene(db_session, "Look")
    interface.set_channel(1, 1, 60)

    body = client.post(f"/api/scenes/update-current/{scene.id}").json()
    assert len(body["values"]) == 1024  # both universes captured


def test_update_current_refreshes_group_values(client, db_session, interface):
    scene = add_scene(db_session, "Look")
    group = Group(name="G", master_value=50, enabled=True)
    db_session.add(group)
    db_session.commit()

    body = client.post(f"/api/scenes/update-current/{scene.id}",
                       json={"universe_ids": []}).json()
    assert body["group_values"][0]["master_value"] == 50


def test_update_current_can_capture_masters(client, db_session, interface):
    scene = add_scene(db_session, "Look")
    interface.set_global_grandmaster(200)
    interface.set_universe_grandmaster(1, 100)

    body = client.post(f"/api/scenes/update-current/{scene.id}", json={
        "universe_ids": [1], "include_global_master": True,
        "include_universe_masters": True}).json()

    kinds = {(mv["master_type"], mv["value"]) for mv in body["master_values"]}
    assert ("global", 200) in kinds
    assert ("universe", 100) in kinds


def test_update_current_missing_scene_is_404(client):
    assert client.post("/api/scenes/update-current/99").status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def test_delete_scene_and_its_values(client, db_session):
    scene = add_scene(db_session, "Look", values=[(1, 1, 10)])

    assert client.delete(f"/api/scenes/{scene.id}").json() == {
        "status": "deleted", "scene_id": scene.id}
    assert db_session.query(Scene).count() == 0
    assert db_session.query(SceneValue).count() == 0


def test_delete_missing_scene_is_404(client):
    assert client.delete("/api/scenes/99").status_code == 404


# ---------------------------------------------------------------------------
# Recall
# ---------------------------------------------------------------------------
def test_recall_applies_values_instantly(client, db_session, interface):
    scene = add_scene(db_session, "Look", values=[(1, 1, 200), (2, 3, 100)])

    body = client.post(f"/api/scenes/recall/{scene.id}").json()

    assert body == {"status": "recalled", "scene_id": scene.id,
                    "transition": "instant", "duration": 0}
    assert interface.get_channel(1, 1) == 200
    assert interface.get_channel(2, 3) == 100


def test_recall_sets_the_active_scene(client, db_session, interface):
    scene = add_scene(db_session, "Look", values=[(1, 1, 1)])
    client.post(f"/api/scenes/recall/{scene.id}")
    assert interface.get_active_scene() == scene.id


def test_recall_honours_transition_overrides(client, db_session, interface):
    scene = add_scene(db_session, "Look", transition_type="fade",
                      duration=5000, values=[(1, 1, 200)])

    body = client.post(f"/api/scenes/recall/{scene.id}", json={
        "override_transition": "instant", "override_duration": 0}).json()

    assert body["transition"] == "instant"
    assert body["duration"] == 0
    assert interface.get_channel(1, 1) == 200


def test_recall_with_a_short_fade(client, db_session, interface):
    scene = add_scene(db_session, "Fade", transition_type="fade", duration=33,
                      values=[(1, 1, 100)])

    client.post(f"/api/scenes/recall/{scene.id}")
    assert interface.get_channel(1, 1) == 100


def test_recall_with_a_crossfade(client, db_session, interface):
    scene = add_scene(db_session, "Cross", transition_type="crossfade",
                      duration=33, values=[(1, 1, 80)])

    client.post(f"/api/scenes/recall/{scene.id}")
    assert interface.get_channel(1, 1) == 80


def test_recall_skips_input_controlled_channels(client, db_session, interface):
    scene = add_scene(db_session, "Look", values=[(1, 1, 200), (1, 20, 50)])
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 10}

    client.post(f"/api/scenes/recall/{scene.id}")

    assert interface.get_channel(1, 1) == 0    # inside the input range
    assert interface.get_channel(1, 20) == 50  # outside it


def test_input_bypass_lets_the_scene_win(client, db_session, interface):
    scene = add_scene(db_session, "Look", values=[(1, 1, 200)])
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 10}
    interface.set_input_bypass(True)

    client.post(f"/api/scenes/recall/{scene.id}")
    assert interface.get_channel(1, 1) == 200


def test_recall_restores_group_master_values(client, db_session, interface):
    scene = add_scene(db_session, "Look")
    group = Group(name="Warm", mode="follow", master_value=0, enabled=True)
    db_session.add(group)
    db_session.commit()
    db_session.add(SceneGroupValue(scene_id=scene.id, group_id=group.id,
                                   master_value=210))
    db_session.commit()
    interface.load_groups([{"id": group.id, "name": "Warm", "mode": "follow",
                            "master_universe": None, "master_channel": None,
                            "master_value": 0, "enabled": True, "members": []}])

    client.post(f"/api/scenes/recall/{scene.id}")

    db_session.expire_all()
    assert db_session.query(Group).one().master_value == 210
    assert interface.get_group(group.id)["master_value"] == 210


def test_recall_writes_a_physical_master_channel(client, db_session, interface):
    scene = add_scene(db_session, "Look")
    group = Group(name="Phys", mode="follow", master_universe=1,
                  master_channel=10, enabled=True)
    db_session.add(group)
    db_session.commit()
    db_session.add(SceneGroupValue(scene_id=scene.id, group_id=group.id,
                                   master_value=145))
    db_session.commit()

    client.post(f"/api/scenes/recall/{scene.id}")
    assert interface.get_channel(1, 10) == 145


def test_recall_restores_colour_state(client, db_session, interface):
    scene = add_scene(db_session, "Colour")
    group = Group(name="Mix", mode="color_mixer", enabled=True)
    db_session.add(group)
    db_session.commit()
    db_session.add(SceneGroupValue(scene_id=scene.id, group_id=group.id,
                                   master_value=255, color_state_h=240.0,
                                   color_state_s=100.0, color_state_l=50.0))
    db_session.commit()
    interface.load_groups([{
        "id": group.id, "name": "Mix", "mode": "color_mixer",
        "master_universe": None, "master_channel": None, "master_value": 0,
        "enabled": True,
        "members": [{"universe_id": 1, "channel": 1, "base_value": 255,
                     "target_type": "channel", "color_role": "blue"}]}])

    client.post(f"/api/scenes/recall/{scene.id}")

    assert interface.get_group(group.id)["color_state"] == {"h": 240.0,
                                                            "s": 100.0,
                                                            "l": 50.0}
    assert interface.get_channel(1, 1) == 255


def test_recall_restores_grandmasters(client, db_session, interface):
    scene = add_scene(db_session, "Masters")
    db_session.add_all([
        SceneMasterValue(scene_id=scene.id, master_type="global", value=120),
        SceneMasterValue(scene_id=scene.id, master_type="universe",
                         universe_id=1, value=60),
    ])
    db_session.commit()

    client.post(f"/api/scenes/recall/{scene.id}")

    assert interface.get_global_grandmaster() == 120
    assert interface.get_universe_grandmaster(1) == 60


def test_recall_missing_scene_is_404(client):
    assert client.post("/api/scenes/recall/99").status_code == 404


def test_recalling_an_empty_scene_is_harmless(client, db_session, interface):
    scene = add_scene(db_session, "Empty")
    assert client.post(f"/api/scenes/recall/{scene.id}").json()["status"] == \
        "recalled"


# ---------------------------------------------------------------------------
# apply_fade helper
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_apply_fade_with_zero_duration_is_instant(interface):
    await apply_fade({1: {1: 200}}, 0)
    assert interface.get_channel(1, 1) == 200


@pytest.mark.asyncio
async def test_apply_fade_reaches_the_target(interface):
    interface.set_channel(1, 1, 0)
    await apply_fade({1: {1: 100}}, 66)
    assert interface.get_channel(1, 1) == 100


@pytest.mark.asyncio
async def test_apply_fade_only_touches_target_channels(interface):
    interface.set_channel(1, 2, 44)
    await apply_fade({1: {1: 100}}, 33)
    assert interface.get_channel(1, 2) == 44


@pytest.mark.asyncio
async def test_apply_fade_across_universes(interface):
    await apply_fade({1: {1: 10}, 2: {1: 20}}, 33)
    assert interface.get_channel(1, 1) == 10
    assert interface.get_channel(2, 1) == 20
