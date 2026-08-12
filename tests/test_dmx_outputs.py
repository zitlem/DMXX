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
