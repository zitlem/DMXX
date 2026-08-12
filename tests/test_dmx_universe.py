"""Tests for the DMXUniverse value container."""
import pytest

from backend.dmx_interface import DMXUniverse


@pytest.fixture
def universe():
    return DMXUniverse(1)


def test_new_universe_is_all_zero_and_inactive(universe):
    assert universe.universe_id == 1
    assert universe.channels == [0] * 512
    assert universe.active is False


def test_set_and_get_channel(universe):
    universe.set_channel(1, 255)
    universe.set_channel(512, 7)
    assert universe.get_channel(1) == 255
    assert universe.get_channel(512) == 7
    assert universe.channels[0] == 255
    assert universe.channels[511] == 7


@pytest.mark.parametrize("channel", [0, -1, 513, 1000])
def test_set_channel_ignores_out_of_range_channels(universe, channel):
    universe.set_channel(channel, 200)
    assert universe.channels == [0] * 512


@pytest.mark.parametrize("value", [-1, 256, 1000])
def test_set_channel_ignores_out_of_range_values(universe, value):
    universe.set_channel(5, value)
    assert universe.get_channel(5) == 0


@pytest.mark.parametrize("channel", [0, -1, 513])
def test_get_channel_out_of_range_returns_zero(universe, channel):
    assert universe.get_channel(channel) == 0


def test_set_all_clamps_values(universe):
    universe.set_all([-5, 300, 128] + [0] * 509)
    assert universe.get_channel(1) == 0
    assert universe.get_channel(2) == 255
    assert universe.get_channel(3) == 128


def test_set_all_ignores_extra_values(universe):
    universe.set_all([1] * 600)
    assert len(universe.channels) == 512
    assert all(v == 1 for v in universe.channels)


def test_set_all_shorter_list_leaves_tail_untouched(universe):
    universe.set_channel(100, 200)
    universe.set_all([9, 9, 9])
    assert universe.get_channel(1) == 9
    assert universe.get_channel(100) == 200


def test_blackout_zeroes_every_channel(universe):
    universe.set_all([255] * 512)
    universe.blackout()
    assert universe.channels == [0] * 512


def test_get_all_returns_a_copy(universe):
    snapshot = universe.get_all()
    snapshot[0] = 123
    assert universe.get_channel(1) == 0
    assert len(snapshot) == 512
