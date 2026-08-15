"""Tests for group/master handling: HTP merge, modes, colour mixing, CRUD."""
import pytest


def member(universe_id=1, channel=1, base_value=255, **extra):
    data = {
        "universe_id": universe_id,
        "channel": channel,
        "base_value": base_value,
        "target_type": "channel",
        "target_universe_id": None,
        "color_role": None,
    }
    data.update(extra)
    return data


def group(group_id=1, name="G", mode="proportional", members=None,
          master_universe=None, master_channel=None, enabled=True, **extra):
    data = {
        "id": group_id,
        "name": name,
        "mode": mode,
        "master_universe": master_universe,
        "master_channel": master_channel,
        "master_value": 0,
        "enabled": enabled,
        "members": members if members is not None else [member()],
    }
    data.update(extra)
    return data


# ---------------------------------------------------------------------------
# load_groups / lookup tables
# ---------------------------------------------------------------------------
def test_load_groups_stores_groups(dmx1):
    dmx1.load_groups([group(1), group(2, name="Second")])
    assert set(dmx1.get_groups()) == {1, 2}
    assert dmx1.get_group(2)["name"] == "Second"


def test_load_groups_replaces_previous_state(dmx1):
    dmx1.load_groups([group(1)])
    dmx1.load_groups([group(9)])
    assert set(dmx1.get_groups()) == {9}


def test_load_groups_builds_master_lookup(dmx1):
    dmx1.load_groups([group(1, master_universe=1, master_channel=10)])
    assert dmx1._master_to_groups == {(1, 10): [1]}


def test_groups_without_master_are_not_in_lookup(dmx1):
    dmx1.load_groups([group(1)])
    assert dmx1._master_to_groups == {}


def test_two_groups_can_share_one_master_channel(dmx1):
    dmx1.load_groups([
        group(1, master_universe=1, master_channel=10),
        group(2, master_universe=1, master_channel=10),
    ])
    assert dmx1._master_to_groups[(1, 10)] == [1, 2]


def test_get_groups_returns_a_copy(dmx1):
    dmx1.load_groups([group(1)])
    snapshot = dmx1.get_groups()
    del snapshot[1]
    assert 1 in dmx1.get_groups()


def test_get_unknown_group_is_none(dmx):
    assert dmx.get_group(404) is None


def test_color_mixer_groups_get_default_white_state(dmx1):
    dmx1.load_groups([group(1, mode="color_mixer")])
    assert dmx1.get_group(1)["color_state"] == {"h": 0, "s": 0, "l": 100}


# ---------------------------------------------------------------------------
# Applying a master value
# ---------------------------------------------------------------------------
def test_proportional_mode_scales_by_base_value(dmx1):
    dmx1.load_groups([group(1, members=[
        member(channel=1, base_value=255),
        member(channel=2, base_value=128),
    ])])

    dmx1.apply_group_direct(1, 255)
    assert dmx1.get_channel(1, 1) == 255
    assert dmx1.get_channel(1, 2) == 128

    dmx1.apply_group_direct(1, 128)
    assert dmx1.get_channel(1, 1) == round(255 * 128 / 255)
    assert dmx1.get_channel(1, 2) == round(128 * 128 / 255)


def test_follow_mode_copies_master_to_every_member(dmx1):
    dmx1.load_groups([group(1, mode="follow", members=[
        member(channel=1, base_value=10),
        member(channel=2, base_value=200),
    ])])

    dmx1.apply_group_direct(1, 77)
    assert dmx1.get_channel(1, 1) == 77
    assert dmx1.get_channel(1, 2) == 77


def test_apply_group_direct_stores_master_value(dmx1):
    dmx1.load_groups([group(1)])
    dmx1.apply_group_direct(1, 99)
    assert dmx1.get_group(1)["master_value"] == 99


def test_disabled_group_is_not_applied(dmx1):
    dmx1.load_groups([group(1, enabled=False)])
    dmx1.apply_group_direct(1, 255)
    assert dmx1.get_channel(1, 1) == 0


def test_applying_an_unknown_group_is_safe(dmx1):
    dmx1.apply_group_direct(404, 255)


def test_group_output_marks_channel_source_as_group(dmx1):
    dmx1.load_groups([group(1)])
    dmx1.apply_group_direct(1, 100)
    assert dmx1.get_channel_source(1, 1) == "group"


def test_group_apply_notifies_callbacks(dmx1, events):
    dmx1.load_groups([group(1)])
    dmx1.apply_group_direct(1, 100)

    changes = [d for kind, d in events if kind == "channel_change"]
    assert changes == [{"universe_id": 1, "channel": 1,
                        "value": 100, "source": "group"}]


def test_group_spans_multiple_universes(dmx12):
    dmx12.load_groups([group(1, mode="follow", members=[
        member(universe_id=1, channel=1),
        member(universe_id=2, channel=1),
    ])])
    dmx12.apply_group_direct(1, 60)
    assert dmx12.get_channel(1, 1) == 60
    assert dmx12.get_channel(2, 1) == 60


def test_members_on_missing_universes_are_skipped(dmx1):
    dmx1.load_groups([group(1, mode="follow", members=[
        member(universe_id=1, channel=1),
        member(universe_id=99, channel=1),
    ])])
    dmx1.apply_group_direct(1, 50)
    assert dmx1.get_channel(1, 1) == 50


def test_members_without_channel_targets_are_skipped(dmx1):
    dmx1.load_groups([group(1, mode="follow", members=[
        member(universe_id=None, channel=None),
        member(channel=1),
    ])])
    dmx1.apply_group_direct(1, 50)
    assert dmx1.get_channel(1, 1) == 50


def test_group_does_not_overwrite_parked_channel(dmx1):
    dmx1.park_channel(1, 1, 42)
    dmx1.load_groups([group(1, mode="follow")])
    dmx1.apply_group_direct(1, 255)
    assert dmx1.get_channel(1, 1) == 42


# ---------------------------------------------------------------------------
# HTP merge between groups
# ---------------------------------------------------------------------------
def test_highest_group_wins_on_a_shared_channel(dmx1):
    dmx1.load_groups([
        group(1, mode="follow", members=[member(channel=1)]),
        group(2, mode="follow", members=[member(channel=1)]),
    ])

    dmx1.apply_group_direct(1, 100)
    dmx1.apply_group_direct(2, 200)
    assert dmx1.get_channel(1, 1) == 200

    dmx1.apply_group_direct(2, 50)
    assert dmx1.get_channel(1, 1) == 100  # group 1 still holds it up


def test_group_contributions_are_tracked_per_group(dmx1):
    dmx1.load_groups([
        group(1, mode="follow", members=[member(channel=1)]),
        group(2, mode="follow", members=[member(channel=1)]),
    ])
    dmx1.apply_group_direct(1, 10)
    dmx1.apply_group_direct(2, 20)
    assert dmx1._group_contributions[(1, 1)] == {1: 10, 2: 20}


def test_clear_group_contribution_reapplies_htp(dmx1):
    dmx1.load_groups([
        group(1, mode="follow", members=[member(channel=1)]),
        group(2, mode="follow", members=[member(channel=1)]),
    ])
    dmx1.apply_group_direct(1, 100)
    dmx1.apply_group_direct(2, 200)

    dmx1.clear_group_contribution(2, 1, 1)
    assert dmx1.get_channel(1, 1) == 100


def test_clearing_the_last_contribution_zeroes_the_channel(dmx1):
    dmx1.load_groups([group(1, mode="follow", members=[member(channel=1)])])
    dmx1.apply_group_direct(1, 100)

    dmx1.clear_group_contribution(1, 1, 1)
    assert dmx1.get_channel(1, 1) == 0
    assert (1, 1) not in dmx1._group_contributions


def test_clear_contribution_for_unknown_channel_is_safe(dmx1):
    dmx1.clear_group_contribution(1, 1, 1)


# ---------------------------------------------------------------------------
# Physical master channels
# ---------------------------------------------------------------------------
def test_setting_the_master_channel_drives_the_group(dmx1):
    dmx1.load_groups([group(1, mode="follow", master_universe=1,
                            master_channel=10,
                            members=[member(channel=1), member(channel=2)])])

    dmx1.set_channel(1, 10, 123)

    assert dmx1.get_channel(1, 1) == 123
    assert dmx1.get_channel(1, 2) == 123
    assert dmx1.get_group(1)["master_value"] == 123


def test_master_channel_via_bulk_set(dmx1, task_recorder):
    dmx1.load_groups([group(1, mode="follow", master_universe=1,
                            master_channel=10, members=[member(channel=1)])])

    dmx1.set_channels(1, {10: 200})

    assert dmx1.get_channel(1, 1) == 200
    assert task_recorder.count >= 1  # group value broadcast scheduled


def test_one_master_channel_drives_two_groups(dmx1):
    dmx1.load_groups([
        group(1, mode="follow", master_universe=1, master_channel=10,
              members=[member(channel=1)]),
        group(2, mode="follow", master_universe=1, master_channel=10,
              members=[member(channel=2)]),
    ])
    dmx1.set_channel(1, 10, 90)
    assert dmx1.get_channel(1, 1) == 90
    assert dmx1.get_channel(1, 2) == 90


# ---------------------------------------------------------------------------
# Reverse control: moving a member fader updates the master
# ---------------------------------------------------------------------------
def test_moving_a_member_in_follow_mode_sets_the_master(dmx1):
    dmx1.load_groups([group(1, mode="follow",
                            members=[member(channel=1), member(channel=2)])])

    dmx1.set_channels(1, {1: 150}, source="user_a")

    assert dmx1.get_group(1)["master_value"] == 150
    assert dmx1.get_channel(1, 1) == 150
    assert dmx1.get_channel(1, 2) == 150


def test_moving_a_member_in_proportional_mode_back_calculates_master(dmx1):
    dmx1.load_groups([group(1, members=[member(channel=1, base_value=128)])])

    dmx1.set_channels(1, {1: 64}, source="user_a")

    assert dmx1.get_group(1)["master_value"] == round(64 * 255 / 128)


def test_reverse_calculation_is_capped_at_255(dmx1):
    dmx1.load_groups([group(1, members=[member(channel=1, base_value=10)])])
    dmx1.set_channels(1, {1: 255}, source="user_a")
    assert dmx1.get_group(1)["master_value"] == 255


def test_zero_base_value_falls_back_to_the_raw_value(dmx1):
    dmx1.load_groups([group(1, members=[member(channel=1, base_value=0)])])
    dmx1.set_channels(1, {1: 90}, source="user_a")
    assert dmx1.get_group(1)["master_value"] == 90


def test_member_of_two_groups_snaps_back(dmx1, events):
    dmx1.load_groups([
        group(1, mode="follow", members=[member(channel=1)]),
        group(2, mode="follow", members=[member(channel=1)]),
    ])
    dmx1.apply_group_direct(1, 80)
    events.clear()

    dmx1.set_channels(1, {1: 200}, source="user_a")

    rejects = [d for kind, d in events if kind == "channel_change"
               and d["source"] == "group_reject"]
    assert rejects and rejects[0]["value"] == 80
    assert dmx1.get_channel(1, 1) == 80


def test_non_user_sources_bypass_group_reverse_logic(dmx1):
    dmx1.load_groups([group(1, mode="follow", members=[member(channel=1)])])
    dmx1.set_channels(1, {1: 200}, source="input")
    assert dmx1.get_channel(1, 1) == 200
    assert dmx1.get_group(1)["master_value"] == 0


def test_physical_master_channel_follows_reverse_calculation(dmx1, events):
    dmx1.load_groups([group(1, mode="follow", master_universe=1,
                            master_channel=10, members=[member(channel=1)])])

    dmx1.set_channels(1, {1: 111}, source="user_a")

    assert dmx1.get_channel(1, 10) == 111
    assert dmx1.get_channel_source(1, 10) == "group_reverse"
    assert any(d["source"] == "group_reverse"
               for kind, d in events if kind == "channel_change")


def test_disabled_group_members_behave_like_plain_channels(dmx1):
    dmx1.load_groups([group(1, mode="follow", enabled=False,
                            members=[member(channel=1)])])
    dmx1.set_channels(1, {1: 210}, source="user_a")
    assert dmx1.get_channel(1, 1) == 210


# ---------------------------------------------------------------------------
# Virtual targets
# ---------------------------------------------------------------------------
def test_group_can_drive_a_universe_grandmaster(dmx12):
    dmx12.load_groups([group(1, mode="follow", members=[
        member(target_type="universe_master", universe_id=None,
               channel=None, target_universe_id=2)])])

    dmx12.apply_group_direct(1, 128)
    assert dmx12.get_universe_grandmaster(2) == 128


def test_group_can_drive_the_global_grandmaster(dmx1):
    dmx1.load_groups([group(1, mode="follow", members=[
        member(target_type="global_master", universe_id=None, channel=None)])])

    dmx1.apply_group_direct(1, 64)
    assert dmx1.get_global_grandmaster() == 64


def test_universe_master_target_without_id_is_skipped(dmx1):
    dmx1.load_groups([group(1, mode="follow", members=[
        member(target_type="universe_master", universe_id=None,
               channel=None, target_universe_id=None)])])
    dmx1.apply_group_direct(1, 64)  # must not raise


def test_proportional_scaling_applies_to_virtual_targets(dmx1):
    dmx1.load_groups([group(1, members=[
        member(target_type="global_master", universe_id=None,
               channel=None, base_value=128)])])
    dmx1.apply_group_direct(1, 255)
    assert dmx1.get_global_grandmaster() == 128


# ---------------------------------------------------------------------------
# Colour mixer groups
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("h,s,l,rgb", [
    (0, 0, 100, (255, 255, 255)),     # white
    (0, 0, 0, (0, 0, 0)),             # black
    (0, 100, 50, (255, 0, 0)),        # red
    (120, 100, 50, (0, 255, 0)),      # green
    (240, 100, 50, (0, 0, 255)),      # blue
    (60, 100, 50, (255, 255, 0)),     # yellow
    (180, 100, 50, (0, 255, 255)),    # cyan
    (300, 100, 50, (255, 0, 255)),    # magenta
])
def test_hsl_to_rgb(dmx, h, s, l, rgb):
    assert dmx._hsl_to_rgb(h, s, l) == rgb


def test_hsl_to_rgb_greys_are_achromatic(dmx):
    assert dmx._hsl_to_rgb(200, 0, 50) == (127, 127, 127)


@pytest.mark.parametrize("role,expected", [
    ("red", 200), ("green", 100), ("blue", 50),
    ("yellow", 100),    # min(r, g)
    ("cyan", 50),       # min(g, b)
    ("magenta", 50),    # min(r, b)
    ("white", 50),      # min(r, g, b)
    ("warm_white", 50), ("cool_white", 50),
    ("uv", 50),         # follows blue
    ("unknown_role", 0),
])
def test_color_role_to_value(dmx, role, expected):
    assert dmx._color_role_to_value(role, 200, 100, 50) == expected


def test_orange_role_fires_only_when_red_dominates(dmx):
    assert dmx._color_role_to_value("orange", 200, 100, 0) == min(200, 200)
    assert dmx._color_role_to_value("orange", 100, 200, 0) == 0


def test_lime_role_fires_only_when_green_dominates(dmx):
    assert dmx._color_role_to_value("lime", 100, 200, 0) == min(200, 200)
    assert dmx._color_role_to_value("lime", 200, 100, 0) == 0


def test_amber_role_needs_red_and_green_without_blue(dmx):
    assert dmx._color_role_to_value("amber", 200, 100, 0) == 100
    assert dmx._color_role_to_value("amber", 200, 100, 255) == 0
    assert dmx._color_role_to_value("amber", 0, 100, 0) == 0


def test_color_mixer_group_writes_rgb_channels(dmx1):
    dmx1.load_groups([group(1, mode="color_mixer", members=[
        member(channel=1, color_role="red"),
        member(channel=2, color_role="green"),
        member(channel=3, color_role="blue"),
    ], color_state={"h": 0, "s": 100, "l": 50})])

    dmx1.apply_group_direct(1, 255)

    assert dmx1.get_channel(1, 1) == 255
    assert dmx1.get_channel(1, 2) == 0
    assert dmx1.get_channel(1, 3) == 0


def test_color_mixer_brightness_scales_the_colour(dmx1):
    dmx1.load_groups([group(1, mode="color_mixer", members=[
        member(channel=1, color_role="red")],
        color_state={"h": 0, "s": 100, "l": 50})])

    dmx1.apply_group_direct(1, 128)
    assert dmx1.get_channel(1, 1) == int(255 * 128 / 255)


def test_color_mixer_defaults_to_white(dmx1):
    dmx1.load_groups([group(1, mode="color_mixer", members=[
        member(channel=1, color_role="red"),
        member(channel=2, color_role="white"),
    ])])

    dmx1.apply_group_direct(1, 255)
    assert dmx1.get_channel(1, 1) == 255
    assert dmx1.get_channel(1, 2) == 255


def test_color_mixer_skips_members_without_a_role(dmx1):
    dmx1.load_groups([group(1, mode="color_mixer", members=[
        member(channel=1, color_role=None)])])
    dmx1.apply_group_direct(1, 255)
    assert dmx1.get_channel(1, 1) == 0


def test_color_mixer_respects_parked_channels(dmx1):
    dmx1.park_channel(1, 1, 5)
    dmx1.load_groups([group(1, mode="color_mixer", members=[
        member(channel=1, color_role="red")],
        color_state={"h": 0, "s": 100, "l": 50})])

    dmx1.apply_group_direct(1, 255)
    assert dmx1.get_channel(1, 1) == 5


def test_set_group_color_updates_state_and_output(dmx1):
    dmx1.load_groups([group(1, mode="color_mixer", members=[
        member(channel=1, color_role="red"),
        member(channel=2, color_role="blue"),
    ])])
    dmx1.apply_group_direct(1, 255)

    assert dmx1.set_group_color(1, 240, 100, 50) is True
    assert dmx1.get_group(1)["color_state"] == {"h": 240, "s": 100, "l": 50}
    assert dmx1.get_channel(1, 1) == 0
    assert dmx1.get_channel(1, 2) == 255


def test_set_group_color_defaults_to_full_brightness(dmx1):
    grp = group(1, mode="color_mixer",
                members=[member(channel=1, color_role="red")])
    grp["master_value"] = None
    dmx1.load_groups([grp])

    dmx1.set_group_color(1, 0, 100, 50)
    assert dmx1.get_channel(1, 1) == 255


def test_set_group_color_rejects_non_color_groups(dmx1):
    dmx1.load_groups([group(1, mode="follow")])
    assert dmx1.set_group_color(1, 0, 100, 50) is False


def test_set_group_color_rejects_unknown_groups(dmx1):
    assert dmx1.set_group_color(99, 0, 100, 50) is False


def test_is_color_mixer_member(dmx1):
    dmx1.load_groups([
        group(1, mode="color_mixer", members=[member(channel=1, color_role="red")]),
        group(2, mode="follow", members=[member(channel=2)]),
    ])
    assert dmx1.is_color_mixer_member(1, 1) is True
    assert dmx1.is_color_mixer_member(1, 2) is False
    assert dmx1.is_color_mixer_member(9, 1) is False


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def test_add_group(dmx1):
    dmx1.add_group(group(1, master_universe=1, master_channel=5))
    assert dmx1.get_group(1) is not None
    assert dmx1._master_to_groups[(1, 5)] == [1]


def test_add_group_is_idempotent_for_the_master_lookup(dmx1):
    grp = group(1, master_universe=1, master_channel=5)
    dmx1.add_group(grp)
    dmx1.add_group(grp)
    assert dmx1._master_to_groups[(1, 5)] == [1]


def test_add_color_mixer_group_gets_default_state(dmx1):
    dmx1.add_group(group(1, mode="color_mixer"))
    assert dmx1.get_group(1)["color_state"] == {"h": 0, "s": 0, "l": 100}


def test_update_group_moves_the_master_mapping(dmx1):
    dmx1.load_groups([group(1, master_universe=1, master_channel=5)])
    dmx1.update_group(group(1, master_universe=1, master_channel=6))

    assert (1, 5) not in dmx1._master_to_groups
    assert dmx1._master_to_groups[(1, 6)] == [1]


def test_update_group_can_drop_the_master(dmx1):
    dmx1.load_groups([group(1, master_universe=1, master_channel=5)])
    dmx1.update_group(group(1))
    assert dmx1._master_to_groups == {}


def test_update_group_replaces_members(dmx1):
    dmx1.load_groups([group(1, members=[member(channel=1)])])
    dmx1.update_group(group(1, members=[member(channel=7)]))
    assert dmx1.get_group(1)["members"][0]["channel"] == 7


def test_remove_group_drops_it_and_its_output(dmx1):
    dmx1.load_groups([group(1, mode="follow", master_universe=1,
                            master_channel=5, members=[member(channel=1)])])
    dmx1.apply_group_direct(1, 200)

    dmx1.remove_group(1)

    assert dmx1.get_group(1) is None
    assert dmx1._master_to_groups == {}
    assert dmx1.get_channel(1, 1) == 0


def test_remove_group_keeps_the_other_groups_contribution(dmx1):
    dmx1.load_groups([
        group(1, mode="follow", members=[member(channel=1)]),
        group(2, mode="follow", members=[member(channel=1)]),
    ])
    dmx1.apply_group_direct(1, 100)
    dmx1.apply_group_direct(2, 200)

    dmx1.remove_group(2)
    assert dmx1.get_channel(1, 1) == 100


def test_remove_unknown_group_is_safe(dmx1):
    dmx1.remove_group(404)


# ---------------------------------------------------------------------------
# Membership queries
# ---------------------------------------------------------------------------
def test_is_channel_group_controlled(dmx1):
    dmx1.load_groups([group(1, members=[member(channel=3)])])
    assert dmx1.is_channel_group_controlled(1, 3) is True
    assert dmx1.is_channel_group_controlled(1, 4) is False


def test_get_channel_group_info(dmx1):
    dmx1.load_groups([group(1, name="Warm", master_universe=1,
                            master_channel=9,
                            members=[member(channel=3, base_value=200)])])

    info = dmx1.get_channel_group_info(1, 3)
    assert info == {
        "group_id": 1,
        "group_name": "Warm",
        "mode": "proportional",
        "master_universe": 1,
        "master_channel": 9,
        "base_value": 200,
    }


def test_get_channel_group_info_for_free_channel(dmx1):
    dmx1.load_groups([group(1, members=[member(channel=3)])])
    assert dmx1.get_channel_group_info(1, 4) is None


def test_get_groups_containing_member_skips_disabled(dmx1):
    dmx1.load_groups([
        group(1, members=[member(channel=1)]),
        group(2, enabled=False, members=[member(channel=1)]),
    ])
    found = dmx1._get_groups_containing_member(1, 1)
    assert [g["id"] for g in found] == [1]


def test_get_member_base_value_defaults_to_full(dmx1):
    grp = group(1, members=[member(channel=1, base_value=77)])
    assert dmx1._get_member_base_value(grp, 1, 1) == 77
    assert dmx1._get_member_base_value(grp, 1, 2) == 255


# ---------------------------------------------------------------------------
# Cross-language colour contract
#
# frontend/src/lib/color.js mirrors _hsl_to_rgb so the colour picker shows the
# RGB the fixtures actually receive. Both sides are asserted against this
# fixture, so changing one implementation alone fails a suite.
# ---------------------------------------------------------------------------
import json
import os

HSL_REFERENCE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "fixtures", "hsl_reference.json")


def load_reference():
    with open(HSL_REFERENCE) as handle:
        return json.load(handle)["samples"]


def test_the_reference_fixture_has_samples():
    assert len(load_reference()) > 500


def test_hsl_to_rgb_matches_the_reference(dmx):
    mismatches = [
        s for s in load_reference()
        if dmx._hsl_to_rgb(s["h"], s["s"], s["l"]) != (s["r"], s["g"], s["b"])
    ]
    assert mismatches == []


def test_the_reference_covers_the_hue_circle():
    hues = {s["h"] for s in load_reference()}
    assert 0 in hues and 360 in hues
    assert len(hues) > 20


def test_the_reference_covers_the_saturation_and_lightness_extremes():
    samples = load_reference()
    assert {s["s"] for s in samples} >= {0, 100}
    assert {s["l"] for s in samples} >= {0, 100}
