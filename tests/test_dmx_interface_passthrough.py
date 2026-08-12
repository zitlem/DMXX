"""Tests for DMX input passthrough, merge modes, channel mapping and bypass."""
import pytest


def frame(**channels):
    """Build a 512-value input frame from 1-indexed channel/value pairs."""
    values = [0] * 512
    for channel, value in channels.items():
        values[int(channel) - 1] = value
    return values


def configure_input(dmx, universe_id, mode="faders_output", merge="htp",
                    channel_start=1, channel_end=512):
    """Register a fake input handler and passthrough config for a universe."""
    dmx.inputs[universe_id] = object()
    dmx._passthrough_config[universe_id] = {
        "passthrough_mode": mode,
        "mode": merge,
        "enabled": mode in ("faders_output", "output_only"),
        "show_ui": mode in ("view_only", "faders_output"),
        "channel_start": channel_start,
        "channel_end": channel_end,
    }


# ---------------------------------------------------------------------------
# set_passthrough configuration
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode,enabled,show_ui", [
    ("off", False, False),
    ("view_only", False, True),
    ("faders_output", True, True),
    ("output_only", True, False),
])
def test_set_passthrough_derives_legacy_flags(dmx1, mode, enabled, show_ui):
    dmx1.set_passthrough(1, passthrough_mode=mode)
    config = dmx1._passthrough_config[1]
    assert config["passthrough_mode"] == mode
    assert config["enabled"] is enabled
    assert config["show_ui"] is show_ui


def test_set_passthrough_legacy_signature(dmx1):
    dmx1.set_passthrough(1, enabled=True, mode="ltp", show_ui=True)
    config = dmx1._passthrough_config[1]
    assert config == {"enabled": True, "mode": "ltp", "show_ui": True}


def test_set_passthrough_records_merge_mode(dmx1):
    dmx1.set_passthrough(1, passthrough_mode="faders_output", mode="ltp")
    assert dmx1._passthrough_config[1]["mode"] == "ltp"


# ---------------------------------------------------------------------------
# HTP passthrough
# ---------------------------------------------------------------------------
def test_htp_takes_the_higher_of_fader_and_input(dmx1):
    configure_input(dmx1, 1, merge="htp")
    dmx1.set_channel(1, 1, 200, source="local")
    dmx1.set_channel(1, 2, 10, source="local")

    dmx1._on_input_received(1, frame(**{"1": 100, "2": 150}))

    assert dmx1.get_channel(1, 1) == 200  # fader wins
    assert dmx1.get_channel(1, 2) == 150  # input wins


def test_htp_only_touches_channels_in_the_input_range(dmx1):
    configure_input(dmx1, 1, merge="htp", channel_start=1, channel_end=2)
    dmx1.set_channel(1, 3, 20, source="local")

    dmx1._on_input_received(1, frame(**{"1": 100, "3": 255}))

    assert dmx1.get_channel(1, 1) == 100
    assert dmx1.get_channel(1, 3) == 20  # outside range, untouched


def test_input_values_are_stored_for_later_reads(dmx1):
    configure_input(dmx1, 1)
    values = frame(**{"5": 55})
    dmx1._on_input_received(1, values)
    assert dmx1.get_input_values(1) == values


def test_get_input_values_defaults_to_zeros(dmx):
    assert dmx.get_input_values(3) == [0] * 512


# ---------------------------------------------------------------------------
# LTP passthrough
# ---------------------------------------------------------------------------
def test_ltp_applies_a_changing_input(dmx1):
    configure_input(dmx1, 1, merge="ltp")
    dmx1._on_input_received(1, frame(**{"1": 100}))
    assert dmx1.get_channel(1, 1) == 100


def test_ltp_lets_the_ui_override_a_stable_input(dmx1):
    configure_input(dmx1, 1, merge="ltp")
    dmx1._on_input_received(1, frame(**{"1": 100}))

    dmx1.set_channel(1, 1, 20, source="user_a")
    dmx1._on_input_received(1, frame(**{"1": 100}))  # unchanged input

    assert dmx1.get_channel(1, 1) == 20


def test_ltp_ignores_jitter_below_threshold(dmx1):
    configure_input(dmx1, 1, merge="ltp")
    dmx1._on_input_received(1, frame(**{"1": 100}))
    dmx1.set_channel(1, 1, 20, source="user_a")

    dmx1._on_input_received(1, frame(**{"1": 102}))  # within jitter threshold
    assert dmx1.get_channel(1, 1) == 20

    dmx1._on_input_received(1, frame(**{"1": 110}))  # real move
    assert dmx1.get_channel(1, 1) == 110


def test_ltp_always_applies_zero(dmx1):
    configure_input(dmx1, 1, merge="ltp")
    dmx1._on_input_received(1, frame(**{"1": 200}))
    dmx1.set_channel(1, 1, 255, source="user_a")

    dmx1._on_input_received(1, frame())  # all-zero input turns things off
    assert dmx1.get_channel(1, 1) == 0


# ---------------------------------------------------------------------------
# Passthrough modes
# ---------------------------------------------------------------------------
def test_view_only_mode_does_not_touch_the_output(dmx1):
    configure_input(dmx1, 1, mode="view_only")
    dmx1._on_input_received(1, frame(**{"1": 200}))
    assert dmx1.get_channel(1, 1) == 0


def test_off_mode_does_not_touch_the_output(dmx1):
    configure_input(dmx1, 1, mode="off")
    dmx1._on_input_received(1, frame(**{"1": 200}))
    assert dmx1.get_channel(1, 1) == 0


def test_output_only_mode_applies_without_ui_notification(dmx1, events):
    configure_input(dmx1, 1, mode="output_only")
    dmx1._on_input_received(1, frame(**{"1": 200}))

    assert dmx1.get_channel(1, 1) == 200
    assert not [d for kind, d in events if kind == "input_to_ui"]


def test_faders_output_mode_notifies_the_ui(dmx1, events):
    configure_input(dmx1, 1, mode="faders_output")
    dmx1._on_input_received(1, frame(**{"1": 200}))

    ui = [d for kind, d in events if kind == "input_to_ui"]
    assert len(ui) == 1
    assert ui[0]["universe_id"] == 1
    assert ui[0]["values"][0] == 200


def test_view_only_mode_still_notifies_the_ui(dmx1, events):
    configure_input(dmx1, 1, mode="view_only")
    dmx1._on_input_received(1, frame(**{"1": 200}))
    assert [d for kind, d in events if kind == "input_to_ui"]


def test_ui_notification_marks_out_of_range_channels_with_sentinel(dmx1, events):
    configure_input(dmx1, 1, mode="view_only", channel_start=2, channel_end=3)
    dmx1._on_input_received(1, frame(**{"2": 50, "3": 60}))

    values = [d for kind, d in events if kind == "input_to_ui"][0]["values"]
    assert values[0] == -1     # channel 1 outside range
    assert values[1] == 50
    assert values[2] == 60
    assert values[3] == -1


def test_ui_notification_marks_channels_as_input_sourced(dmx1):
    configure_input(dmx1, 1, mode="view_only", channel_start=1, channel_end=2)
    dmx1._on_input_received(1, frame(**{"1": 5}))

    assert dmx1.get_channel_source(1, 1) == "input"
    assert dmx1.get_channel_source(1, 3) == "unknown"


def test_input_received_event_carries_the_raw_frame(dmx1, events):
    configure_input(dmx1, 1, mode="off")
    values = frame(**{"1": 9})
    dmx1._on_input_received(1, values)

    received = [d for kind, d in events if kind == "input_received"]
    assert received == [{"universe_id": 1, "values": values}]


def test_broadcasts_are_throttled(dmx1, events):
    configure_input(dmx1, 1, mode="off")
    dmx1._on_input_received(1, frame(**{"1": 1}))
    dmx1._on_input_received(1, frame(**{"1": 2}))

    received = [d for kind, d in events if kind == "input_received"]
    assert len(received) == 1  # second frame within the throttle window


# ---------------------------------------------------------------------------
# Input bypass
# ---------------------------------------------------------------------------
def test_bypass_defaults_off(dmx):
    assert dmx.get_input_bypass() is False


def test_bypass_stops_input_reaching_the_output(dmx1):
    configure_input(dmx1, 1)
    dmx1.set_input_bypass(True)

    dmx1._on_input_received(1, frame(**{"1": 200}))

    assert dmx1.get_input_bypass() is True
    assert dmx1.get_channel(1, 1) == 0


def test_bypass_still_reports_input_to_the_io_monitor(dmx1, events):
    configure_input(dmx1, 1)
    dmx1.set_input_bypass(True)
    dmx1._on_input_received(1, frame(**{"1": 200}))

    assert [d for kind, d in events if kind == "input_received"]
    assert not [d for kind, d in events if kind == "input_to_ui"]


def test_releasing_bypass_reapplies_the_last_input(dmx1):
    configure_input(dmx1, 1)
    dmx1.set_input_bypass(True)
    dmx1._on_input_received(1, frame(**{"1": 200}))
    assert dmx1.get_channel(1, 1) == 0

    dmx1.set_input_bypass(False)
    assert dmx1.get_channel(1, 1) == 200


def test_releasing_bypass_clears_fader_values_in_the_input_range(dmx1):
    configure_input(dmx1, 1, channel_start=1, channel_end=4)
    dmx1._on_input_received(1, frame(**{"1": 50}))

    dmx1.set_input_bypass(True)
    dmx1.set_channel(1, 1, 255, source="user_a")  # user pushes it up during bypass
    dmx1.set_input_bypass(False)

    # HTP would otherwise keep 255; local values inside the range are reset
    assert dmx1.get_channel(1, 1) == 50


# ---------------------------------------------------------------------------
# Channel mapping configuration
# ---------------------------------------------------------------------------
def test_set_channel_mapping_builds_forward_and_reverse_maps(dmx12):
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7},
    ])

    assert dmx12.get_mapped_destination(1, 1) == [{
        "target_type": "channel", "universe": 2,
        "channel": 7, "target_universe_id": None,
    }]
    assert dmx12.get_mapped_source(2, 7) == (1, 1)
    assert dmx12._mapping_enabled is True


def test_mapping_status(dmx1):
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 1, "dst_channel": 2},
    ], unmapped_behavior="ignore")

    assert dmx1.get_channel_mapping_status() == {
        "enabled": True, "unmapped_behavior": "ignore", "mapping_count": 1,
    }


def test_empty_mapping_disables_mapping(dmx1):
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 1, "dst_channel": 2},
    ])
    dmx1.set_channel_mapping([])

    assert dmx1._mapping_enabled is False
    assert dmx1.get_channel_mapping_status()["mapping_count"] == 0
    assert dmx1.get_mapped_destination(1, 1) == []
    assert dmx1.get_mapped_source(1, 2) is None


def test_one_source_can_feed_several_destinations(dmx12):
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 1, "dst_channel": 5},
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 6},
    ])
    assert len(dmx12.get_mapped_destination(1, 1)) == 2


def test_virtual_targets_are_not_in_the_reverse_map(dmx1):
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1,
         "dst_target_type": "global_master"},
    ])
    assert dmx1.get_mapped_source(1, 1) is None
    assert dmx1.get_mapped_destination(1, 1)[0]["target_type"] == "global_master"


# ---------------------------------------------------------------------------
# Mapped passthrough
# ---------------------------------------------------------------------------
def test_mapped_input_routes_to_the_destination_channel(dmx12):
    configure_input(dmx12, 1)
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7},
    ], unmapped_behavior="ignore")

    dmx12._on_input_received(1, frame(**{"1": 123}))

    assert dmx12.get_channel(2, 7) == 123
    assert dmx12.get_channel(1, 1) == 0


def test_unmapped_channels_pass_through_when_configured(dmx12):
    configure_input(dmx12, 1, channel_start=1, channel_end=4)
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7},
    ], unmapped_behavior="passthrough")

    dmx12._on_input_received(1, frame(**{"1": 10, "2": 20}))

    assert dmx12.get_channel(2, 7) == 10
    assert dmx12.get_channel(1, 2) == 20  # unmapped 1:1


def test_unmapped_channels_are_dropped_when_ignoring(dmx12):
    configure_input(dmx12, 1)
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7},
    ], unmapped_behavior="ignore")

    dmx12._on_input_received(1, frame(**{"2": 20}))
    assert dmx12.get_channel(1, 2) == 0


def test_unmapped_passthrough_respects_the_input_range(dmx1):
    configure_input(dmx1, 1, channel_start=1, channel_end=2)
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 1, "dst_channel": 10},
    ], unmapped_behavior="passthrough")
    dmx1.set_channel(1, 5, 33, source="local")

    dmx1._on_input_received(1, frame(**{"1": 10, "5": 99}))

    assert dmx1.get_channel(1, 5) == 33  # outside range stays manual


def test_mapped_destination_is_protected_from_unmapped_passthrough(dmx1):
    configure_input(dmx1, 1, channel_start=1, channel_end=10)
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 1, "dst_channel": 5},
    ], unmapped_behavior="passthrough")

    # Source channel 1 = 200 maps to channel 5; channel 5's own input is 30
    dmx1._on_input_received(1, frame(**{"1": 200, "5": 30}))

    assert dmx1.get_channel(1, 5) == 200


def test_mapping_can_drive_the_universe_grandmaster(dmx12):
    configure_input(dmx12, 1)
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1,
         "dst_target_type": "universe_master", "dst_target_universe_id": 2},
    ], unmapped_behavior="ignore")

    dmx12._on_input_received(1, frame(**{"1": 77}))
    assert dmx12.get_universe_grandmaster(2) == 77


def test_mapping_can_drive_the_global_grandmaster(dmx1):
    configure_input(dmx1, 1)
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_target_type": "global_master"},
    ], unmapped_behavior="ignore")

    dmx1._on_input_received(1, frame(**{"1": 88}))
    assert dmx1.get_global_grandmaster() == 88


def test_mapped_ui_notification_targets_the_destination_fader(dmx12, events):
    configure_input(dmx12, 1, mode="faders_output")
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7},
    ], unmapped_behavior="ignore")

    dmx12._on_input_received(1, frame(**{"1": 42}))

    ui = [d for kind, d in events if kind == "input_to_ui"]
    assert len(ui) == 1
    assert ui[0]["universe_id"] == 2
    assert ui[0]["values"][6] == 42
    assert ui[0]["values"][0] == -1


def test_blackout_blocks_passthrough(dmx1):
    configure_input(dmx1, 1)
    dmx1.blackout()
    dmx1._on_input_received(1, frame(**{"1": 200}))
    assert dmx1.get_channel(1, 1) == 0


def test_blackout_blocks_mapped_passthrough(dmx12):
    configure_input(dmx12, 1)
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7},
    ])
    dmx12.blackout()
    dmx12._on_input_received(1, frame(**{"1": 200}))
    assert dmx12.get_channel(2, 7) == 0


# ---------------------------------------------------------------------------
# Input-controlled channel queries
# ---------------------------------------------------------------------------
def test_input_controlled_channels_for_direct_passthrough(dmx1):
    configure_input(dmx1, 1, channel_start=3, channel_end=5)
    assert dmx1.get_input_controlled_channels(1) == {3, 4, 5}


def test_no_channels_controlled_when_passthrough_is_off(dmx1):
    configure_input(dmx1, 1, mode="view_only")
    assert dmx1.get_input_controlled_channels(1) == set()


def test_no_channels_controlled_without_an_input(dmx1):
    assert dmx1.get_input_controlled_channels(1) == set()


def test_input_controlled_channels_with_mapping(dmx12):
    configure_input(dmx12, 1, channel_start=1, channel_end=2)
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7},
    ], unmapped_behavior="ignore")

    assert dmx12.get_input_controlled_channels(2) == {7}


def test_input_controlled_channels_include_unmapped_passthrough(dmx1):
    configure_input(dmx1, 1, channel_start=1, channel_end=3)
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 1, "dst_channel": 9},
    ], unmapped_behavior="passthrough")

    controlled = dmx1.get_input_controlled_channels(1)
    assert 9 in controlled       # mapped destination
    assert 2 in controlled and 3 in controlled  # 1:1 passthrough
    assert 1 not in controlled   # remapped elsewhere


# ---------------------------------------------------------------------------
# get_input_value_for_channel
# ---------------------------------------------------------------------------
def test_input_value_for_direct_channel(dmx1):
    configure_input(dmx1, 1)
    dmx1._on_input_received(1, frame(**{"4": 44}))
    assert dmx1.get_input_value_for_channel(1, 4) == 44


def test_input_value_none_outside_the_range(dmx1):
    configure_input(dmx1, 1, channel_start=1, channel_end=3)
    dmx1._on_input_received(1, frame(**{"4": 44}))
    assert dmx1.get_input_value_for_channel(1, 4) is None


def test_input_value_none_when_passthrough_is_off(dmx1):
    configure_input(dmx1, 1, mode="off")
    dmx1._on_input_received(1, frame(**{"4": 44}))
    assert dmx1.get_input_value_for_channel(1, 4) is None


def test_input_value_follows_the_mapping(dmx12):
    configure_input(dmx12, 1)
    dmx12.set_channel_mapping([
        {"src_universe": 1, "src_channel": 2, "dst_universe": 2, "dst_channel": 8},
    ], unmapped_behavior="ignore")
    dmx12._on_input_received(1, frame(**{"2": 66}))

    assert dmx12.get_input_value_for_channel(2, 8) == 66
    assert dmx12.get_input_value_for_channel(2, 9) is None


def test_input_value_for_unmapped_passthrough_channel(dmx1):
    configure_input(dmx1, 1, channel_start=1, channel_end=5)
    dmx1.set_channel_mapping([
        {"src_universe": 1, "src_channel": 1, "dst_universe": 1, "dst_channel": 9},
    ], unmapped_behavior="passthrough")
    dmx1._on_input_received(1, frame(**{"1": 10, "3": 30}))

    assert dmx1.get_input_value_for_channel(1, 3) == 30
    assert dmx1.get_input_value_for_channel(1, 1) is None  # remapped away


def test_input_value_none_for_universe_without_input(dmx1):
    assert dmx1.get_input_value_for_channel(1, 1) is None


# ---------------------------------------------------------------------------
# Input status
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_input_status_includes_passthrough_config():
    from backend.dmx_interface import DMXInterface

    interface = DMXInterface()
    await interface.add_input(1, "midi_input", {"device_name": "X"},
                              passthrough_enabled=True, passthrough_show_ui=True)

    status = interface.get_input_status(1)
    assert status["type"] == "midi"
    assert status["passthrough"]["passthrough_mode"] == "faders_output"


def test_get_input_status_none_without_input(dmx1):
    assert dmx1.get_input_status(1) is None


@pytest.mark.asyncio
async def test_add_input_stores_channel_range():
    from backend.dmx_interface import DMXInterface

    interface = DMXInterface()
    await interface.add_input(1, "midi_input",
                              {"channel_start": 10, "channel_end": 20})

    config = interface._passthrough_config[1]
    assert config["channel_start"] == 10
    assert config["channel_end"] == 20


@pytest.mark.asyncio
async def test_add_input_none_type_only_stores_config():
    from backend.dmx_interface import DMXInterface

    interface = DMXInterface()
    assert await interface.add_input(1, "none", {}) is True
    assert interface.inputs == {}
    assert 1 in interface._passthrough_config


@pytest.mark.asyncio
async def test_remove_input_clears_values():
    from backend.dmx_interface import DMXInterface

    interface = DMXInterface()
    await interface.add_input(1, "midi_input", {})
    await interface.remove_input(1)

    assert interface.inputs == {}
    assert 1 not in interface._input_values


@pytest.mark.asyncio
async def test_remove_unknown_input_is_safe():
    from backend.dmx_interface import DMXInterface

    await DMXInterface().remove_input(5)


@pytest.mark.asyncio
async def test_adding_an_input_twice_replaces_the_handler():
    from backend.dmx_interface import DMXInterface

    interface = DMXInterface()
    await interface.add_input(1, "midi_input", {})
    first = interface.inputs[1]
    await interface.add_input(1, "midi_input", {})

    assert interface.inputs[1] is not first
    assert first.running is False
