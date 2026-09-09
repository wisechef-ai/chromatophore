"""Painting the TERMINAL's own background — the honest fix for "background keeps
to be black".

WHY THE SKIN CANNOT DO THIS

The classic CLI's `input-area` style template is the empty string, deliberately:
`hermes_cli/skin_engine.py` leaves it unset so typed text inherits whatever
colours the user's terminal already has. Only 18 of the 44 style classes paint a
`bg:` at all, and every one of them is a bar or a menu. There is no app-background
style class to set, so no value of `background` in a skin can tint the window in
the classic CLI. (The desktop/TUI is different — it reads `background` — which is
why we still write the key.)

So the window stays the terminal's own colour, and Adam's report is exactly right:
everything else themed, background still black.

WHAT ACTUALLY WORKS: OSC 11

Terminals expose their own background through OSC 11:

    ESC ] 11 ; #rrggbb BEL      set the background
    ESC ] 111 BEL               reset it to the profile default

This is not a repaint we own — it changes the emulator's state — which is why it
works where a style class cannot, and why resetting on exit is mandatory rather
than polite. Leaving it set would follow the user out of Hermes into their shell.

SUPPORT, AND WHY WE DON'T PROBE FOR IT

Supported by xterm, iTerm2, kitty, alacritty, wezterm, foot, Windows Terminal,
GNOME Terminal/VTE, Konsole. Terminals that do not implement it IGNORE the
sequence silently — an unknown OSC is swallowed, not printed — so the failure
mode is "background unchanged", never garbage on screen.

We deliberately do NOT query first (OSC 11 with `?` asks the terminal to reply).
A query means reading from stdin, and stdin belongs to prompt_toolkit while the
CLI is running; racing it for a reply that may never arrive risks eating the
user's keystrokes. Writing blind is safe; reading is not.

WRITE TO THE TTY, NOT TO STDOUT

The one hazard: this must never reach a pipe or a log. Hermes' output is captured
in cron jobs and `-z` runs, and an escape sequence in a log is corruption. So we
open /dev/tty directly and skip entirely when there is no controlling terminal.
That is also what stops this from repeating the mistake it replaces: the previous
banner printed raw ANSI through `print()`, which is exactly how a wall of
`?[38;2;4;28;0m?[48;2;5;33;0m` ends up in a transcript.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

__all__ = ["set_terminal_background", "reset_terminal_background", "supported"]

_BEL = "\a"


def supported() -> bool:
    """Is it safe to emit OSC 11 right now?

    Conservative on purpose: a false negative costs a tinted background, a false
    positive costs escape sequences in someone's log file.
    """
    if os.environ.get("NO_COLOR"):
        return False
    term = os.environ.get("TERM", "")
    if not term or term == "dumb":
        return False
    # Multiplexers pass OSC through only when configured to, and a wrong guess
    # here paints the WRONG pane. Skip rather than gamble.
    if os.environ.get("TMUX") or term.startswith("screen"):
        return False
    return True


def _write_tty(seq: str) -> bool:
    """Write an escape sequence to the controlling terminal only.

    Never stdout: that is what lands escape codes in cron output and `-z`
    transcripts. Returns True if the sequence actually went to a terminal.
    """
    try:
        with open("/dev/tty", "w", encoding="utf-8") as tty:
            tty.write(seq)
            tty.flush()
        return True
    except OSError:
        # No controlling terminal (cron, pipe, CI). Correct to do nothing.
        return False
    except Exception:  # pragma: no cover - defensive
        logger.debug("cuttlefish: OSC write failed", exc_info=True)
        return False


def set_terminal_background(hex_color: str | None) -> bool:
    """Set the terminal's background to *hex_color*. True if it was emitted."""
    if not hex_color or not supported():
        return False
    value = hex_color.strip()
    if not (len(value) == 7 and value.startswith("#")):
        return False
    try:
        int(value[1:], 16)
    except ValueError:
        return False
    return _write_tty(f"\033]11;{value}{_BEL}")


def reset_terminal_background() -> bool:
    """Restore the terminal's configured background (OSC 111)."""
    if not supported():
        return False
    return _write_tty(f"\033]111{_BEL}")
