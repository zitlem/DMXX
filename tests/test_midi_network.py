"""Tests for the rtpMIDI network handler."""
import types

import pytest

from backend import midi_network as mn
from backend.midi_network import NetworkMIDIHandler


def command(cmd_type, **params):
    return types.SimpleNamespace(command=cmd_type, params=params)


def peer(name="Studio Mac", addr="10.0.0.9", sender=None):
    obj = types.SimpleNamespace(name=name, addr=addr)
    if sender is not None:
        obj.send = sender
    return obj


@pytest.fixture
def handler():
    received = []
    h = NetworkMIDIHandler(on_message_callback=lambda t, d: received.append((t, d)))
    h.received = received
    return h


# ---------------------------------------------------------------------------
# Command translation
# ---------------------------------------------------------------------------
def test_note_on_command(handler):
    handler._handle_command(peer(), command("note_on", channel=2, key=60,
                                            velocity=100))

    msg_type, data = handler.received[0]
    assert msg_type == "note_on"
    assert data["channel"] == 2
    assert data["note"] == 60
    assert data["velocity"] == 100
    assert data["peer"] == "Studio Mac"
    assert data["device_name"] == "network:Studio Mac"


def test_note_off_command_forces_zero_velocity(handler):
    handler._handle_command(peer(), command("note_off", channel=1, key=60,
                                            velocity=99))
    assert handler.received[0][1]["velocity"] == 0


def test_control_change_command(handler):
    handler._handle_command(peer(), command("control_change", channel=0,
                                            control=7, value=64))
    data = handler.received[0][1]
    assert (data["control"], data["value"]) == (7, 64)


def test_program_change_command(handler):
    handler._handle_command(peer(), command("program_change", channel=0, program=3))
    assert handler.received[0][1]["program"] == 3


def test_pitchwheel_command(handler):
    handler._handle_command(peer(), command("pitchwheel", channel=0, pitch=-500))
    assert handler.received[0][1]["pitch"] == -500


def test_missing_params_fall_back_to_defaults(handler):
    handler._handle_command(peer(), command("note_on"))
    data = handler.received[0][1]
    assert (data["channel"], data["note"], data["velocity"]) == (0, 0, 0)


def test_unknown_command_type_still_reports_basics(handler):
    handler._handle_command(peer(), command("sysex"))
    msg_type, data = handler.received[0]
    assert msg_type == "sysex"
    assert "channel" not in data


def test_peer_without_a_name_uses_its_repr(handler):
    anonymous = types.SimpleNamespace()
    handler._handle_command(anonymous, command("note_on", key=1))
    assert handler.received[0][1]["peer"] == str(anonymous)


def test_commands_are_counted(handler):
    for _ in range(3):
        handler._handle_command(peer(), command("note_on", key=1))
    assert handler._messages_received == 3


def test_callback_errors_are_contained():
    h = NetworkMIDIHandler(on_message_callback=lambda *_: 1 / 0)
    h._handle_command(peer(), command("note_on", key=1))
    assert h._messages_received == 1


def test_handler_without_a_callback(handler):
    h = NetworkMIDIHandler()
    h._handle_command(peer(), command("note_on", key=1))
    assert h._messages_received == 1


# ---------------------------------------------------------------------------
# Peers & status
# ---------------------------------------------------------------------------
def test_status_of_a_stopped_handler(handler):
    status = handler.get_status()
    assert status["available"] == mn.PYMIDI_AVAILABLE
    assert status["server_running"] is False
    assert status["port"] is None
    assert status["name"] is None
    assert status["peers"] == []
    assert status["peer_count"] == 0


def test_status_of_a_running_handler(handler):
    handler._running = True
    handler._port = 5010
    handler._name = "Booth"
    handler._peers = {"Mac": peer("Mac")}

    status = handler.get_status()
    assert status["server_running"] is True
    assert status["port"] == 5010
    assert status["name"] == "Booth"
    assert status["peer_count"] == 1


def test_connected_peers_listing(handler):
    handler._peers = {"Mac": peer("Mac", addr="10.0.0.2")}
    assert handler.get_connected_peers() == [{"name": "Mac", "address": "10.0.0.2"}]


def test_peer_without_address_reports_unknown(handler):
    handler._peers = {"Mac": types.SimpleNamespace()}
    assert handler.get_connected_peers() == [{"name": "Mac", "address": "unknown"}]


def test_is_available_matches_module_flag():
    assert NetworkMIDIHandler.is_available() == mn.PYMIDI_AVAILABLE


# ---------------------------------------------------------------------------
# send_to_all
# ---------------------------------------------------------------------------
def test_send_to_all_when_stopped(handler):
    handler._peers = {"Mac": peer(sender=lambda b: None)}
    assert handler.send_to_all(b"\x90\x3c\x7f") == 0


def test_send_to_all_without_peers(handler):
    handler._running = True
    assert handler.send_to_all(b"\x90\x3c\x7f") == 0


def test_send_to_all_delivers_to_every_peer(handler):
    sent_a, sent_b = [], []
    handler._running = True
    handler._peers = {
        "a": peer("a", sender=sent_a.append),
        "b": peer("b", sender=sent_b.append),
    }

    assert handler.send_to_all(b"\x90\x3c\x7f") == 2
    assert sent_a == [b"\x90\x3c\x7f"]
    assert sent_b == [b"\x90\x3c\x7f"]
    assert handler._messages_sent == 2


def test_peers_without_send_are_skipped(handler):
    handler._running = True
    handler._peers = {"a": types.SimpleNamespace(name="a")}
    assert handler.send_to_all(b"\x90") == 0


def test_a_failing_peer_does_not_stop_the_others(handler):
    delivered = []

    def boom(_):
        raise ConnectionResetError

    handler._running = True
    handler._peers = {
        "bad": peer("bad", sender=boom),
        "good": peer("good", sender=delivered.append),
    }

    assert handler.send_to_all(b"\x90") == 1
    assert delivered == [b"\x90"]


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_start_server_reports_false_without_pymidi(handler, monkeypatch):
    monkeypatch.setattr(mn, "PYMIDI_AVAILABLE", False)
    assert await handler.start_server() is False
    assert handler._running is False


@pytest.mark.asyncio
async def test_stop_server_when_never_started(handler):
    await handler.stop_server()
    assert handler._running is False
    assert handler._peers == {}
