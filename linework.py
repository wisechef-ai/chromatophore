"""Rich-safe input-rule chromatophores driven by the body-pattern field.

WHY THIS IS TEXT: a plugin cannot paint arbitrary terminal pixels through semantic
skin keys. Rich markup is ours to emit, so each cell can carry one measured pigment.
The rule therefore samples the same coherent, seeded body grammar as the mantle
instead of cycling a palette by x-coordinate (the old output was terminal tinsel).
"""
from __future__ import annotations

from functools import lru_cache

from .color.identity import allocate
from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex
from .pattern import render
from .patterns import field_for

# Share of columns that carry a pigment. Real Metasepia display measures 11-16%
# vivid over a 2D patch, but a 2D fraction re-read on ONE row leaves voids the
# eye reads as emptiness: at 0.16 the longest dark gap on an 80-column rule was
# 33 cells. 0.30 restores the density a single row needs to read as skin.
_VIVID_FRACTION = 0.30


def _identity_variants(session_id: str) -> tuple[str, ...]:
    return _oklch_variants(allocate(session_id).oklch)


def _oklch_variants(base: OKLCh) -> tuple[str, ...]:
    return tuple(oklch_to_hex(base.with_(L=0.50 + 0.30 * fraction))
                 for fraction in (i / 15 for i in range(16)))


def _acute_variants(signal: str) -> tuple[str, ...]:
    from .pattern import ACUTE_AMBER, ACUTE_FAULT
    base = ACUTE_FAULT if signal in ("fault", "error") else ACUTE_AMBER
    return tuple(oklch_to_hex(base.with_(L=0.62 + 0.20 * fraction))
                 for fraction in (i / 15 for i in range(16)))


def _signal_time(signal: str) -> float:
    if signal in ("needs-me", "needs_me"):
        return 0.35
    if signal in ("fault", "error"):
        return 0.70
    return 0.0


@lru_cache(maxsize=512)
def cells(session_id: str, signal: str, width: int) -> tuple[tuple[str, str, str], ...]:
    """(fg, bg, glyph) per column — the one source every formatter renders from."""
    width = max(0, int(width))
    if not width:
        return ()

    # A one-cell-high terminal rule is a projection of a small body patch. Take
    # the local maximum, then select by rank rather than an absolute threshold:
    # every seed gets the same recruitment budget, including degenerate fields
    # whose values all fall below a percentile cutoff.
    #
    # Select WITHIN fixed segments, not globally. A global top-N inherits the 2D
    # patch's clustering: measured on one row of 80 it lit 3 clumps separated by
    # a 33-cell void — "scattered with a lot of black spaces". Per-segment picks
    # keep the clusters (neighbours still win together) while guaranteeing the
    # gap can never exceed ~2 segments.
    _, field = field_for(session_id, width, 3, t=_signal_time(signal))
    values = [max(field.get(x, y) for y in range(field.height)) for x in range(width)]
    segment = 10
    per_segment = max(1, round(_VIVID_FRACTION * segment))
    vivid: set[int] = set()
    for start in range(0, width, segment):
        columns = range(start, min(width, start + segment))
        vivid.update(sorted(columns, key=lambda x: (values[x], x),
                            reverse=True)[:per_segment])
    vivid_count = max(1, len(vivid))

    ground = render(allocate(session_id)).ground_hex
    variants = (_acute_variants(signal) if signal in ("fault", "error", "needs-me", "needs_me")
                else _identity_variants(session_id))
    ranked_vivid = sorted(vivid, key=lambda x: (values[x], x), reverse=True)
    out: list[tuple[str, str, str]] = []
    for x, value in enumerate(values):
        if x not in vivid:
            out.append((ground, ground, "─"))
        else:
            rank = ranked_vivid.index(x)
            colour = variants[min(len(variants) - 1, int((rank + 1) * len(variants) / vivid_count))]
            out.append((colour, ground, "━" if value >= 0.70 else "─"))
    return tuple(out)


def separator_markup(session_id: str, signal: str, width: int) -> str:
    return "".join(f"[{fg} on {bg}]{glyph}[/]"
                   for fg, bg, glyph in cells(session_id, signal, width))


def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))


__all__ = ["cells", "separator", "separator_markup"]
