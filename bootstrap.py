"""Making the theme actually VISIBLE at startup — the fix for "nothing changes".

THE BUG THIS MODULE EXISTS TO FIX

Every earlier version wrote a beautiful 37-key skin and nothing appeared on
screen. The reason is a startup-ordering problem that no amount of engine-level
testing could reveal, because the engine was working perfectly:

  1. `cli.py:511` runs `init_skin_from_config(CLI_CONFIG)` at STARTUP. It reads
     `display.skin` from config.yaml. We never set that key, so it resolved
     `default` and the CLI painted stock Hermes gold — #FFD700, #CD7F32.
  2. Our `on_session_start` hook fires AFTER that, writes the session skin and
     calls `set_active_skin()`. But the repaint path (`_apply_tui_skin_style`)
     only works on a RUNNING prompt_toolkit Application, and at session-start
     there isn't one yet. So the call succeeded and repainted nothing.
  3. `on_session_end` then DELETED the file, so even the next startup had
     nothing to resolve.

Net effect: the plugin was writing skins into a directory nobody read, and the
one moment that mattered — the CLI resolving its palette at startup — always saw
`default`.

HOW IT WAS FOUND, AND WHY IT SURVIVED SO LONG

Every previous check tested the ENGINE API: write a skin, call
`get_prompt_toolkit_style_overrides()`, count the keys. All green, every time,
while the terminal stayed gold. The measurement that actually found it spawns
`hermes` on a real pty and counts the DISTINCT COLOURS IN THE BYTES IT WRITES
(`tools/pty_capture.py`). That reported 6 truecolor values, all of them stock
Hermes gold, and the diagnosis followed in minutes.

The lesson is in the repo now as a test: an API that returns the right colours is
not the same claim as a terminal that paints them.

THE FIX

Maintain ONE stable skin named `cuttlefish` that persists across sessions and is
referenced by `display.skin`. Session start rewrites its CONTENTS for the current
identity; it does not create a new name each time. So:

  * startup resolution finds it (the name never changes),
  * the live repaint still works mid-session (same file, rewritten),
  * session end leaves it in place rather than deleting the only thing the next
    startup could load.

Per-session files still exist for the `watch` board, but the ACTIVE skin — the one
the CLI resolves — is this stable one.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = ["STABLE_SKIN", "ensure_configured", "is_configured", "config_path"]

# The single name `display.skin` points at, for the life of the install.
STABLE_SKIN = "cuttlefish"


def config_path() -> Path:
    """The active Hermes config, honouring $HERMES_HOME (profiles set it)."""
    root = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    return root / "config.yaml"


def _read_display_skin() -> Optional[str]:
    try:
        import yaml

        with open(config_path(), "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        display = cfg.get("display")
        if isinstance(display, dict):
            value = display.get("skin")
            return value.strip() if isinstance(value, str) else None
    except FileNotFoundError:
        return None
    except Exception:
        logger.debug("cuttlefish: could not read display.skin", exc_info=True)
    return None


def is_configured() -> bool:
    return _read_display_skin() == STABLE_SKIN


def ensure_configured(*, apply: bool = True) -> dict:
    """Point `display.skin` at our stable skin, once.

    Returns a report rather than a bool so `doctor` can explain the state to a
    human instead of silently doing nothing.

    Deliberately conservative:
      * if the user has chosen some OTHER non-default skin, we do NOT overwrite
        it — that is their choice, and a theme that hijacks an explicit setting
        is a theme people uninstall. We report `blocked` and let `doctor` say so.
      * the write goes through Hermes' own config writer, never a hand-rolled
        YAML dump: a stray indent here corrupts the file and breaks the gateway.
    """
    current = _read_display_skin()
    if current == STABLE_SKIN:
        return {"state": "already-configured", "display_skin": current}

    if current not in (None, "", "default"):
        return {
            "state": "blocked",
            "display_skin": current,
            "detail": (f"display.skin is {current!r}, set by you. Run "
                       f"`hermes config set display.skin {STABLE_SKIN}` to switch."),
        }

    if not apply:
        return {"state": "would-configure", "display_skin": current}

    try:
        from hermes_cli import config as config_mod

        if getattr(config_mod, "is_managed", lambda: False)():
            return {"state": "blocked", "display_skin": current,
                    "detail": "managed install; config is administrator-controlled"}
        cfg = config_mod.load_config() or {}
        display = cfg.get("display")
        cfg["display"] = display = display if isinstance(display, dict) else {}
        display["skin"] = STABLE_SKIN
        config_mod.save_config(cfg)
        return {"state": "configured", "display_skin": STABLE_SKIN}
    except Exception as exc:
        logger.debug("cuttlefish: could not set display.skin", exc_info=True)
        return {"state": "failed", "display_skin": current, "detail": str(exc)}
