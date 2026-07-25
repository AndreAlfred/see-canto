# Voice Trainer — Master Plan

The single source of truth for what we're building and why. This is the map;
granular, trackable work lives in **GitHub Issues**. See also
[CLAUDE.md](CLAUDE.md) (working conventions) and [Lessons.md](Lessons.md)
(mistakes log).

## Vision
Give classical singers real-time feedback on their voice that is both **beautiful
to use** and **pedagogically prescriptive** — not just showing *what* the voice is
doing (pitch, resonance, formants), but guiding *how* to adjust it, grounded in
real bel canto vocal acoustics. A free, open desktop tool that grows incrementally
from a solid spectrogram core.

---

## ▶ Next up — start a work session here
**Goal 1a (fast, high-res spectrogram) is DONE — both litmus targets MET** and
regression-guarded, shipped through the benchmark harness (#15), the Round 1
resampling-matrix rewrite, and Round 2 multi-resolution analysis (#18). The clean
autonomous loop is finished.

**Next arc — turn the app from a passive mirror into a practice tool.** Direction
decided (2026-07-24): ship **intonation → ring → memory**, in that order. First,
a tiny warm-up — **a live taste pass on the new pipeline** (#18's only open box):
sing low sustained notes and confirm the multi-res spectrogram reads crisp, not
noisy — visual-only, not a loop gate. Then the three ships:

1. **Intonation feedback** (#21) — a target-note line + live cents-deviation readout
   ("+8¢ sharp of G4"). Today the pitch display shows note + Hz only; there is no
   concept of *in-tune-ness* anywhere in the code. This is the most-used feedback
   in a practice room **and** the safe on-ramp to Goal 2: it's the prescriptive
   interaction (draw a target → compare live → nudge) on a domain where correctness
   is free (G4 is 392 Hz — no vocal-science debate). *Precision first:* the
   autocorrelation estimator resolves only to integer lags (~34¢/step at A5), so add
   sub-sample (parabolic) peak interpolation — a clean loop, litmus: recover a
   synthetic tone to <1¢. The target-line + cue widget it builds is later reused by
   the formant target-zone overlay (#10).
2. **Ring meter** (#22) — quantify Singer's-Formant energy (2–3.5 kHz band vs. total) as a
   single "ring / chiaroscuro" readout. Today that band is only a visual highlight
   (`singers_formant_visible` toggle); turning it into a number gives real resonance
   feedback — prescriptive-*lite*, no chart required. Machine-measurable (band-energy
   ratio / spectral tilt); mild genre caveat to confirm with Andrew.
3. **Memory** (#23) — the app currently has none: sung audio scrolls off and is gone. Start
   small (freeze / scroll-back the last N seconds to inspect), then grow toward
   session record + playback and reference overlays (compare a take to a target).
   Promotes the "Session recording + playback" / "Reference overlays" backlog items.
   Turns the live toy into something you practice *against*.

**Deliberately back-burnered:** vibrato rate + extent. A clean-loop feature and a
good future pick, but not in this arc.

**Full prescription (Goal 2 proper)** — formant target zones (#10), live
vowel-modification cues (#11), voice-type profiles (#12) — follows once intonation
has proven the target/cue UX and #8 has hardened F1/F2 up high (see Goal 2 below).

**Goal 1a litmus record** — kept as the regression baseline; how it was won:

1. ~~Build the benchmark harness~~ — done. Run with
   `python -m tools.benchmark_spectrogram --bins 2048 --duration 30`.
2. **Baseline measured — the litmus is already met at current settings.**
   Harness (2026-07-08, offscreen Qt): at 2048 bins / 30 s synthetic audio,
   ~97 FPS, ~0 ms steady-state latency. Short warm-up runs spike to ~127 ms in
   the first second (cold caches / Qt font init), but steady state is clean.
   **Human confirmation (2026-07-08):** Andrew ran the live app and sang/clapped
   into it — real mic, real screen compositing, the two stages the harness
   can't see — and it "feels nice and fast," no perceptible glass-to-glass lag.
   The synthetic proxy and the human test agree, so the harness is trustworthy
   as a self-verifiable litmus and regression guard. **Open question from before
   — "does the offscreen harness capture real glass-to-glass cost?" — resolved:
   close enough; the human test corroborates it.**
3. **Round 1 resolution work landed** (see
   `docs/superpowers/specs/2026-07-09-spectrogram-resolution-design.md`):
   Gaussian blur removed, log-resampling matrix in its place, FFT 2048→4096
   with hop held at 1024 (75% overlap, scroll rate preserved). Litmus
   re-verified at the new config (2026-07-09, offscreen Qt):
   `columns=1288 wall=19.73s fps=65.3 latency: mean=0.0ms p95=0.0ms max=0.0ms`
   — PASS with 2× headroom. A new two-tone separability test guards real
   frequency resolution as a machine-checkable regression.
4. **Resolution is now machine-measurable — the "eye chart" (2026-07-09).**
   Andrew flagged (correctly) that judging crispness by eye is confounded by
   display settings (dB floor/ceiling) and can't anchor a loop. The harness now
   measures resolution directly: `python -m tools.benchmark_spectrogram
   --resolution --n-fft 4096` reports the smallest two-tone gap (in cents) that
   renders as two distinct ridges, at musically spread centers. Measured
   (old → Round 1): C3 800→600¢, G3 600→300¢, C4 600→300¢, A4 300→200¢,
   A5 200→100¢, A6 100→50¢, A7 50→25¢; G2 not separable in either. Round 1
   roughly halved the gaps, **but the low-mid voice (G2–C4) still can't show
   2–3-semitone intervals as separate** — that is the metric-backed case for
   **Round 2: constant-Q / multi-resolution analysis** (long windows for low
   notes, short for high). Proposed Round 2 litmus, pending Andrew's sign-off:
   **≤100 cents (one semitone) separable at every tested center G2–A7, while
   holding ≥30 FPS / ≤120 ms p95 and `pytest` green.** (Signed off by Andrew
   2026-07-09.)
5. **Round 2 landed: multi-resolution analysis (2026-07-09).** Three FFTs per
   hop, stitched by band: 32768-sample window (~0.74 s, ~1.35 Hz bins) paints
   80–400 Hz, 8192 paints 400–1600 Hz, 4096 paints 1600 Hz+ — fine pitch where
   notes are low and sustained, crisp time where onsets live (see
   `MULTIRES_BANDS` in audio/analysis.py). Eye chart with the app's bands:
   **every center G2–A7 ≤ 100¢** (G2 100¢, C3 100¢, G3 50¢, C4 25¢, A4 100¢,
   A5 50¢, A6 50¢, A7 25¢) — G2 was previously not separable at all. Perf
   litmus in multires mode: `fps=92.2, p95=0.0ms` — PASS with 3× headroom.
   A regression test pins the ≤100¢ litmus. **Goal 1a litmus: MET on both
   axes.** Remaining: Andrew's final taste pass on the live app (visual only,
   not a loop gate).

**Perf litmus:** ≥ 30 FPS and ≤ 120 ms p95 glass-to-glass over a 30 s synthetic
run, `pytest tests/` green. **Status: MET** through Round 2 multires
(2026-07-09, fps=92.2).
**Resolution litmus (Round 2):** ≤ 100¢ separable at every tested center G2–A7.
**Status: MET** (2026-07-09, guarded by regression test).

---

## North Star Goal 1 — Beautiful

### 1a. High-resolution spectrogram without lag *(top priority)*
The visualization must be high-resolution **and** stay real-time. Resolution and
latency are in tension; the whole game is pushing both up together.

- **Approach:** profile before optimizing — measure where each frame's time goes
  (FFT compute, interpolation, Gaussian blur, Qt paint) before changing anything.
- **Likely levers:** scrolling ring-buffer rendering (append one column per hop
  instead of recomputing the whole image); efficient FFT sizes; decoupled
  capture/analysis/render threads; GPU-accelerated rendering (pyqtgraph OpenGL /
  shaders); analysis resolution decoupled from display resolution.
- **Loop suitability: EXCELLENT.** Objective, self-verifiable litmus (see
  [How we work: looping](#how-we-work-looping)). Example target: *sustain ≥ 30 FPS
  and ≤ 120 ms glass-to-glass latency at 2048 log-frequency bins over a 30 s
  synthetic-audio run, with `pytest tests/` green.*

### 1b. Fun, friendly, characterful UI *(secondary)*
- **Aesthetic direction:** Frutiger Aero — glossy glass, translucency, aqua/water
  and nature motifs, soft gradients, lens-glint highlights — with tasteful
  **skeuomorphism** for character (physical-feeling knobs, dials, meters).
- **Implementation note:** PySide6/Qt styling via QSS + custom-painted widgets;
  skeuomorphic controls likely need custom `QWidget.paintEvent` work.
- **Loop suitability: LOW (needs human taste).** "Cohesive and polished" is
  judged by Andrew's eyes, not a metric. Run these as **iterate-with-checkpoints**:
  Claude produces a variation + screenshot, Andrew reacts, repeat. Not a clean
  autonomous loop.
- **Inspiration:** Frutiger Aero / skeuomorphic reference images are collected at
  `~/Desktop/passaggiatta/` (the hash-named `.jpg`s). Local only — review when
  Goal 1b begins; do not commit them.

Folds in existing item: **color-scheme exploration** (spectrogram palettes that
keep quiet-sound contrast and stay legible under the gold Singer's Formant band).

---

## North Star Goal 2 — Prescriptive (bel canto vocal science)

Turn the tool from **diagnostic** ("here's your F1/F2") into **prescriptive**
("for this note and vowel, modify toward *this* shape"). The measurement
infrastructure already exists — live fo, F1, F2 — so this is mostly a
domain-knowledge + UX problem, not a new-sensing problem.

### The core idea: formant tuning / vowel modification
As a singer ascends in pitch, the fundamental (fo) and its harmonics rise toward —
and eventually past — the vocal tract's formants (esp. F1). Modifying the vowel
(vocal-tract shape) keeps formants favorably related to harmonics, giving fuller
resonance while often preserving the *perceived* vowel. E.g. a female voice on
"oo" above ~C5 opening toward "uh" raises F1 to track fo, freeing the resonance
while the listener still reads "oo".

### Source materials
1. **Berton Coffin, *Chromatic Vowel Chart for Voice Building and Tone Placing***
   (© 1979 / 1986; based on *The Sounds of Singing*, Scarecrow Press) — the "graph
   behind the piano keys." A chromatic grid: **pitch** (columns, reference # 1–59,
   Hz 98–2794) × **vowel family** (Front / Neutral / Back / Umlaut) × acoustical
   "track" (register) → the recommended IPA vowel to sing, **color-coded by
   resonance safety**: red = dangerously spread (avoid), yellow = open/bright,
   green = safe resonance, blue = closed/low-energy. Separate **Male** and
   **Female** charts, each transposed per voice type (Fach) by clef placement;
   a side panel gives each vowel's first-resonance (F1) pitch.
   → **digitize into our own dataset** (voice type × pitch × vowel family/track →
   {target vowel, resonance rating}).
2. **Kenneth Bozeman, *Practical Vocal Acoustics*** — the physics engine:
   F1/fo relationships, the passaggio "turning over" where fo crosses F1,
   open vs. closed timbre, the singer's-formant cluster, etc.

**Source assessment (2026-07-07, chart ingested):** The Coffin chart is
**genuinely useful, not outdated.** Its two axes — sung pitch (Hz) and vowel/F1
resonance — map *directly* onto what the app already measures (fo, F1), and its
color code is a ready-made overlay for a "aim here / avoid here" display. Caveats:
(a) Coffin's values are *approximations* — cross-check against modern measured
formant data (e.g. Hillenbrand, Sundberg); (b) his terminology ("tracks", "organ
pipe series", "super whistle") is idiosyncratic — translate to modern
F1/harmonic language in the UI. Coffin supplies the empirical *what* (which vowel
at which pitch); Bozeman supplies the *why* and lets us generalize from measured
formants instead of a fixed table. Use Coffin as the v1 lookup source; Bozeman as
the generalization/validation layer.

**IP note (applies to both sources):** implement the *principles and physics*
(not copyrightable), cite the authors, and **never commit the chart photos or a
verbatim reproduction of either source** to this public repo. Build our own
derived dataset. Chart photos live at `~/Desktop/passaggiatta/` (local only).
(Same respect-for-IP posture as the VoceVista rule in [CLAUDE.md](CLAUDE.md).)

### Milestones (diagnostic → prescriptive, incremental)
1. **Target-zone overlay** — given the current note + intended vowel + voice type,
   draw the *target* formant zones on the spectrogram so the singer sees where to
   aim. (Extends the existing F1/F2 overlay.)
2. **Live prescription** — compare measured (fo, F1, F2) to target and surface a
   plain-language cue: "open toward 'uh'", "your F1 is below fo — raise it".
3. **Voice-type profiles** — soprano/mezzo/tenor/baritone/bass presets that set
   the right formant targets; later, estimate/assist voice-type selection.

Folds in existing item: **IPA vowel display** (live (F1,F2) → nearest IPA vowel)
becomes the readout layer that prescription builds on.

- **Loop suitability: LOW (needs domain judgment).** Correctness of vocal-science
  claims must be checked by Andrew (a trained singer) and against the sources —
  not machine-verifiable. Build via **checkpoints**, not autonomous loops.

---

## Current state (shipped)
- Real-time scrolling spectrogram (80–8000 Hz, logarithmic frequency)
- Fundamental frequency display (Hz + note name)
- Custom colormap with a visible quiet-sound floor (−60 dB)
- Singer's Formant highlight band (2,000–3,500 Hz)
- F1/F2 formant rolling-dot overlay
- Visual customization sidebar (colormap presets, dB range, dot sizes, background) — persisted
- Crisp multi-resolution rendering: three FFT bands stitched by frequency + a
  precomputed log-resampling matrix (Gaussian blur removed), 1024 log bins;
  ≤100¢ two-tone separability G2–A7, guarded by a regression test (#18)
- Packaged as a macOS `.app` (PyInstaller)

## Backlog (not yet designed)
- Vibrato rate + extent tracking *(back-burner — see Next up)*
- Time-scale zoom for the scrolling window
- Session recording + playback *(→ scheduled as the "memory" ship, Next up)*
- Reference overlays (compare against a recording) *(→ part of the "memory" ship)*
- ~~Higher FFT resolution/overlap (n_fft 4096, 75% overlap)~~ — shipped in #18
  (FFT 4096, hop 1024, plus multi-resolution bands)

## How we work: looping
We use `/loop` to iterate autonomously toward a goal. A loop is only as good as
its **litmus** — the test that lets the *looping agent* decide "done" without
Andrew in the room. Principles:
- **Clear goal:** one unambiguous definition of done per loop.
- **Self-verifiable litmus:** a metric Claude can measure itself — FPS, latency
  (ms), bin count, `pytest` green, no dropped frames over N seconds.
- **Bounded iteration:** each pass makes one measurable improvement, then re-checks.
- **Termination + escalation:** stop when the litmus is met; escalate to Andrew
  when stuck or when the next step needs human judgment.

**Rule of thumb:** if judging "done" requires Andrew's eyes, ears, or taste, it is
*not* a clean loop — it's iterate-with-checkpoints. Good loop targets here:
Goal 1a (spectrogram performance). Poor loop targets: Goal 1b (UI aesthetics) and
Goal 2 (vocal-science correctness).

## How we track work
- **This file** = the map: vision, priorities, what's done.
- **GitHub Issues** = the granular units for each roadmap item.
- **docs/plans/** = detailed design + implementation docs, per feature.

## Open questions (to resolve with Andrew)
- Goal 1a: what's the *current* FPS/latency and where's the bottleneck? (profile first)
- Goal 1b: any Frutiger Aero reference images to anchor the look?
- Goal 2: is the vowel-modification chart available to digitize (image/data), and
  which voice type(s) does it cover? What voice type(s) do we target first?
- Goal 2: which Bozeman principle is the highest-value first implementation
  (F1/fo crossing feedback is a strong candidate)?

## Working agreement (learning goals)
This project doubles as a place to build professional developer habits and to
learn `/loop`. Favor: branches + pull requests over direct commits, Conventional
Commit messages, tests kept green, wrong turns captured in [Lessons.md](Lessons.md),
and loops built around self-verifiable litmus tests.
