# Intonation Gauge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tachometer-style needle gauge that shows how sharp or flat the singer is against the nearest equal-tempered note.

**Architecture:** Pure note-deviation math + a stateful `IntonationTracker` (no Qt, fully unit-tested) feed a custom-painted `TunerWidget`. The widget is wired into the existing audio-frame loop in `ui/app.py`, receiving the same per-frame pitch estimate the readout already gets. Auto-nearest-note mode: no target picking.

**Tech Stack:** Python 3, numpy, PySide6 (Qt), pytest. Venv Python: `/Users/andrewtrimble/voice-trainer/venv/bin/python`.

**Spec:** `docs/superpowers/specs/2026-07-24-intonation-gauge-design.md`. Read it first.

---

## File Structure

- **Modify `audio/analysis.py`** — add `hz_to_midi`, `midi_to_nearest_note`, `nearest_note_deviation` next to the existing `hz_to_note_name` (reuse `_A4_HZ`, `_A4_MIDI`, `_NOTE_NAMES`).
- **Create `audio/intonation.py`** — `IntonationTracker`: rolling raw/center/stability state. No Qt.
- **Create `ui/tuner.py`** — `TunerWidget`: custom-painted needle gauge.
- **Modify `ui/app.py`** — instantiate the widget, add to layout, feed it per frame, theme it.
- **Create `tests/test_intonation.py`** — unit tests for the math + tracker.
- **Create `tests/test_tuner_widget.py`** — widget smoke test.

Run the full suite with: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/ -q` (baseline: 94 passed).

---

## Task 1: Note-deviation math

**Files:**
- Modify: `audio/analysis.py` (add after `hz_to_note_name`, ~line 66)
- Test: `tests/test_intonation.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_intonation.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_intonation.py -q`
Expected: FAIL with `ImportError: cannot import name 'hz_to_midi'`.

- [ ] **Step 3: Write minimal implementation**

Add to `audio/analysis.py` after `hz_to_note_name` (keep the existing `_A4_HZ`, `_A4_MIDI`, `_NOTE_NAMES`):

```python
def hz_to_midi(frequency_hz: float) -> float | None:
    """Convert Hz to a fractional MIDI note number (unrounded).

    Unlike hz_to_note_name, this does NOT round — the fractional part is what
    carries cents-accurate intonation. Returns None for non-positive input.
    """
    if frequency_hz <= 0:
        return None
    return _A4_MIDI + 12 * math.log2(frequency_hz / _A4_HZ)


def midi_to_nearest_note(midi: float) -> tuple[str, int, float]:
    """Nearest note and cents deviation for a fractional MIDI value.

    Returns (note_name, octave, cents) with cents in [-50, 50] — negative is
    flat, positive is sharp.
    """
    nearest = round(midi)
    cents = (midi - nearest) * 100.0
    return _NOTE_NAMES[nearest % 12], (nearest // 12) - 1, cents


def nearest_note_deviation(frequency_hz: float) -> tuple[str, int, float] | None:
    """Nearest note + cents deviation for a frequency in Hz, or None if <= 0."""
    midi = hz_to_midi(frequency_hz)
    if midi is None:
        return None
    return midi_to_nearest_note(midi)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_intonation.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add audio/analysis.py tests/test_intonation.py
git commit -m "feat: note-deviation math for intonation (nearest note + cents) (#21)"
```

---

## Task 2: IntonationTracker — raw + smoothed center

**Files:**
- Create: `audio/intonation.py`
- Test: `tests/test_intonation.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_intonation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_intonation.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'audio.intonation'`.

- [ ] **Step 3: Write minimal implementation**

Create `audio/intonation.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_intonation.py -q`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add audio/intonation.py tests/test_intonation.py
git commit -m "feat: IntonationTracker raw + median-smoothed center (#21)"
```

---

## Task 3: Center-stability (fade) flag

**Files:**
- Modify: `audio/intonation.py` (add `center_stable` property)
- Test: `tests/test_intonation.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_intonation.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_intonation.py::TestCenterStability -q`
Expected: FAIL with `AttributeError: 'IntonationTracker' object has no attribute 'center_stable'`.

- [ ] **Step 3: Write minimal implementation**

Add this property to `IntonationTracker` in `audio/intonation.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_intonation.py -q`
Expected: PASS (all intonation tests).

- [ ] **Step 5: Commit**

```bash
git add audio/intonation.py tests/test_intonation.py
git commit -m "feat: center-stability fade flag (vibrato stays, runs fade) (#21)"
```

---

## Task 4: TunerWidget

**Files:**
- Create: `ui/tuner.py`
- Test: `tests/test_tuner_widget.py` (create)

**Note:** the needle *aesthetics* are Andrew's eyes, not a test — the smoke test only proves it constructs, accepts updates, paints without error, and switches theme. Ornate skeuomorphic styling is a Goal 1b follow-up.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tuner_widget.py
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from ui.tuner import TunerWidget


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_tuner_smoke(qt_app):
    w = TunerWidget()
    w.resize(240, 160)
    w.update_pitch(440.0)     # in tune
    w.grab()                  # forces paintEvent offscreen
    w.update_pitch(452.0)     # sharp
    w.grab()
    w.update_pitch(None)      # silence
    w.grab()
    w.set_theme_mode("dark")
    w.grab()
    w.set_theme_mode("light")
    w.grab()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_tuner_widget.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'ui.tuner'`.

- [ ] **Step 3: Write minimal implementation**

Create `ui/tuner.py`:

```python
"""
ui/tuner.py — Tachometer-style intonation needle gauge.

Vertical needle = in tune; leans left for flat, right for sharp. During a
glissando the nearest-note target hands off, so the needle sweeps to one edge
and flies back to the other ("shifting gears") — an emergent consequence of the
+/-50-cent nearest-note invariant, not a scripted animation.

update_pitch(hz) is called once per analysis frame; pass None for silence.
"""

import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget

from audio.intonation import IntonationTracker

_MAX_CENTS = 50.0      # full needle deflection
_MAX_DEGREES = 60.0    # ...maps to +/- 60 degrees from vertical


class TunerWidget(QWidget):
    """Needle gauge showing cents deviation from the nearest note."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracker = IntonationTracker()
        self._mode = "light"
        self.setMinimumHeight(150)

    def update_pitch(self, frequency_hz: float | None) -> None:
        self._tracker.update(frequency_hz)
        self.update()  # schedule a repaint

    def set_theme_mode(self, mode: str) -> None:
        self._mode = mode
        self.update()

    # -- painting -----------------------------------------------------------
    def _colors(self) -> dict:
        if self._mode == "dark":
            return {"arc": QColor("#5c626b"), "tick": QColor("#5c626b"),
                    "needle": QColor("#e5573f"), "center": QColor("#3fbd72"),
                    "text": QColor("#e8eaed"), "green": QColor("#3fbd72"),
                    "muted": QColor("#9aa0a8")}
        return {"arc": QColor("#c9ccd1"), "tick": QColor("#a2a7ae"),
                "needle": QColor("#c0392b"), "center": QColor("#2e9e5b"),
                "text": QColor("#22252a"), "green": QColor("#2e9e5b"),
                "muted": QColor("#6b7078")}

    def _cents_to_angle_rad(self, cents: float) -> float:
        # 0 cents -> straight up; +cents (sharp) -> clockwise (right).
        clamped = max(-_MAX_CENTS, min(_MAX_CENTS, cents))
        return math.radians((clamped / _MAX_CENTS) * _MAX_DEGREES)

    def paintEvent(self, event) -> None:
        c = self._colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        pivot = QPointF(w / 2, h * 0.88)
        radius = min(w / 2.2, h * 0.78)

        # Arc + ticks (every 10 cents).
        p.setPen(QPen(c["arc"], 2))
        for cents in range(-50, 51, 10):
            a = self._cents_to_angle_rad(cents)
            outer = QPointF(pivot.x() + radius * math.sin(a),
                            pivot.y() - radius * math.cos(a))
            inner_r = radius - (14 if cents % 50 == 0 else 8)
            inner = QPointF(pivot.x() + inner_r * math.sin(a),
                            pivot.y() - inner_r * math.cos(a))
            p.setPen(QPen(c["tick"], 2 if cents % 50 == 0 else 1))
            p.drawLine(inner, outer)

        raw = self._tracker.raw

        # Calm center marker (only when the center is stable).
        center = self._tracker.center
        if center is not None and self._tracker.center_stable:
            a = self._cents_to_angle_rad(center[2])
            tip = QPointF(pivot.x() + radius * math.sin(a),
                          pivot.y() - radius * math.cos(a))
            base_r = radius - 20
            base = QPointF(pivot.x() + base_r * math.sin(a),
                           pivot.y() - base_r * math.cos(a))
            pen = QPen(c["center"], 6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(base, tip)

        # Live needle.
        cents = raw[2] if raw is not None else 0.0
        a = self._cents_to_angle_rad(cents)
        end = QPointF(pivot.x() + radius * 0.92 * math.sin(a),
                      pivot.y() - radius * 0.92 * math.cos(a))
        needle_color = c["needle"] if raw is not None else c["muted"]
        pen = QPen(needle_color, 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(pivot, end)

        # Hub.
        p.setBrush(c["text"])
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(pivot, 7, 7)

        # Note + cents readout.
        if raw is not None:
            name, octave, cents = raw
            in_tune = abs(cents) <= self._tracker.green_cents
            label = f"{name}{octave}   {cents:+.0f}¢"
            p.setPen(c["green"] if in_tune else c["text"])
        else:
            label = "—"
            p.setPen(c["muted"])
        font = QFont()
        font.setPointSize(15)
        font.setBold(True)
        p.setFont(font)
        p.drawText(0, int(h * 0.90), w, int(h * 0.12),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   label)
        p.end()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/test_tuner_widget.py -q`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add ui/tuner.py tests/test_tuner_widget.py
git commit -m "feat: TunerWidget needle gauge (raw needle + calm center) (#21)"
```

---

## Task 5: Wire the gauge into the app

**Files:**
- Modify: `ui/app.py` (imports; `_setup_ui`; theme handler; audio-frame loop)

- [ ] **Step 1: Add the import**

In `ui/app.py`, add to the `ui` imports near the top (beside the `PitchDisplayWidget` import):

```python
from ui.tuner import TunerWidget
```

- [ ] **Step 2: Instantiate and add to the layout**

In `_setup_ui`, immediately after the `self._pitch_display` is created and added (currently ~line 85-86):

```python
        self._tuner = TunerWidget()
        self._central_layout.addWidget(self._tuner)
```

- [ ] **Step 3: Theme it**

In the theme-change handler, next to `self._pitch_display.set_theme_mode(mode)` (currently ~line 108):

```python
        self._tuner.set_theme_mode(mode)
```

- [ ] **Step 4: Feed it each frame**

In the audio-frame loop, next to `self._pitch_display.update_pitch(latest_pitch)` (currently ~line 190):

```python
        self._tuner.update_pitch(latest_pitch)
```

- [ ] **Step 5: Verify the suite is still green**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python -m pytest tests/ -q`
Expected: PASS — 94 baseline + new intonation/tuner tests, zero regressions.

- [ ] **Step 6: Manual verification (Andrew)**

Run: `/Users/andrewtrimble/voice-trainer/venv/bin/python main.py`
Sing sustained notes (needle should settle near vertical, center marker steady), slide between notes (needle sweeps and flies back at each midpoint), and add vibrato (needle sways, center marker holds). This taste pass is a checkpoint, not a gate.

- [ ] **Step 7: Commit**

```bash
git add ui/app.py
git commit -m "feat: wire intonation gauge into the app window (#21)"
```

---

## Self-Review (spec coverage)

- Auto-nearest-note mode → Task 1 (`nearest_note_deviation`), used throughout. ✓
- ±50¢ → ±60° needle, emergent fly-back → Task 4 (`_cents_to_angle_rad`, `_MAX_*`); no clamping needed beyond the invariant. ✓
- Raw needle + calm center marker → Task 2 (raw/center) + Task 4 (both drawn). ✓
- Green ±8¢ → `green_cents=8.0` (Task 2), applied in Task 4 readout. ✓
- 0.5 s median smoothing in MIDI/log domain → Task 2 (`np.median` over MIDI window). ✓
- Fade on center motion, not raw spread → Task 3 (`center_stable` on center range); vibrato test proves it. ✓
- No spectrogram changes → confirmed; only `app.py` layout touched. ✓
- Testing: pure functions unit-tested (boundaries, vibrato, median outlier); widget smoke only. ✓
- Non-goals (manual target, plot overlays, ornate face, reactive smoothing) → not in any task. ✓
- Forward notes (adaptive PITCH_WINDOW, One Euro reactive smoothing, review-vs-live + #23 stored pitch series) → documented in the spec, intentionally not implemented here. ✓
