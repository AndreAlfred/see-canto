"""
audio/analysis.py — Signal processing for the voice trainer.

This module contains all the math:
  - hz_to_note_name:          convert a frequency (Hz) to a note name
  - compute_spectrogram_column: compute one time-slice of the spectrogram
  - estimate_pitch:            estimate the fundamental frequency of a sound
  - estimate_formants:         estimate F1 and F2 vowel formant frequencies (LPC)

All functions are pure (no side effects, no hardware access) so they
are easy to test and reason about.
"""

import math
import numpy as np


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Standard tuning: A4 = 440 Hz, MIDI note 69
_A4_HZ = 440.0
_A4_MIDI = 69

# All 12 chromatic note names starting from C
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# ---------------------------------------------------------------------------
# Note name conversion
# ---------------------------------------------------------------------------

def hz_to_note_name(frequency_hz: float) -> tuple[str | None, int | None]:
    """Convert a frequency in Hz to a musical note name and octave number.

    Uses equal temperament tuning (A4 = 440 Hz).

    Args:
        frequency_hz: Frequency in Hz. Must be positive.

    Returns:
        (note_name, octave) tuple, e.g. ("A", 4) for 440 Hz.
        Returns (None, None) if frequency is zero or negative.

    Examples:
        >>> hz_to_note_name(440.0)
        ('A', 4)
        >>> hz_to_note_name(261.63)
        ('C', 4)
    """
    if frequency_hz <= 0:
        return None, None

    # Convert Hz to MIDI note number.
    # Formula: MIDI = 69 + 12 * log2(f / 440)
    # Each octave doubles the frequency; each semitone multiplies by 2^(1/12).
    midi = round(_A4_MIDI + 12 * math.log2(frequency_hz / _A4_HZ))

    # Extract note name (0=C, 1=C#, ... 11=B)
    note_name = _NOTE_NAMES[midi % 12]

    # Extract octave number. MIDI 0 = C-1, MIDI 12 = C0, MIDI 60 = C4.
    octave = (midi // 12) - 1

    return note_name, octave


# ---------------------------------------------------------------------------
# Spectrogram computation
# ---------------------------------------------------------------------------

def compute_spectrogram_column(
    samples: np.ndarray,
    sample_rate: int = 44100,
    n_fft: int = 2048,
) -> np.ndarray:
    """Compute one vertical column of a spectrogram from audio samples.

    Applies a Hann window to reduce spectral leakage, then computes the
    real FFT and converts to decibels.

    Args:
        samples:     Audio samples as a 1D float32 numpy array.
                     Should have length >= n_fft.
        sample_rate: Samples per second (Hz). Default: 44100.
        n_fft:       FFT size. Larger = better frequency resolution but
                     more CPU. Default: 2048 (~46 ms at 44100 Hz).

    Returns:
        1D numpy array of shape (n_fft//2 + 1,) containing the magnitude
        spectrum in decibels (dB). Higher values = louder at that frequency.

    Note:
        The frequency of bin i is: i * sample_rate / n_fft Hz.
        So bin 0 = 0 Hz (DC), bin 1 = ~21.5 Hz, ..., bin 1024 = 22050 Hz.
    """
    # Use the most recent n_fft samples (or all samples if shorter)
    chunk = samples[-n_fft:] if len(samples) >= n_fft else samples

    # Pad with zeros if shorter than n_fft
    if len(chunk) < n_fft:
        chunk = np.pad(chunk, (0, n_fft - len(chunk)))

    # Apply a Hann window to reduce "spectral leakage" — the phenomenon
    # where energy from one frequency bleeds into neighboring bins.
    window = np.hanning(n_fft)
    windowed = chunk.astype(np.float64) * window

    # Real FFT: since audio is real-valued, we only need the positive
    # frequency half. Output has n_fft//2 + 1 complex values.
    spectrum_complex = np.fft.rfft(windowed, n=n_fft)

    # Magnitude: |complex| gives amplitude at each frequency bin.
    # Normalize by n_fft so that a full-scale sine wave peaks near 0 dB.
    magnitude = np.abs(spectrum_complex) / n_fft

    # Convert to decibels. Add a tiny floor (1e-10) to avoid log(0).
    # 20 * log10 because we're working with amplitude (not power).
    spectrum_db = 20.0 * np.log10(magnitude + 1e-10)

    return spectrum_db.astype(np.float32)


# ---------------------------------------------------------------------------
# Multi-resolution spectrogram (Goal 1a Round 2)
# ---------------------------------------------------------------------------

# Frequency bands and the FFT window used for each: (band_lo_hz, band_hi_hz,
# n_fft). hi=None means "up to Nyquist". Long windows resolve fine pitch at
# the bottom of the range (a semitone at G2 is only ~5.7 Hz, needing ~0.74 s
# of signal); short windows keep time crisp at the top, where onsets and
# consonants live. The display stitches one strip per band.
MULTIRES_BANDS = (
    (0.0,    400.0, 32768),   # ~0.74 s window, ~1.35 Hz bins
    (400.0, 1600.0, 8192),    # ~0.19 s window, ~5.4 Hz bins
    (1600.0, None,  4096),    # ~93 ms window, ~10.8 Hz bins
)

# The audio history a caller must retain to feed the longest band window.
MULTIRES_MAX_WINDOW = max(n_fft for (_, _, n_fft) in MULTIRES_BANDS)


def compute_multires_column(
    samples: np.ndarray,
    sample_rate: int = 44100,
    bands: tuple = MULTIRES_BANDS,
) -> list[np.ndarray]:
    """Compute one spectrum per band, each from that band's window length.

    Every band's window ends at the same instant — the most recent sample —
    so the strips stay time-aligned. compute_spectrogram_column already
    takes the trailing n_fft samples (zero-padding if short), so each call
    just requests a different window size from the same history buffer.

    Args:
        samples:     Audio history, 1D float array. For full resolution
                     supply at least MULTIRES_MAX_WINDOW samples.
        sample_rate: Samples per second.
        bands:       (lo_hz, hi_hz, n_fft) tuples; hi of one band must equal
                     lo of the next (validated by tests, used by the display
                     to stitch non-overlapping strips).

    Returns:
        List of dB spectra, one per band, shapes (n_fft_i//2 + 1,).
    """
    return [
        compute_spectrogram_column(samples, sample_rate, n_fft)
        for (_lo, _hi, n_fft) in bands
    ]


# ---------------------------------------------------------------------------
# Pitch estimation
# ---------------------------------------------------------------------------

def estimate_pitch(
    samples: np.ndarray,
    sample_rate: int = 44100,
    fmin: float = 80.0,
    fmax: float = 1200.0,
    confidence_threshold: float = 0.3,
) -> float | None:
    """Estimate the fundamental frequency (pitch) of a voice signal.

    Uses normalized autocorrelation: a signal with a period of T samples
    will have a strong autocorrelation peak at lag T.

    Args:
        samples:              Audio samples, 1D float array.
        sample_rate:          Samples per second.
        fmin:                 Minimum detectable pitch in Hz (default: 80 Hz, low bass).
        fmax:                 Maximum detectable pitch in Hz (default: 1200 Hz, high soprano).
        confidence_threshold: Minimum normalized correlation to accept as voiced.
                              Range 0–1. Higher = stricter. Default: 0.3.

    Returns:
        Estimated frequency in Hz, or None if no clear pitch is detected.
    """
    if len(samples) < 2:
        return None

    # Convert lag range from Hz to samples.
    # A 440 Hz pitch repeats every 44100/440 ≈ 100 samples.
    min_lag = int(sample_rate / fmax)  # shortest period = highest pitch
    max_lag = int(sample_rate / fmin)  # longest period = lowest pitch

    if max_lag >= len(samples):
        max_lag = len(samples) - 1
    if min_lag >= max_lag:
        return None

    # Normalize samples to avoid scale effects on confidence
    samples_f = samples.astype(np.float64)
    samples_norm = samples_f / (np.max(np.abs(samples_f)) + 1e-10)

    # Check signal level — don't try to pitch-detect silence
    rms = np.sqrt(np.mean(samples_norm ** 2))
    if rms < 0.01:  # Threshold: ~-40 dB
        return None

    # Compute autocorrelation via convolution with reversed self.
    # autocorr[lag] measures how similar the signal is to itself shifted by `lag` samples.
    n = len(samples_norm)
    autocorr = np.correlate(samples_norm, samples_norm, mode='full')
    autocorr = autocorr[n - 1:]  # Keep only non-negative lags

    # Normalize by the zero-lag value (autocorr[0] = total signal energy).
    # This gives values in [-1, 1] regardless of signal amplitude.
    if autocorr[0] <= 0:
        return None
    autocorr = autocorr / autocorr[0]

    # Find the lag with the highest autocorrelation within our pitch range.
    search_region = autocorr[min_lag:max_lag + 1]
    if len(search_region) == 0:
        return None

    peak_offset = np.argmax(search_region)
    peak_lag = peak_offset + min_lag
    peak_confidence = autocorr[peak_lag]

    # Reject if confidence is too low — likely noise or silence.
    if peak_confidence < confidence_threshold:
        return None

    # Sub-sample refinement: peak_lag is an INTEGER, so frequency
    # (sample_rate / lag) is quantized to a discrete set of values — the
    # step between neighboring lags is small at low pitches but grows to
    # tens of cents by the top of the vocal range, which is far too coarse
    # for cents-accurate intonation feedback. Fit a parabola through the
    # peak sample and its two immediate neighbors and use its vertex as a
    # sub-sample estimate of the true peak location (standard parabolic /
    # quadratic peak interpolation).
    refined_lag = float(peak_lag)
    if 0 < peak_lag < len(autocorr) - 1:
        y_left = autocorr[peak_lag - 1]
        y0 = autocorr[peak_lag]
        y_right = autocorr[peak_lag + 1]
        denom = y_left - 2.0 * y0 + y_right
        if denom != 0:  # denom == 0 means a flat peak — no better estimate
            delta = 0.5 * (y_left - y_right) / denom
            refined_lag = peak_lag + delta
    # else: peak sits at the edge of `autocorr` with no neighbor on one
    # side — fall back to the integer lag rather than interpolate blind.

    # Convert lag (samples) back to frequency (Hz).
    return float(sample_rate / refined_lag)


# ---------------------------------------------------------------------------
# Formant estimation
# ---------------------------------------------------------------------------

def _lpc_levinson(signal: np.ndarray, order: int) -> np.ndarray:
    """Solve Yule-Walker equations via Levinson-Durbin recursion.

    Returns the LPC polynomial [1, a_1, ..., a_order] — same convention
    as scipy.signal.lpc (a[0] = 1, remaining coefficients are the filter).

    Args:
        signal: 1D float64 array (pre-emphasized audio frame).
        order:  LPC model order (number of poles).
    """
    n = len(signal)
    # Biased autocorrelation r[0 .. order]
    r = np.correlate(signal, signal, 'full')
    r = r[n - 1:n + order] / n

    if r[0] < 1e-15:
        poly = np.zeros(order + 1)
        poly[0] = 1.0
        return poly

    lp = np.zeros(order, dtype=np.float64)
    E = float(r[0])

    for m in range(order):
        # Reflection coefficient for stage m
        k = -(r[m + 1] + np.dot(lp[:m], r[m:0:-1])) / E
        # Levinson update: new coefficients from previous + reflection
        lp_prev = lp[:m].copy()
        lp[m] = k
        lp[:m] += k * lp_prev[::-1]
        # Prediction error shrinks by (1 - k^2) each stage
        E *= 1.0 - k * k
        if E <= 0.0:
            break

    poly = np.empty(order + 1, dtype=np.float64)
    poly[0] = 1.0
    poly[1:] = lp
    return poly


def estimate_formants(
    samples: np.ndarray,
    sample_rate: int = 44100,
    order: int = 14,
) -> tuple[float | None, float | None]:
    """Estimate F1 and F2 vowel formant frequencies using LPC.

    LPC (Linear Predictive Coding) models the vocal tract as an all-pole
    filter. The poles of this filter correspond to the resonance peaks
    (formants) of the vocal tract. F1 and F2 are the two lowest-frequency
    resonances and directly reflect vowel articulation:
      - F1 correlates with jaw openness (low jaw → high F1)
      - F2 correlates with tongue front/back position (front tongue → high F2)

    Args:
        samples:     Audio samples, 1D float array. Must be > order samples.
        sample_rate: Samples per second.
        order:       LPC model order. 14 is standard for voice analysis
                     (rule of thumb: order ≈ 2 + sample_rate / 1000).

    Returns:
        (f1_hz, f2_hz) tuple. Either value is None if not reliably detected.
        F1 range: 200–900 Hz. F2 range: 700–3200 Hz.
    """
    if len(samples) <= order:
        return None, None

    # Silence check — LPC on near-silent signals gives meaningless results
    rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
    if rms < 0.01:
        return None, None

    # Pre-emphasis filter: y[n] = x[n] - 0.97 * x[n-1]
    # Boosts high frequencies so formants above 1 kHz are clearly visible
    # to the LPC model. Standard in speech processing.
    pre = np.empty_like(samples, dtype=np.float64)
    pre[0] = samples[0]
    pre[1:] = samples[1:].astype(np.float64) - 0.97 * samples[:-1].astype(np.float64)

    # Fit an all-pole LPC model of the given order.
    # `a` is shape (order+1,) with a[0] = 1. The vocal tract is modelled as
    # H(z) = 1 / A(z) where A(z) = sum(a[k] * z^(-k)).
    a = _lpc_levinson(pre, order)

    # Find the poles: roots of the LPC polynomial A(z).
    roots = np.roots(a)

    # Keep only roots with non-negative imaginary part.
    # Roots come in conjugate pairs; the positive-imaginary root of each pair
    # gives a unique frequency. (Its conjugate gives the same frequency.)
    roots = roots[np.imag(roots) >= 0]

    # Convert root angles to frequencies in Hz.
    # A root at angle θ on the unit circle corresponds to frequency f = θ·sr/(2π).
    freqs = np.angle(roots) * sample_rate / (2.0 * np.pi)

    # Bandwidth of each resonance: narrow bandwidth = sharp, real formant.
    # Formula: BW = -ln(|root|) * sr / π
    # Roots well inside the unit circle (|root| << 1) have large bandwidth
    # (broad, diffuse resonances) — likely artifacts, not formants.
    bandwidths = -np.log(np.abs(roots) + 1e-12) * sample_rate / np.pi

    # Keep poles in the voice frequency range with reasonably narrow bandwidth.
    valid = (
        (freqs > 90.0) &        # above noise floor
        (freqs < 4000.0) &      # below the range we care about
        (bandwidths > 0.0) &    # stable pole (inside unit circle)
        (bandwidths < 500.0)    # narrow enough to be a real resonance
    )
    freqs = np.sort(freqs[valid])

    # Apply formant-specific range gates and take the lowest candidate in each.
    # F1: jaw/height vowel dimension (200–900 Hz)
    # F2: tongue front/back dimension (700–3200 Hz)
    f1_candidates = freqs[(freqs >= 200.0) & (freqs <= 900.0)]
    f2_candidates = freqs[(freqs >= 700.0) & (freqs <= 3200.0)]

    f1 = float(f1_candidates[0]) if len(f1_candidates) > 0 else None
    f2 = float(f2_candidates[0]) if len(f2_candidates) > 0 else None

    return f1, f2
