"""Rich-safe input-rule chromatophores driven by the body-pattern field.

WHY THIS IS TEXT: a plugin cannot paint arbitrary terminal pixels through semantic
skin keys. Rich markup is ours to emit, so each cell can carry one measured pigment.
The rule therefore samples the same coherent, seeded body grammar as the mantle
instead of cycling a palette by x-coordinate (the old output was terminal tinsel).
"""
from __future__ import annotations

from functools import lru_cache

from .color.identity import allocate
from .color.oklab import hex_to_oklch, oklch_to_hex
from .palette import dominant_pigments, pigment_hex
from .pattern import render
from .patterns import field_for


def _pigment_variants(name: str) -> tuple[str, ...]:
    base = hex_to_oklch(pigment_hex(name))
    return tuple(oklch_to_hex(base.with_(L=0.50 + 0.30 * fraction))
                 for fraction in (i / 15 for i in range(16)))


def _signal_time(signal: str) -> float:
    if signal in ("needs-me", "needs_me"):
        return 0.35
    if signal in ("fault", "error"):
        return 0.70
    return 0.0


@lru_cache(maxsize=512)
def separator_markup(session_id: str, signal: str, width: int) -> str:
    width = max(0, int(width))
    if not width:
        return ""

    # A one-cell-high terminal rule is a projection of a small body patch. Taking
    # the local maximum preserves transverse recruitment without turning a dark
    # pattern into a flat line; the percentile cut keeps retracted skin dominant.
    _, field = field_for(session_id, width, 3, t=_signal_time(signal))
    values = [max(field.get(x, y) for y in range(field.height)) for x in range(width)]
    ordered = sorted(values)
    cutoff_index = 0.48 if signal in ("needs-me", "needs_me") else (0.66 if signal in ("fault", "error") else 0.58)
    cutoff = ordered[min(len(ordered) - 1, int(len(ordered) * cutoff_index))]

    ground = render(allocate(session_id)).ground_hex
    pigments = tuple(pigment_hex(name) for name in dominant_pigments(session_id))
    parts: list[str] = []
    for x, value in enumerate(values):
        if value <= cutoff:
            colour = ground
            glyph = "─"
        else:
            # Intensity chooses among this session's 2–3 chromatophore hues. It
            # remains a body grammar: neighbouring values recruit neighbouring
            # pigments, rather than exposing every global palette colour.
            level = (value - cutoff) / max(1e-9, 1.0 - cutoff)
            pigment = pigments[min(len(pigments) - 1, int(level * len(pigments)))]
            variants = _pigment_variants(dominant_pigments(session_id)[min(len(pigments) - 1, int(level * len(pigments)))])
            colour = variants[min(len(variants) - 1, int(level * len(variants)))]
            glyph = "━" if value >= 0.70 else "─"
        parts.append(f"[{colour} on {ground}]{glyph}[/]")
    return "".join(parts)


def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))


__all__ = ["separator", "separator_markup"]
