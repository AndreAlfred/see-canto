# Intonation Gauge — Design (v1)

Part of #21 (intonation feedback). Precision prerequisite already shipped
(#25, sub-sample pitch via parabolic interpolation). This spec covers the
**display**: a tachometer-style needle gauge showing how sharp or flat the
singer is against the nearest equal-tempered note.

## Goal

Turn the existing pitch measurement into live intonation feedback the singer
reads at a glance. Auto-nearest-note mode: no target picking — just sing, and
the gauge shows deviation from the closest note.

## The metaphor

A car-tachometer needle:

- **In tune → needle vertical** (12 o'clock).
- **Flat → leans left. Sharp → leans right.**
- **Gliss between notes → the needle sweeps to one edge, then "flies back" to
  the opposite edge** as the nearest-note target hands off — "shifting gears."

The fly-back is **emergent, not scripted**. Because the target is always the
nearest note, deviation is mathematically confined to `[-50, +50)` cents;
crossing the midpoint between two notes flips the target, so the needle jumps
from one edge to the other on its own. The metaphor is the math.

Mapping: **±50¢ → ±60° of needle travel** (120° total sweep). No clamping is
needed — the ±50¢ invariant provides natural hard stops.

## Two indicators from one signal, split by timescale

- **Raw needle (red)** — the instantaneous pitch, updated every analysis frame
  (~43/sec). Vibrato (5–7 Hz) visibly sways it. Always moment-to-moment
  accurate; this is the melismatic-detail view.
- **Calm center marker** — a slower, smoothed indicator answering "is the note,
  as a whole, in tune / is my vibrato centered?" Fades out when the pitch is
  moving (see Center-marker stability).

Same data, two windows — which is why "both" costs barely more than "raw" and
answers a question neither could alone.

## Decided parameters

| Parameter | Value | Notes |
|---|---|---|
| Needle full deflection | ±60° at ±50¢ | Emergent hard stops |
| "In tune" (green) threshold | **±8¢** | Andrew's call |
| Center-marker smoothing window | **0.5 s** (~21 hops) | Andrew's call |
| Smoothing method | **median of MIDI values** | Log domain + outlier-robust (see below) |

## Component design

Three units, each independently testable.

### 1. Pure math — `audio/analysis.py` (no Qt)

- `hz_to_midi(hz) -> float` and `nearest_note_deviation(hz) -> (name, octave,
  cents)` with `cents ∈ [-50, +50)`.
- **Smoothing must happen in the MIDI/log domain, not Hz.** Averaging raw Hz
  over a vibrato cycle biases the center *sharp*, because a semitone up spans
  more Hz than a semitone down. We take the **median** (not mean) of recent MIDI
  values over 0.5 s — median so a single octave-error blip can't yank the marker.
- Fully unit-testable; this is where the bug-prone logic lives (the ±50¢
  wraparound at note boundaries, the log-domain smoothing, median robustness).

### 2. Widget — `ui/tuner.py` (new)

- Custom-painted `QWidget` (follows the existing custom-paint pattern in
  `ui/ornaments.py`).
- Draws: arc + tick marks, red needle (live pitch), calm center marker
  (smoothed), note name, cents number (green within ±8¢).
- Follows the existing `set_theme_mode(mode)` pattern for light/dark.
- **v1 look is functional, not ornate.** The brass-and-glass skeuomorphic
  treatment is Goal 1b taste work — a follow-up checkpoint once the mechanism
  feels right when Andrew sings to it.

### 3. Wiring — `ui/app.py`

- One call beside the existing `self._pitch_display.update_pitch(latest_pitch)`
  in the audio-frame loop (~line 190), feeding the gauge the same `latest_pitch`.
- The gauge keeps its own short rolling history of MIDI values for smoothing;
  the app just pushes each new estimate.

## Center-marker stability (fade logic)

The 0.5 s window spans several notes during a melisma, so its reading would be
meaningless there. The marker fades when the pitch is **moving** and reappears
when it **settles**.

- **Fade on center *motion*, NOT raw spread.** Vibrato inflates instantaneous
  spread but keeps the smoothed center still — and vibrato is exactly when we
  want the marker. So the stability signal is the **velocity of the smoothed
  median** (or, equivalently, how often the nearest-note target is flipping):
  vibrato → center holds → show; run → center slides → fade.
- The motion threshold is **tune-by-ear** against Andrew's real singing; the
  spec fixes the *mechanism*, not the constant.

## Testing

- **Pure functions:** real unit tests — cents at note boundaries (the ±50¢
  wraparound), log-domain smoothing correctness, median robustness to an octave
  outlier, and that a synthetic vibrato (oscillation around a fixed center)
  yields a stable smoothed center.
- **Widget:** smoke test only (constructs, accepts updates, switches theme).
  Needle *aesthetics* are Andrew's eyes, not a test.

## Non-goals (v1)

- Manual target-note picking (fixed target to drill a specific pitch).
- Spectrogram plot overlays (the plot stays untouched).
- Ornate skeuomorphic gauge face (Goal 1b follow-up).
- Reactive/adaptive smoothing (see Forward notes).

## Forward notes (not this task)

- **`PITCH_WINDOW = 4096` is squeezed from both ends.** Too *short* for low-bass
  precision (~9 cycles → the 2–4.6¢ residual from #25) and too *long* for fast
  melisma (~93 ms straddles notes in a run — sixteenths at ♩≈160 are right at
  the limit; faster is below it). This is real evidence the window should
  eventually be **adaptive** (longer when pitch is low and steady, shorter when
  moving) rather than a fixed constant. Same root cause behind two separate
  limitations.
- **Reactive smoothing (follow-up).** A One Euro Filter adapts smoothing to
  signal speed and would let the center marker track fast passages instead of
  fading. The hard part is our signal: vibrato and melisma both look "fast," so
  it must gate on center-translation (built here for the fade) vs. raw speed.
  Tune by ear — a checkpoint task once the basic gauge exists.
- **Review vs. live smoothing (for #23 memory).** When paused to review a
  passage, smoothing is pure loss — show the raw, moment-to-moment track. Design
  smoothing as a *parameter* now (so review can pass "no smoothing"); don't
  build review wiring yet (no review mode exists). When #23 lands, it should
  record the **per-frame pitch series** alongside audio — re-deriving pitch later
  at a different window size would produce different numbers than what was shown
  live, which would mislead rather than illuminate.
