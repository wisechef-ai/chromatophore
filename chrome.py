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

# Where the mantle pigment sits. Lifted from the original 0.235: the xterm-256
# cube has no dark chromatic entries below roughly this lightness, so anything
# darker quantises to grey however much chroma it carries.
_PIGMENT_L = 0.30
_PIGMENT_C_GAIN = 1.30

# Anything painted BEHIND TEXT must clear WCAG AA against the body foreground.
# A lightness ceiling only approximates this: at L .52 a dark red clears 4.6:1
# while an equally light green reaches 4.1:1, so the ratio is measured instead.
_BODY_FOREGROUND = "#E8E6EA"
_AA_RATIO = 4.5
_DARKENING_STEPS = (0.52, 0.46, 0.40, 0.34, 0.28, 0.22)


@lru_cache(maxsize=32)
def _mantle_palette(session_id: str) -> tuple[str, str]:
    """(ground, pigment) for a session's transcript mantle.

    The pigment is snapped to the nearest xterm-256 COLOUR CUBE entry, never a
    free hex. prompt_toolkit renders at DEPTH_8_BIT, so whatever we emit is
    quantised before it reaches the screen, and the 256 palette is sparse in the
    dark region: a low-chroma near-black lands on the greyscale ramp (232-255)
    and the mantle arrives as flat grey. Measured: 5 of 8 sessions collapsed.
    Choosing from the cube makes the hue survive by construction.

    Both values are session constants and `render(allocate(...))` alone costs
    ~46us, far too much to repeat for every printed line.
    """
    identity = allocate(session_id)
    wanted = identity.oklch.with_(L=_PIGMENT_L, C=identity.oklch.C * _PIGMENT_C_GAIN)
    return render(identity).ground_hex, _index_to_hex(quantize_cube_256(oklch_to_hex(wanted)))


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
    """
    from .mantle import chromatophore_set
    return tuple(_readable(c.oklch)
                 for c in chromatophore_set(allocate(session_id), Signal(signal)))


def _readable(colour: OKLCh) -> str:
    """Darken `colour` until the body foreground clears AA on top of it.

    Quantisation happens first: AA has to hold for the hex the TERMINAL is sent,
    not the one we asked for.
    """
    for lightness in (colour.L, *_DARKENING_STEPS):
        if lightness > colour.L:
            continue
        candidate = _index_to_hex(quantize_cube_256(oklch_to_hex(colour.with_(L=lightness))))
        if contrast_ratio(_BODY_FOREGROUND, candidate) >= _AA_RATIO:
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
    ground, _pigment = _mantle_palette(session_id)
    classes = _mantle_classes(session_id, signal)
    row = cells(session_id, signal, width, row_key)
    # cells() draws its lit pigments from a graded ramp; rank the distinct ones by
    # lightness so the most expanded cells reach the brightest class.
    ramp = sorted({fg for fg, _bg, _g in row if fg != ground},
                  key=lambda pigment: hex_to_oklch(pigment).L)
    band = {pigment: rank * len(classes) // len(ramp) for rank, pigment in enumerate(ramp)}
    return tuple((f"bg:{ground if fg == ground else classes[band[fg]]}", " ")
                 for fg, _bg, _glyph in row)


def chrome_renderer(surface: str, width: int, ctx: dict[str, Any]) -> list[tuple[str, str]] | None:
    """Render persistent chrome, failing closed on any repaint-path problem."""
    try:
        signal = collapse(ctx.get("pet_state"))
        if surface == "status_bar_bg":
            if signal is Signal.RESTING:
                return None
            colour = oklch_to_hex(ACUTE_FAULT if signal is Signal.FAULT else ACUTE_AMBER)
            # Fill the bar: the core pads a short list with the EMPTY style, so
            # one cell would leave the rest stock — an alarm you cannot see.
            return [(f"bg:{colour}", " " * max(0, int(width)))]
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
