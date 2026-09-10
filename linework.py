"""Rich-safe separator rows for Tier A classic CLI output."""
from __future__ import annotations
from functools import lru_cache
from .chrome import chrome_fragments

@lru_cache(maxsize=256)
def separator_markup(session_id: str, signal, width: int) -> str:
    return ''.join(f'[{style}]{char}[/]' for style, char in chrome_fragments(session_id, signal, width))

def separator(session_id: str, signal, width: int) -> str:
    return separator_markup(session_id, signal, width)

__all__ = ['separator', 'separator_markup']
