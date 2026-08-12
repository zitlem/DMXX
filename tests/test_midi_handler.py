"""Tests for MIDIHandler message dispatch, learn mode, status and sending."""
import types

import pytest

from backend import midi_handler as mh
from backend.midi_handler import MIDIHandler


class FakeMessage:
    """Stand-in for a mido Message."""

    def __init__(self, type, channel=0, **fields):
        self.type = type
        self.channel = channel
        for key, value in fields.items():
            setattr(self, key, value)


class FakePort:
    def __init__(self):
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


@pytest.fixture
def handler():
    received = []
    h = MIDIHandler(on_message_callback=lambda t, d: received.append((t, d)))
    h.received = received
    return h


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------
def test_handle_control_change(handler):
    handler._handle_message("Launchpad", FakeMessage("control_change", channel=3,
                                                     control=7, value=64))

    msg_type, data = handler.received[0]
    assert msg_type == "control_change"
    assert data["channel"] == 3
    assert data["control"] == 7
    assert data["value"] == 64
    assert data["device_name"] == "Launchpad"
    assert handler._messages_received == 1


def test_handle_note_on_and_off(handler):
    handler._handle_message("dev", FakeMessage("note_on", note=60, velocity=100))
    handler._handle_message("dev", FakeMessage("note_off", note=60, velocity=0))

    assert handler.received[0][1]["note"] == 60
    assert handler.received[0][1]["velocity"] == 100
    assert handler.received[1][0] == "note_off"
    assert handler.received[1][1]["velocity"] == 0


def test_handle_program_change(handler):
    handler._handle_message("dev", FakeMessage("program_change", program=5))
    assert handler.received[0][1]["program"] == 5


def test_handle_unknown_message_type_still_dispatches(handler):
    handler._handle_message("dev", FakeMessage("clock"))
    assert handler.received[0][0] == "clock"


def test_message_without_channel_attribute(handler):
    msg = types.SimpleNamespace(type="sysex")
    handler._handle_message("dev", msg)
    assert handler.received[0][1]["channel"] is None


def test_callback_errors_are_swallowed():
    h = MIDIHandler(on_message_callback=lambda *_: 1 / 0)
    h._handle_message("dev", FakeMessage("note_on", note=1, velocity=1))
    assert h._messages_received == 1


def test_handler_without_callback_is_fine():
    h = MIDIHandler()
    h._handle_message("dev", FakeMessage("note_on", note=1, velocity=1))
    assert h._messages_received == 1


def test_message_counter_increments(handler):
    for _ in range(3):
        handler._handle_message("dev", FakeMessage("note_on", note=1, velocity=1))
    assert handler._messages_received == 3


# ---------------------------------------------------------------------------
# Learn mode
# ---------------------------------------------------------------------------
def test_learn_mode_captures_the_last_message(handler):
    handler.start_learn_mode()
    handler._handle_message("dev", FakeMessage("control_change", control=1, value=2))

    learned = handler.get_last_learned_message()
    assert learned["control"] == 1
    assert learned["value"] == 2


def test_messages_are_not_captured_outside_learn_mode(handler):
    handler._handle_message("dev", FakeMessage("control_change", control=1, value=2))
    assert handler.get_last_learned_message() is None


def test_start_learn_mode_clears_the_previous_capture(handler):
    handler.start_learn_mode()
    handler._handle_message("dev", FakeMessage("control_change", control=1, value=2))
    handler.start_learn_mode()
    assert handler.get_last_learned_message() is None


def test_stop_learn_mode_freezes_the_capture(handler):
    handler.start_learn_mode()
    handler._handle_message("dev", FakeMessage("control_change", control=1, value=2))
    handler.stop_learn_mode()
    handler._handle_message("dev", FakeMessage("control_change", control=9, value=9))

    assert handler._learn_mode is False
    assert handler.get_last_learned_message()["control"] == 1


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def test_send_without_an_output_port_returns_false(handler):
    assert handler.send_cc(0, 1, 2) is False
    assert handler.send_note_on(0, 60) is False
    assert handler.send_note_off(0, 60) is False
    assert handler._messages_sent == 0


@pytest.mark.skipif(not mh.MIDO_AVAILABLE, reason="mido not installed")
def test_send_cc_writes_to_the_port(handler):
    port = FakePort()
    handler._output_port = port

    assert handler.send_cc(2, 7, 100) is True
    assert handler._messages_sent == 1

    msg = port.sent[0]
    assert msg.type == "control_change"
    assert (msg.channel, msg.control, msg.value) == (2, 7, 100)


@pytest.mark.skipif(not mh.MIDO_AVAILABLE, reason="mido not installed")
def test_send_cc_clamps_the_value(handler):
    port = FakePort()
    handler._output_port = port

    handler.send_cc(0, 1, 999)
    handler.send_cc(0, 1, -5)
    assert [m.value for m in port.sent] == [127, 0]


@pytest.mark.skipif(not mh.MIDO_AVAILABLE, reason="mido not installed")
def test_send_note_on_and_off(handler):
    port = FakePort()
    handler._output_port = port

    assert handler.send_note_on(1, 60, 90) is True
    assert handler.send_note_off(1, 60) is True

    assert port.sent[0].type == "note_on"
    assert port.sent[0].velocity == 90
    assert port.sent[1].type == "note_off"
    assert port.sent[1].velocity == 0
    assert handler._messages_sent == 2


@pytest.mark.skipif(not mh.MIDO_AVAILABLE, reason="mido not installed")
def test_send_note_on_clamps_velocity(handler):
    port = FakePort()
    handler._output_port = port
    handler.send_note_on(0, 60, 999)
    assert port.sent[0].velocity == 127


@pytest.mark.skipif(not mh.MIDO_AVAILABLE, reason="mido not installed")
def test_send_failure_is_reported_as_false(handler):
    class BrokenPort:
        def send(self, msg):
            raise OSError("cable unplugged")

    handler._output_port = BrokenPort()
    assert handler.send_cc(0, 1, 2) is False
    assert handler._messages_sent == 0


def test_send_returns_false_when_mido_missing(handler, monkeypatch):
    monkeypatch.setattr(mh, "MIDO_AVAILABLE", False)
    handler._output_port = FakePort()
    assert handler.send_cc(0, 1, 2) is False
    assert handler.send_note_on(0, 1) is False
    assert handler.send_note_off(0, 1) is False


# ---------------------------------------------------------------------------
# Status & device discovery
# ---------------------------------------------------------------------------
def test_status_of_a_fresh_handler(handler):
    status = handler.get_status()

    assert status["available"] == mh.MIDO_AVAILABLE
    assert status["input"] == {"running": False, "device": None,
                               "devices": [], "messages_received": 0}
    assert status["output"] == {"running": False, "device": None,
                                "messages_sent": 0}
    assert status["learn_mode"] is False
    assert status["last_message"] is None
    assert "network" in status


def test_status_reflects_connected_input_devices(handler):
    handler._input_ports = {"Launchpad": object(), "APC": object()}
    handler._running = True

    status = handler.get_status()
    assert status["input"]["running"] is True
    assert status["input"]["device"] == "Launchpad"
    assert sorted(status["input"]["devices"]) == ["APC", "Launchpad"]


def test_status_reflects_output_port(handler):
    handler._output_port = FakePort()
    handler._output_device = "IAC Bus 1"

    status = handler.get_status()
    assert status["output"]["running"] is True
    assert status["output"]["device"] == "IAC Bus 1"


def test_is_available_matches_module_flag():
    assert MIDIHandler.is_available() == mh.MIDO_AVAILABLE


def test_device_listing_returns_lists():
    assert isinstance(MIDIHandler.list_input_devices(), list)
    assert isinstance(MIDIHandler.list_output_devices(), list)


def test_device_listing_is_empty_without_mido(monkeypatch):
    monkeypatch.setattr(mh, "MIDO_AVAILABLE", False)
    assert MIDIHandler.list_input_devices() == []
    assert MIDIHandler.list_output_devices() == []


def test_device_listing_survives_backend_errors(monkeypatch):
    if not mh.MIDO_AVAILABLE:
        pytest.skip("mido not installed")

    def boom():
        raise RuntimeError("no midi backend")

    monkeypatch.setattr(mh.mido, "get_input_names", boom)
    monkeypatch.setattr(mh.mido, "get_output_names", boom)
    assert MIDIHandler.list_input_devices() == []
    assert MIDIHandler.list_output_devices() == []


def test_network_status_shape(handler):
    status = handler.get_network_status()
    assert isinstance(status, dict)
    assert "available" in status


def test_network_peers_default_empty(handler):
    assert handler.get_network_peers() == []


def test_network_sends_without_a_server_reach_nobody(handler):
    assert handler.send_network_cc(0, 1, 2) == 0
    assert handler.send_network_note_on(0, 60, 100) == 0
    assert handler.send_network_note_off(0, 60) == 0


@pytest.mark.asyncio
async def test_stopping_an_unstarted_handler_is_safe(handler):
    await handler.stop_input()
    await handler.stop_output()
    await handler.stop_network_server()
    assert handler.get_status()["input"]["running"] is False
