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


import numpy as np
from audio.intonation import IntonationTracker


def _sine(freq, seconds, sr=44100):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


class TestTrackerRawAndCenter:
    def _feed_steady(self, tracker, midi, n):
        # Feed n frames of a constant pitch (given as a MIDI value).
        hz = 440.0 * 2 ** ((midi - 69) / 12)
        for _ in range(n):
            tracker.update(hz)

    def test_raw_reports_latest_pitch(self):
        tr = IntonationTracker()
        tr.update(440.0)
        assert tr.raw == ("A", 4, pytest.approx(0.0, abs=1e-6))

    def test_none_clears_raw(self):
        tr = IntonationTracker()
        tr.update(440.0)
        tr.update(None)
        assert tr.raw is None

    def test_center_is_median_of_window(self):
        tr = IntonationTracker(window_seconds=0.5)
        self._feed_steady(tr, 69.0, tr._window_len)
        name, octave, cents = tr.center
        assert (name, octave) == ("A", 4)
        assert cents == pytest.approx(0.0, abs=1.0)

    def test_center_ignores_single_octave_outlier(self):
        # A steady A4 window with one octave-down blip: the median center
        # must barely move (robustness the mean would fail).
        tr = IntonationTracker(window_seconds=0.5)
        self._feed_steady(tr, 69.0, tr._window_len - 1)
        tr.update(220.0)  # one octave-low outlier
        _, _, cents = tr.center
        assert abs(cents) < 5.0

    def test_vibrato_center_stays_near_zero(self):
        # +/-40 cent, 6 Hz vibrato around A4 -> raw swings, center ~ 0.
        tr = IntonationTracker(window_seconds=0.5)
        sr, hop = 44100, 1024
        for k in range(tr._window_len):
            cents = 40.0 * math.sin(2 * math.pi * 6.0 * k * hop / sr)
            hz = 440.0 * 2 ** (cents / 1200.0)
            tr.update(hz)
        _, _, center_cents = tr.center
        assert abs(center_cents) < 15.0


class TestCenterStability:
    def test_warmup_is_unstable(self):
        tr = IntonationTracker()
        tr.update(440.0)
        assert tr.center_stable is False   # not enough centers yet

    def test_sustained_note_is_stable(self):
        tr = IntonationTracker()
        for _ in range(tr._window_len + tr._center_len):
            tr.update(440.0)
        assert tr.center_stable is True

    def test_vibrato_is_stable(self):
        # Vibrato moves raw pitch but not the median center -> stable.
        tr = IntonationTracker()
        sr, hop = 44100, 1024
        for k in range(tr._window_len + tr._center_len):
            cents = 40.0 * math.sin(2 * math.pi * 6.0 * k * hop / sr)
            tr.update(440.0 * 2 ** (cents / 1200.0))
        assert tr.center_stable is True

    def test_run_is_unstable(self):
        # A fast rising ramp (a melisma) slides the center -> unstable.
        tr = IntonationTracker()
        midi = 60.0
        for _ in range(tr._window_len + tr._center_len):
            hz = 440.0 * 2 ** ((midi - 69) / 12)
            tr.update(hz)
            midi += 0.4   # ~0.4 semitone per frame: clearly moving
        assert tr.center_stable is False
