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


# ---------------------------------------------------------------------------
# Reader thread and process loop
#
# _read_loop is the body of the background thread; _process_loop is the async
# consumer. Both are driven directly here with fake ports - no MIDI device and
# no real thread involved.
# ---------------------------------------------------------------------------
class PollingPort:
    """Yields a scripted sequence of messages, then unregisters itself."""

    def __init__(self, handler, device_name, messages):
        self.handler = handler
        self.device_name = device_name
        self.messages = list(messages)
        self.polls = 0
        self.closed = False

    def poll(self):
        self.polls += 1
        if self.messages:
            return self.messages.pop(0)
        # Nothing left - drop out of _input_ports so the loop terminates
        self.handler._input_ports.pop(self.device_name, None)
        return None

    def close(self):
        self.closed = True


def test_read_loop_queues_messages_with_their_device(handler):
    messages = [FakeMessage("note_on", note=60, velocity=1),
                FakeMessage("control_change", control=7, value=2)]
    port = PollingPort(handler, "APC", messages)
    handler._input_ports["APC"] = port
    handler._running = True

    handler._read_loop("APC", port)

    queued = []
    while not handler._message_queue.empty():
        queued.append(handler._message_queue.get_nowait())
    assert [device for device, _ in queued] == ["APC", "APC"]
    assert [msg.type for _, msg in queued] == ["note_on", "control_change"]


def test_read_loop_stops_when_the_handler_stops(handler):
    port = PollingPort(handler, "APC", [FakeMessage("note_on", note=1, velocity=1)])
    handler._input_ports["APC"] = port
    handler._running = False

    handler._read_loop("APC", port)

    assert port.polls == 0
    assert handler._message_queue.empty()


def test_read_loop_stops_when_the_device_is_removed(handler):
    port = PollingPort(handler, "APC", [])
    handler._input_ports["APC"] = port
    handler._running = True

    handler._read_loop("APC", port)   # terminates rather than spinning
    assert "APC" not in handler._input_ports


def test_read_loop_survives_a_failing_port(handler):
    class BrokenPort:
        def poll(self):
            raise OSError("device unplugged")

    handler._input_ports["APC"] = BrokenPort()
    handler._running = True

    handler._read_loop("APC", handler._input_ports["APC"])  # breaks out, no raise


async def run_one_process_pass(handler):
    """Run a single iteration of the async process loop."""
    import asyncio

    handler._running = True

    async def stop_after_first_sleep(_delay):
        handler._running = False

    real_sleep = asyncio.sleep
    asyncio.sleep = stop_after_first_sleep
    try:
        await handler._process_loop()
    finally:
        asyncio.sleep = real_sleep


@pytest.mark.asyncio
async def test_process_loop_dispatches_a_queued_message(handler):
    handler._message_queue.put(("APC", FakeMessage("note_on", note=60,
                                                   velocity=100)))

    await run_one_process_pass(handler)

    assert len(handler.received) == 1
    msg_type, data = handler.received[0]
    assert msg_type == "note_on"
    assert data["device_name"] == "APC"


@pytest.mark.asyncio
async def test_process_loop_tolerates_an_empty_queue(handler):
    await run_one_process_pass(handler)
    assert handler.received == []


@pytest.mark.asyncio
async def test_process_loop_exits_on_cancellation(handler):
    import asyncio

    handler._running = True
    task = asyncio.create_task(handler._process_loop())
    await asyncio.sleep(0)
    task.cancel()
    await task
    assert task.done()


# ---------------------------------------------------------------------------
# Input port lifecycle (mido stubbed - no hardware)
# ---------------------------------------------------------------------------
@pytest.fixture
def stub_mido(monkeypatch):
    """Replace mido's port discovery/opening with in-memory fakes."""
    opened = {}

    class StubPort:
        def __init__(self, name):
            self.name = name
            self.closed = False

        def poll(self):
            return None

        def close(self):
            self.closed = True

    def open_input(name):
        if name == "Broken":
            raise OSError("cannot open device")
        port = StubPort(name)
        opened[name] = port
        return port

    monkeypatch.setattr(mh, "MIDO_AVAILABLE", True)
    monkeypatch.setattr(mh.mido, "get_input_names", lambda: ["APC", "Launchpad"])
    monkeypatch.setattr(mh.mido, "open_input", open_input)
    return opened


@pytest.mark.asyncio
async def test_start_input_opens_the_named_device(handler, stub_mido):
    assert await handler.start_input("Launchpad") is True

    assert list(handler._input_ports) == ["Launchpad"]
    assert handler._running is True
    assert handler.get_status()["input"]["devices"] == ["Launchpad"]

    await handler.stop_input()


@pytest.mark.asyncio
async def test_start_input_defaults_to_the_first_device(handler, stub_mido):
    assert await handler.start_input() is True
    assert list(handler._input_ports) == ["APC"]

    await handler.stop_input()


@pytest.mark.asyncio
async def test_start_input_is_additive(handler, stub_mido):
    await handler.start_input("APC")
    await handler.start_input("Launchpad")

    assert sorted(handler._input_ports) == ["APC", "Launchpad"]

    await handler.stop_input()


@pytest.mark.asyncio
async def test_starting_the_same_device_twice_is_a_noop(handler, stub_mido):
    await handler.start_input("APC")
    port = handler._input_ports["APC"]

    assert await handler.start_input("APC") is True
    assert handler._input_ports["APC"] is port

    await handler.stop_input()


@pytest.mark.asyncio
async def test_start_input_reports_an_unopenable_device(handler, stub_mido):
    assert await handler.start_input("Broken") is False
    assert handler._input_ports == {}


@pytest.mark.asyncio
async def test_start_input_without_any_devices(handler, monkeypatch, stub_mido):
    monkeypatch.setattr(mh.mido, "get_input_names", lambda: [])
    assert await handler.start_input() is False


@pytest.mark.asyncio
async def test_stop_input_closes_only_the_named_device(handler, stub_mido):
    await handler.start_input("APC")
    await handler.start_input("Launchpad")
    apc = handler._input_ports["APC"]

    await handler.stop_input("APC")

    assert apc.closed is True
    assert list(handler._input_ports) == ["Launchpad"]
    assert handler._running is True   # still reading the other device

    await handler.stop_input()


@pytest.mark.asyncio
async def test_stopping_the_last_device_stops_the_process_loop(handler, stub_mido):
    await handler.start_input("APC")

    await handler.stop_input()

    assert handler._input_ports == {}
    assert handler._running is False
    assert handler._process_task is None


@pytest.mark.asyncio
async def test_stopping_an_unknown_device_leaves_the_others(handler, stub_mido):
    await handler.start_input("APC")

    await handler.stop_input("Nonexistent")

    assert list(handler._input_ports) == ["APC"]
    await handler.stop_input()


@pytest.mark.asyncio
async def test_start_input_returns_false_without_mido(handler, monkeypatch):
    monkeypatch.setattr(mh, "MIDO_AVAILABLE", False)
    assert await handler.start_input("APC") is False


# ---------------------------------------------------------------------------
# Output port lifecycle (mido stubbed)
# ---------------------------------------------------------------------------
@pytest.fixture
def stub_mido_output(monkeypatch):
    class StubOutPort:
        def __init__(self, name):
            self.name = name
            self.closed = False

        def send(self, msg):
            pass

        def close(self):
            self.closed = True

    def open_output(name):
        if name == "Broken":
            raise OSError("cannot open device")
        return StubOutPort(name)

    monkeypatch.setattr(mh, "MIDO_AVAILABLE", True)
    monkeypatch.setattr(mh.mido, "get_output_names", lambda: ["IAC Bus 1", "APC"])
    monkeypatch.setattr(mh.mido, "open_output", open_output)


@pytest.mark.asyncio
async def test_start_output_opens_the_named_device(handler, stub_mido_output):
    assert await handler.start_output("APC") is True

    assert handler._output_device == "APC"
    assert handler.get_status()["output"] == {"running": True, "device": "APC",
                                              "messages_sent": 0}


@pytest.mark.asyncio
async def test_start_output_defaults_to_the_first_device(handler,
                                                         stub_mido_output):
    assert await handler.start_output() is True
    assert handler._output_device == "IAC Bus 1"


@pytest.mark.asyncio
async def test_restarting_output_closes_the_previous_port(handler,
                                                          stub_mido_output):
    await handler.start_output("APC")
    first = handler._output_port

    await handler.start_output("IAC Bus 1")

    assert first.closed is True
    assert handler._output_device == "IAC Bus 1"


@pytest.mark.asyncio
async def test_start_output_reports_an_unopenable_device(handler,
                                                         stub_mido_output):
    assert await handler.start_output("Broken") is False


@pytest.mark.asyncio
async def test_start_output_without_any_devices(handler, stub_mido_output,
                                                monkeypatch):
    monkeypatch.setattr(mh.mido, "get_output_names", lambda: [])
    assert await handler.start_output() is False


@pytest.mark.asyncio
async def test_stop_output_closes_and_clears_the_port(handler, stub_mido_output):
    await handler.start_output("APC")
    port = handler._output_port

    await handler.stop_output()

    assert port.closed is True
    assert handler._output_port is None
    assert handler._output_device is None
    assert handler.get_status()["output"]["running"] is False


@pytest.mark.asyncio
async def test_stop_output_tolerates_a_failing_close(handler):
    class BrokenPort:
        def close(self):
            raise OSError("already gone")

    handler._output_port = BrokenPort()
    await handler.stop_output()
    assert handler._output_port is None


@pytest.mark.asyncio
async def test_start_output_returns_false_without_mido(handler, monkeypatch):
    monkeypatch.setattr(mh, "MIDO_AVAILABLE", False)
    assert await handler.start_output("APC") is False


# ---------------------------------------------------------------------------
# Network MIDI delegation
# ---------------------------------------------------------------------------
class StubNetworkHandler:
    def __init__(self):
        self.sent = []
        self.started = None
        self.stopped = 0

    async def start_server(self, port, name):
        self.started = (port, name)
        return True

    async def stop_server(self):
        self.stopped += 1

    def get_status(self):
        return {"available": True, "server_running": True, "port": 5004,
                "name": "DMXX", "peers": [], "peer_count": 0,
                "messages_received": 0, "messages_sent": 0}

    def get_connected_peers(self):
        return [{"name": "Studio Mac", "address": "10.0.0.9"}]

    def send_to_all(self, midi_bytes):
        self.sent.append(midi_bytes)
        return 1


def test_the_network_handler_is_created_once(handler):
    first = handler._get_or_create_network_handler()
    assert handler._get_or_create_network_handler() is first
    assert handler._network_handler is first


def test_network_messages_reach_the_main_callback(handler):
    handler._get_or_create_network_handler()

    handler._on_network_message("note_on", {"note": 60, "peer": "Studio Mac"})

    assert handler.received == [("note_on", {"note": 60, "peer": "Studio Mac"})]
    assert handler._messages_received == 1


def test_network_messages_are_captured_in_learn_mode(handler):
    handler.start_learn_mode()
    handler._on_network_message("control_change", {"control": 7})

    assert handler.get_last_learned_message() == {"control": 7}


def test_network_callback_errors_are_contained():
    h = MIDIHandler(on_message_callback=lambda *_: 1 / 0)
    h._on_network_message("note_on", {"note": 1})
    assert h._messages_received == 1


@pytest.mark.asyncio
async def test_start_network_server_delegates(handler):
    stub = StubNetworkHandler()
    handler._network_handler = stub

    assert await handler.start_network_server(5010, "Booth") is True
    assert stub.started == (5010, "Booth")

    await handler.stop_network_server()
    assert stub.stopped == 1


def test_network_status_and_peers_delegate(handler):
    handler._network_handler = StubNetworkHandler()

    assert handler.get_network_status()["server_running"] is True
    assert handler.get_network_peers() == [{"name": "Studio Mac",
                                            "address": "10.0.0.9"}]


def test_network_sends_build_the_right_bytes(handler):
    stub = StubNetworkHandler()
    handler._network_handler = stub

    assert handler.send_network_cc(1, 7, 100) == 1
    assert handler.send_network_note_on(2, 60, 127) == 1
    assert handler.send_network_note_off(3, 60) == 1

    assert stub.sent == [bytes([0xB1, 7, 100]),
                         bytes([0x92, 60, 127]),
                         bytes([0x83, 60, 0])]


def test_is_network_available_matches_the_module_flag():
    from backend import midi_network

    assert MIDIHandler.is_network_available() == midi_network.PYMIDI_AVAILABLE
