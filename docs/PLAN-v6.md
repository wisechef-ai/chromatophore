---
tags: [projects]
title: "Plan V6 — bioluminescent frame"
created: 2026-09-10
---

# cuttlefish-theme v6 — bioluminescent skin, whole-frame (VTE ceiling)

Status: SPEC LOCKED 2026-09-10 12:50. Impl: gpt-5.6-luna. Review: opus-5 + glm-5.3. Supervisor: Tori.
Repo: github.com/wisechef-ai/cuttlefish-theme main @ 5fa09dd → v0.5.0. Target host: Chef (Adam tests there).
Recon: [[RECON-v6]]. Previous: [[PLAN-v5-as-built]].

## Adam's brief (verbatim essentials)
Bioluminescent cuttlefish skin as a dark premium terminal UI. Base = uniform near-black navy/indigo,
equally dark everywhere (night sessions). On it: tiny chromatophore-like dots/cells forming organic
cuttlefish patterns — stripes, mottling, waves, clouds, soft camouflage fields. Palette vivid but
restrained: cyan, teal, electric blue, violet, magenta, amber, orange, pearl-white highlights — as tiny
glowing cells and narrow bands, never large bright areas. UI stays technical/minimal: crisp monospace,
off-white body text, thin separators. Commands/warnings/identity/state use stronger accents.
KEY FEATURE: pixel-scattered multicolour linework — borders, separators and ESPECIALLY the bottom input
line look like rows of active chromatophores, not smooth gradients.
Direction = Chromatophore Grid (cellular structure) + Pearl Nebula (darker, cleaner readability).

## Decisions (clarify, 2026-09-10)
D1 Terminal: GNOME Terminal/VTE. No wallpaper exists; field = per-cell `bg:` on lines WE print.
   Empty scrollback rows stay OSC-11 ground. Accepted by Adam.
D2 Surface: classic CLI only. No TUI work. No window titles. No `watch` board work.
D3 Priority: IDENTITY (which of 10-20 windows is this) > state > anything.
D4 Identity = (pattern CLASS from a library) + (multi-hue palette weighting) + (name). All blake2b-seeded
   by session id — survives restart/reconnect. Classes ≈ Hanlon&Messenger: uniform-fine-mottle, coarse
   mottle, stripes/zebra, passing-cloud bands, disruptive patches, pearl scatter. ≥6 classes.
D5 Palette: multi-hue neon (cyan/teal/blue/violet/magenta/amber/orange + pearl white) on navy/indigo
   ground; per-session weighting picks 2-3 dominant hues. Dots dimmer than body text. Dark theme only.
D6 Acute layer: whole field recolours (amber cast INPUT, red cast ERROR) + status pill `INPUT 4m` — the
   existing engine behaviour, kept. Blanch/recover curves kept.
D7 Image paste: OUT of scope (core has /paste + raw Ctrl-V for GNOME Terminal).
D8 Where the field lives: status bar, input line (chromatophore row), panel borders/separators
   (chromatophore linework), banner hero (mantle), AND faint field inside response panels/blocks.

## Hard constraints
- Plugin-only; no hermes core edits. Only documented skin keys + Rich markup + prompt_toolkit styles.
- Never raw ANSI to stdout (transcript). OSC only via /dev/tty (termbg.py pattern).
- Contrast: every text cell ≥ 4.5:1 vs its own bg (WCAG), enforced by a test over rendered cells.
- Idle = zero repaints. Per-(session,signal) rendered strings cached; render cost budget ≤ 30 ms/frame
  measured; banner ≤ 80 ms.
- Ground: OKLab L ≈ 0.14-0.17, hue navy/indigo (h≈270), C ≤ 0.02. Same L for every session.
- Fix: replace `abs(hash(session_id))` in mantle.py:211 and cli.py:215 with blake2b (test: same id in
  two processes → identical field).
- Acceptance is REAL BYTES: tests/proofs/terminal_paint_proof.py extended — pty spawn, assert (a) stock
  gold absent, (b) ≥ N distinct colours, (c) input line row contains ≥ 8 distinct bg colours,
  (d) two different session ids produce different pattern classes/fields, (e) same id twice → identical.
- Keep `make test` green; add tests for every new module. No change-detector tests.

## Skin-engine reality (from hermes_cli/skin_engine.py @ installed core)
- `input-area` style is "" by design; typed text inherits terminal colours. The INPUT LINE chromatophore
  row must therefore be a separator/prompt row we render (prompt symbol + a rule above the input), not
  the input-area bg itself.
- Style classes carrying bg: status-bar*, subagent-dock*, completion-menu*, voice-status. Keys:
  status_bar_bg/text/strong/dim/good/warn/bad/critical, session_label, badge_bg/fg, menu_* .
- `banner_logo` / `banner_hero` (hero = LEFT column, exactly 30x15) are whole-string Rich markup fields.
- response_border, banner_border, ui_accent, ui_primary reachable via 3 paths (see PLAN-v5 B4).
- Repaint path: skin_engine.set_active_skin(name) + cli._apply_tui_skin_style() (live.py).

## Core-reachability correction (2026-09-10 13:40, verified in hermes_cli/cli_tui_mixin.py + skin_engine.py)
Status bar, input rules and Panel borders are ONE style class each (`input-rule: '#CD7F32'`, `status-bar:
bg:{status_bg}`, `Panel(border_style=response_border)`). A skin sets THE colour, not per-cell colours. Per-cell
chromatophore linework there requires a hermes-core render hook — deferred (Adam unanswered → bounded default
= plugin-only). Reachable per-cell surfaces: `banner_logo` + `banner_hero` (Rich markup) and rows the plugin
PRINTS itself (on_stream_end hook → chromatophore separator after each response, via Rich console, never raw ANSI).
Attempt 1 (branch v6-attempt1): 148-line stub, linework.py never wired, `random.Random` patterns — rejected.

## Deliverables (revised)
1. `patterns.py` — class library (≥6), pure, seeded, returns expansion field + class name.
2. `palette.py` — multi-hue pigment sets (weighted per session), navy ground, contrast helpers.
3. `linework.py` — chromatophore rows for borders/separators/input rule/status bar (Rich + pt styles).
4. `mantle.py` — uses patterns + new palette; blake2b seed.
5. Response-panel faint field (Rich renderable wrapper or skin keys — implementer chooses, documents why).
6. Proofs + tests as above; README updated (honest about VTE ceiling); version 0.5.0; CHANGELOG entry.
7. `tools/render_preview.py` renders 6 sessions × 3 signals to PNG for Adam's eye.

## Out of scope
kitty/wezterm wallpaper tier · window titles · `watch` board · TUI · image paste.

## Related
[[RECON-v6]] · [[PLAN-v5-as-built]] · [[hub]]
