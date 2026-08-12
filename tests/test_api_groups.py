"""API tests for groups, grids, members and group actions."""
import pytest

from backend.api import groups as groups_api
from backend.database import Group, GroupGrid, GroupMember, ParkedChannel
from backend.dmx_interface import DMXInterface, DMXUniverse


@pytest.fixture
def interface(monkeypatch):
    dmx = DMXInterface()
    dmx.universes[1] = DMXUniverse(1)
    dmx.universes[2] = DMXUniverse(2)
    monkeypatch.setattr(groups_api, "dmx_interface", dmx)
    return dmx


@pytest.fixture
def client(make_app, interface):
    return make_app(groups_api.router, prefix="/api/groups")


def create_group(client, name="Warm", **extra):
    payload = {"name": name}
    payload.update(extra)
    return client.post("/api/groups", json=payload).json()


def channel_member(universe_id=1, channel=1, base_value=255, **extra):
    data = {"universe_id": universe_id, "channel": channel,
            "base_value": base_value, "target_type": "channel"}
    data.update(extra)
    return data


# ---------------------------------------------------------------------------
# Groups CRUD
# ---------------------------------------------------------------------------
def test_list_is_empty_initially(client):
    assert client.get("/api/groups").json() == {"groups": []}


def test_create_group_defaults(client, db_session):
    body = create_group(client)

    assert body["name"] == "Warm"
    assert body["mode"] == "proportional"
    assert body["enabled"] is True
    assert body["master_universe"] is None
    assert body["members"] == []
    assert body["color_state"] == {"h": 0, "s": 0, "l": 100}
    assert db_session.query(Group).count() == 1


def test_create_group_with_members(client, db_session):
    body = create_group(client, name="RGB", mode="follow", members=[
        channel_member(1, 1), channel_member(1, 2, base_value=128)])

    assert len(body["members"]) == 2
    assert body["members"][1]["base_value"] == 128
    assert db_session.query(GroupMember).count() == 2


def test_create_group_registers_it_in_the_runtime(client, interface):
    body = create_group(client, mode="follow", members=[channel_member(1, 1)])
    assert interface.get_group(body["id"]) is not None


def test_creating_a_group_creates_a_default_grid(client, db_session):
    body = create_group(client)

    grid = db_session.query(GroupGrid).one()
    assert grid.name == "Groups"
    assert body["grid_id"] == grid.id


def test_new_groups_join_the_first_existing_grid(client, db_session):
    grid = GroupGrid(name="Stage", position=0)
    db_session.add(grid)
    db_session.commit()

    assert create_group(client)["grid_id"] == grid.id


def test_the_second_group_gets_the_next_position(client):
    first = create_group(client, name="A")
    second = create_group(client, name="B")
    assert second["position"] == first["position"] + 1


def test_groups_are_listed_in_position_order(client, db_session):
    a = create_group(client, name="A")
    b = create_group(client, name="B")
    client.put("/api/groups/reorder", json={"group_ids": [a["id"], b["id"]]})

    names = [g["name"] for g in client.get("/api/groups").json()["groups"]]
    assert names == ["A", "B"]


def test_get_one_group(client):
    created = create_group(client)
    assert client.get(f"/api/groups/{created['id']}").json()["name"] == "Warm"


def test_get_missing_group_is_404(client):
    assert client.get("/api/groups/99").status_code == 404


def test_update_group_fields(client, interface):
    created = create_group(client)

    body = client.put(f"/api/groups/{created['id']}", json={
        "name": "Cool", "mode": "follow", "enabled": False,
        "color": "#00ff00"}).json()

    assert body["name"] == "Cool"
    assert body["mode"] == "follow"
    assert body["enabled"] is False
    assert body["color"] == "#00ff00"
    assert interface.get_group(created["id"])["mode"] == "follow"


def test_update_can_attach_and_clear_a_master_channel(client, interface):
    created = create_group(client)

    client.put(f"/api/groups/{created['id']}",
               json={"master_universe": 1, "master_channel": 10})
    assert interface._master_to_groups == {(1, 10): [created["id"]]}

    client.put(f"/api/groups/{created['id']}",
               json={"master_universe": None, "master_channel": None})
    assert interface._master_to_groups == {}


def test_update_missing_group_is_404(client):
    assert client.put("/api/groups/99", json={"name": "x"}).status_code == 404


def test_delete_group(client, db_session, interface):
    created = create_group(client, members=[channel_member(1, 1)])

    assert client.delete(f"/api/groups/{created['id']}").json() == {
        "status": "deleted", "group_id": created["id"]}
    assert db_session.query(Group).count() == 0
    assert db_session.query(GroupMember).count() == 0
    assert interface.get_group(created["id"]) is None


def test_delete_missing_group_is_404(client):
    assert client.delete("/api/groups/99").status_code == 404


def test_reorder_groups(client):
    a = create_group(client, name="A")
    b = create_group(client, name="B")

    client.put("/api/groups/reorder", json={"group_ids": [b["id"], a["id"]]})

    names = [g["name"] for g in client.get("/api/groups").json()["groups"]]
    assert names == ["B", "A"]


def test_runtime_values_endpoint(client, interface):
    created = create_group(client, mode="follow", members=[channel_member(1, 1)])
    interface.apply_group_direct(created["id"], 150)

    values = client.get("/api/groups/runtime-values").json()["values"]
    assert values[str(created["id"])] == 150


# ---------------------------------------------------------------------------
# Grids
# ---------------------------------------------------------------------------
def test_grid_list_is_empty_initially(client):
    assert client.get("/api/groups/grids").json() == {"grids": []}


def test_create_grid(client, db_session):
    body = client.post("/api/groups/grids",
                       json={"name": "Stage", "color": "#ff0000"}).json()

    assert body["name"] == "Stage"
    assert body["color"] == "#ff0000"
    assert body["position"] == 0
    assert body["groups"] == []
    assert db_session.query(GroupGrid).count() == 1


def test_the_second_grid_gets_the_next_position(client):
    client.post("/api/groups/grids", json={"name": "First"})
    second = client.post("/api/groups/grids", json={"name": "Second"}).json()
    assert second["position"] == 1


def test_grids_are_listed_in_position_order(client):
    a = client.post("/api/groups/grids", json={"name": "First"}).json()
    b = client.post("/api/groups/grids", json={"name": "Second"}).json()
    client.put("/api/groups/grids/reorder", json={"grid_ids": [a["id"], b["id"]]})

    names = [g["name"] for g in client.get("/api/groups/grids").json()["grids"]]
    assert names == ["First", "Second"]


def test_grid_includes_its_groups(client):
    grid = client.post("/api/groups/grids", json={"name": "Stage"}).json()
    create_group(client, name="In grid", grid_id=grid["id"])

    body = client.get(f"/api/groups/grids/{grid['id']}").json()
    assert [g["name"] for g in body["groups"]] == ["In grid"]


def test_get_missing_grid_is_404(client):
    assert client.get("/api/groups/grids/99").status_code == 404


def test_update_grid(client):
    grid = client.post("/api/groups/grids", json={"name": "Old"}).json()

    body = client.put(f"/api/groups/grids/{grid['id']}",
                      json={"name": "New", "color": "#123456"}).json()
    assert body["name"] == "New"
    assert body["color"] == "#123456"


def test_grid_colour_can_be_cleared(client):
    grid = client.post("/api/groups/grids",
                       json={"name": "G", "color": "#ffffff"}).json()

    body = client.put(f"/api/groups/grids/{grid['id']}",
                      json={"color": None}).json()
    assert body["color"] is None


def test_update_missing_grid_is_404(client):
    assert client.put("/api/groups/grids/99", json={"name": "x"}).status_code == 404


def test_reorder_grids(client):
    a = client.post("/api/groups/grids", json={"name": "A"}).json()
    b = client.post("/api/groups/grids", json={"name": "B"}).json()

    client.put("/api/groups/grids/reorder", json={"grid_ids": [b["id"], a["id"]]})

    names = [g["name"] for g in client.get("/api/groups/grids").json()["grids"]]
    assert names == ["B", "A"]


def test_deleting_a_grid_moves_its_groups(client, db_session):
    keep = client.post("/api/groups/grids", json={"name": "Keep"}).json()
    doomed = client.post("/api/groups/grids", json={"name": "Doomed"}).json()
    group = create_group(client, grid_id=doomed["id"])

    body = client.delete(f"/api/groups/grids/{doomed['id']}").json()

    assert body["groups_moved_to"] == keep["id"]
    db_session.expire_all()
    assert db_session.query(Group).get(group["id"]).grid_id == keep["id"]


def test_deleting_the_last_grid_creates_a_replacement(client, db_session):
    grid = client.post("/api/groups/grids", json={"name": "Only"}).json()
    create_group(client, grid_id=grid["id"])

    client.delete(f"/api/groups/grids/{grid['id']}")

    remaining = db_session.query(GroupGrid).all()
    assert len(remaining) == 1
    assert remaining[0].name == "Groups"


def test_delete_missing_grid_is_404(client):
    assert client.delete("/api/groups/grids/99").status_code == 404


def test_moving_a_group_between_grids(client):
    grid_a = client.post("/api/groups/grids", json={"name": "A"}).json()
    grid_b = client.post("/api/groups/grids", json={"name": "B"}).json()
    group = create_group(client, grid_id=grid_a["id"])

    body = client.put(f"/api/groups/{group['id']}",
                      json={"grid_id": grid_b["id"]}).json()
    assert body["grid_id"] == grid_b["id"]


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
def test_add_a_member(client, db_session, interface):
    group = create_group(client)

    body = client.post(f"/api/groups/{group['id']}/members",
                       json=channel_member(1, 5, base_value=200)).json()

    assert body["universe_id"] == 1
    assert body["channel"] == 5
    assert body["base_value"] == 200
    assert db_session.query(GroupMember).count() == 1
    assert len(interface.get_group(group["id"])["members"]) == 1


def test_duplicate_channel_members_are_rejected(client):
    group = create_group(client, members=[channel_member(1, 1)])

    response = client.post(f"/api/groups/{group['id']}/members",
                           json=channel_member(1, 1))
    assert response.status_code == 400
    assert response.json()["detail"] == "Member already exists in group"


def test_virtual_master_members(client, db_session):
    group = create_group(client)

    client.post(f"/api/groups/{group['id']}/members", json={
        "target_type": "universe_master", "target_universe_id": 2})
    client.post(f"/api/groups/{group['id']}/members", json={
        "target_type": "global_master"})

    body = client.get(f"/api/groups/{group['id']}").json()
    kinds = {m["target_type"] for m in body["members"]}
    assert kinds == {"universe_master", "global_master"}


def test_duplicate_virtual_members_are_rejected(client):
    group = create_group(client)
    payload = {"target_type": "global_master"}
    client.post(f"/api/groups/{group['id']}/members", json=payload)

    assert client.post(f"/api/groups/{group['id']}/members",
                       json=payload).status_code == 400


def test_duplicate_universe_master_members_are_rejected(client):
    group = create_group(client)
    payload = {"target_type": "universe_master", "target_universe_id": 2}
    client.post(f"/api/groups/{group['id']}/members", json=payload)

    assert client.post(f"/api/groups/{group['id']}/members",
                       json=payload).status_code == 400


def test_add_member_to_a_missing_group_is_404(client):
    assert client.post("/api/groups/99/members",
                       json=channel_member()).status_code == 404


def test_update_a_member(client):
    group = create_group(client, members=[channel_member(1, 1)])
    member_id = client.get(f"/api/groups/{group['id']}").json()["members"][0]["id"]

    body = client.put(f"/api/groups/{group['id']}/members/{member_id}",
                      json=channel_member(2, 9, base_value=64,
                                          color_role="red")).json()

    assert body["universe_id"] == 2
    assert body["channel"] == 9
    assert body["base_value"] == 64
    assert body["color_role"] == "red"


def test_updating_a_member_clears_its_old_contribution(client, interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    interface.apply_group_direct(group["id"], 200)
    assert interface.get_channel(1, 1) == 200

    member_id = client.get(f"/api/groups/{group['id']}").json()["members"][0]["id"]
    client.put(f"/api/groups/{group['id']}/members/{member_id}",
               json=channel_member(1, 2))

    assert interface.get_channel(1, 1) == 0


def test_update_can_convert_a_member_to_a_virtual_master(client, db_session,
                                                        interface):
    """Regression: target_type used to be ignored, leaving a broken row."""
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    member_id = client.get(f"/api/groups/{group['id']}").json()["members"][0]["id"]

    body = client.put(f"/api/groups/{group['id']}/members/{member_id}",
                      json={"target_type": "global_master"}).json()

    assert body["target_type"] == "global_master"
    stored = db_session.query(GroupMember).one()
    assert stored.target_type == "global_master"

    # And it actually drives the global grandmaster now
    interface.apply_group_direct(group["id"], 64)
    assert interface.get_global_grandmaster() == 64


def test_update_can_convert_a_member_to_a_universe_master(client, db_session,
                                                          interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    member_id = client.get(f"/api/groups/{group['id']}").json()["members"][0]["id"]

    body = client.put(f"/api/groups/{group['id']}/members/{member_id}", json={
        "target_type": "universe_master", "target_universe_id": 2}).json()

    assert body["target_type"] == "universe_master"
    assert body["target_universe_id"] == 2

    interface.apply_group_direct(group["id"], 120)
    assert interface.get_universe_grandmaster(2) == 120


def test_update_can_convert_a_virtual_master_back_to_a_channel(client,
                                                               db_session,
                                                               interface):
    group = create_group(client)
    client.post(f"/api/groups/{group['id']}/members",
                json={"target_type": "global_master"})
    member_id = client.get(f"/api/groups/{group['id']}").json()["members"][0]["id"]

    body = client.put(f"/api/groups/{group['id']}/members/{member_id}",
                      json=channel_member(1, 4)).json()

    assert body["target_type"] == "channel"
    assert body["target_universe_id"] is None
    assert db_session.query(GroupMember).one().channel == 4


def test_update_missing_member_is_404(client):
    group = create_group(client)
    assert client.put(f"/api/groups/{group['id']}/members/99",
                      json=channel_member()).status_code == 404


def test_remove_a_member(client, db_session, interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    interface.apply_group_direct(group["id"], 150)
    member_id = client.get(f"/api/groups/{group['id']}").json()["members"][0]["id"]

    body = client.delete(f"/api/groups/{group['id']}/members/{member_id}").json()

    assert body == {"status": "deleted", "member_id": member_id}
    assert db_session.query(GroupMember).count() == 0
    assert interface.get_channel(1, 1) == 0


def test_remove_missing_member_is_404(client):
    group = create_group(client)
    assert client.delete(
        f"/api/groups/{group['id']}/members/99").status_code == 404


def test_bulk_add_members(client, db_session):
    group = create_group(client)

    body = client.post(f"/api/groups/{group['id']}/members/bulk", json={
        "members": [channel_member(1, 1), channel_member(1, 2),
                    channel_member(1, 3)]}).json()

    assert body["added"] == 3
    assert body["skipped"] == 0
    assert db_session.query(GroupMember).count() == 3


def test_bulk_add_skips_duplicates(client):
    group = create_group(client, members=[channel_member(1, 1)])

    body = client.post(f"/api/groups/{group['id']}/members/bulk", json={
        "members": [channel_member(1, 1), channel_member(1, 2)]}).json()

    assert body["added"] == 1
    assert body["skipped"] == 1
    assert body["skipped_members"] == [{"universe_id": 1, "channel": 1}]


def test_bulk_add_to_a_missing_group_is_404(client):
    assert client.post("/api/groups/99/members/bulk",
                       json={"members": []}).status_code == 404


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------
def test_trigger_a_virtual_master(client, db_session, interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])

    body = client.post(f"/api/groups/{group['id']}/trigger?value=128").json()

    assert body["value"] == 128
    assert interface.get_channel(1, 1) == 128
    db_session.expire_all()
    assert db_session.query(Group).one().master_value == 128


def test_trigger_a_dmx_linked_master(client, interface):
    group = create_group(client, mode="follow", master_universe=1,
                         master_channel=10, members=[channel_member(1, 1)])

    client.post(f"/api/groups/{group['id']}/trigger?value=99")

    assert interface.get_channel(1, 10) == 99
    assert interface.get_channel(1, 1) == 99


@pytest.mark.parametrize("value", [-1, 256])
def test_trigger_validates_the_value(client, value):
    group = create_group(client)
    assert client.post(
        f"/api/groups/{group['id']}/trigger?value={value}").status_code == 400


def test_trigger_missing_group_is_404(client):
    assert client.post("/api/groups/99/trigger?value=1").status_code == 404


def test_get_group_master_value(client, interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    client.post(f"/api/groups/{group['id']}/trigger?value=44")

    assert client.get(f"/api/groups/{group['id']}/trigger").json()["value"] == 44


def test_get_master_value_reads_the_linked_channel(client, interface):
    group = create_group(client, master_universe=1, master_channel=10)
    interface.set_channel(1, 10, 77)

    assert client.get(f"/api/groups/{group['id']}/trigger").json()["value"] == 77


def test_trigger_is_blocked_when_the_master_is_input_controlled(client,
                                                                interface):
    group = create_group(client, mode="follow", master_universe=1,
                         master_channel=10, members=[channel_member(1, 1)])
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 20}

    response = client.post(f"/api/groups/{group['id']}/trigger?value=100")
    assert response.status_code == 400
    assert "Input Bypass" in response.json()["detail"]


def test_input_bypass_re_enables_triggering(client, interface):
    group = create_group(client, mode="follow", master_universe=1,
                         master_channel=10, members=[channel_member(1, 1)])
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 20}
    interface.set_input_bypass(True)

    assert client.post(
        f"/api/groups/{group['id']}/trigger?value=100").status_code == 200


def test_trigger_is_blocked_when_members_are_input_controlled(client, interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    interface.inputs[1] = object()
    interface._passthrough_config[1] = {"passthrough_mode": "faders_output",
                                        "mode": "htp", "channel_start": 1,
                                        "channel_end": 5}

    response = client.post(f"/api/groups/{group['id']}/trigger?value=100")
    assert response.status_code == 400
    assert "member channels" in response.json()["detail"]


def test_trigger_is_blocked_when_every_member_is_parked(client, interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    interface.park_channel(1, 1, 50)

    response = client.post(f"/api/groups/{group['id']}/trigger?value=100")
    assert response.status_code == 400
    assert "parked" in response.json()["detail"]


def test_trigger_is_blocked_when_every_member_is_highlighted(client, interface):
    group = create_group(client, mode="follow", members=[channel_member(1, 1)])
    interface.start_highlight(1, [1])

    response = client.post(f"/api/groups/{group['id']}/trigger?value=100")
    assert response.status_code == 400
    assert "highlighted" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Colour mixer
# ---------------------------------------------------------------------------
def test_update_group_colour(client, db_session, interface):
    group = create_group(client, mode="color_mixer", members=[
        channel_member(1, 1, color_role="red"),
        channel_member(1, 2, color_role="blue")])
    client.post(f"/api/groups/{group['id']}/trigger?value=255")

    body = client.put(f"/api/groups/{group['id']}/color",
                      json={"h": 240, "s": 100, "l": 50}).json()

    assert body["color_state"] == {"h": 240, "s": 100, "l": 50}
    assert interface.get_channel(1, 1) == 0
    assert interface.get_channel(1, 2) == 255

    db_session.expire_all()
    stored = db_session.query(Group).one()
    assert (stored.color_state_h, stored.color_state_s,
            stored.color_state_l) == (240, 100, 50)


def test_colour_endpoint_rejects_other_modes(client):
    group = create_group(client, mode="follow")
    response = client.put(f"/api/groups/{group['id']}/color",
                          json={"h": 1, "s": 1, "l": 1})
    assert response.status_code == 400
    assert response.json()["detail"] == "Group is not a color_mixer"


@pytest.mark.parametrize("payload,detail", [
    ({"h": 400, "s": 50, "l": 50}, "Hue must be 0-360"),
    ({"h": 10, "s": 200, "l": 50}, "Saturation must be 0-100"),
    ({"h": 10, "s": 50, "l": 200}, "Lightness must be 0-100"),
])
def test_colour_validation(client, payload, detail):
    group = create_group(client, mode="color_mixer")
    response = client.put(f"/api/groups/{group['id']}/color", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == detail


def test_colour_endpoint_missing_group_is_404(client):
    assert client.put("/api/groups/99/color",
                      json={"h": 1, "s": 1, "l": 1}).status_code == 404


# ---------------------------------------------------------------------------
# Group highlight & park
# ---------------------------------------------------------------------------
def test_highlight_a_group(client, interface):
    group = create_group(client, members=[channel_member(1, 1),
                                          channel_member(1, 2)])

    body = client.post(f"/api/groups/{group['id']}/highlight").json()

    assert body["highlighted_channels"] == 2
    assert interface.is_channel_highlighted(1, 1) is True
    assert interface.is_channel_highlighted(1, 2) is True


def test_stop_highlighting_a_group(client, interface):
    group = create_group(client, members=[channel_member(1, 1)])
    client.post(f"/api/groups/{group['id']}/highlight")

    body = client.post(f"/api/groups/{group['id']}/highlight/stop").json()

    assert body["unhighlighted_channels"] == 1
    assert interface.get_highlight_state()["active"] is False


def test_highlighting_a_group_without_channels_is_rejected(client):
    group = create_group(client)
    response = client.post(f"/api/groups/{group['id']}/highlight")
    assert response.status_code == 400
    assert "no channel members" in response.json()["detail"]


def test_group_highlight_requires_the_permission(make_app, interface, client):
    group = create_group(client, members=[channel_member(1, 1)])
    restricted = make_app(groups_api.router, prefix="/api/groups",
                          user={"can_highlight": False})

    assert restricted.post(
        f"/api/groups/{group['id']}/highlight").status_code == 403
    assert restricted.post(
        f"/api/groups/{group['id']}/highlight/stop").status_code == 403


def test_park_a_group_at_its_current_values(client, interface, db_session):
    group = create_group(client, members=[channel_member(1, 1),
                                          channel_member(1, 2)])
    interface.set_channel(1, 1, 90)
    interface.set_channel(1, 2, 45)

    body = client.post(f"/api/groups/{group['id']}/park").json()

    assert body["parked_channels"] == 2
    assert interface.get_parked_channels(1) == {1: 90, 2: 45}
    stored = {(p.channel, p.value) for p in db_session.query(ParkedChannel)}
    assert stored == {(1, 90), (2, 45)}


def test_unpark_a_group(client, interface, db_session):
    group = create_group(client, members=[channel_member(1, 1)])
    client.post(f"/api/groups/{group['id']}/park")

    body = client.post(f"/api/groups/{group['id']}/unpark").json()

    assert body["unparked_channels"] == 1
    assert interface.get_parked_channels(1) == {}
    assert db_session.query(ParkedChannel).count() == 0


def test_parking_a_group_without_channels_is_rejected(client):
    group = create_group(client)
    assert client.post(f"/api/groups/{group['id']}/park").status_code == 400


def test_group_park_requires_the_permission(make_app, interface, client):
    group = create_group(client, members=[channel_member(1, 1)])
    restricted = make_app(groups_api.router, prefix="/api/groups",
                          user={"can_park": False})

    assert restricted.post(f"/api/groups/{group['id']}/park").status_code == 403
    assert restricted.post(f"/api/groups/{group['id']}/unpark").status_code == 403


def test_group_actions_require_a_known_group(client):
    for path in ("/api/groups/99/highlight", "/api/groups/99/highlight/stop",
                 "/api/groups/99/park", "/api/groups/99/unpark"):
        assert client.post(path).status_code == 404


# ---------------------------------------------------------------------------
# Bulk input link
# ---------------------------------------------------------------------------
def test_bulk_input_link_assigns_sequential_channels(client, interface):
    a = create_group(client, name="A")
    b = create_group(client, name="B")

    body = client.post("/api/groups/bulk-input-link", json={
        "group_ids": [a["id"], b["id"]], "start_universe": 1,
        "start_channel": 500}).json()

    assert body["updated"] == 2
    channels = [g["master_channel"] for g in body["updated_groups"]]
    assert channels == [500, 501]
    assert interface._master_to_groups == {(1, 500): [a["id"]],
                                           (1, 501): [b["id"]]}


def test_bulk_input_link_reports_unknown_groups(client):
    a = create_group(client, name="A")

    body = client.post("/api/groups/bulk-input-link", json={
        "group_ids": [a["id"], 999], "start_universe": 1,
        "start_channel": 1}).json()

    assert body["updated"] == 1
    assert body["not_found_ids"] == [999]


def test_bulk_input_link_requires_group_ids(client):
    response = client.post("/api/groups/bulk-input-link", json={
        "group_ids": [], "start_universe": 1, "start_channel": 1})
    assert response.status_code == 400
    assert response.json()["detail"] == "No group IDs provided"


@pytest.mark.parametrize("start_channel", [0, 513])
def test_bulk_input_link_validates_the_start_channel(client, start_channel):
    group = create_group(client)
    response = client.post("/api/groups/bulk-input-link", json={
        "group_ids": [group["id"]], "start_universe": 1,
        "start_channel": start_channel})
    assert response.status_code == 400


def test_bulk_input_link_rejects_a_range_that_overflows(client):
    groups = [create_group(client, name=f"G{i}")["id"] for i in range(3)]

    response = client.post("/api/groups/bulk-input-link", json={
        "group_ids": groups, "start_universe": 1, "start_channel": 511})
    assert response.status_code == 400
    assert "Not enough channels" in response.json()["detail"]
