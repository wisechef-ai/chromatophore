"""Prompt-toolkit chrome rendering for the persistent input rule."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from .color.identity import allocate
from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex
from .color.terminal import _index_to_hex, contrast_ratio, quantize_cube_256
from .linework import cells
from .pattern import ACUTE_AMBER, ACUTE_FAULT, render
from .session import Signal, collapse

# Anything painted BEHIND TEXT must clear WCAG AA against the body foreground.
# A lightness ceiling only approximates this: at L .52 a dark red clears 4.6:1
# while an equally light green reaches 4.1:1, so the ratio is measured instead.
_BODY_FOREGROUND = "#E8E6EA"
_AA_RATIO = 4.5
_DARKENING_STEPS = (0.52, 0.46, 0.40, 0.34, 0.28, 0.22)

# The acute status bar is a LOUD surface, not a background: it should catch the
# eye across a room. Adam, 2026-09-11: "the bars should be bright and the text is
# white." Pure white on a bright bar is not reachable at AA — #FFAF00 carries
# white at only 1.84:1 — so the bar sits at the brightest cube entry that still
# holds white text: measured 4.71:1 (amber) and 5.40:1 (red).
_ACUTE_BAR_L = 0.57
_ACUTE_BAR_FOREGROUND = "#FFFFFF"

# (lightness delta, hue delta) tried in order when two classes quantise onto one
# cube entry. Lightness first — it separates without changing what the class IS.
_SEPARATION_NUDGES = ((0.08, 0), (-0.08, 0), (0.16, 0), (-0.16, 0),
                      (0.0, 25), (0.0, -25), (0.24, 0), (0.0, 50))


@lru_cache(maxsize=32)
def _mantle_palette(session_id: str) -> str:
    """The ground the session's transcript mantle is painted on.

    Cached because `render(allocate(...))` costs ~46us and this is a session
    constant asked for once per printed line.
    """
    return render(allocate(session_id)).ground_hex


@lru_cache(maxsize=64)
def _mantle_classes(session_id: str, signal: str) -> tuple[str, ...]:
    """The session's chromatophore classes, quantised, darkest first.

    Four classes, not one colour: two dark pigments from different hue families,
    the cool iridophore complement, and the sparse bright leucophore. Under an
    acute signal `chromatophore_set` returns the FIXED amber/red sets instead,
    so "that terminal needs me" reads the same across every session.

    In the animal the iridophore and leucophore are the BACKDROP the pigments sit
    above; here they sit BEHIND TEXT, so every class is darkened until it clears
    WCAG AA against the body foreground. Lightness alone is the wrong guard: a
    saturated green at L .52 still reaches only 4.1:1, so the contract is
    measured directly rather than approximated. Hue and ordering survive.

    Classes are then separated: the cube is sparse down here, so 77 of 1000
    sessions had two classes quantise onto one entry (s10 rendered three colours
    where four were designed). A collapsed class is a session that looks like
    another session, which is the identity the mantle exists to carry.
    """
    from .mantle import chromatophore_set
    return _distinct(tuple(c.oklch for c in
                           chromatophore_set(allocate(session_id), Signal(signal))))


def _distinct(colours: tuple[OKLCh, ...]) -> tuple[str, ...]:
    """Quantise `colours`, nudging any that land on an already-used cube entry.

    Lightness moves first and hue only as a fallback, because a class is defined
    by its hue family: shifting L keeps "the dark red one" dark red, while
    shifting h turns it into a different class entirely.
    """
    taken: list[str] = []
    for colour in colours:
        candidate = _readable(colour)
        for nudge in _SEPARATION_NUDGES:
            if candidate not in taken:
                break
            candidate = _readable(colour.with_(L=max(0.12, colour.L + nudge[0]),
                                               h=(colour.h + nudge[1]) % 360))
        taken.append(candidate)
    return tuple(taken)


def _readable(colour: OKLCh, foreground: str = _BODY_FOREGROUND) -> str:
    """Darken `colour` until `foreground` clears AA on top of it.

    Quantisation happens first: AA has to hold for the hex the TERMINAL is sent,
    not the one we asked for. The foreground is a parameter because the status
    bar pairs a bright background with white text, where the body's near-white
    would give a different answer.
    """
    for lightness in (colour.L, *_DARKENING_STEPS):
        if lightness > colour.L:
            continue
        candidate = _index_to_hex(quantize_cube_256(oklch_to_hex(colour.with_(L=lightness))))
        if contrast_ratio(foreground, candidate) >= _AA_RATIO:
            return candidate
    return _index_to_hex(quantize_cube_256(oklch_to_hex(colour.with_(L=_DARKENING_STEPS[-1]))))


@lru_cache(maxsize=512)
def _mantle_row(session_id: str, width: int, row_key: int,
                signal: str = Signal.RESTING.value) -> tuple[tuple[str, str], ...]:
    """One row of the transcript mantle, as prompt_toolkit fragments.

    WHICH class shows at a cell follows that cell's own pigment, which `cells`
    already assigns by field intensity — deeper classes for stronger expansion,
    as the animal recruits them. Never by column index: that is the alternating
    stripe v7 removed.

    Cached whole: this is called once per printed line, and rebuilding an
    80-element list of f-strings per line is most of the cost at that rate.
    """
    ground = _mantle_palette(session_id)
    classes = _mantle_classes(session_id, signal)
    row = cells(session_id, signal, width, row_key)
    # cells() draws its lit pigments from a graded ramp; rank the distinct ones by
    # lightness so the most expanded cells reach the brightest class.
    ramp = sorted({fg for fg, _bg, _g in row if fg != ground},
                  key=lambda pigment: hex_to_oklch(pigment).L)
    band = {pigment: rank * len(classes) // len(ramp) for rank, pigment in enumerate(ramp)}
    return tuple((f"bg:{ground if fg == ground else classes[band[fg]]}", " ")
                 for fg, _bg, _glyph in row)


def _acute_status_bar(signal: Signal) -> tuple[str, str]:
    """The acute bar's background AND the foreground that stays legible on it.

    The bar is painted over fragments carrying their own colours — silver, gold,
    olive-grey — and prompt_toolkit lets the last style win, so the plugin must
    supply both halves of the pair. Supplying only a background left the default
    #C0C0C0 text at 1.01:1 on quantised amber: the status bar went blank exactly
    when it had something to say.

    No cube colour clears AA against all six stock status-bar foregrounds at once
    (#8B8682 sits mid-range and collides with everything), so the plugin pins its
    own pair: the brightest cube entry that still carries WHITE text.
    """
    oklch = ACUTE_FAULT if signal is Signal.FAULT else ACUTE_AMBER
    background = _readable(oklch.with_(L=_ACUTE_BAR_L), _ACUTE_BAR_FOREGROUND)
    return background, _ACUTE_BAR_FOREGROUND


def chrome_renderer(surface: str, width: int, ctx: dict[str, Any]) -> list[tuple[str, str]] | None:
    """Render persistent chrome, failing closed on any repaint-path problem."""
    try:
        signal = collapse(ctx.get("pet_state"))
        if surface == "status_bar_bg":
            if signal is Signal.RESTING:
                return None
            colour, foreground = _acute_status_bar(signal)
            # Fill the bar: the core pads a short list with the EMPTY style, so
            # one cell would leave the rest stock — an alarm you cannot see.
            return [(f"bg:{colour} {foreground}", " " * max(0, int(width)))]
        session_id = ctx.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return None
        if surface == "transcript_line":
            row_key = ctx.get("row_key")
            row_key = int(row_key) if isinstance(row_key, int) and not isinstance(row_key, bool) else 0
            return list(_mantle_row(session_id, int(width), row_key, signal.value))
        if surface not in {"input_rule_top", "input_rule_bot"}:
            return None
        return [(f"fg:{fg} bg:{bg}", glyph)
                for fg, bg, glyph in cells(session_id, signal.value, int(width))]
    except Exception:
        return None


__all__ = ["chrome_renderer"]
