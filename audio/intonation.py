"""
audio/intonation.py — Intonation tracking for the tuner gauge.

Turns the per-frame pitch estimate into what the needle needs:
  - raw:    deviation from the nearest note (drives the live needle),
  - center: a smoothed deviation over ~0.5 s (the calm marker),
  - center_stable: is the note sustained, or is the pitch moving?

Pure Python + numpy, no Qt, so it is fully unit-testable.
"""

from collections import deque

import numpy as np

from audio.analysis import hz_to_midi, midi_to_nearest_note


class IntonationTracker:
    """Rolling intonation state, fed one pitch estimate per analysis frame."""

    def __init__(
        self,
        sample_rate: int = 44100,
        hop_size: int = 1024,
        window_seconds: float = 0.5,
        green_cents: float = 8.0,
        motion_threshold_cents: float = 40.0,
    ) -> None:
        hops_per_second = sample_rate / hop_size
        self._window_len = max(1, round(window_seconds * hops_per_second))
        # Watch center motion over ~half the smoothing window.
        self._center_len = max(2, self._window_len // 2)
        self.green_cents = green_cents
        self.motion_threshold_cents = motion_threshold_cents
        self._midi_window: deque[float] = deque(maxlen=self._window_len)
        self._center_window: deque[float] = deque(maxlen=self._center_len)
        self._raw_midi: float | None = None

    def update(self, pitch_hz: float | None) -> None:
        """Feed one pitch estimate (or None for silence)."""
        midi = None if pitch_hz is None else hz_to_midi(pitch_hz)
        self._raw_midi = midi
        if midi is None:
            return
        self._midi_window.append(midi)
        self._center_window.append(float(np.median(self._midi_window)))

    @property
    def raw(self) -> tuple[str, int, float] | None:
        """(note, octave, cents) for the live needle, or None if no pitch."""
        if self._raw_midi is None:
            return None
        return midi_to_nearest_note(self._raw_midi)

    @property
    def center(self) -> tuple[str, int, float] | None:
        """(note, octave, cents) for the smoothed center marker, or None."""
        if not self._center_window:
            return None
        return midi_to_nearest_note(self._center_window[-1])

    @property
    def center_stable(self) -> bool:
        """True when the smoothed center is holding still (sustained note).

        Keys on the RANGE of recent centers, NOT the raw pitch spread: vibrato
        oscillates the raw pitch but leaves the median center fixed, so vibrato
        reads as stable (we want the marker then); a run slides the center and
        trips unstable (we fade the marker). Threshold is tune-by-ear.
        """
        if len(self._center_window) < self._center_len:
            return False
        span_cents = (max(self._center_window) - min(self._center_window)) * 100.0
        return span_cents <= self.motion_threshold_cents
