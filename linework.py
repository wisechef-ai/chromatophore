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

    # A one-cell-high terminal rule is a projection of a small body patch. Take
    # the local maximum, then select by rank rather than an absolute threshold:
    # every seed gets the same sparse recruitment budget, including degenerate
    # fields whose values all fall below a percentile cutoff.
    _, field = field_for(session_id, width, 3, t=_signal_time(signal))
    values = [max(field.get(x, y) for y in range(field.height)) for x in range(width)]
    vivid_count = max(1, round(0.16 * width))
    vivid = set(sorted(range(width), key=lambda x: (values[x], x), reverse=True)[:vivid_count])

    ground = render(allocate(session_id)).ground_hex
    names = dominant_pigments(session_id)
    parts: list[str] = []
    ranked_vivid = sorted(vivid, key=lambda x: (values[x], x), reverse=True)
    for x, value in enumerate(values):
        if x not in vivid:
            colour = ground
            glyph = "─"
        else:
            # Acute signals recruit a different identity pigment. Fault also
            # uses the companion pigment for some pearls, guaranteeing more than
            # a single quantised colour even when the field is degenerate.
            if signal in ("fault", "error") and len(names) > 1:
                pigment_index = 0 if ranked_vivid.index(x) % 3 else 1
            elif signal in ("needs-me", "needs_me") and len(names) > 1:
                pigment_index = 1
            else:
                pigment_index = 0
            rank = ranked_vivid.index(x)
            variants = _pigment_variants(names[pigment_index])
            colour = variants[min(len(variants) - 1, int((rank + 1) * len(variants) / vivid_count))]
            glyph = "━" if value >= 0.70 else "─"
        parts.append(f"[{colour} on {ground}]{glyph}[/]")
    return "".join(parts)


def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))


__all__ = ["separator", "separator_markup"]
