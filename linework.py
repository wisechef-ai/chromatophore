"""Rich-safe separator rows made from discrete chromatophore cells.

WHY THIS IS TEXT: a plugin cannot paint arbitrary terminal pixels through semantic
skin keys. Rich markup is ours to emit, so each cell can carry its own pigment.
"""
from __future__ import annotations
from functools import lru_cache
from .palette import PIGMENTS, pigment_hex

_COLOURS = tuple(pigment_hex(n) for n in PIGMENTS)

@lru_cache(maxsize=512)
def separator_markup(session_id: str, signal: str, width: int) -> str:
    width = max(0, int(width))
    names = tuple(PIGMENTS)
    shift = sum(ord(c) for c in session_id) % len(names)
    if signal in ("needs-me", "needs_me"):
        shift += 1
    elif signal in ("fault", "error"):
        shift += 2
    parts = []
    for x in range(width):
        colour = _COLOURS[(x + shift) % len(_COLOURS)]
        parts.append(f"[bg:#1C1B43 {colour}]{'━' if x % 3 == 0 else '─'}[/]")
    return ''.join(parts)

def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))

__all__ = ["separator", "separator_markup"]
