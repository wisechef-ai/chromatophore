"""Optional Tier-B prompt-toolkit chrome renderer.

Tier A remains the ordinary skin keys.  This module is deliberately independent of
Hermes core: it only returns the documented style/text fragment pairs.
"""
from __future__ import annotations
from functools import lru_cache
from .patterns import field_for
from .palette import pigment_hex, dominant_pigments
from .pattern import render
from .color.identity import allocate

@lru_cache(maxsize=256)
def chrome_fragments(session_id: str, signal, width: int) -> tuple[tuple[str, str], ...]:
    width = max(0, int(width))
    identity = allocate(session_id)
    from .session import Signal
    if isinstance(signal, str):
        aliases = {'needs-me': Signal.NEEDS_ME, 'resting': Signal.RESTING, 'fault': Signal.FAULT}
        signal = aliases.get(signal, Signal.RESTING)
    # Keep separators fast: chrome is a small deterministic raster, not the mantle.
    from .palette import PIGMENTS
    pigments = [pigment_hex(n) for n in PIGMENTS]
    bg = '#1C1B43' if signal is Signal.RESTING else ('#3B2510' if signal is Signal.NEEDS_ME else '#3B1515')
    out = []
    for x in range(width):
        fg = pigments[(x + (0 if signal is Signal.RESTING else 1)) % len(pigments)]
        out.append((f'bg:{bg} {fg}', '━' if x % 3 == 0 else '─'))
    return tuple(out)

def chrome_renderer(surface: str, width: int, ctx: dict):
    if surface not in {'input_rule_top', 'input_rule_bot', 'status_bar_bg'}:
        return None
    sid = str(ctx.get('session_id') or '')
    if not sid:
        return None
    return list(chrome_fragments(sid, ctx.get('signal', 'resting'), width))

__all__ = ['chrome_fragments', 'chrome_renderer']
