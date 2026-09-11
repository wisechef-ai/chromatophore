"""Prompt-toolkit chrome rendering for the persistent input rule."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from .color.identity import allocate
from .color.oklab import hex_to_oklch, oklch_to_hex
from .color.terminal import _index_to_hex, quantize_cube_256
from .linework import cells
from .pattern import ACUTE_AMBER, ACUTE_FAULT, render
from .session import Signal, collapse

# Where the mantle pigment sits. Lifted from the original 0.235: the xterm-256
# cube has no dark chromatic entries below roughly this lightness, so anything
# darker quantises to grey however much chroma it carries.
_PIGMENT_L = 0.30
_PIGMENT_C_GAIN = 1.30

# Ceiling for anything painted BEHIND TEXT. Above this the body foreground drops
# under WCAG AA (measured: an L 0.89 pearl gives 1.05:1) and the line is lost.
_MAX_BACKGROUND_L = 0.52


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
    above; here they sit BEHIND TEXT, so every class is capped at
    ``_MAX_BACKGROUND_L``. Left at its natural lightness the pearl reaches
    contrast 1.05:1 and the line on it is unreadable. Hue and ordering survive;
    only lightness is bounded.
    """
    from .mantle import chromatophore_set
    return tuple(
        _index_to_hex(quantize_cube_256(oklch_to_hex(
            c.oklch.with_(L=min(c.oklch.L, _MAX_BACKGROUND_L)))))
        for c in chromatophore_set(allocate(session_id), Signal(signal)))


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
