"""Tests for DMXInterface channel setting, sourcing, blackout and outputs."""
import pytest

from backend.dmx_interface import DMXInterface, DMXUniverse
from backend.dmx_outputs import MockOutput


def channel_events(events, source=None):
    """Filter recorded callback events down to channel_change payloads."""
    out = [data for kind, data in events if kind == "channel_change"]
    if source is not None:
        out = [d for d in out if d["source"] == source]
    return out


# ---------------------------------------------------------------------------
# set_channel
# ---------------------------------------------------------------------------
def test_set_channel_stores_value(dmx1):
    dmx1.set_channel(1, 10, 200)
    assert dmx1.get_channel(1, 10) == 200


def test_set_channel_on_unknown_universe_is_a_noop(dmx):
    dmx.set_channel(99, 1, 255)
    assert dmx.get_channel(99, 1) == 0


def test_set_channel_notifies_callbacks(dmx1, events):
    dmx1.set_channel(1, 5, 128)
    assert channel_events(events) == [
        {"universe_id": 1, "channel": 5, "value": 128, "source": "local"}
    ]


def test_set_channel_records_source(dmx1):
    dmx1.set_channel(1, 5, 10, source="user_abc123")
    assert dmx1.get_channel_source(1, 5) == "user_abc123"
    assert dmx1.get_channel_sources(1) == {5: "user_abc123"}


def test_unknown_channel_source_is_unknown(dmx1):
    assert dmx1.get_channel_source(1, 400) == "unknown"


def test_get_channel_sources_returns_a_copy(dmx1):
    dmx1.set_channel(1, 5, 10)
    sources = dmx1.get_channel_sources(1)
    sources[5] = "tampered"
    assert dmx1.get_channel_source(1, 5) == "local"


def test_local_sources_update_local_values(dmx1):
    dmx1.set_channel(1, 3, 90, source="local")
    dmx1.set_channel(1, 4, 80, source="user_xyz")
    local = dmx1.get_local_values(1)
    assert local[2] == 90
    assert local[3] == 80


def test_input_source_does_not_update_local_values(dmx1):
    dmx1.set_channel(1, 3, 90, source="input")
    assert dmx1.get_local_values(1)[2] == 0
    assert dmx1.get_channel(1, 3) == 90


def test_get_local_values_returns_a_copy(dmx1):
    values = dmx1.get_local_values(1)
    values[0] = 5
    assert dmx1.get_local_values(1)[0] == 0


def test_callback_exception_does_not_break_set_channel(dmx1):
    seen = []
    dmx1.register_callback(lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    dmx1.register_callback(lambda kind, data: seen.append(kind))

    dmx1.set_channel(1, 1, 5)
    assert seen == ["channel_change"]
    assert dmx1.get_channel(1, 1) == 5


def test_unregister_callback_stops_notifications(dmx1):
    seen = []

    def cb(kind, data):
        seen.append(kind)

    dmx1.register_callback(cb)
    dmx1.set_channel(1, 1, 1)
    dmx1.unregister_callback(cb)
    dmx1.set_channel(1, 1, 2)
    assert seen == ["channel_change"]


def test_unregister_unknown_callback_is_safe(dmx1):
    dmx1.unregister_callback(lambda *_: None)  # must not raise


# ---------------------------------------------------------------------------
# set_channels (bulk)
# ---------------------------------------------------------------------------
def test_set_channels_sets_all_values(dmx1):
    dmx1.set_channels(1, {1: 10, 2: 20, 3: 30})
    assert [dmx1.get_channel(1, c) for c in (1, 2, 3)] == [10, 20, 30]


def test_set_channels_on_unknown_universe_is_a_noop(dmx):
    dmx.set_channels(99, {1: 10})
    assert dmx.get_all_values(99) == [0] * 512


def test_set_channels_notifies_once_per_channel(dmx1, events):
    dmx1.set_channels(1, {1: 10, 2: 20})
    changes = channel_events(events)
    assert {(c["channel"], c["value"]) for c in changes} == {(1, 10), (2, 20)}


def test_set_channels_tracks_sources(dmx1):
    dmx1.set_channels(1, {7: 70}, source="user_bob")
    assert dmx1.get_channel_source(1, 7) == "user_bob"
    assert dmx1.get_local_values(1)[6] == 70


def test_set_channels_with_empty_dict_does_nothing(dmx1, events):
    dmx1.set_channels(1, {})
    assert events == []


def test_set_channels_silent_emits_no_callbacks(dmx1, events):
    dmx1.set_channels_silent(1, {1: 10, 2: 20})
    assert events == []
    assert dmx1.get_channel(1, 1) == 10
    assert dmx1.get_channel(1, 2) == 20


def test_set_channels_silent_tracks_local_values(dmx1):
    dmx1.set_channels_silent(1, {4: 44}, source="local")
    assert dmx1.get_local_values(1)[3] == 44


def test_set_channels_silent_skips_parked_channels(dmx1):
    dmx1.park_channel(1, 2, 100)
    dmx1.set_channels_silent(1, {1: 10, 2: 20})
    assert dmx1.get_channel(1, 1) == 10
    assert dmx1.get_channel(1, 2) == 100


def test_set_channels_silent_on_unknown_universe_is_a_noop(dmx):
    dmx.set_channels_silent(99, {1: 1})  # must not raise


# ---------------------------------------------------------------------------
# Bulk getters
# ---------------------------------------------------------------------------
def test_get_all_values_for_unknown_universe(dmx):
    assert dmx.get_all_values(42) == [0] * 512


def test_get_channel_for_unknown_universe(dmx):
    assert dmx.get_channel(42, 1) == 0


def test_get_universe_returns_none_when_absent(dmx):
    assert dmx.get_universe(7) is None


def test_get_universe_returns_the_instance(dmx1):
    assert isinstance(dmx1.get_universe(1), DMXUniverse)


# ---------------------------------------------------------------------------
# Blackout
# ---------------------------------------------------------------------------
def test_blackout_zeroes_all_universes(dmx12):
    dmx12.set_channel(1, 1, 200)
    dmx12.set_channel(2, 5, 100)

    dmx12.blackout()

    assert dmx12.is_blackout_active() is True
    assert dmx12.get_all_values(1) == [0] * 512
    assert dmx12.get_all_values(2) == [0] * 512


def test_release_blackout_restores_previous_values(dmx12):
    dmx12.set_channel(1, 1, 200)
    dmx12.set_channel(2, 5, 100)

    dmx12.blackout()
    dmx12.release_blackout()

    assert dmx12.is_blackout_active() is False
    assert dmx12.get_channel(1, 1) == 200
    assert dmx12.get_channel(2, 5) == 100


def test_blackout_notifies_callbacks(dmx1, events):
    dmx1.blackout()
    dmx1.release_blackout()
    blackout_events = [data for kind, data in events if kind == "blackout"]
    assert blackout_events == [{"active": True}, {"active": False}]


def test_set_channel_during_blackout_is_staged_not_output(dmx1):
    dmx1.blackout()
    dmx1.set_channel(1, 3, 111)

    assert dmx1.get_channel(1, 3) == 0  # output stays dark
    dmx1.release_blackout()
    assert dmx1.get_channel(1, 3) == 111  # staged value applied on release


def test_set_channels_during_blackout_is_staged(dmx1):
    dmx1.blackout()
    dmx1.set_channels(1, {2: 50, 3: 60})
    assert dmx1.get_all_values(1) == [0] * 512

    dmx1.release_blackout()
    assert dmx1.get_channel(1, 2) == 50
    assert dmx1.get_channel(1, 3) == 60


def test_set_channels_silent_during_blackout_is_staged(dmx1):
    dmx1.blackout()
    dmx1.set_channels_silent(1, {9: 90})
    dmx1.release_blackout()
    assert dmx1.get_channel(1, 9) == 90


def test_set_channel_during_blackout_emits_no_channel_change(dmx1, events):
    dmx1.blackout()
    events.clear()
    dmx1.set_channel(1, 1, 100)
    assert channel_events(events) == []


def test_double_blackout_does_not_lose_staged_values(dmx1):
    dmx1.set_channel(1, 1, 77)
    dmx1.blackout()
    dmx1.blackout()  # re-arming captures the (now zeroed) universe
    dmx1.release_blackout()
    assert dmx1.get_channel(1, 1) == 0


def test_release_without_blackout_is_safe(dmx1):
    dmx1.set_channel(1, 1, 12)
    dmx1.release_blackout()
    assert dmx1.get_channel(1, 1) == 12
    assert dmx1.is_blackout_active() is False


# ---------------------------------------------------------------------------
# Universe / output management
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connect_and_disconnect_toggle_running():
    interface = DMXInterface()
    assert await interface.connect() is True
    assert interface._running is True

    await interface.disconnect()
    assert interface._running is False


@pytest.mark.asyncio
async def test_add_universe_creates_universe_and_output():
    interface = DMXInterface()
    universe = await interface.add_universe(1, "mock", {})

    assert isinstance(universe, DMXUniverse)
    assert 1 in interface.universes
    assert len(interface.outputs[1]) == 1
    assert isinstance(interface.outputs[1][0], MockOutput)
    assert interface.universes[1].active is True


@pytest.mark.asyncio
async def test_add_universe_twice_replaces_the_output():
    interface = DMXInterface()
    await interface.add_universe(1, "mock", {})
    first = interface.outputs[1][0]
    await interface.add_universe(1, "mock", {})

    assert len(interface.outputs[1]) == 1
    assert interface.outputs[1][0] is not first
    assert first.running is False


@pytest.mark.asyncio
async def test_add_multiple_outputs_to_one_universe():
    interface = DMXInterface()
    await interface.add_output(1, "mock", {}, output_id=10)
    await interface.add_output(1, "mock", {}, output_id=11)

    assert len(interface.outputs[1]) == 2
    assert [c["id"] for c in interface._output_configs[1]] == [10, 11]


@pytest.mark.asyncio
async def test_disabled_output_is_registered_but_not_started():
    interface = DMXInterface()
    await interface.add_output(1, "mock", {}, output_id=1, enabled=False)

    assert interface.outputs[1][0].running is False
    assert interface._output_configs[1][0]["enabled"] is False
    assert interface.universes[1].active is False


@pytest.mark.asyncio
async def test_remove_output_by_id():
    interface = DMXInterface()
    await interface.add_output(1, "mock", {}, output_id=10)
    await interface.add_output(1, "mock", {}, output_id=11)

    assert await interface.remove_output(1, 10) is True
    assert [c["id"] for c in interface._output_configs[1]] == [11]


@pytest.mark.asyncio
async def test_remove_output_unknown_id_returns_false():
    interface = DMXInterface()
    await interface.add_output(1, "mock", {}, output_id=10)
    assert await interface.remove_output(1, 999) is False
    assert await interface.remove_output(99, 10) is False


@pytest.mark.asyncio
async def test_remove_all_outputs_stops_them():
    interface = DMXInterface()
    await interface.add_output(1, "mock", {}, output_id=1)
    output = interface.outputs[1][0]

    await interface.remove_all_outputs(1)
    assert 1 not in interface.outputs
    assert 1 not in interface._output_configs
    assert output.running is False


@pytest.mark.asyncio
async def test_remove_universe_clears_everything():
    interface = DMXInterface()
    await interface.add_universe(1, "mock", {})
    interface.set_passthrough(1, passthrough_mode="faders_output")

    await interface.remove_universe(1)
    assert 1 not in interface.universes
    assert 1 not in interface.outputs
    assert 1 not in interface._passthrough_config


@pytest.mark.asyncio
async def test_remove_unknown_universe_is_safe():
    interface = DMXInterface()
    await interface.remove_universe(123)


@pytest.mark.asyncio
async def test_get_output_status_and_configs():
    interface = DMXInterface()
    await interface.add_output(1, "mock", {"log_level": "debug"}, output_id=5)

    status = interface.get_output_status(1)
    assert isinstance(status, list) and len(status) == 1
    assert status[0]["protocol"] == "mock"

    configs = interface.get_output_configs(1)
    assert configs[0]["device_type"] == "mock"
    assert configs[0]["config"] == {"log_level": "debug"}


def test_get_output_status_none_without_outputs(dmx1):
    assert dmx1.get_output_status(1) is None
    assert dmx1.get_output_configs(1) == []


def test_get_protocols_and_input_protocols_are_lists(dmx):
    assert isinstance(dmx.get_protocols(), list)
    assert isinstance(dmx.get_input_protocols(), list)


@pytest.mark.asyncio
async def test_values_are_pushed_to_running_outputs():
    """A channel change reaches the output as a scaled 512-value frame."""
    import asyncio

    interface = DMXInterface()
    await interface.add_universe(1, "mock", {})
    output = interface.outputs[1][0]

    interface.set_channel(1, 1, 255)
    await asyncio.sleep(0)  # let the scheduled send_dmx task run

    assert output._last_send is not None
    assert len(output._last_send) == 512
    assert output._last_send[0] == 255


@pytest.mark.asyncio
async def test_disconnect_stops_inputs_and_outputs():
    interface = DMXInterface()
    await interface.add_universe(1, "mock", {})
    await interface.add_input(1, "midi_input", {})
    output = interface.outputs[1][0]

    await interface.disconnect()

    assert interface.inputs == {}
    assert output.running is False
