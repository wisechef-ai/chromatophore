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
    # The tag shape is Rich's grammar, not ours: `[fg on bg]` parses;
    # `[bg:#x #fg]` silently yields an EMPTY Style and the art renders
    # styleless (caught live on Chef — the rule painted one colour).
    # The ground is the shared navy so every cell reads as skin.
    from .color.identity import allocate
    from .pattern import render
    ground = render(allocate(session_id)).ground_hex
    parts = []
    for x in range(width):
        colour = _COLOURS[(x + shift) % len(_COLOURS)]
        parts.append(f"[{colour} on {ground}]{'━' if x % 3 == 0 else '─'}[/]")
    return ''.join(parts)

def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))

__all__ = ["separator", "separator_markup"]
