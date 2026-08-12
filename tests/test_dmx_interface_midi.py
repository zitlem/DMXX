"""Tests for the MIDI integration inside DMXInterface."""
import pytest

from backend.dmx_inputs import MIDIInput


class FakeMIDIHandler:
    """Minimal MIDIHandler stand-in that records outgoing messages."""

    def __init__(self, with_port=True):
        self._output_port = object() if with_port else None
        self.cc = []
        self.notes_on = []
        self.notes_off = []
        self.learn_started = 0
        self.learn_stopped = 0
        self.last_message = {"type": "control_change"}

    def send_cc(self, channel, control, value):
        self.cc.append((channel, control, value))
        return True

    def send_note_on(self, channel, note, velocity=127):
        self.notes_on.append((channel, note, velocity))
        return True

    def send_note_off(self, channel, note):
        self.notes_off.append((channel, note))
        return True

    def start_learn_mode(self):
        self.learn_started += 1

    def stop_learn_mode(self):
        self.learn_stopped += 1

    def get_last_learned_message(self):
        return self.last_message

    def get_status(self):
        return {"available": True,
                "input": {"running": True, "device": "Fake",
                          "messages_received": 3},
                "output": {"running": True, "device": "Fake",
                           "messages_sent": 0},
                "network": {"server_running": False, "port": None, "peers": []}}


def cc_mapping(cc_number=1, input_channel=1, midi_channel=-1, enabled=True,
               device_name=None, label=""):
    return {"cc_number": cc_number, "input_channel": input_channel,
            "midi_channel": midi_channel, "enabled": enabled,
            "device_name": device_name, "label": label}


def trigger(note=60, action="scene", target_id=1, midi_channel=-1,
            enabled=True, device_name=None):
    return {"note": note, "action": action, "target_id": target_id,
            "midi_channel": midi_channel, "enabled": enabled,
            "device_name": device_name, "label": ""}


# ---------------------------------------------------------------------------
# Loading mappings and triggers
# ---------------------------------------------------------------------------
def test_load_cc_mappings_filters_disabled(dmx):
    dmx.load_midi_cc_mappings([cc_mapping(1), cc_mapping(2, enabled=False)])
    assert [m["cc_number"] for m in dmx._midi_cc_mappings] == [1]


def test_load_triggers_filters_disabled(dmx):
    dmx.load_midi_triggers([trigger(60), trigger(61, enabled=False)])
    assert [t["note"] for t in dmx._midi_triggers] == [60]


def test_loading_replaces_previous_mappings(dmx):
    dmx.load_midi_cc_mappings([cc_mapping(1)])
    dmx.load_midi_cc_mappings([])
    assert dmx._midi_cc_mappings == []


def test_midi_input_values_start_at_zero(dmx):
    values = dmx.get_midi_input_values()
    assert values == [0] * 512
    values[0] = 5
    assert dmx.get_midi_input_values()[0] == 0  # a copy is returned


def test_set_midi_input_enabled(dmx):
    assert dmx._midi_input_enabled is False
    dmx.set_midi_input_enabled(True)
    assert dmx._midi_input_enabled is True


def test_set_midi_output_enabled(dmx):
    dmx.set_midi_output_enabled(True)
    assert dmx._midi_output_enabled is True


# ---------------------------------------------------------------------------
# CC -> input channel routing
# ---------------------------------------------------------------------------
@pytest.fixture
def midi_universe(dmx1):
    """A universe whose input is a MIDIInput handler."""
    received = []
    handler = MIDIInput(1, {}, lambda uid, values: received.append((uid, values)))
    handler._running = True
    dmx1.inputs[1] = handler
    dmx1.received = received
    return dmx1


def test_cc_updates_the_mapped_input_channel(midi_universe):
    midi_universe.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=3)])
    midi_universe._handle_midi_cc_input(0, 7, 127)

    universe_id, values = midi_universe.received[-1]
    assert universe_id == 1
    assert values[2] == 255  # MIDI 127 -> DMX 255


def test_cc_value_is_scaled_to_dmx(midi_universe):
    midi_universe.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=1)])
    midi_universe._handle_midi_cc_input(0, 7, 64)
    assert midi_universe.received[-1][1][0] == 128


def test_unmapped_cc_is_ignored(midi_universe):
    midi_universe.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=1)])
    midi_universe._handle_midi_cc_input(0, 8, 127)
    assert midi_universe.received == []


def test_cc_channel_filter(midi_universe):
    midi_universe.load_midi_cc_mappings(
        [cc_mapping(cc_number=7, input_channel=1, midi_channel=2)])

    midi_universe._handle_midi_cc_input(1, 7, 127)
    assert midi_universe.received == []

    midi_universe._handle_midi_cc_input(2, 7, 127)
    assert len(midi_universe.received) == 1


def test_cc_channel_wildcard_accepts_any_channel(midi_universe):
    midi_universe.load_midi_cc_mappings(
        [cc_mapping(cc_number=7, input_channel=1, midi_channel=-1)])
    midi_universe._handle_midi_cc_input(9, 7, 127)
    assert len(midi_universe.received) == 1


def test_cc_device_filter_on_the_mapping(midi_universe):
    midi_universe.load_midi_cc_mappings(
        [cc_mapping(cc_number=7, input_channel=1, device_name="Launchpad")])

    midi_universe._handle_midi_cc_input(0, 7, 127, device_name="APC")
    assert midi_universe.received == []

    midi_universe._handle_midi_cc_input(0, 7, 127, device_name="Launchpad")
    assert len(midi_universe.received) == 1


def test_cc_device_filter_on_the_universe_input(dmx1):
    received = []
    handler = MIDIInput(1, {"device_name": "Launchpad"},
                        lambda uid, values: received.append((uid, values)))
    handler._running = True
    dmx1.inputs[1] = handler
    dmx1.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=1)])

    dmx1._handle_midi_cc_input(0, 7, 127, device_name="APC")
    assert received == []

    dmx1._handle_midi_cc_input(0, 7, 127, device_name="Launchpad")
    assert len(received) == 1


def test_cc_skips_stopped_inputs(midi_universe):
    midi_universe.inputs[1]._running = False
    midi_universe.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=1)])
    midi_universe._handle_midi_cc_input(0, 7, 127)
    assert midi_universe.received == []


def test_cc_skips_non_midi_inputs(dmx1):
    dmx1.inputs[1] = object()
    dmx1.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=1)])
    dmx1._handle_midi_cc_input(0, 7, 127)  # must not raise


@pytest.mark.parametrize("input_channel", [0, 513, None])
def test_cc_with_bad_input_channel_is_ignored(midi_universe, input_channel):
    midi_universe.load_midi_cc_mappings(
        [cc_mapping(cc_number=7, input_channel=input_channel)])
    midi_universe._handle_midi_cc_input(0, 7, 127)
    assert midi_universe.received == []


def test_cc_with_missing_number_or_value_is_ignored(midi_universe):
    midi_universe.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=1)])
    midi_universe._handle_midi_cc_input(0, None, 127)
    midi_universe._handle_midi_cc_input(0, 7, None)
    assert midi_universe.received == []


def test_one_cc_can_drive_several_channels(midi_universe):
    midi_universe.load_midi_cc_mappings([
        cc_mapping(cc_number=7, input_channel=1),
        cc_mapping(cc_number=7, input_channel=2),
    ])
    midi_universe._handle_midi_cc_input(0, 7, 127)

    values = midi_universe.received[-1][1]
    assert values[0] == 255 and values[1] == 255


# ---------------------------------------------------------------------------
# Note triggers
# ---------------------------------------------------------------------------
def test_note_trigger_recalls_a_scene(dmx):
    recalled = []
    dmx.set_scene_recall_callback(lambda scene_id, velocity:
                                  recalled.append((scene_id, velocity)))
    dmx.load_midi_triggers([trigger(note=60, action="scene", target_id=5)])

    dmx._handle_midi_note_trigger(0, 60, 100, on=True)
    assert recalled == [(5, 100)]


def test_scene_trigger_only_fires_on_note_on(dmx):
    recalled = []
    dmx.set_scene_recall_callback(lambda s, v: recalled.append(s))
    dmx.load_midi_triggers([trigger(note=60, action="scene", target_id=5)])

    dmx._handle_midi_note_trigger(0, 60, 0, on=False)
    assert recalled == []


def test_scene_trigger_without_a_callback_is_safe(dmx):
    dmx.load_midi_triggers([trigger(note=60, action="scene", target_id=5)])
    dmx._handle_midi_note_trigger(0, 60, 100, on=True)


def test_scene_recall_callback_errors_are_contained(dmx):
    dmx.set_scene_recall_callback(lambda s, v: 1 / 0)
    dmx.load_midi_triggers([trigger(note=60, action="scene", target_id=5)])
    dmx._handle_midi_note_trigger(0, 60, 100, on=True)


def test_note_trigger_toggles_blackout(dmx1):
    dmx1.load_midi_triggers([trigger(note=61, action="blackout", target_id=None)])

    dmx1._handle_midi_note_trigger(0, 61, 127, on=True)
    assert dmx1.is_blackout_active() is True

    dmx1._handle_midi_note_trigger(0, 61, 127, on=True)
    assert dmx1.is_blackout_active() is False


def test_blackout_trigger_ignores_note_off(dmx1):
    dmx1.load_midi_triggers([trigger(note=61, action="blackout", target_id=None)])
    dmx1._handle_midi_note_trigger(0, 61, 0, on=False)
    assert dmx1.is_blackout_active() is False


def test_note_trigger_drives_a_group_scaled_by_velocity(dmx1, task_recorder):
    dmx1.load_groups([{
        "id": 3, "name": "G", "mode": "follow", "master_universe": None,
        "master_channel": None, "master_value": 0, "enabled": True,
        "members": [{"universe_id": 1, "channel": 1, "base_value": 255,
                     "target_type": "channel", "target_universe_id": None,
                     "color_role": None}],
    }])
    dmx1.load_midi_triggers([trigger(note=62, action="group", target_id=3)])

    dmx1._handle_midi_note_trigger(0, 62, 127, on=True)

    assert dmx1.get_channel(1, 1) == 255
    assert task_recorder.count == 1


def test_note_trigger_channel_filter(dmx1):
    dmx1.load_midi_triggers([trigger(note=61, action="blackout",
                                     target_id=None, midi_channel=5)])

    dmx1._handle_midi_note_trigger(1, 61, 127, on=True)
    assert dmx1.is_blackout_active() is False

    dmx1._handle_midi_note_trigger(5, 61, 127, on=True)
    assert dmx1.is_blackout_active() is True


def test_note_trigger_device_filter(dmx1):
    dmx1.load_midi_triggers([trigger(note=61, action="blackout", target_id=None,
                                     device_name="Launchpad")])

    dmx1._handle_midi_note_trigger(0, 61, 127, on=True, device_name="APC")
    assert dmx1.is_blackout_active() is False

    dmx1._handle_midi_note_trigger(0, 61, 127, on=True, device_name="Launchpad")
    assert dmx1.is_blackout_active() is True


def test_unmatched_note_does_nothing(dmx1):
    dmx1.load_midi_triggers([trigger(note=61, action="blackout", target_id=None)])
    dmx1._handle_midi_note_trigger(0, 99, 127, on=True)
    assert dmx1.is_blackout_active() is False


def test_note_none_is_ignored(dmx1):
    dmx1.load_midi_triggers([trigger(note=61, action="blackout", target_id=None)])
    dmx1._handle_midi_note_trigger(0, None, 127, on=True)
    assert dmx1.is_blackout_active() is False


# ---------------------------------------------------------------------------
# _on_midi_message dispatch
# ---------------------------------------------------------------------------
def test_on_midi_message_routes_control_change(midi_universe):
    midi_universe.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=1)])
    midi_universe._on_midi_message("control_change",
                                   {"channel": 0, "control": 7, "value": 127})
    assert midi_universe.received


def test_on_midi_message_routes_notes(dmx1):
    dmx1.load_midi_triggers([trigger(note=61, action="blackout", target_id=None)])
    dmx1._on_midi_message("note_on", {"channel": 0, "note": 61, "velocity": 127})
    assert dmx1.is_blackout_active() is True


def test_on_midi_message_broadcasts_activity(dmx1, events):
    dmx1._on_midi_message("note_on", {"channel": 0, "note": 61, "velocity": 1})

    activity = [d for kind, d in events if kind == "midi_activity"]
    assert activity == [{"type": "note_on",
                         "data": {"channel": 0, "note": 61, "velocity": 1}}]


def test_on_midi_message_ignores_other_types(dmx1, events):
    dmx1._on_midi_message("clock", {})
    assert [d for kind, d in events if kind == "midi_activity"]


# ---------------------------------------------------------------------------
# MIDI feedback output
# ---------------------------------------------------------------------------
def test_channel_change_sends_cc_feedback(dmx1):
    handler = FakeMIDIHandler()
    dmx1._midi_handler = handler
    dmx1.set_midi_output_enabled(True)
    dmx1.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=3,
                                           midi_channel=-1)])

    dmx1.set_channel(1, 3, 254)

    assert handler.cc == [(0, 7, 127)]  # midi_channel -1 falls back to 0


def test_no_feedback_when_output_disabled(dmx1):
    handler = FakeMIDIHandler()
    dmx1._midi_handler = handler
    dmx1.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=3)])

    dmx1.set_channel(1, 3, 254)
    assert handler.cc == []


def test_no_feedback_without_an_output_port(dmx1):
    handler = FakeMIDIHandler(with_port=False)
    dmx1._midi_handler = handler
    dmx1.set_midi_output_enabled(True)
    dmx1.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=3)])

    dmx1.set_channel(1, 3, 254)
    assert handler.cc == []


def test_midi_sourced_changes_do_not_echo_back(dmx1):
    handler = FakeMIDIHandler()
    dmx1._midi_handler = handler
    dmx1.set_midi_output_enabled(True)
    dmx1.load_midi_cc_mappings([cc_mapping(cc_number=7, input_channel=3)])

    dmx1.set_channel(1, 3, 254, source="midi")
    assert handler.cc == []


def test_scene_activation_lights_the_button(dmx):
    handler = FakeMIDIHandler()
    dmx._midi_handler = handler
    dmx.set_midi_output_enabled(True)
    dmx.load_midi_triggers([trigger(note=40, action="scene", target_id=7)])

    dmx.set_active_scene(7)
    assert handler.notes_on == [(0, 40, 127)]
    assert dmx.get_active_scene() == 7

    dmx.set_active_scene(None)
    assert handler.notes_off == [(0, 40)]
    assert dmx.get_active_scene() is None


def test_switching_scenes_turns_the_old_button_off(dmx):
    handler = FakeMIDIHandler()
    dmx._midi_handler = handler
    dmx.set_midi_output_enabled(True)
    dmx.load_midi_triggers([
        trigger(note=40, action="scene", target_id=7),
        trigger(note=41, action="scene", target_id=8),
    ])

    dmx.set_active_scene(7)
    dmx.set_active_scene(8)

    assert handler.notes_off == [(0, 40)]
    assert handler.notes_on == [(0, 40, 127), (0, 41, 127)]


def test_reactivating_the_same_scene_does_not_send_note_off(dmx):
    handler = FakeMIDIHandler()
    dmx._midi_handler = handler
    dmx.set_midi_output_enabled(True)
    dmx.load_midi_triggers([trigger(note=40, action="scene", target_id=7)])

    dmx.set_active_scene(7)
    dmx.set_active_scene(7)
    assert handler.notes_off == []


def test_blackout_sends_note_feedback(dmx1):
    handler = FakeMIDIHandler()
    dmx1._midi_handler = handler
    dmx1.set_midi_output_enabled(True)
    dmx1.load_midi_triggers([trigger(note=50, action="blackout", target_id=None)])

    dmx1.blackout()
    assert handler.notes_on == [(0, 50, 127)]

    dmx1.release_blackout()
    assert handler.notes_off == [(0, 50)]


def test_grandmaster_feedback_is_a_noop(dmx):
    dmx.send_midi_grandmaster_value("global", 128)  # documented as unimplemented


# ---------------------------------------------------------------------------
# Status passthrough
# ---------------------------------------------------------------------------
def test_midi_status_without_a_handler(dmx):
    status = dmx.get_midi_status()
    assert status["input"]["running"] is False
    assert status["output"]["running"] is False
    assert status["learn_mode"] is False


def test_midi_status_delegates_to_the_handler(dmx):
    dmx._midi_handler = FakeMIDIHandler()
    assert dmx.get_midi_status()["input"]["device"] == "Fake"


def test_midi_devices_listing(dmx):
    devices = dmx.get_midi_devices()
    assert set(devices) == {"inputs", "outputs"}
    assert isinstance(devices["inputs"], list)


def test_learn_mode_delegates_to_the_handler(dmx):
    handler = FakeMIDIHandler()
    dmx._midi_handler = handler

    dmx.start_midi_learn()
    dmx.stop_midi_learn()
    assert (handler.learn_started, handler.learn_stopped) == (1, 1)
    assert dmx.get_midi_last_message() == {"type": "control_change"}


def test_learn_mode_without_a_handler_is_safe(dmx):
    dmx.start_midi_learn()
    dmx.stop_midi_learn()
    assert dmx.get_midi_last_message() is None


def test_midi_input_status_summary(dmx):
    dmx._midi_handler = FakeMIDIHandler()
    dmx.set_midi_input_enabled(True)
    dmx.load_midi_cc_mappings([cc_mapping(1), cc_mapping(2)])
    dmx.load_midi_triggers([trigger(60)])
    dmx._midi_input_values[0] = 100

    status = dmx.get_midi_input_status()
    assert status["type"] == "midi"
    assert status["enabled"] is True
    assert status["running"] is True
    assert status["active_channels"] == 1
    assert status["cc_mappings_count"] == 2
    assert status["triggers_count"] == 1
    assert status["messages_received"] == 3


def test_midi_network_peers_without_a_handler(dmx):
    assert dmx.get_midi_network_peers() == []


# ---------------------------------------------------------------------------
# MIDI input applied to output
# ---------------------------------------------------------------------------
def test_direct_midi_input_uses_htp_against_faders(dmx1):
    dmx1.set_channel(1, 1, 200, source="local")
    dmx1._midi_input_values[0] = 100
    dmx1._midi_input_values[1] = 150

    dmx1._apply_midi_direct_input({1, 2})

    assert dmx1.get_channel(1, 1) == 200
    assert dmx1.get_channel(1, 2) == 150


def test_direct_midi_input_notifies_the_ui(dmx1, events):
    dmx1._midi_input_values[0] = 10
    dmx1._apply_midi_direct_input({1})

    ui = [d for kind, d in events if kind == "midi_input_to_ui"]
    assert ui and ui[0]["universe_id"] == 1
    assert ui[0]["channels"] == [1]


def test_direct_midi_input_is_blocked_by_blackout(dmx1):
    dmx1.blackout()
    dmx1._midi_input_values[0] = 200
    dmx1._apply_midi_direct_input({1})
    assert dmx1.get_channel(1, 1) == 0


def test_direct_midi_input_without_universes_is_safe(dmx):
    dmx._midi_input_values[0] = 200
    dmx._apply_midi_direct_input({1})


def test_mapped_midi_input_routes_through_universe_zero(dmx12):
    dmx12.set_channel_mapping([
        {"src_universe": 0, "src_channel": 1, "dst_universe": 2, "dst_channel": 5},
    ], unmapped_behavior="ignore")
    dmx12._midi_input_values[0] = 199

    dmx12._apply_midi_mapped_input({1})
    assert dmx12.get_channel(2, 5) == 199


def test_mapped_midi_input_can_drive_grandmasters(dmx12):
    dmx12.set_channel_mapping([
        {"src_universe": 0, "src_channel": 1, "dst_target_type": "global_master"},
        {"src_universe": 0, "src_channel": 2,
         "dst_target_type": "universe_master", "dst_target_universe_id": 2},
    ], unmapped_behavior="ignore")
    dmx12._midi_input_values[0] = 111
    dmx12._midi_input_values[1] = 22

    dmx12._apply_midi_mapped_input({1, 2})

    assert dmx12.get_global_grandmaster() == 111
    assert dmx12.get_universe_grandmaster(2) == 22


def test_mapped_midi_input_is_blocked_by_blackout(dmx12):
    dmx12.set_channel_mapping([
        {"src_universe": 0, "src_channel": 1, "dst_universe": 2, "dst_channel": 5},
    ])
    dmx12.blackout()
    dmx12._midi_input_values[0] = 199
    dmx12._apply_midi_mapped_input({1})
    assert dmx12.get_channel(2, 5) == 0


def test_mapped_midi_input_skips_missing_universes(dmx1):
    dmx1.set_channel_mapping([
        {"src_universe": 0, "src_channel": 1, "dst_universe": 9, "dst_channel": 5},
    ])
    dmx1._midi_input_values[0] = 199
    dmx1._apply_midi_mapped_input({1})  # must not raise


def test_on_midi_input_received_broadcasts_and_applies(dmx1, events):
    dmx1.set_midi_input_enabled(True)
    dmx1._midi_input_values[0] = 77

    dmx1._on_midi_input_received({1})

    assert [d for kind, d in events if kind == "midi_input_received"]
    assert dmx1.get_channel(1, 1) == 77


def test_on_midi_input_received_is_throttled(dmx1, events):
    dmx1._on_midi_input_received({1})
    dmx1._on_midi_input_received({1})
    assert len([d for kind, d in events if kind == "midi_input_received"]) == 1


def test_on_midi_input_received_without_integration_only_broadcasts(dmx1, events):
    dmx1._midi_input_values[0] = 77
    dmx1._on_midi_input_received({1})

    assert [d for kind, d in events if kind == "midi_input_received"]
    assert dmx1.get_channel(1, 1) == 0
