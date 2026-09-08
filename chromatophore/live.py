"""Live repaint: keeping a running Hermes CLI's colours in sync with its state.

The requirement (Adam, 2026-09-08): "I expect the profile to be selected on the
session start and then dynamically change so it's not like one time load and forget
but continuous that persists with the chat rolling — it can even be lower frequency,
can be less than 1Hz, actually can be 0.2 or even 0.1Hz."

HOW THIS WORKS, AND WHY IT IS SAFE

Hermes ships a global skin watcher, but it only runs inside the tui_gateway process
(tui_gateway/change_watcher.py, started from ws.py and entry.py) and it polls on a
0.5s timer. The classic prompt-toolkit CLI has no such watcher. So the documented
"write the YAML and everyone repaints" path does NOT reach the classic CLI at all.

What DOES work in the classic CLI, verified against the live install:

  skin_engine.set_active_skin(name)      # re-reads the YAML from disk
  cli._apply_tui_skin_style()            # app.style = ...; app.invalidate()

`_build_tui_style_dict` (cli_tui_mixin.py:311) calls
`get_prompt_toolkit_style_overrides()` on every invocation, so it re-reads whatever
the skin engine currently holds. Probe result on this machine: writing new colours
into the active skin's YAML and calling `set_active_skin` again changed the returned
style overrides immediately. That is the whole mechanism.

We reach the running application through prompt_toolkit's own
`get_app_or_none()` rather than by importing Hermes internals or reaching for a
module-level CLI handle (there isn't one). That keeps this a plugin, not a patch:
we touch no core file, and if the API is ever absent we degrade to identity-only.

WHY THE LOW FREQUENCY IS A FEATURE, NOT A COMPROMISE

0.1-0.2 Hz is one repaint every 5-10 seconds. That is far too slow to read as
animation, which is exactly right: continuous motion in peripheral vision is the
fastest route to a UI you learn to ignore, and the cuttlefish itself is static at
rest (its acute displays run 0.38-1 Hz and last a second or two, never continuously).
At this cadence the cost is negligible and the effect is ambient rather than
demanding.

We also repaint only when the palette actually CHANGES. Most ticks are no-ops.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from chromatophore.pattern import Palette

logger = logging.getLogger(__name__)

__all__ = ["LiveRepainter", "apply_palette_now", "DEFAULT_INTERVAL"]


# 8 seconds = 0.125 Hz, inside the 0.1-0.2 Hz band. Chosen over 5s because the
# extra latency is imperceptible for an ambient channel while the syscall and
# repaint budget halves.
DEFAULT_INTERVAL = 8.0


def _skin_engine():
    """Import the skin engine lazily.

    Lazy because a plugin must not explode at import time on a Hermes version that
    moved this module; a missing skin engine degrades this feature, it does not
    break the user's shell.
    """
    from hermes_cli import skin_engine  # noqa: PLC0415 - deliberate lazy import

    return skin_engine


def apply_palette_now(palette: Palette, skin_name: str) -> bool:
    """Write *palette* into the named skin and repaint the running CLI.

    Returns True when a live application was found and repainted. False means the
    colours are on disk and correct but nothing is currently displaying them (for
    example during a non-interactive run) — not an error.
    """
    engine = _skin_engine()
    # Re-activating re-reads the YAML we just wrote; this is the step that makes
    # the change visible rather than merely persisted.
    engine.set_active_skin(skin_name)

    app = _current_app()
    if app is None:
        return False

    # prompt_toolkit's Application does not expose a documented way to rebuild
    # Hermes' style dict, so we go through the CLI object that owns it when we can
    # reach it, and fall back to invalidating so the next render picks up whatever
    # the skin engine now holds.
    cli = _owning_cli(app)
    if cli is not None and hasattr(cli, "_apply_tui_skin_style"):
        try:
            return bool(cli._apply_tui_skin_style())
        except Exception:  # pragma: no cover - defensive across Hermes versions
            logger.debug("chromatophore: _apply_tui_skin_style failed", exc_info=True)

    try:
        app.invalidate()
        return True
    except Exception:  # pragma: no cover
        logger.debug("chromatophore: invalidate failed", exc_info=True)
        return False


def _current_app():
    """The running prompt_toolkit Application, or None outside an interactive CLI."""
    try:
        from prompt_toolkit.application.current import get_app_or_none
    except ImportError:  # pragma: no cover - prompt_toolkit is a Hermes dependency
        return None
    try:
        return get_app_or_none()
    except Exception:  # pragma: no cover
        return None


def _owning_cli(app) -> Optional[object]:
    """Best-effort handle on the HermesCLI instance that built *app*.

    Hermes keeps no module-level CLI singleton, so we look for the back-reference
    the application carries. This is intentionally best-effort: when it fails we
    still repaint via invalidate(), just without the style rebuild.
    """
    for attr in ("_hermes_cli", "hermes_cli", "_cli"):
        cli = getattr(app, attr, None)
        if cli is not None:
            return cli
    return None


class LiveRepainter:
    """A low-frequency background loop that keeps one session's colours current.

    Owns exactly one session's appearance. Started at session start, stopped at
    session end, and safe to stop twice.
    """

    def __init__(
        self,
        compute: Callable[[], Palette],
        write: Callable[[Palette], None],
        skin_name: str,
        *,
        interval: float = DEFAULT_INTERVAL,
    ) -> None:
        if interval <= 0:
            raise ValueError("interval must be positive")
        self._compute = compute
        self._write = write
        self._skin_name = skin_name
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: Palette | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        # Daemon: a cosmetic layer must never be the reason a shell refuses to exit.
        self._thread = threading.Thread(
            target=self._loop, name="chromatophore-repaint", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)

    def tick_once(self) -> bool:
        """One iteration, exposed for tests and for a synchronous first paint.

        Returns True when a repaint actually happened.
        """
        palette = self._compute()
        # The common case is "nothing changed"; comparing first keeps a 0.125 Hz
        # loop from doing any disk or terminal work for a session that is simply
        # sitting there.
        if self._last is not None and palette == self._last:
            return False
        self._last = palette
        self._write(palette)
        return apply_palette_now(palette, self._skin_name)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.tick_once()
            except Exception:
                # A cosmetic loop must never kill the session it is decorating.
                # Log and keep going; a transient registry read or disk hiccup
                # should cost one frame, not the feature.
                logger.debug("chromatophore: repaint tick failed", exc_info=True)
