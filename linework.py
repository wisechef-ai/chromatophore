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

    # A one-cell-high rule is a projection of a small body patch: take the local
    # maximum, then pick by rank per 10-column segment. Rank (not an absolute
    # threshold) gives every seed the same budget, including degenerate fields.
    # Segments (not a global top-N) stop the 2D field's clustering from leaving
    # voids — globally it lit 3 clumps around a 33-cell dead gap.
    _, field = field_for(session_id, width, 3, t=_signal_time(signal))
    values = [max(field.get(x, y) for y in range(field.height)) for x in range(width)]
    hottest = lambda columns, n: sorted(columns, key=lambda x: (values[x], x), reverse=True)[:n]
    segment = 10
    vivid = {x for start in range(0, width, segment)
             for x in hottest(range(start, min(width, start + segment)),
                              max(1, round(_VIVID_FRACTION * segment)))}

    ground = render(allocate(session_id)).ground_hex
    variants = (_acute_variants(signal) if signal in ("fault", "error", "needs-me", "needs_me")
                else _identity_variants(session_id))
    rank = {x: i for i, x in enumerate(hottest(vivid, len(vivid)))}
    out: list[tuple[str, str, str]] = []
    for x, value in enumerate(values):
        if x not in vivid:
            out.append((ground, ground, "─"))
        else:
            # Brightest cell gets the palest pigment — retracted skin reveals
            # the layer beneath, it does not simply go dark.
            step = int((rank[x] + 1) * len(variants) / len(vivid))
            out.append((variants[min(len(variants) - 1, step)], ground,
                        "━" if value >= 0.70 else "─"))
    return tuple(out)


def separator_markup(session_id: str, signal: str, width: int) -> str:
    return "".join(f"[{fg} on {bg}]{glyph}[/]"
                   for fg, bg, glyph in cells(session_id, signal, width))


def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))


__all__ = ["cells", "separator", "separator_markup"]
