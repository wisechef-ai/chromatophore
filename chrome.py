"""Optional Tier-B prompt-toolkit chrome renderer.

Tier A remains the ordinary skin keys.  This module is deliberately independent of
Hermes core: it only returns the documented style/text fragment pairs.
"""
from __future__ import annotations
from functools import lru_cache
from .patterns import field_for
from .pattern import render
from .color.identity import allocate

@lru_cache(maxsize=256)
def chrome_fragments(session_id: str, signal, width: int) -> tuple[tuple[str, str], ...]:
    width = max(0, int(width))
    identity = allocate(session_id)
    from .session import Signal
    if isinstance(signal, str):
        signal = Signal(signal) if signal in {s.value for s in Signal} else Signal.RESTING
    palette = render(identity, signal)
    colors = palette.skin_colors()
    field = field_for(session_id, max(1, width), 2)[1]
    bg = colors.get('status_bar_bg', palette.ground_hex)
    # Quantised expansion yields visible cells without a smooth gradient.
    out = []
    for x in range(width):
        v = field.get(x, 0)
        fg = colors.get('ui_accent', palette.identity_hex) if v > .42 else colors.get('banner_dim', palette.sheen_dim_hex)
        out.append((f'bg:{bg} {fg}', '━' if v > .55 else '─'))
    return tuple(out)

def chrome_renderer(surface: str, width: int, ctx: dict):
    if surface not in {'input_rule_top', 'input_rule_bot', 'status_bar_bg'}:
        return None
    sid = str(ctx.get('session_id') or '')
    if not sid:
        return None
    return list(chrome_fragments(sid, ctx.get('signal', 'resting'), width))

__all__ = ['chrome_fragments', 'chrome_renderer']
