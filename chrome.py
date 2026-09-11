"""Prompt-toolkit chrome rendering for the persistent input rule."""
from __future__ import annotations

from typing import Any

from .color.identity import allocate
from .color.oklab import oklch_to_hex
from .linework import cells
from .pattern import ACUTE_AMBER, ACUTE_FAULT, render
from .session import Signal, collapse


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
        if surface == "transcript_line":
            session_id = ctx.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                return None
            row_key = ctx.get("row_key")
            row_key = int(row_key) if isinstance(row_key, int) and not isinstance(row_key, bool) else 0
            identity = allocate(session_id)
            ground = render(identity).ground_hex
            pigment = oklch_to_hex(identity.oklch.with_(L=0.235, C=identity.oklch.C * 0.80))
            grid = cells(session_id, Signal.RESTING.value, int(width), row_key)
            return [(f"bg:{pigment if fg != ground else ground}", " ")
                    for fg, _bg, _glyph in grid]
        if surface not in {"input_rule_top", "input_rule_bot"}:
            return None
        session_id = ctx.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return None
        return [(f"fg:{fg} bg:{bg}", glyph)
                for fg, bg, glyph in cells(session_id, signal.value, int(width))]
    except Exception:
        return None


__all__ = ["chrome_renderer"]
