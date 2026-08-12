"""Tests for the passive Art-Net/sACN network monitor."""
import time

import pytest

from backend.network_monitor import (
    ArtNetMonitorProtocol,
    NetworkMonitor,
    SACNMonitorProtocol,
    SourceInfo,
)
from conftest import make_artnet_packet, make_sacn_packet


@pytest.fixture
def monitor():
    return NetworkMonitor()


class FakeWebSocket:
    def __init__(self, fail=False):
        self.sent = []
        self.accepted = False
        self.fail = fail

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        if self.fail:
            raise ConnectionError("client gone")
        self.sent.append(message)


# ---------------------------------------------------------------------------
# SourceInfo
# ---------------------------------------------------------------------------
def test_source_info_defaults():
    now = time.time()
    source = SourceInfo(ip="10.0.0.1", protocol="artnet", universe=0,
                        first_seen=now, last_seen=now)

    assert source.packet_count == 0
    assert source.last_values == [0] * 512
    assert source.changing_channels == set()


def test_source_info_is_active_when_recently_seen():
    now = time.time()
    fresh = SourceInfo("10.0.0.1", "artnet", 0, now, now)
    stale = SourceInfo("10.0.0.2", "artnet", 0, now - 100, now - 100)

    assert fresh.is_active is True
    assert stale.is_active is False


def test_packets_per_second():
    now = time.time()
    source = SourceInfo("10.0.0.1", "artnet", 0, now - 10, now, packet_count=100)
    assert 9 < source.packets_per_second < 11


def test_packets_per_second_is_zero_before_time_passes():
    future = time.time() + 100
    source = SourceInfo("10.0.0.1", "artnet", 0, future, future, packet_count=5)
    assert source.packets_per_second == 0.0


def test_to_dict_omits_values_by_default():
    now = time.time()
    source = SourceInfo("10.0.0.1", "sacn", 3, now, now, packet_count=2)
    data = source.to_dict()

    assert data["ip"] == "10.0.0.1"
    assert data["protocol"] == "sacn"
    assert data["universe"] == 3
    assert data["packet_count"] == 2
    assert "values" not in data


def test_to_dict_can_include_values():
    now = time.time()
    source = SourceInfo("10.0.0.1", "sacn", 3, now, now)
    assert source.to_dict(include_values=True)["values"] == [0] * 512


def test_to_dict_caps_changing_channels_at_20():
    now = time.time()
    source = SourceInfo("10.0.0.1", "artnet", 0, now, now,
                        changing_channels=set(range(1, 100)))
    assert len(source.to_dict()["changing_channels"]) == 20


# ---------------------------------------------------------------------------
# on_packet_received
# ---------------------------------------------------------------------------
def test_first_packet_registers_a_source(monitor):
    monitor.on_packet_received("artnet", "10.0.0.5", 0, [1] + [0] * 511)

    sources = monitor.get_all_sources()
    assert list(sources) == ["artnet:10.0.0.5:0"]
    assert sources["artnet:10.0.0.5:0"]["packet_count"] == 1


def test_repeat_packets_increment_the_counter(monitor):
    values = [0] * 512
    monitor.on_packet_received("artnet", "10.0.0.5", 0, values)
    monitor.on_packet_received("artnet", "10.0.0.5", 0, values)
    assert monitor.get_all_sources()["artnet:10.0.0.5:0"]["packet_count"] == 2


def test_sources_are_keyed_by_protocol_ip_and_universe(monitor):
    monitor.on_packet_received("artnet", "10.0.0.5", 0, [0] * 512)
    monitor.on_packet_received("artnet", "10.0.0.5", 1, [0] * 512)
    monitor.on_packet_received("sacn", "10.0.0.5", 1, [0] * 512)

    assert set(monitor.get_all_sources()) == {
        "artnet:10.0.0.5:0", "artnet:10.0.0.5:1", "sacn:10.0.0.5:1",
    }


def test_changing_channels_are_detected(monitor):
    monitor.on_packet_received("artnet", "10.0.0.5", 0, [0] * 512)

    values = [0] * 512
    values[0] = 10
    values[4] = 20
    monitor.on_packet_received("artnet", "10.0.0.5", 0, values)

    update = monitor._pending_updates["artnet:10.0.0.5:0"]
    assert sorted(update["changing_channels"]) == [1, 5]
    assert update["changed_values"] == {1: 10, 5: 20}


def test_unchanged_frames_report_no_channel_changes(monitor):
    values = [3] * 512
    monitor.on_packet_received("artnet", "10.0.0.5", 0, values)
    monitor.on_packet_received("artnet", "10.0.0.5", 0, list(values))

    update = monitor._pending_updates["artnet:10.0.0.5:0"]
    assert update["changing_channels"] == []
    assert update["changed_values"] == {}


def test_new_sacn_universe_is_added_to_the_watch_list(monitor):
    monitor.on_packet_received("sacn", "10.0.0.5", 42, [0] * 512)
    assert 42 in monitor._sacn_universes_to_monitor


def test_known_sacn_universes_are_not_duplicated(monitor):
    before = list(monitor._sacn_universes_to_monitor)
    monitor.on_packet_received("sacn", "10.0.0.5", 1, [0] * 512)
    assert monitor._sacn_universes_to_monitor == before


def test_get_source_returns_full_values(monitor):
    values = [7] * 512
    monitor.on_packet_received("artnet", "10.0.0.5", 0, values)

    detail = monitor.get_source("artnet:10.0.0.5:0")
    assert detail["values"] == values
    assert monitor.get_source("nope") is None


def test_stats_summarise_all_sources(monitor):
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    monitor.on_packet_received("artnet", "10.0.0.2", 0, [0] * 512)
    monitor.on_packet_received("sacn", "10.0.0.3", 1, [0] * 512)

    stats = monitor.get_stats()
    assert stats["total_sources"] == 3
    assert stats["active_sources"] == 3
    assert stats["total_packets"] == 3
    assert stats["artnet_sources"] == 2
    assert stats["sacn_sources"] == 1
    assert stats["connected_clients"] == 0


def test_fresh_monitor_stats_are_empty(monitor):
    assert monitor.get_stats()["total_sources"] == 0
    assert monitor.get_all_sources() == {}
    assert monitor.is_running() is False


# ---------------------------------------------------------------------------
# Monitor protocols
# ---------------------------------------------------------------------------
def test_artnet_monitor_protocol_reports_any_universe(monitor):
    protocol = ArtNetMonitorProtocol(monitor)
    protocol.datagram_received(make_artnet_packet(9, [5, 6]), ("192.168.0.9", 6454))

    source = monitor.get_all_sources()["artnet:192.168.0.9:9"]
    assert source["universe"] == 9
    assert monitor.get_source("artnet:192.168.0.9:9")["values"][:2] == [5, 6]


def test_artnet_monitor_protocol_ignores_bad_packets(monitor):
    protocol = ArtNetMonitorProtocol(monitor)
    protocol.datagram_received(b"tiny", ("1.2.3.4", 6454))
    protocol.datagram_received(b"X" * 40, ("1.2.3.4", 6454))

    bad_opcode = bytearray(make_artnet_packet(0, [1]))
    bad_opcode[8:10] = (0x00, 0x20)
    protocol.datagram_received(bytes(bad_opcode), ("1.2.3.4", 6454))

    assert monitor.get_all_sources() == {}


def test_sacn_monitor_protocol_reports_any_universe(monitor):
    protocol = SACNMonitorProtocol(monitor)
    protocol.datagram_received(make_sacn_packet(4, [1, 2]), ("192.168.0.4", 5568))
    assert "sacn:192.168.0.4:4" in monitor.get_all_sources()


def test_sacn_monitor_protocol_ignores_bad_packets(monitor):
    protocol = SACNMonitorProtocol(monitor)
    protocol.datagram_received(b"\x00" * 50, ("1.2.3.4", 5568))
    protocol.datagram_received(make_sacn_packet(1, [1], start_code=0xDD),
                               ("1.2.3.4", 5568))

    bad_id = bytearray(make_sacn_packet(1, [1]))
    bad_id[4:16] = b"Y" * 12
    protocol.datagram_received(bytes(bad_id), ("1.2.3.4", 5568))

    assert monitor.get_all_sources() == {}


def test_monitor_protocols_store_their_transport(monitor):
    sentinel = object()
    for protocol in (ArtNetMonitorProtocol(monitor), SACNMonitorProtocol(monitor)):
        protocol.connection_made(sentinel)
        assert protocol.transport is sentinel
        protocol.error_received(OSError("x"))  # logs only
        protocol.connection_lost(None)


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connect_client_sends_current_state(monitor):
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    ws = FakeWebSocket()

    await monitor.connect_client(ws)

    assert ws.accepted is True
    assert ws.sent[0]["type"] == "monitor_status"
    assert "artnet:10.0.0.1:0" in ws.sent[0]["data"]["sources"]
    assert monitor.get_stats()["connected_clients"] == 1


@pytest.mark.asyncio
async def test_disconnect_client_cleans_up(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)

    monitor.disconnect_client(ws)
    assert monitor.get_stats()["connected_clients"] == 0
    assert ws not in monitor._subscribed_sources


def test_disconnecting_an_unknown_client_is_safe(monitor):
    monitor.disconnect_client(FakeWebSocket())


@pytest.mark.asyncio
async def test_subscribe_sends_current_values(monitor):
    values = [4] * 512
    monitor.on_packet_received("artnet", "10.0.0.1", 0, values)
    ws = FakeWebSocket()
    await monitor.connect_client(ws)

    await monitor.subscribe_source(ws, "artnet:10.0.0.1:0")

    assert ws.sent[-1]["type"] == "monitor_source_values"
    assert ws.sent[-1]["data"]["values"] == values
    assert "artnet:10.0.0.1:0" in monitor._subscribed_sources[ws]


@pytest.mark.asyncio
async def test_subscribe_to_unknown_source_records_but_sends_nothing(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)
    before = len(ws.sent)

    await monitor.subscribe_source(ws, "artnet:1.1.1.1:0")

    assert monitor._subscribed_sources[ws] == {"artnet:1.1.1.1:0"}
    assert len(ws.sent) == before


@pytest.mark.asyncio
async def test_subscribe_from_unknown_client_is_ignored(monitor):
    await monitor.subscribe_source(FakeWebSocket(), "key")


@pytest.mark.asyncio
async def test_unsubscribe(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)
    await monitor.subscribe_source(ws, "key")

    monitor.unsubscribe_source(ws, "key")
    assert monitor._subscribed_sources[ws] == set()

    monitor.unsubscribe_source(FakeWebSocket(), "key")  # unknown client, no raise


@pytest.mark.asyncio
async def test_broadcast_drops_dead_clients(monitor):
    good, bad = FakeWebSocket(), FakeWebSocket(fail=True)
    await monitor.connect_client(good)
    monitor._clients.add(bad)
    monitor._subscribed_sources[bad] = set()

    await monitor._broadcast_to_clients({"type": "ping"})

    assert bad not in monitor._clients
    assert good in monitor._clients
    assert good.sent[-1] == {"type": "ping"}


@pytest.mark.asyncio
async def test_stop_on_an_unstarted_monitor_is_safe(monitor):
    await monitor.stop()
    assert monitor.is_running() is False


# ---------------------------------------------------------------------------
# Cleanup loop: timeout announcements and stale removal
# ---------------------------------------------------------------------------
async def run_one_cleanup_pass(monitor):
    """Run exactly one iteration of the cleanup loop, without waiting 5s."""
    import asyncio

    monitor._running = True

    async def stop_after_first_sleep(_delay):
        monitor._running = False

    real_sleep = asyncio.sleep
    asyncio.sleep = stop_after_first_sleep
    try:
        await monitor._cleanup_loop()
    finally:
        asyncio.sleep = real_sleep


def age_source(monitor, key, seconds):
    monitor._sources[key].last_seen = time.time() - seconds


@pytest.mark.asyncio
async def test_a_quiet_source_is_announced_once(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    age_source(monitor, "artnet:10.0.0.1:0", 10)
    ws.sent.clear()

    await run_one_cleanup_pass(monitor)
    timeouts = [m for m in ws.sent if m["type"] == "monitor_source_timeout"]
    assert len(timeouts) == 1
    assert timeouts[0]["data"]["key"] == "artnet:10.0.0.1:0"

    # Still quiet on the next pass - but no repeat announcement
    ws.sent.clear()
    await run_one_cleanup_pass(monitor)
    assert [m for m in ws.sent if m["type"] == "monitor_source_timeout"] == []


@pytest.mark.asyncio
async def test_an_active_source_is_not_announced(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    ws.sent.clear()

    await run_one_cleanup_pass(monitor)
    assert [m for m in ws.sent if m["type"] == "monitor_source_timeout"] == []


@pytest.mark.asyncio
async def test_resuming_traffic_re_arms_the_timeout(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    age_source(monitor, "artnet:10.0.0.1:0", 10)
    await run_one_cleanup_pass(monitor)
    assert monitor._sources["artnet:10.0.0.1:0"].timeout_notified is True

    # Packets resume, then it goes quiet again - a second event is expected
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [1] * 512)
    assert monitor._sources["artnet:10.0.0.1:0"].timeout_notified is False

    age_source(monitor, "artnet:10.0.0.1:0", 10)
    ws.sent.clear()
    await run_one_cleanup_pass(monitor)
    assert len([m for m in ws.sent if m["type"] == "monitor_source_timeout"]) == 1


@pytest.mark.asyncio
async def test_stale_sources_are_removed(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    age_source(monitor, "artnet:10.0.0.1:0", 40)
    ws.sent.clear()

    await run_one_cleanup_pass(monitor)

    assert monitor.get_all_sources() == {}
    removals = [m for m in ws.sent if m["type"] == "monitor_source_removed"]
    assert removals[0]["data"]["key"] == "artnet:10.0.0.1:0"


@pytest.mark.asyncio
async def test_a_stale_source_is_removed_without_a_timeout_event(monitor):
    ws = FakeWebSocket()
    await monitor.connect_client(ws)
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    age_source(monitor, "artnet:10.0.0.1:0", 40)
    ws.sent.clear()

    await run_one_cleanup_pass(monitor)
    assert [m for m in ws.sent if m["type"] == "monitor_source_timeout"] == []


def test_new_sources_start_un_notified(monitor):
    monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    assert monitor._sources["artnet:10.0.0.1:0"].timeout_notified is False
