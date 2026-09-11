# v9 — the background becomes a real mantle

## The finding that unblocks this

"The background cannot carry a pattern" was true of **OSC 11** and false as a
general claim. OSC 11 sets ONE flat colour for empty cells, and VTE has nothing
behind its cell grid — that part stands. But the transcript is not empty cells:
it is **text we print**, and a per-cell `bg:` on a printed line paints exactly
where the text is.

Verified in a real pty (`/tmp/probe_pty_mantle.py`): 6 rows, each with its own
background tint plus sparse pigment cells, **6/6 rows carried a true background**.

Two hazards, both measured and both cheap to defeat
(`/tmp/probe_line_bg.py`):

1. **Rich resets kill the background mid-line.** A rendered line contains its
   own `\x1b[0m` (3 in a representative line); each one drops the tint for the
   remainder. Fix: re-assert the background after every reset.
2. **The tint stops where the text stops.** A 16-character line in an 80-column
   terminal leaves 64 untinted columns. Fix: pad to terminal width.

## The seam

`cli.py::_cprint(text)` is the single function every transcript line passes
through — **280 call sites, one choke point**. `ChatConsole.print` already
splits Rich output into individual lines and calls it per line. So a core hook
placed there reaches the whole scrolling transcript with zero call-site changes.

## Core PR contract (hermes-agent)

Surface name: `transcript_line`. It joins the existing three
(`input_rule_top`, `input_rule_bot`, `status_bar_bg`) in `_CHROME_SURFACES`,
reusing `render_chrome()` — **no new plugin API**, no new registration call, no
new ctx shape. That is the whole point: the mechanism already exists and is
tested; this adds one surface to it.

    render_chrome("transcript_line", width, ctx) -> [(style, text)] | None

Contract:
- Returns `None` (the overwhelmingly common case, and every case without a
  plugin) → `_cprint` behaves EXACTLY as today. Zero-cost default.
- The renderer supplies a **background per column**; the line's own foreground
  colours are preserved. It decorates, never replaces — a theme must not be
  able to blank the user's transcript.
- Runs on the print path, so it is bounded: any exception disables the renderer
  for the session (the existing `render_chrome` guard already does this).

### Hermes-team acceptance bar (the PR will be read against these)

From `AGENTS.md` and the contribution rubric — every one of these is a real
rejection reason:

- **Narrow waist.** No new core tool, no new env var, no new plugin API. One
  entry added to an existing frozenset, one call in one function.
- **Speculative infrastructure is rejected.** State the concrete consumer:
  cuttlefish-theme, shipping, with the hook wired.
- **Behaviour contracts, not snapshots.** Tests assert relationships (bg
  survives resets; width is filled; None is identical to today), never frozen
  escape strings.
- **E2E with real imports**, not mocks, against a temp `HERMES_HOME`.
- **Prompt caching / alternation invariants untouched** — this is pure
  rendering, say so and mean it.
- **No `try/except: pass` around code that cannot fail**, no defensive wrappers,
  no comment restating the code.
- Run `scripts/run_tests.sh` (NEVER bare pytest) and paste the real tail.

## Outcomes (each needs a test that FAILS before the change)

1. `transcript_line` is a member of `_CHROME_SURFACES` and `render_chrome`
   accepts it; unknown surfaces still raise `ValueError`.
2. `_cprint` consults the renderer and applies the returned background to the
   line, preserving the line's own foreground SGR.
3. **Resets do not kill the tint**: a line containing `\x1b[0m` is still tinted
   after the reset. Assert on the emitted bytes.
4. **The row is filled**: a line shorter than the terminal width is padded so
   the tint reaches the last column.
5. **`None` is byte-identical to today.** The critical regression test: with no
   renderer registered, `_cprint`'s output is unchanged, character for
   character. This is what protects every existing user.
6. **A renderer exception degrades silently** and disables for the session;
   the transcript keeps printing.
7. **No measurable cost when absent**: the no-renderer path must not add work
   per line beyond one dict lookup.

## Plugin side (cuttlefish-theme)

8. Extend `chrome_renderer` to serve `transcript_line`, driven by the SAME
   `cells()` source already used for the rule, so the mantle and the rule are
   one pattern. Per-line variation comes from the row's position in the
   session's field — the arrangement stays stable per (session, signal), which
   is the property Adam asked for and v8 already guarantees.
9. The ground must stay near-black (L < 0.32) so text contrast is untouched;
   assert WCAG AA against the tinted ground.

## Out of scope

- No OSC 11 redesign. It keeps setting the flat base colour for empty cells.
- No change to the three existing surfaces.
- No new config keys.

## Gate

Core: `scripts/run_tests.sh tests/hermes_cli/` green, real tail pasted.
Plugin: `PYTHONPATH=~/.hermes/hermes-agent make test` green (243 today).
Then a real pty capture on Chef showing >1 distinct background across the
transcript region — the only claim that counts.
