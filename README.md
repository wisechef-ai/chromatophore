# chromatophore

Ambient session identity and state signalling for [Hermes](https://github.com/NousResearch/hermes-agent), modelled on cuttlefish.

Every chat session gets its own colour and its own pronounceable name, held for the life of the session. When a session needs you, an acute signal layers on top — and is released again afterwards, leaving the identity intact underneath.

```
hermes chromatophore watch      every session at once
hermes chromatophore legend     learn the language in one screen
hermes chromatophore doctor     what your terminal can do
```

## Why

Three problems, in the order they bite:

1. **Every session looks the same.** With six terminals open you cannot tell which is which without reading.
2. **You cannot see state at a glance.** Which one is blocked on you? For how long?
3. **Status bars are ugly.** A tool you look at all day should be beautiful.

## The language

Cuttlefish layer two kinds of pattern (Hanlon & Messenger, 1988). We use the same split, because it maps exactly onto the two jobs above:

| | lasts | carries |
|---|---|---|
| **chronic** | minutes to hours | who this session is |
| **acute** | seconds | what it needs from you |

Every appearance is one rule:

```
PATTERN = CHRONIC(identity) + [ACUTE(signal) only when needed]
```

### Identity — endless, never doubling

Colours are not drawn from a fixed list; they are **allocated** in [OKLab](https://bottosson.github.io/posts/oklab/) by farthest-point sampling against the sessions that are live *right now*. The space is continuous, so it never runs out, and allocation maximises perceptual distance, so concurrent sessions never look alike.

Measured, 8 concurrent sessions: worst pairwise separation **0.16 OKLab**, zero flagged crowded.

Names are generated the same way — a phonotactic grammar, not a word list (155,520 forms, `name_space_size()` computes it rather than asserting it). `megena`, `panis`, `hugur`, `brubora`. Say them out loud; that is the point.

Both are deterministic via blake2b, so a session keeps its colour and name across reconnects. (Not Python's `hash()`, which is randomised per process and would rename your session every restart.)

### The three signals

Seven agent states collapse to three, because peripheral colour discrimination does not support seven categories:

| signal | from | shows |
|---|---|---|
| **resting** | idle, run, review, wave, jump | the session's own colour, no badge |
| **needs me** | waiting | amber + `INPUT 4m` |
| **fault** | failed | red + `ERROR 2m` |

`run` and `review` both mean *autonomous work, leave it alone* — a distinction that is useless from across a room.

**Age is text, never colour.** A hue cannot say "four minutes". So the label does.

**Nothing animates.** A cuttlefish at rest is static; its acute displays run 0.38–1 Hz and last a second or two. Continuous motion in peripheral vision is the fastest way to build a UI you learn to ignore.

### Release, not replacement

When a fault clears, the identity returns. This is [blanching](https://www.nature.com/articles/s41586-023-06259-2): the animal pales at a threat, *retains a trace of its prior pattern*, and returns to it — in 16 of 17 measured trials. The acute layer overrides identity; it never destroys it.

## Install

```bash
git clone https://github.com/wisechef-ai/chromatophore ~/.hermes/plugins/chromatophore
hermes plugins enable chromatophore
```

No core changes. It registers a CLI command and two session hooks through the documented plugin surface, and declines tool-override privileges because it does not need them.

## How the live repaint works

The documented "write the skin YAML and everything repaints" path runs in the gateway watcher and **does not reach the classic CLI** — that watcher only starts inside `tui_gateway`. What does work, verified against the live install:

```python
skin_engine.set_active_skin(name)   # re-reads the YAML from disk
cli._apply_tui_skin_style()         # app.style = ...; app.invalidate()
```

`_build_tui_style_dict` calls `get_prompt_toolkit_style_overrides()` on every invocation, so re-activating picks up a rewritten file immediately. We reach the running application through prompt_toolkit's own `get_app_or_none()`, which is why this stays a plugin rather than a patch.

Repaints run at **0.125 Hz** (every 8s) and only when the resolved palette actually changed — most ticks are no-ops.

## Safety

Writes are **atomic** (temp + fsync + rename), and this is not optional. Hermes' watcher records a skin file's mtime *before* parsing it, and a parse failure silently falls back to the default skin — so a torn read does not glitch, it **latches**.

Skin files are **fully materialized**. Hermes merges a skin over the built-in default, not over another skin, so a sparse per-session file would inherit the wrong palette.

Cleanup is defensive: session end restores the previous skin only if we still own the active one (compare-and-set, so a manual `/skin` wins), and an orphan sweep on start reclaims files left by sessions that died without cleanup.

`watch` is strictly read-only.

## Tests

```bash
python3 -m pytest tests/ -q
python3 tests/proofs/live_repaint_proof.py   # against the real skin engine
```

## License

MIT
