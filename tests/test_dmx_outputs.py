"""Tests for the DMX output protocol layer."""
import pytest

from backend import dmx_outputs
from backend.dmx_outputs import (
    ArtNetOutput,
    MockOutput,
    SACNOutput,
    create_output,
    get_available_protocols,
)


# ---------------------------------------------------------------------------
# MockOutput
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_output_lifecycle():
    out = MockOutput(1, {})
    assert out.running is False

    assert await out.start() is True
    assert out.running is True

    await out.stop()
    assert out.running is False


@pytest.mark.asyncio
async def test_mock_output_records_last_send_when_running():
    out = MockOutput(1, {})
    await out.start()

    values = [0] * 512
    values[0] = 255
    await out.send_dmx(values)

    assert out._last_send == values
    assert out.get_status() == {"protocol": "mock", "running": True, "last_send": True}


@pytest.mark.asyncio
async def test_mock_output_drops_sends_when_stopped():
    out = MockOutput(2, {})
    await out.send_dmx([1] * 512)
    assert out._last_send is None
    assert out.get_status()["last_send"] is False


@pytest.mark.asyncio
async def test_mock_output_debug_log_level_does_not_break_send():
    out = MockOutput(1, {"log_level": "debug"})
    await out.start()
    await out.send_dmx([5] * 512)
    assert out._last_send is not None


# ---------------------------------------------------------------------------
# create_output factory
# ---------------------------------------------------------------------------
def test_create_output_mock():
    assert isinstance(create_output(1, "mock", {}), MockOutput)


def test_create_output_unknown_type_falls_back_to_mock():
    assert isinstance(create_output(1, "definitely-not-a-protocol", {}), MockOutput)


def test_create_output_none_type_falls_back_to_mock():
    assert isinstance(create_output(1, None, {}), MockOutput)


def test_create_output_is_case_insensitive():
    assert isinstance(create_output(1, "MOCK", {}), MockOutput)


@pytest.mark.parametrize("device_type,expected", [
    ("artnet", ArtNetOutput),
    ("sacn", SACNOutput),
    ("e131", SACNOutput),
])
def test_create_output_network_protocols(device_type, expected):
    out = create_output(1, device_type, {})
    if dmx_outputs.PYARTNET_AVAILABLE:
        assert isinstance(out, expected)
    else:
        assert isinstance(out, MockOutput)


def test_create_output_falls_back_to_mock_without_pyartnet(monkeypatch):
    monkeypatch.setattr(dmx_outputs, "PYARTNET_AVAILABLE", False)
    assert isinstance(dmx_outputs.create_output(1, "artnet", {}), MockOutput)
    assert isinstance(dmx_outputs.create_output(1, "sacn", {}), MockOutput)


def test_create_output_passes_config_through():
    out = create_output(3, "mock", {"log_level": "debug"})
    assert out.universe_id == 3
    assert out.config == {"log_level": "debug"}


# ---------------------------------------------------------------------------
# Art-Net / sACN status + guards (no sockets involved)
# ---------------------------------------------------------------------------
def test_artnet_status_defaults():
    status = ArtNetOutput(3, {}).get_status()
    assert status["protocol"] == "artnet"
    assert status["running"] is False
    assert status["ip"] == "255.255.255.255"
    assert status["port"] == 6454
    assert status["artnet_universe"] == 2  # Art-Net is 0-indexed


def test_artnet_status_honours_config():
    status = ArtNetOutput(1, {"ip": "10.0.0.5", "port": 6455, "universe": 12}).get_status()
    assert status["ip"] == "10.0.0.5"
    assert status["port"] == 6455
    assert status["artnet_universe"] == 12


def test_sacn_status_defaults():
    status = SACNOutput(4, {}).get_status()
    assert status["protocol"] == "sacn"
    assert status["running"] is False
    assert status["sacn_universe"] == 4  # sACN is 1-indexed
    assert status["multicast"] is True


@pytest.mark.asyncio
async def test_artnet_start_returns_false_without_pyartnet(monkeypatch):
    monkeypatch.setattr(dmx_outputs, "PYARTNET_AVAILABLE", False)
    out = ArtNetOutput(1, {})
    assert await out.start() is False
    assert out.running is False


@pytest.mark.asyncio
async def test_sacn_start_returns_false_without_pyartnet(monkeypatch):
    monkeypatch.setattr(dmx_outputs, "PYARTNET_AVAILABLE", False)
    out = SACNOutput(1, {})
    assert await out.start() is False


@pytest.mark.asyncio
async def test_stopping_a_never_started_output_is_a_noop():
    for out in (ArtNetOutput(1, {}), SACNOutput(1, {})):
        await out.stop()
        assert out.running is False


@pytest.mark.asyncio
async def test_send_on_stopped_network_output_is_ignored():
    for out in (ArtNetOutput(1, {}), SACNOutput(1, {})):
        await out.send_dmx([255] * 512)  # must not raise


# ---------------------------------------------------------------------------
# Protocol catalogue
# ---------------------------------------------------------------------------
def test_get_available_protocols_shape():
    protocols = get_available_protocols()
    ids = [p["id"] for p in protocols]
    assert ids == ["artnet", "sacn", "mock"]

    for protocol in protocols:
        assert {"id", "name", "available", "config_schema"} <= set(protocol)
        assert isinstance(protocol["available"], bool)
        for field in protocol["config_schema"].values():
            assert "type" in field and "default" in field and "description" in field


def test_mock_protocol_is_always_available():
    mock = next(p for p in get_available_protocols() if p["id"] == "mock")
    assert mock["available"] is True


def test_network_protocol_availability_tracks_pyartnet():
    for protocol in get_available_protocols():
        if protocol["id"] in ("artnet", "sacn"):
            assert protocol["available"] == dmx_outputs.PYARTNET_AVAILABLE


# ---------------------------------------------------------------------------
# Shared node lifecycle
#
# Art-Net and sACN outputs share one pyartnet node per destination and
# reference-count it. These tests drive that bookkeeping with a fake node, so
# no socket is opened.
# ---------------------------------------------------------------------------
class FakeChannel:
    def __init__(self):
        self.values = None

    def set_values(self, values):
        self.values = values


class FakeUniverse:
    def add_channel(self, start, width):
        return FakeChannel()


class FakeNode:
    """Stands in for ArtNetNode / SacnNode."""

    created = 0
    closed = 0
    fail_add_universe = False

    def __init__(self):
        self.entered = False

    @classmethod
    def reset(cls):
        cls.created = cls.closed = 0
        cls.fail_add_universe = False

    @classmethod
    def create(cls, *args, **kwargs):
        cls.created += 1
        return cls()

    create_multicast = create

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *exc):
        type(self).closed += 1

    def add_universe(self, universe):
        if type(self).fail_add_universe:
            raise RuntimeError("duplicate universe")
        return FakeUniverse()


@pytest.fixture
def fake_node(monkeypatch):
    """Install FakeNode for both output classes and isolate their shared state."""
    FakeNode.reset()
    monkeypatch.setattr(dmx_outputs, "PYARTNET_AVAILABLE", True)
    monkeypatch.setattr(dmx_outputs, "ArtNetNode", FakeNode, raising=False)
    monkeypatch.setattr(dmx_outputs, "SacnNode", FakeNode, raising=False)
    for cls in (ArtNetOutput, SACNOutput):
        monkeypatch.setattr(cls, "_shared_nodes", {})
        monkeypatch.setattr(cls, "_node_refs", {})
    return FakeNode


@pytest.mark.asyncio
async def test_outputs_to_the_same_destination_share_one_node(fake_node):
    a = ArtNetOutput(1, {"ip": "10.0.0.1"})
    b = ArtNetOutput(2, {"ip": "10.0.0.1"})

    assert await a.start() is True
    assert await b.start() is True

    assert fake_node.created == 1
    assert ArtNetOutput._node_refs == {"artnet:10.0.0.1:6454": 2}


@pytest.mark.asyncio
async def test_different_destinations_get_their_own_node(fake_node):
    await ArtNetOutput(1, {"ip": "10.0.0.1"}).start()
    await ArtNetOutput(2, {"ip": "10.0.0.2"}).start()

    assert fake_node.created == 2
    assert len(ArtNetOutput._shared_nodes) == 2


@pytest.mark.asyncio
async def test_the_node_closes_only_when_the_last_output_stops(fake_node):
    a = ArtNetOutput(1, {"ip": "10.0.0.1"})
    b = ArtNetOutput(2, {"ip": "10.0.0.1"})
    await a.start()
    await b.start()

    await a.stop()
    assert fake_node.closed == 0                     # b is still using it
    assert ArtNetOutput._node_refs == {"artnet:10.0.0.1:6454": 1}

    await b.stop()
    assert fake_node.closed == 1
    assert ArtNetOutput._shared_nodes == {}
    assert ArtNetOutput._node_refs == {}


@pytest.mark.asyncio
async def test_a_failed_start_returns_its_reference(fake_node):
    """Regression: the refcount used to leak, so the node was never closed."""
    owner = ArtNetOutput(1, {"ip": "10.0.0.1"})
    await owner.start()

    fake_node.fail_add_universe = True
    failed = ArtNetOutput(2, {"ip": "10.0.0.1"})
    assert await failed.start() is False
    fake_node.fail_add_universe = False

    assert ArtNetOutput._node_refs == {"artnet:10.0.0.1:6454": 1}

    await owner.stop()
    assert fake_node.closed == 1
    assert ArtNetOutput._shared_nodes == {}


@pytest.mark.asyncio
async def test_a_failed_first_start_leaves_no_shared_state(fake_node):
    fake_node.fail_add_universe = True
    out = ArtNetOutput(1, {"ip": "10.0.0.1"})

    assert await out.start() is False

    assert ArtNetOutput._shared_nodes == {}
    assert ArtNetOutput._node_refs == {}
    assert fake_node.closed == 1  # the node it opened was closed again


@pytest.mark.asyncio
async def test_a_failed_start_leaves_the_output_stopped(fake_node):
    fake_node.fail_add_universe = True
    out = ArtNetOutput(1, {"ip": "10.0.0.1"})
    await out.start()

    assert out.running is False
    await out.send_dmx([255] * 512)   # must not raise
    await out.stop()                  # must not raise


@pytest.mark.asyncio
async def test_a_started_output_sends_to_its_channel(fake_node):
    out = ArtNetOutput(1, {"ip": "10.0.0.1"})
    await out.start()

    values = [7] * 512
    await out.send_dmx(values)
    assert out._channel.values == values


@pytest.mark.asyncio
async def test_sacn_shares_and_releases_nodes_the_same_way(fake_node):
    a = SACNOutput(1, {"multicast": True})
    b = SACNOutput(2, {"multicast": True})
    await a.start()
    await b.start()

    assert SACNOutput._node_refs == {"sacn:multicast": 2}

    await a.stop()
    assert fake_node.closed == 0
    await b.stop()
    assert fake_node.closed == 1
    assert SACNOutput._shared_nodes == {}


@pytest.mark.asyncio
async def test_sacn_failed_start_returns_its_reference(fake_node):
    owner = SACNOutput(1, {"multicast": True})
    await owner.start()

    fake_node.fail_add_universe = True
    assert await SACNOutput(2, {"multicast": True}).start() is False
    fake_node.fail_add_universe = False

    assert SACNOutput._node_refs == {"sacn:multicast": 1}
    await owner.stop()
    assert SACNOutput._shared_nodes == {}


@pytest.mark.asyncio
async def test_sacn_unicast_targets_are_keyed_separately(fake_node):
    await SACNOutput(1, {"multicast": False, "unicast_ip": "10.0.0.1"}).start()
    await SACNOutput(2, {"multicast": False, "unicast_ip": "10.0.0.2"}).start()

    assert set(SACNOutput._shared_nodes) == {"sacn:unicast:10.0.0.1",
                                             "sacn:unicast:10.0.0.2"}


@pytest.mark.asyncio
async def test_stopping_twice_does_not_double_release(fake_node):
    a = ArtNetOutput(1, {"ip": "10.0.0.1"})
    b = ArtNetOutput(2, {"ip": "10.0.0.1"})
    await a.start()
    await b.start()

    await a.stop()
    await a.stop()          # second call is a no-op: not running any more

    assert ArtNetOutput._node_refs == {"artnet:10.0.0.1:6454": 1}
    assert fake_node.closed == 0
