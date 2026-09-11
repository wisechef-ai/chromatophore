# v7 — the rule becomes skin, and identity survives the scroll

## Why

Measured on Chef (real pty capture, `/tmp/cf_capture2.txt`, 2026-09-11):

1. **The rule is a modulo rainbow.** `linework.py` does
   `_COLOURS[(x + shift) % len(_COLOURS)]` over every pigment. Captured output is
   the same 8 xterm indices repeating across 79 cells:
   `202 230 37 36 39 105 207 172` — orange, cream, cyan, teal, blue, violet,
   magenta, amber. Adam: "christmas tree lights, not what cuttlefishes have."
   He is right, and it is true by construction.
2. **The pattern lives for 9 lines.** Of 606 captured lines exactly 9 carry a
   per-cell field (indices 29–43, the banner). The 562 lines after it contain
   ZERO background colour. Identity is gone after one scroll.
3. **`patterns.py` is orphaned.** The body-pattern library (UniformFineMottle,
   CoarseMottle, TransverseStripes, PassingCloudBands, DisruptivePatches,
   PearlScatter) is imported by nothing that paints the rule. The grammar we
   need is already written and unused.
4. **OSC 11 works and cannot carry a pattern.** One `#0B0C10` emitted, one
   OSC 111 reset. Adam's emulator is GNOME Terminal / VTE 0.76 — a cell grid
   with nothing behind it, no background-image support. A wallpaper behind the
   text is unreachable there at any effort. Do not attempt it in v7.

## The grammar (what a cuttlefish actually is)

NOT a rainbow. A cuttlefish display is:

- **One dominant pigment** holding most of the field — the session's identity hue.
- **Sparse high-contrast cells** (measured ~11–16% vivid fraction, per
  `tools/sample_photos.py`) — leucophore pearls and a second pigment, never a
  third of the row.
- **Structure, not alternation** — bands, mottle clusters, or a directional
  passing-cloud wave. Neighbouring cells are CORRELATED; that is the whole
  difference between skin and tinsel.
- Ground stays the shared navy near-black.

## Outcomes (each needs a test that FAILS on e643a9d)

1. **`separator_markup` is driven by `patterns.py`, not by modulo.**
   The rule's cell values come from `field_for(session_id, width=N, height=1)`
   (or the pattern's own field sampled on one row). Assert: no `% len(` over a
   pigment tuple survives in `linework.py`.

2. **Dominance.** In any rendered rule of width >= 60, ONE pigment family
   occupies >= 55% of cells. Test asserts the modal colour's share >= 0.55.
   (On e643a9d it is 1/8 = 12.5% — fails RED.)

3. **Sparsity.** Vivid/bright cells (the non-dominant, high-chroma ones) are
   >= 8% and <= 20% of the row. (On e643a9d: 87.5% — fails RED.)

4. **Spatial correlation.** Adjacent cells share a colour more often than chance.
   Measure run-length: mean run of identical colour >= 2.0 cells.
   (On e643a9d every run is exactly 1 — fails RED.)

5. **Identity survives the scroll.** The session's pattern reaches a PERSISTENT
   surface, not only the banner. Reachable plugin-only: the rule above the input
   (`input_rule_art`) is redrawn every repaint — so the rule IS the persistent
   surface. Assert the rule's dominant hue == the session's allocated identity
   hue (`color.identity.allocate`), so two sessions differ at a glance, and that
   it is stable across processes (blake2b seed, not `hash()`).

6. **Quantisation honesty.** prompt_toolkit renders this through xterm-256
   (captured: 1629 `38;5;` spans vs 673 truecolor). Pick cell colours so that
   AFTER quantisation to the 256 palette the dominance and sparsity in (2)/(3)
   still hold. Use the existing `color/terminal.py` quantiser; assert on the
   QUANTISED colours, not the source hex.

7. **Acute state still reads.** amber INPUT / red ERROR whole-field recolour
   survives: with signal=fault the dominant family is the fault hue.

## Explicitly OUT of scope for v7

- No core changes. Plugin hooks are only `on_session_start` / `on_session_end`;
  there is no render hook. Do not edit `hermes-agent`.
- No background wallpaper / no OSC 11 redesign (see Why #4).
- The unpushed core commit `4e0037fee2` (input_rule_art) stays parked on branch
  `cuttlefish/input-rule-art` on Chef. It is Adam's call whether it goes upstream.

## Gate

`make test` green, plus the 7 tests above proven RED on `e643a9d` first.
Then `tools/render_preview.py` / `render_chat.py` to PNG and LOOK at it.
