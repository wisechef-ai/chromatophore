"""Prompt-toolkit chrome rendering for the persistent input rule."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .color.oklab import oklch_to_hex
from .linework import separator_markup
from .pattern import ACUTE_AMBER, ACUTE_FAULT
from .session import Signal, collapse

_TAG = re.compile(r"\[#([0-9A-Fa-f]{6}) on #([0-9A-Fa-f]{6})\](.*?)\[/\]", re.DOTALL)


def rich_to_prompt_toolkit(markup: str) -> list[tuple[str, str]]:
    """Convert linework's restricted Rich cell grammar to PT fragments.

    The linework renderer intentionally emits only ``[#fg on #bg]text[/]`` cells.
    Parse that grammar explicitly rather than passing Rich markup to a PT style.
    """
    fragments: list[tuple[str, str]] = []
    pos = 0
    for match in _TAG.finditer(markup):
        if match.start() != pos:
            raise ValueError("unsupported or malformed Rich markup")
        fg, bg, text = match.groups()
        if not text:
            raise ValueError("empty Rich cell")
        fragments.append((f"fg:#{fg.lower()} bg:#{bg.lower()}", text))
        pos = match.end()
    if pos != len(markup):
        raise ValueError("unsupported or malformed Rich markup")
    return fragments


def _acute_style(signal: Signal) -> str:
    colour = oklch_to_hex(ACUTE_FAULT if signal is Signal.FAULT else ACUTE_AMBER)
    return f"bg:{colour}"


@lru_cache(maxsize=512)
def _rule_fragments(session_id: str, signal: Signal, width: int) -> tuple[tuple[str, str], ...]:
    return tuple(rich_to_prompt_toolkit(separator_markup(session_id, signal.value, width)))


def chrome_renderer(surface: str, width: int, ctx: dict[str, Any]) -> list[tuple[str, str]] | None:
    """Render persistent chrome, failing closed on any repaint-path problem."""
    try:
        if surface == "status_bar_bg":
            signal = collapse(ctx.get("pet_state"))
            if signal is Signal.RESTING:
                return None
            return [(_acute_style(signal), " ")]
        if surface not in {"input_rule_top", "input_rule_bot"}:
            return None
        session_id = ctx.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return None
        signal = collapse(ctx.get("pet_state"))
        return list(_rule_fragments(session_id, signal, int(width)))
    except Exception:
        return None


__all__ = ["chrome_renderer", "rich_to_prompt_toolkit"]
