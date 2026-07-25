"""
Tests for sub-cent pitch precision in audio/analysis.py::estimate_pitch.

estimate_pitch locates the autocorrelation peak at an INTEGER sample lag
(np.argmax over the search region). Because pitch is a nonlinear function
of lag (f = sample_rate / lag), snapping to the nearest integer lag
quantizes the returned frequency — and the quantization step grows with
frequency. Near A5 (~880 Hz, period ~50 samples at 44100 Hz) one lag step
is ~34 cents, which makes cents-accurate intonation feedback impossible.

These tests synthesize pure tones whose true period falls between two
integer sample lags (never exactly on one), across the vocal range, and
require recovery to within 1 cent — well beyond what integer-lag
resolution can deliver, and only reachable with sub-sample (parabolic)
interpolation of the autocorrelation peak.

Run with: pytest tests/test_pitch_precision.py -v
"""

import math

import numpy as np

from audio.analysis import estimate_pitch


class TestPitchSubCentPrecision:
    """estimate_pitch must recover pure tones to within 1 cent."""

    SAMPLE_RATE = 44100

    # Frequencies deliberately chosen so sample_rate/freq is NOT an integer
    # (i.e. the true peak falls between two integer autocorrelation lags),
    # spanning low bass to high soprano.
    VOCAL_RANGE_FREQUENCIES = [110.0, 220.0, 440.0, 660.0, 880.0, 1046.5]

    # Number of full periods of signal to synthesize. A short, fixed sample
    # count (e.g. 4096) gives a low-frequency tone only ~10 periods to work
    # with, and edge effects in the (unwindowed) autocorrelation bias the
    # peak shape enough to blow the 1-cent budget. Scaling the buffer to a
    # fixed period count keeps that bias negligible at every frequency,
    # matching how a real capture buffer would be sized for a target
    # pitch-tracking latency.
    NUM_PERIODS = 30

    def _sine_wave(self, frequency_hz: float) -> np.ndarray:
        n_samples = int(self.NUM_PERIODS * self.SAMPLE_RATE / frequency_hz)
        t = np.linspace(0, n_samples / self.SAMPLE_RATE, n_samples, endpoint=False)
        return np.sin(2 * np.pi * frequency_hz * t).astype(np.float32)

    def _cents_error(self, estimated_hz: float, true_hz: float) -> float:
        return 1200.0 * math.log2(estimated_hz / true_hz)

    def test_recovers_vocal_range_tones_within_one_cent(self):
        """Every test tone should be recovered to < 1 cent of its true pitch."""
        for freq in self.VOCAL_RANGE_FREQUENCIES:
            samples = self._sine_wave(freq)
            pitch = estimate_pitch(samples, self.SAMPLE_RATE)
            assert pitch is not None, f"expected a pitch estimate at {freq} Hz"
            cents_error = self._cents_error(pitch, freq)
            assert abs(cents_error) < 1.0, (
                f"{freq} Hz: estimated {pitch:.4f} Hz, "
                f"{cents_error:+.3f} cents off (must be < 1.0 cent)"
            )
