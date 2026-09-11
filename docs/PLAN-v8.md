# v8 — the chrome renderer: patterns that survive the scroll, and state you can see

## Why this is now possible

Until today a plugin could only paint the rule as STATIC skin data
(`input_rule_art`), written once into the YAML. Two core commits change that:

- `plugins: add chrome renderer hook` — `ctx.register_chrome_renderer(fn)`.
  `fn(surface, width, ctx) -> list[(style, text)] | None` for the surfaces
  `input_rule_top`, `input_rule_bot`, `status_bar_bg`. Returning `None` keeps the
  built-in. Exceptions disable the renderer for the session and log once.
  Fragments are normalised to exactly `width` cells by the core.
- `plugins(chrome): pass the live pet_state to chrome renderers` — the ctx dict
  now carries `session_id`, `skin`, and **`pet_state`**.

Both are applied on Chef (`07a6696f46`) and on the workstation. 22 core tests green.

This matters because chrome is **redrawn on every repaint**. The banner scrolls
away after 9 lines (measured); the rule above the input does not. It is the only
plugin-reachable surface that persists.

## The two layers (README's own model — do not invent a new one)

    PATTERN = CHRONIC(identity) + [ACUTE(signal) only when needed]

**Layer 1 — identity (chronic).** Which chat is this? Per-session hue + body
pattern, allocated in OKLab, stable across reconnects via blake2b. Already built:
`color/identity.allocate`, `patterns.field_for`, `seed.seed_for`.

**Layer 2 — state (acute).** What does the agent need from me? The core now hands
us `pet_state`; `session.collapse()` ALREADY maps all seven pet states onto the
three signals, and `session.signal_label()` already formats the text label:

    idle/run/review/wave/jump -> RESTING   ""            (visually silent)
    waiting                   -> NEEDS_ME  "INPUT {age}" (amber)
    failed                    -> FAULT     "ERROR {age}" (red)

`session.py`'s docstring says explicitly: *"Do not fake a state source: a wrong
NEEDS_ME is worse than none."* The hook is now that honest source. Use it; never
guess a state from the registry.

## Outcomes (each needs a test that FAILS before the change)

1. **Register a chrome renderer, guarded.** In `register()`, wrap
   `ctx.register_chrome_renderer` in its own try/except like every other
   registration — an older Hermes without the hook must lose this ONE feature,
   not the whole plugin. Assert: a ctx lacking the method still registers hooks.

2. **`input_rule_top` renders the session's body pattern**, reusing
   `linework.separator_markup`'s grammar (dominance >= 55%, vivid 8-20%, mean run
   >= 2.0, measured on xterm-256-quantised colours). Do NOT re-roll the pattern:
   the density work is done and verified over 72 combinations. Convert its Rich
   markup to prompt_toolkit `(style, text)` fragments — style strings are
   `"fg:#rrggbb bg:#rrggbb"`, NOT Rich's `[fg on bg]`.

3. **The renderer is driven by live `pet_state`.** `ctx["pet_state"]` -> 
   `session.collapse()` -> the signal that picks the hue family. Assert:
   `pet_state="waiting"` renders amber-family, `"failed"` renders red-family,
   `"idle"`/`"run"` render the session's own identity hue. A missing or unknown
   `pet_state` must render RESTING, never an invented alarm.

4. **Identity still separates.** Two different session_ids at the same pet_state
   produce different vivid-cell colour sets (the v7 allocator work stands).

5. **`status_bar_bg` carries the acute signal.** When the signal is not RESTING,
   tint the status bar so the state is readable even if the user's eyes are on
   the rule. RESTING must stay visually silent (return `None`).

6. **Never raise, never block.** The renderer runs on the repaint path. Wrap the
   body in try/except returning `None`, and keep it fast: cache per
   `(session_id, signal, width)` — `linework.separator_markup` is already
   `lru_cache`d; do not add per-frame allocation. Assert a cached call is served
   without recomputation.

7. **Degrade honestly.** If `pet_state` is absent (older core), the rule still
   renders identity; only layer 2 goes quiet.

## Out of scope

- No background wallpaper. OSC 11 sets ONE flat colour and VTE has nothing behind
  the cell grid; a pattern behind the text is unreachable on Adam's emulator.
- Do not modify `~/.hermes/hermes-agent`. The core side is done.
- Do not weaken any v7 density threshold.

## Gate

`PYTHONPATH=~/.hermes/hermes-agent make test` green (231 tests today), plus the
new tests, plus the v7 density audit still passing over 72 combinations.
