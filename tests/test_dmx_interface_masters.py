"""Tests for grand master scaling, park and highlight overrides."""
import pytest


# ---------------------------------------------------------------------------
# Grand masters
# ---------------------------------------------------------------------------
def test_global_grandmaster_defaults_to_full(dmx):
    assert dmx.get_global_grandmaster() == 255


def test_universe_grandmaster_defaults_to_full(dmx):
    assert dmx.get_universe_grandmaster(1) == 255


def test_set_global_grandmaster(dmx1):
    dmx1.set_global_grandmaster(128)
    assert dmx1.get_global_grandmaster() == 128


@pytest.mark.parametrize("value,expected", [(-10, 0), (0, 0), (300, 255), (255, 255)])
def test_global_grandmaster_is_clamped(dmx1, value, expected):
    dmx1.set_global_grandmaster(value)
    assert dmx1.get_global_grandmaster() == expected


@pytest.mark.parametrize("value,expected", [(-1, 0), (999, 255), (77, 77)])
def test_universe_grandmaster_is_clamped(dmx1, value, expected):
    dmx1.set_universe_grandmaster(1, value)
    assert dmx1.get_universe_grandmaster(1) == expected


def test_grandmaster_change_notifies_callbacks(dmx1, events):
    dmx1.set_global_grandmaster(100)
    dmx1.set_universe_grandmaster(1, 50)

    payloads = [data for kind, data in events if kind == "grandmaster_changed"]
    assert payloads == [
        {"type": "global", "value": 100},
        {"type": "universe", "universe_id": 1, "value": 50},
    ]


def test_get_all_grandmasters(dmx1):
    dmx1.set_global_grandmaster(200)
    dmx1.set_universe_grandmaster(1, 100)
    assert dmx1.get_all_grandmasters() == {"global": 200, "universes": {1: 100}}


def test_grandmaster_info_matches_all_grandmasters(dmx1):
    dmx1.set_universe_grandmaster(1, 10)
    assert dmx1.get_grandmaster_info() == dmx1.get_all_grandmasters()


def test_get_all_grandmasters_returns_a_copy(dmx1):
    dmx1.set_universe_grandmaster(1, 100)
    snapshot = dmx1.get_all_grandmasters()
    snapshot["universes"][1] = 0
    assert dmx1.get_universe_grandmaster(1) == 100


# ---------------------------------------------------------------------------
# Grand master scaling of the output frame
# ---------------------------------------------------------------------------
def test_no_scaling_when_both_masters_are_full(dmx1):
    dmx1.set_channel(1, 1, 200)
    assert dmx1.get_scaled_values(1)[0] == 200


def test_global_grandmaster_halves_output(dmx1):
    dmx1.set_channel(1, 1, 200)
    dmx1.set_global_grandmaster(128)
    assert dmx1.get_scaled_values(1)[0] == round(200 * 128 / 255)


def test_universe_grandmaster_scales_only_its_universe(dmx12):
    dmx12.set_channel(1, 1, 200)
    dmx12.set_channel(2, 1, 200)
    dmx12.set_universe_grandmaster(1, 0)

    assert dmx12.get_scaled_values(1)[0] == 0
    assert dmx12.get_scaled_values(2)[0] == 200


def test_masters_multiply(dmx1):
    dmx1.set_channel(1, 1, 255)
    dmx1.set_global_grandmaster(128)
    dmx1.set_universe_grandmaster(1, 128)

    expected = min(255, round(255 * (128 / 255) * (128 / 255)))
    assert dmx1.get_scaled_values(1)[0] == expected


def test_scaling_never_exceeds_255(dmx1):
    dmx1.set_channel(1, 1, 255)
    dmx1.set_global_grandmaster(255)
    dmx1.set_universe_grandmaster(1, 254)
    assert max(dmx1.get_scaled_values(1)) <= 255


def test_scaling_leaves_raw_values_untouched(dmx1):
    dmx1.set_channel(1, 1, 200)
    dmx1.set_global_grandmaster(0)
    assert dmx1.get_all_values(1)[0] == 200
    assert dmx1.get_scaled_values(1)[0] == 0


def test_scaled_values_length(dmx1):
    assert len(dmx1.get_scaled_values(1)) == 512


# ---------------------------------------------------------------------------
# Park
# ---------------------------------------------------------------------------
def test_park_channel_locks_the_value(dmx1):
    dmx1.park_channel(1, 5, 128)
    assert dmx1.is_channel_parked(1, 5) is True
    assert dmx1.get_channel(1, 5) == 128
    assert dmx1.get_parked_channels(1) == {5: 128}


def test_parked_channel_rejects_set_channel(dmx1, events):
    dmx1.park_channel(1, 5, 128)
    events.clear()

    dmx1.set_channel(1, 5, 255)

    assert dmx1.get_channel(1, 5) == 128
    rejects = [d for kind, d in events if kind == "channel_change"
               and d["source"] == "park_reject"]
    assert rejects == [{"universe_id": 1, "channel": 5,
                        "value": 128, "source": "park_reject"}]


def test_parked_channel_rejects_bulk_set(dmx1, events):
    dmx1.park_channel(1, 5, 128)
    events.clear()

    dmx1.set_channels(1, {4: 40, 5: 255})

    assert dmx1.get_channel(1, 4) == 40
    assert dmx1.get_channel(1, 5) == 128
    sources = {d["source"] for _, d in events if _ == "channel_change"}
    assert "park_reject" in sources


def test_unpark_restores_control(dmx1):
    dmx1.park_channel(1, 5, 128)
    dmx1.unpark_channel(1, 5)

    assert dmx1.is_channel_parked(1, 5) is False
    assert dmx1.get_parked_channels(1) == {}

    dmx1.set_channel(1, 5, 255)
    assert dmx1.get_channel(1, 5) == 255


def test_unpark_unknown_channel_is_safe(dmx1):
    dmx1.unpark_channel(1, 5)
    dmx1.unpark_channel(99, 1)


@pytest.mark.parametrize("channel,value", [(0, 10), (513, 10), (5, -1), (5, 256)])
def test_park_rejects_out_of_range_arguments(dmx1, channel, value):
    dmx1.park_channel(1, channel, value)
    assert dmx1.get_parked_channels(1) == {}


def test_park_emits_park_update_events(dmx1, events):
    dmx1.park_channel(1, 5, 100)
    dmx1.unpark_channel(1, 5)

    updates = [d for kind, d in events if kind == "park_update"]
    assert updates == [
        {"universe_id": 1, "channel": 5, "value": 100, "parked": True},
        {"universe_id": 1, "channel": 5, "value": None, "parked": False},
    ]


def test_parked_value_overrides_output_frame(dmx1):
    dmx1.set_channel(1, 5, 20)
    dmx1.park_channel(1, 5, 200)
    assert dmx1.get_scaled_values(1)[4] == 200


def test_park_still_scaled_by_grandmaster(dmx1):
    dmx1.park_channel(1, 5, 200)
    dmx1.set_global_grandmaster(0)
    assert dmx1.get_scaled_values(1)[4] == 0


def test_get_all_parked_channels_across_universes(dmx12):
    dmx12.park_channel(1, 1, 10)
    dmx12.park_channel(2, 2, 20)
    assert dmx12.get_all_parked_channels() == {1: {1: 10}, 2: {2: 20}}


def test_get_parked_channels_returns_a_copy(dmx1):
    dmx1.park_channel(1, 1, 10)
    snapshot = dmx1.get_parked_channels(1)
    snapshot[1] = 0
    assert dmx1.get_parked_channels(1) == {1: 10}


def test_parking_the_same_channel_twice_updates_the_value(dmx1):
    dmx1.park_channel(1, 1, 10)
    dmx1.park_channel(1, 1, 20)
    assert dmx1.get_parked_channels(1) == {1: 20}


# ---------------------------------------------------------------------------
# Highlight / solo
# ---------------------------------------------------------------------------
def test_start_highlight_sets_state(dmx1):
    dmx1.start_highlight(1, [3, 4], dim_level=10)

    state = dmx1.get_highlight_state()
    assert state["active"] is True
    assert state["dim_level"] == 10
    assert sorted(state["channels"][1]) == [3, 4]
    assert dmx1.is_channel_highlighted(1, 3) is True
    assert dmx1.is_channel_highlighted(1, 9) is False


def test_highlight_forces_output_frame(dmx1):
    dmx1.set_channel(1, 1, 100)
    dmx1.set_channel(1, 3, 50)
    dmx1.start_highlight(1, [3], dim_level=7)

    scaled = dmx1.get_scaled_values(1)
    assert scaled[2] == 255   # highlighted channel
    assert scaled[0] == 7     # everything else dimmed
    assert dmx1.get_channel(1, 1) == 100  # underlying values preserved


def test_highlight_dim_level_is_clamped(dmx1):
    dmx1.start_highlight(1, [1], dim_level=999)
    assert dmx1.get_highlight_state()["dim_level"] == 255
    dmx1.stop_highlight()
    dmx1.start_highlight(1, [1], dim_level=-5)
    assert dmx1.get_highlight_state()["dim_level"] == 0


def test_highlight_ignores_out_of_range_channels(dmx1):
    dmx1.start_highlight(1, [0, 513, 5])
    assert dmx1.get_highlight_state()["channels"][1] == [5]


def test_add_to_highlight_activates_mode(dmx1):
    dmx1.add_to_highlight(1, 2)
    assert dmx1.get_highlight_state()["active"] is True
    assert dmx1.is_channel_highlighted(1, 2) is True


@pytest.mark.parametrize("channel", [0, 513])
def test_add_to_highlight_rejects_bad_channels(dmx1, channel):
    dmx1.add_to_highlight(1, channel)
    assert dmx1.get_highlight_state()["active"] is False


def test_remove_from_highlight_keeps_mode_while_others_remain(dmx1):
    dmx1.start_highlight(1, [1, 2])
    dmx1.remove_from_highlight(1, 1)

    state = dmx1.get_highlight_state()
    assert state["active"] is True
    assert state["channels"][1] == [2]


def test_removing_last_highlight_stops_mode(dmx1):
    dmx1.start_highlight(1, [1])
    dmx1.remove_from_highlight(1, 1)

    state = dmx1.get_highlight_state()
    assert state["active"] is False
    assert state["channels"] == {}


def test_stop_highlight_resets_everything(dmx1):
    dmx1.start_highlight(1, [1, 2], dim_level=30)
    dmx1.stop_highlight()

    assert dmx1.get_highlight_state() == {"active": False, "dim_level": 0,
                                          "channels": {}}


def test_highlight_broadcasts_state_to_callbacks(dmx1, events):
    dmx1.start_highlight(1, [1])
    dmx1.stop_highlight()

    updates = [d for kind, d in events if kind == "highlight_update"]
    assert len(updates) == 2
    assert updates[0]["active"] is True
    assert updates[1]["active"] is False


def test_park_beats_highlight(dmx1):
    """Park has the highest priority in the override chain."""
    dmx1.park_channel(1, 1, 42)
    dmx1.start_highlight(1, [2], dim_level=0)

    scaled = dmx1.get_scaled_values(1)
    assert scaled[0] == 42   # parked, not dimmed to 0
    assert scaled[1] == 255  # highlighted


def test_highlight_spans_universes_in_output(dmx12):
    dmx12.set_channel(2, 1, 100)
    dmx12.start_highlight(1, [1], dim_level=0)

    # Highlight is global: other universes get dimmed too
    assert dmx12.get_scaled_values(2)[0] == 0
    assert dmx12.get_scaled_values(1)[0] == 255


def test_remove_from_unhighlighted_universe_is_safe(dmx1):
    dmx1.remove_from_highlight(1, 1)
    assert dmx1.get_highlight_state()["active"] is False
