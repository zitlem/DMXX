"""Tests for DMX input packet parsing, filtering and the input factory."""
import struct

import pytest

from backend import dmx_inputs
from backend.dmx_inputs import (
    ArtNetInput,
    ArtNetProtocol,
    MIDIInput,
    SACNInput,
    SACNProtocol,
    create_input,
    get_available_input_protocols,
)
from conftest import make_artnet_packet, make_sacn_packet


class Recorder:
    """Callback stand-in that records (universe_id, values) calls."""

    def __init__(self):
        self.calls = []

    def __call__(self, universe_id, values):
        self.calls.append((universe_id, list(values)))

    @property
    def last(self):
        return self.calls[-1]


@pytest.fixture
def recorder():
    return Recorder()


# ---------------------------------------------------------------------------
# Art-Net parsing
# ---------------------------------------------------------------------------
@pytest.fixture
def artnet(recorder):
    inp = ArtNetInput(1, {}, recorder)
    inp._artnet_universe = 0
    return inp


def test_artnet_parses_valid_packet(artnet, recorder):
    artnet._parse_artnet_packet(make_artnet_packet(0, [10, 20, 30]))

    universe_id, values = recorder.last
    assert universe_id == 1
    assert len(values) == 512
    assert values[:3] == [10, 20, 30]
    assert values[3:] == [0] * 509
    assert artnet._packets_received == 1


def test_artnet_tracks_sequence_number(artnet):
    artnet._parse_artnet_packet(make_artnet_packet(0, [1], sequence=42))
    assert artnet._last_sequence == 42


def test_artnet_full_512_channel_packet(artnet, recorder):
    values = [i % 256 for i in range(512)]
    artnet._parse_artnet_packet(make_artnet_packet(0, values))
    assert recorder.last[1] == values


def test_artnet_truncates_oversized_payload(artnet, recorder):
    packet = make_artnet_packet(0, [7] * 600, length=600)
    artnet._parse_artnet_packet(packet)
    assert len(recorder.last[1]) == 512


def test_artnet_ignores_short_packet(artnet, recorder):
    artnet._parse_artnet_packet(b"Art-Net\x00short")
    assert recorder.calls == []
    assert artnet._packets_received == 0


def test_artnet_ignores_bad_header(artnet, recorder):
    packet = bytearray(make_artnet_packet(0, [1, 2, 3]))
    packet[:8] = b"NotArt\x00\x00"
    artnet._parse_artnet_packet(bytes(packet))
    assert recorder.calls == []


def test_artnet_ignores_non_dmx_opcode(artnet, recorder):
    packet = bytearray(make_artnet_packet(0, [1, 2, 3]))
    packet[8:10] = struct.pack("<H", 0x2000)  # OpPoll
    artnet._parse_artnet_packet(bytes(packet))
    assert recorder.calls == []


def test_artnet_ignores_other_universes(artnet, recorder):
    artnet._parse_artnet_packet(make_artnet_packet(5, [1, 2, 3]))
    assert recorder.calls == []
    assert artnet._packets_received == 0


def test_artnet_accepts_configured_universe(recorder):
    inp = ArtNetInput(1, {}, recorder)
    inp._artnet_universe = 5
    inp._parse_artnet_packet(make_artnet_packet(5, [99]))
    assert recorder.last[1][0] == 99


def test_artnet_survives_missing_callback():
    inp = ArtNetInput(1, {}, None)
    inp._artnet_universe = 0
    inp._parse_artnet_packet(make_artnet_packet(0, [1]))
    assert inp._packets_received == 1


def test_artnet_status_reports_config_and_counters(recorder):
    inp = ArtNetInput(1, {"bind_ip": "10.0.0.1", "port": 6455}, recorder)
    inp._artnet_universe = 3
    inp._parse_artnet_packet(make_artnet_packet(3, [1]))

    status = inp.get_status()
    assert status["protocol"] == "artnet_input"
    assert status["running"] is False
    assert status["bind_ip"] == "10.0.0.1"
    assert status["port"] == 6455
    assert status["artnet_universe"] == 3
    assert status["packets_received"] == 1


# ---------------------------------------------------------------------------
# Art-Net source filtering (protocol layer)
# ---------------------------------------------------------------------------
def test_artnet_protocol_whitelist_blocks_other_sources(artnet, recorder):
    artnet._source_ip_filter = "192.168.1.50"
    protocol = ArtNetProtocol(artnet)

    protocol.datagram_received(make_artnet_packet(0, [1]), ("192.168.1.99", 6454))
    assert recorder.calls == []

    protocol.datagram_received(make_artnet_packet(0, [1]), ("192.168.1.50", 6454))
    assert len(recorder.calls) == 1


def test_artnet_protocol_blacklist_blocks_named_source(artnet, recorder):
    artnet._ignore_ip_filter = "192.168.1.50"
    protocol = ArtNetProtocol(artnet)

    protocol.datagram_received(make_artnet_packet(0, [1]), ("192.168.1.50", 6454))
    assert recorder.calls == []

    protocol.datagram_received(make_artnet_packet(0, [1]), ("192.168.1.51", 6454))
    assert len(recorder.calls) == 1


def test_artnet_protocol_ignore_self_blocks_local_ips(artnet, recorder):
    artnet._ignore_self = True
    protocol = ArtNetProtocol(artnet)

    protocol.datagram_received(make_artnet_packet(0, [1]), ("127.0.0.1", 6454))
    assert recorder.calls == []

    protocol.datagram_received(make_artnet_packet(0, [1]), ("203.0.113.7", 6454))
    assert len(recorder.calls) == 1


def test_artnet_protocol_without_filters_accepts_everything(artnet, recorder):
    protocol = ArtNetProtocol(artnet)
    protocol.datagram_received(make_artnet_packet(0, [1]), ("127.0.0.1", 6454))
    protocol.datagram_received(make_artnet_packet(0, [2]), ("8.8.8.8", 6454))
    assert len(recorder.calls) == 2


def test_artnet_protocol_connection_made_stores_transport(artnet):
    protocol = ArtNetProtocol(artnet)
    sentinel = object()
    protocol.connection_made(sentinel)
    assert protocol.transport is sentinel


# ---------------------------------------------------------------------------
# sACN parsing
# ---------------------------------------------------------------------------
@pytest.fixture
def sacn(recorder):
    inp = SACNInput(1, {}, recorder)
    inp._sacn_universe = 1
    return inp


def test_sacn_parses_valid_packet(sacn, recorder):
    sacn._parse_sacn_packet(make_sacn_packet(1, [11, 22, 33]))

    universe_id, values = recorder.last
    assert universe_id == 1
    assert len(values) == 512
    assert values[:3] == [11, 22, 33]
    assert sacn._packets_received == 1


def test_sacn_ignores_short_packet(sacn, recorder):
    sacn._parse_sacn_packet(b"\x00" * 100)
    assert recorder.calls == []


def test_sacn_ignores_bad_acn_identifier(sacn, recorder):
    packet = bytearray(make_sacn_packet(1, [1]))
    packet[4:16] = b"X" * 12
    sacn._parse_sacn_packet(bytes(packet))
    assert recorder.calls == []


def test_sacn_ignores_other_universes(sacn, recorder):
    sacn._parse_sacn_packet(make_sacn_packet(7, [1]))
    assert recorder.calls == []


def test_sacn_ignores_non_zero_start_code(sacn, recorder):
    sacn._parse_sacn_packet(make_sacn_packet(1, [1], start_code=0xDD))
    assert recorder.calls == []


def test_sacn_truncates_oversized_payload(sacn, recorder):
    sacn._parse_sacn_packet(make_sacn_packet(1, [3] * 600))
    assert len(recorder.last[1]) == 512


def test_sacn_status(recorder):
    inp = SACNInput(2, {"multicast": False}, recorder)
    inp._sacn_universe = 9
    status = inp.get_status()
    assert status["protocol"] == "sacn_input"
    assert status["sacn_universe"] == 9
    assert status["multicast"] is False
    assert status["packets_received"] == 0


def test_sacn_protocol_filters_mirror_artnet(sacn, recorder):
    sacn._source_ip_filter = "10.1.1.1"
    protocol = SACNProtocol(sacn)
    protocol.datagram_received(make_sacn_packet(1, [1]), ("10.1.1.2", 5568))
    assert recorder.calls == []
    protocol.datagram_received(make_sacn_packet(1, [1]), ("10.1.1.1", 5568))
    assert len(recorder.calls) == 1


# ---------------------------------------------------------------------------
# MIDIInput
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_midi_input_lifecycle(recorder):
    inp = MIDIInput(1, {"device_name": "LaunchControl"}, recorder)
    assert inp.running is False
    assert inp.get_device_name() == "LaunchControl"

    assert await inp.start() is True
    assert inp.running is True
    assert inp.get_status() == {
        "type": "midi",
        "universe_id": 1,
        "device_name": "LaunchControl",
        "running": True,
    }

    await inp.stop()
    assert inp.running is False


def test_midi_input_set_channel_emits_full_frame(recorder):
    inp = MIDIInput(1, {}, recorder)
    inp.set_channel(3, 200)

    universe_id, values = recorder.last
    assert universe_id == 1
    assert len(values) == 512
    assert values[2] == 200


def test_midi_input_accumulates_channel_state(recorder):
    inp = MIDIInput(1, {}, recorder)
    inp.set_channel(1, 10)
    inp.set_channel(2, 20)

    values = recorder.last[1]
    assert values[0] == 10
    assert values[1] == 20


def test_midi_input_emits_a_copy_each_time(recorder):
    inp = MIDIInput(1, {}, recorder)
    inp.set_channel(1, 10)
    inp.set_channel(1, 20)
    assert recorder.calls[0][1][0] == 10
    assert recorder.calls[1][1][0] == 20


@pytest.mark.parametrize("channel", [0, -1, 513])
def test_midi_input_ignores_out_of_range_channels(recorder, channel):
    inp = MIDIInput(1, {}, recorder)
    inp.set_channel(channel, 255)
    assert recorder.calls == []


def test_midi_input_default_device_name_is_empty(recorder):
    assert MIDIInput(1, {}, recorder).get_device_name() == ""


# ---------------------------------------------------------------------------
# create_input factory
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("input_type,expected", [
    ("artnet_input", ArtNetInput),
    ("artnet", ArtNetInput),
    ("ARTNET", ArtNetInput),
    ("sacn_input", SACNInput),
    ("sacn", SACNInput),
    ("e131", SACNInput),
    ("midi_input", MIDIInput),
    ("midi", MIDIInput),
])
def test_create_input_types(recorder, input_type, expected):
    assert isinstance(create_input(1, input_type, {}, recorder), expected)


@pytest.mark.parametrize("input_type", ["none", "", None, "bogus"])
def test_create_input_returns_none_for_disabled_or_unknown(recorder, input_type):
    assert create_input(1, input_type, {}, recorder) is None


def test_create_input_wires_universe_config_and_callback(recorder):
    inp = create_input(4, "artnet", {"port": 1234}, recorder)
    assert inp.universe_id == 4
    assert inp.config == {"port": 1234}
    assert inp.callback is recorder


# ---------------------------------------------------------------------------
# Input protocol catalogue & local IP detection
# ---------------------------------------------------------------------------
def test_get_available_input_protocols_shape():
    protocols = get_available_input_protocols()
    assert [p["id"] for p in protocols] == [
        "none", "artnet_input", "sacn_input", "midi_input"
    ]
    for protocol in protocols:
        assert protocol["available"] is True
        assert isinstance(protocol["config_schema"], dict)


def test_artnet_input_protocol_exposes_filter_options():
    artnet = next(p for p in get_available_input_protocols()
                  if p["id"] == "artnet_input")
    assert {"bind_ip", "port", "artnet_universe", "source_ip",
            "ignore_ip", "ignore_self"} <= set(artnet["config_schema"])


def test_local_ips_include_loopback():
    assert "127.0.0.1" in dmx_inputs.LOCAL_IPS
    assert "::1" in dmx_inputs.LOCAL_IPS


def test_get_local_ips_never_raises():
    ips = dmx_inputs._get_local_ips()
    assert isinstance(ips, set)
    assert "127.0.0.1" in ips
