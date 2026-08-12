"""Tests for the MIDI value/name conversion helpers and message builders."""
import pytest

from backend.midi_handler import midi_to_dmx, dmx_to_midi, note_to_name, name_to_note
from backend.midi_network import make_cc_bytes, make_note_on_bytes, make_note_off_bytes


# ---------------------------------------------------------------------------
# midi_to_dmx / dmx_to_midi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("midi,dmx", [(0, 0), (127, 255), (64, 128), (1, 2)])
def test_midi_to_dmx_known_values(midi, dmx):
    assert midi_to_dmx(midi) == dmx


@pytest.mark.parametrize("dmx,midi", [(0, 0), (255, 127), (128, 63), (2, 0)])
def test_dmx_to_midi_known_values(dmx, midi):
    assert dmx_to_midi(dmx) == midi


def test_midi_to_dmx_is_monotonic_and_in_range():
    previous = -1
    for value in range(128):
        result = midi_to_dmx(value)
        assert 0 <= result <= 255
        assert result >= previous
        previous = result


def test_dmx_to_midi_is_monotonic_and_in_range():
    previous = -1
    for value in range(256):
        result = dmx_to_midi(value)
        assert 0 <= result <= 127
        assert result >= previous
        previous = result


def test_round_trip_midi_dmx_midi_stays_within_one_step():
    """Scaling truncates, so a round trip may lose at most one MIDI step."""
    for value in range(128):
        assert abs(dmx_to_midi(midi_to_dmx(value)) - value) <= 1


def test_round_trip_endpoints_are_exact():
    for value in (0, 127):
        assert dmx_to_midi(midi_to_dmx(value)) == value


# ---------------------------------------------------------------------------
# note_to_name / name_to_note
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("note,name", [
    (0, "C-1"),
    (12, "C0"),
    (60, "C4"),
    (61, "C#4"),
    (69, "A4"),
    (127, "G9"),
])
def test_note_to_name(note, name):
    assert note_to_name(note) == name


@pytest.mark.parametrize("name,note", [
    ("C4", 60),
    ("c4", 60),
    (" C4 ", 60),
    ("C#4", 61),
    ("Db4", 61),
    ("A4", 69),
    ("C-1", 0),
    ("G9", 127),
])
def test_name_to_note(name, note):
    assert name_to_note(name) == note


def test_name_to_note_round_trip_for_all_notes():
    for note in range(128):
        assert name_to_note(note_to_name(note)) == note


@pytest.mark.parametrize("bad", ["", "H4", "C", "#4", "Cx", "4"])
def test_name_to_note_rejects_garbage(bad):
    assert name_to_note(bad) is None


def test_enharmonic_names_agree():
    assert name_to_note("D#3") == name_to_note("Eb3")
    assert name_to_note("A#5") == name_to_note("Bb5")


# ---------------------------------------------------------------------------
# Raw MIDI byte builders
# ---------------------------------------------------------------------------
def test_make_cc_bytes():
    assert make_cc_bytes(0, 7, 100) == bytes([0xB0, 7, 100])
    assert make_cc_bytes(15, 1, 127) == bytes([0xBF, 1, 127])


def test_make_note_on_bytes():
    assert make_note_on_bytes(0, 60, 127) == bytes([0x90, 60, 127])
    assert make_note_on_bytes(9, 36, 64) == bytes([0x99, 36, 64])


def test_make_note_off_bytes_always_zero_velocity():
    assert make_note_off_bytes(0, 60) == bytes([0x80, 60, 0])
    assert make_note_off_bytes(15, 127) == bytes([0x8F, 127, 0])


def test_message_builders_mask_out_of_range_input():
    """Channel is masked to 4 bits, data bytes to 7 bits - never a bad packet."""
    assert make_cc_bytes(16, 200, 300) == bytes([0xB0, 200 & 0x7F, 300 & 0x7F])
    assert make_note_on_bytes(99, 255, 255) == bytes([0x90 | (99 & 0x0F), 127, 127])
    for builder_bytes in (make_cc_bytes(3, 5, 7),
                          make_note_on_bytes(3, 5, 7),
                          make_note_off_bytes(3, 5)):
        assert len(builder_bytes) == 3
        assert all(0 <= b <= 255 for b in builder_bytes)
        assert all(b <= 0x7F for b in builder_bytes[1:])
