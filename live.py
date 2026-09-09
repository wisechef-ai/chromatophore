"""The animator: state changes become motion, rest stays perfectly still.

Adam, 2026-09-09, choosing the cadence: *"Transition-only: animate hard during
state changes, then perfectly still."* That is also what the animal does — a
cuttlefish at rest holds its pattern; the motion is in the transitions.

So this module inverts v1's design. v1 ran a fixed 0.125 Hz tick that recomputed
the palette forever and repainted on the rare occasions it differed. This runs a
SLOW WATCHER that does nothing but detect change, and a SHORT, FAST ANIMATOR that
only exists while a transition is in flight:

    watcher   0.5 Hz, no repaint, no disk write   <- the steady state, ~free
    animator  ~24 fps, for 0.4-2.4s, then EXITS   <- only during a change

Idle cost is one registry read every two seconds and nothing else: no file write,
no skin activation, no prompt_toolkit invalidate. The v1 loop wrote and re-read the
skin file on every tick forever, which was both the wrong biology and a permanent
tax for zero visible benefit.

FRAME BUDGET, MEASURED

On adam-xps against the real engine: atomic write with fsync 4.1ms, set_active_skin
7.4ms, style rebuild 0.2ms => 11.7ms per frame, a ~85 Hz ceiling before
prompt_toolkit's own redraw. Dropping fsync for in-flight frames (safe — atomicity
is os.replace's job, see skinio.write_colors) takes the write to 0.3ms and the frame
to ~8ms. At the default 24 fps we spend ~19% of a core for at most 2.4 seconds, and
0% thereafter.

The animator adapts: if a frame overruns its slot it drops frames rather than
falling behind, so a loaded machine sees a shorter, coarser transition — never a
transition that finishes late and repaints over whatever came next.
"""

from __future__ import annotations

import gc
import logging
import threading
import time
import weakref
from typing import Callable, Mapping, Optional

from .morph import BLANCH, RECOVER, SETTLE, Trajectory, morph
from .pattern import Palette

logger = logging.getLogger(__name__)

__all__ = [
    "Animator",
    "apply_palette_now",
    "apply_colors_now",
    "trajectory_for",
    "DEFAULT_FPS",
    "WATCH_INTERVAL",
]

# 24 fps: the lowest rate at which a 0.4s blanch still reads as motion rather than
# as three discrete steps. Above ~30 the extra frames are invisible on a terminal
# whose own redraw is the bottleneck.
DEFAULT_FPS = 24.0

# The watcher only detects change; it never repaints. 2s is well inside the latency
# a human tolerates for an ambient channel, and costs one registry read.
WATCH_INTERVAL = 2.0


def trajectory_for(previous: Optional[Palette], current: Palette) -> Trajectory:
    """Which measured trajectory this state change should follow.

    The mapping is the biology, not a preference:

    - Anything -> a signal (NEEDS_ME/FAULT) is a BLANCH: fast, direct, open-loop.
      The animal does not deliberate about a threat, and neither should a fault
      indicator — if it eased in gently you would miss the moment it happened.
    - A signal -> resting is a RECOVER: slower, decelerating, staggered onsets.
      The identity comes back the way the skin does, not with a snap.
    - First paint of a session is a SETTLE: the tortuous, intermittent search of
      camouflage matching. The session is finding out who it is.
    """
    from .session import Signal

    if previous is None:
        return SETTLE
    was_resting = previous.signal is Signal.RESTING
    is_resting = current.signal is Signal.RESTING
    if was_resting and not is_resting:
        return BLANCH
    if not was_resting and is_resting:
        return RECOVER
    # Signal -> different signal (amber to red): still a threat escalation.
    if not is_resting:
        return BLANCH
    # Resting -> resting with a different identity (the live set changed around us).
    return SETTLE


def _skin_engine():
    """Import the skin engine lazily.

    Lazy because a plugin must not explode at import time on a Hermes version that
    moved this module; a missing skin engine degrades this feature, it does not
    break the user's shell.
    """
    from hermes_cli import skin_engine  # noqa: PLC0415 - deliberate lazy import

    return skin_engine


def apply_colors_now(skin_name: str) -> bool:
    """Re-read the skin from disk and restyle the running CLI.

    Split from the write deliberately: during an animation the caller writes many
    frames and calls this once per frame, and the write path must not re-resolve
    the CLI every time.
    """
    engine = _skin_engine()
    # Re-activating re-reads the YAML we just wrote; this is the step that makes
    # the change visible rather than merely persisted.
    engine.set_active_skin(skin_name)

    cli = _find_cli()
    if cli is None:
        return False
    try:
        # The Application is built ONCE per session (cli.py sets `self._app` in
        # run()) and its style is resolved once with it, so ONLY this call makes
        # a skin change visible. A bare invalidate() re-renders with the same
        # style object and shows nothing.
        return bool(cli._apply_tui_skin_style())
    except Exception:  # pragma: no cover - defensive across Hermes versions
        logger.debug("cuttlefish: _apply_tui_skin_style failed", exc_info=True)
        return False


def apply_palette_now(palette: Palette, skin_name: str) -> bool:
    """Write *palette* into the named skin and repaint the running CLI.

    Returns True when a live CLI was found and restyled. False means the colours
    are on disk and correct but nothing is currently displaying them (a
    non-interactive run, for example) — not an error.
    """
    from .skinio import write_skin

    write_skin(palette)
    return apply_colors_now(skin_name)


# Resolving the owning CLI needs a gc sweep, far too expensive to repeat per frame.
# One process hosts one CLI, so cache it weakly — this reference must never be what
# keeps a dead CLI alive.
_cli_ref: "weakref.ReferenceType | None" = None


def _find_cli() -> Optional[object]:
    """The live HermesCLI instance in this process, or None.

    Hermes exposes no module-level CLI singleton and the Application carries no
    back-reference (checked: `_hermes_cli`, `hermes_cli`, `_cli` are all absent),
    so we ask the garbage collector for the object that owns a prompt_toolkit
    Application AND can rebuild its style. Deliberately independent of
    prompt_toolkit's "current application" context, which is not set on the
    worker thread Hermes uses for session hooks.
    """
    global _cli_ref

    if _cli_ref is not None:
        cli = _cli_ref()
        if cli is not None and getattr(cli, "_app", None) is not None:
            return cli
        _cli_ref = None  # stale: the CLI went away

    for obj in gc.get_objects():
        try:
            if (
                getattr(obj, "_app", None) is not None
                and hasattr(obj, "_apply_tui_skin_style")
                and hasattr(obj, "_build_tui_style_dict")
            ):
                _cli_ref = weakref.ref(obj)
                return obj
        except Exception:
            # Some objects raise on attribute access; they are not the CLI.
            continue
    return None


class Animator:
    """Watches for state changes and animates the transitions between them.

    Owns exactly one session's appearance. Started at session start, stopped at
    session end, and safe to stop twice.

    Thread model: ONE background thread runs both the slow watch and the fast
    animation, sequentially. A second thread would let a new transition start
    while the previous one was still writing frames, and the two would fight over
    the same file — the last writer would win at an arbitrary point mid-fade and
    latch a half-interpolated palette.
    """

    def __init__(
        self,
        compute: Callable[[], Palette],
        skin_name: str,
        *,
        fps: float = DEFAULT_FPS,
        watch_interval: float = WATCH_INTERVAL,
        tint_background: bool = True,
        animate: bool = True,
        write_colors: Callable[..., object] | None = None,
        apply_fn: Callable[[str], bool] | None = None,
    ) -> None:
        if watch_interval <= 0:
            raise ValueError("watch_interval must be positive")
        self._compute = compute
        self._skin_name = skin_name
        self._fps = fps
        self._watch_interval = watch_interval
        self._tint_background = tint_background
        self._animate = animate
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: Palette | None = None
        self._last_colors: dict[str, str] | None = None
        self._transitions = 0
        # Injectable for tests: the real ones touch disk and the live CLI.
        if write_colors is None:
            from .skinio import write_colors as _wc

            write_colors = _wc
        self._write_colors = write_colors
        self._apply = apply_fn or apply_colors_now

    # --- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        # Daemon: a cosmetic layer must never be the reason a shell refuses to exit.
        self._thread = threading.Thread(
            target=self._loop, name="cuttlefish-animator", daemon=True
        )
        self._thread.start()

    def stop(self, *, timeout: float = 3.0) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=timeout)

    @property
    def transitions(self) -> int:
        """How many transitions have been animated. Used by tests and `doctor`."""
        return self._transitions

    # --- the work ----------------------------------------------------------

    def _colors_for(self, palette: Palette) -> dict[str, str]:
        from .skinio import BASE_DIALECT

        colors = dict(BASE_DIALECT)
        colors.update(palette.skin_colors(tint_background=self._tint_background))
        return colors

    def tick_once(self) -> bool:
        """Detect a change and, if there is one, animate to it. True if we moved.

        The comparison is on the resolved palette, so a tick that finds the world
        unchanged does zero disk and zero terminal work — which is the entire
        steady state.
        """
        palette = self._compute()
        if self._last is not None and palette == self._last:
            return False

        target = self._colors_for(palette)
        trajectory = trajectory_for(self._last, palette)
        start = self._last_colors

        if start is None or not self._animate:
            self._commit(palette, target)
            return True

        self._transitions += 1
        self._run_trajectory(
            palette.session_id, start, target, trajectory,
            seed=(palette.session_id, self._transitions),
        )
        self._commit(palette, target)
        return True

    def _commit(self, palette: Palette, colors: Mapping[str, str]) -> None:
        """Write the final, durable frame and record it as the new resting state."""
        self._write_colors(
            palette.session_id,
            colors,
            description=f"cuttlefish session {palette.session_id} ({palette.signal.value})",
            durable=True,
        )
        self._apply(self._skin_name)
        self._last = palette
        self._last_colors = dict(colors)

    def _run_trajectory(
        self,
        session_id: str,
        start: Mapping[str, str],
        target: Mapping[str, str],
        trajectory: Trajectory,
        *,
        seed: object,
    ) -> None:
        """Play *trajectory* in real time, dropping frames rather than running long.

        Wall-clock driven, not frame-counted: we ask the trajectory where it should
        be at the elapsed time, so a slow frame skips ahead instead of stretching
        the animation. A transition that overruns would still be repainting after
        the next state change had already been detected.
        """
        began = time.monotonic()
        interval = 1.0 / self._fps if self._fps > 0 else trajectory.duration
        next_frame = began

        while not self._stop.is_set():
            now = time.monotonic()
            elapsed = now - began
            if elapsed >= trajectory.duration:
                break
            colors = morph(start, target, trajectory, elapsed, seed=seed)
            try:
                self._write_colors(session_id, colors, durable=False)
                self._apply(self._skin_name)
            except Exception:
                # One dropped frame is invisible; aborting mid-fade is not. Keep
                # going — `_commit` guarantees we land on the target regardless.
                logger.debug("cuttlefish: animation frame failed", exc_info=True)

            next_frame += interval
            sleep_for = next_frame - time.monotonic()
            if sleep_for < 0:
                # Behind schedule: resync rather than accumulate lateness, which
                # is what turns a 2.4s recovery into a 6s one on a loaded box.
                next_frame = time.monotonic()
                continue
            if self._stop.wait(sleep_for):
                return

    def _loop(self) -> None:
        while not self._stop.wait(self._watch_interval):
            try:
                self.tick_once()
            except Exception:
                # A cosmetic loop must never kill the session it is decorating.
                # Log and keep going; a transient registry read or disk hiccup
                # should cost one frame, not the feature.
                logger.debug("cuttlefish: watch tick failed", exc_info=True)
