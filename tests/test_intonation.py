import math
import pytest
from audio.analysis import hz_to_midi, midi_to_nearest_note, nearest_note_deviation


class TestNoteMath:
    def test_hz_to_midi_reference_pitches(self):
        assert hz_to_midi(440.0) == pytest.approx(69.0)
        assert hz_to_midi(880.0) == pytest.approx(81.0)
        assert hz_to_midi(220.0) == pytest.approx(57.0)

    def test_hz_to_midi_nonpositive_returns_none(self):
        assert hz_to_midi(0.0) is None
        assert hz_to_midi(-5.0) is None

    def test_midi_to_nearest_note_in_tune(self):
        assert midi_to_nearest_note(69.0) == ("A", 4, pytest.approx(0.0))

    def test_midi_to_nearest_note_sharp_and_flat(self):
        name, octave, cents = midi_to_nearest_note(69.25)   # 25 cents sharp of A4
        assert (name, octave) == ("A", 4)
        assert cents == pytest.approx(25.0)
        name, octave, cents = midi_to_nearest_note(68.75)   # 25 cents flat of A4
        assert (name, octave) == ("A", 4)
        assert cents == pytest.approx(-25.0)

    def test_cents_stay_within_half_semitone(self):
        # Sweep across a full semitone; cents must never leave [-50, 50].
        for k in range(0, 101):
            midi = 69.0 + k / 100.0
            _, _, cents = midi_to_nearest_note(midi)
            assert -50.0 <= cents <= 50.0

    def test_nearest_note_deviation_from_hz(self):
        assert nearest_note_deviation(440.0) == ("A", 4, pytest.approx(0.0, abs=1e-9))
        assert nearest_note_deviation(0.0) is None
