"""Hermes plugin entrypoint for chromatophore.

Everything here goes through the documented plugin surface — `register_cli_command`,
`register_hook`, `register_command`. No Hermes core file is modified, which is both
the owner's constraint and upstream's own rule (plugins/AGENTS.md: "Plugins never
touch core").

Lifecycle:

  session start -> allocate an identity against the currently-live sessions, write
                   the session's skin, activate it, start the low-frequency repaint
                   loop, and sweep any skins orphaned by an earlier crash.
  during        -> the repaint loop re-evaluates every ~8s (0.125 Hz) and repaints
                   ONLY when the resolved palette actually changed.
  session end   -> stop the loop, restore the previous skin if we still own the
                   current one (compare-and-set), and delete our file.

The compare-and-set on restore matters: if the user ran /skin themselves while we
were active, blindly reverting would stomp their choice. We only put back what we
took if nothing else has changed it since.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .color.identity import allocate
from .live import DEFAULT_INTERVAL, LiveRepainter, apply_palette_now
from .pattern import render
from .session import Signal, snapshot
from .skinio import remove_skin, session_skin_name, sweep_orphans, write_skin

logger = logging.getLogger(__name__)

PLUGIN_NAME = "chromatophore"

# Module state: one session per process, so a single slot is honest here rather
# than a registry that implies multi-tenancy we do not have in the classic CLI.
_state: dict[str, Any] = {
    "session_id": None,
    "repainter": None,
    "previous_skin": None,
    "identity": None,
}


def _current_skin_name() -> Optional[str]:
    try:
        from hermes_cli.skin_engine import get_active_skin_name

        return get_active_skin_name()
    except Exception:
        return None


def _live_identity_colors(exclude: str) -> list[str]:
    """Hex colours of every OTHER live session, so allocation can avoid them."""
    others = [s.session_id for s in snapshot() if s.session_id != exclude]
    return [allocate(sid).hex for sid in others]


def _compute_palette(session_id: str, signal: Signal = Signal.RESTING):
    """Resolve the palette for this session right now.

    Recomputed each tick rather than cached because the live set moves: a session
    that started alone should still look good once five more appear.
    """
    live = _live_identity_colors(session_id)
    identity = allocate(session_id, live)
    _state["identity"] = identity
    sess = next((s for s in snapshot() if s.session_id == session_id), None)
    age = sess.age_label if sess is not None else ""
    return render(identity, signal, age_label=age)


def on_session_start(session_id: str = "", **_kw) -> None:
    """Claim an identity and begin the live loop."""
    if not session_id:
        return
    _state["session_id"] = session_id
    _state["previous_skin"] = _current_skin_name()

    # Reclaim files left behind by sessions that died without cleanup (kill -9,
    # power loss). Cheap, and it keeps the skins directory from growing forever.
    try:
        sweep_orphans({s.session_id for s in snapshot()} | {session_id})
    except Exception:
        logger.debug("chromatophore: orphan sweep failed", exc_info=True)

    skin_name = session_skin_name(session_id)

    def _write(palette) -> None:
        write_skin(palette)

    repainter = LiveRepainter(
        compute=lambda: _compute_palette(session_id),
        write=_write,
        skin_name=skin_name,
        interval=DEFAULT_INTERVAL,
    )
    _state["repainter"] = repainter

    # Paint once synchronously so the session is already itself on the first
    # prompt, rather than plain for the first 8 seconds.
    try:
        palette = _compute_palette(session_id)
        write_skin(palette)
        apply_palette_now(palette, skin_name)
    except Exception:
        logger.debug("chromatophore: initial paint failed", exc_info=True)

    repainter.start()


def on_session_end(session_id: str = "", **_kw) -> None:
    """Stop the loop and hand the terminal back exactly as we found it."""
    repainter = _state.get("repainter")
    if repainter is not None:
        repainter.stop()
    _state["repainter"] = None

    sid = session_id or _state.get("session_id")
    if not sid:
        return

    ours = session_skin_name(sid)
    previous = _state.get("previous_skin")
    # Compare-and-set: only restore if OUR skin is still the active one. If the
    # user switched skins mid-session, that choice wins.
    if previous and _current_skin_name() == ours:
        try:
            from hermes_cli.skin_engine import set_active_skin

            set_active_skin(previous)
        except Exception:
            logger.debug("chromatophore: skin restore failed", exc_info=True)

    try:
        remove_skin(sid)
    except Exception:
        logger.debug("chromatophore: skin cleanup failed", exc_info=True)
    _state["session_id"] = None


def _cli_setup(parser) -> None:
    sub = parser.add_subparsers(dest="chroma_cmd")
    watch = sub.add_parser("watch", help="Live board of every session and what it needs")
    watch.add_argument("--once", action="store_true", help="Render once and exit")
    watch.add_argument("--interval", type=float, default=2.0, help="Refresh seconds")
    sub.add_parser("legend", help="Explain the colour language")
    sub.add_parser("doctor", help="Diagnose terminal capability and current state")


def _cli_handler(args) -> int:
    from .cli import run_doctor, run_legend, run_watch

    cmd = getattr(args, "chroma_cmd", None) or "watch"
    if cmd == "legend":
        return run_legend()
    if cmd == "doctor":
        return run_doctor()
    return run_watch(once=getattr(args, "once", False),
                     interval=getattr(args, "interval", 2.0))


def register(ctx) -> None:
    """Wire the plugin into Hermes.

    Each registration is guarded independently: an older Hermes missing one surface
    should lose that one feature, not the whole plugin. Chef currently runs a
    different version from the workstation, so this is a real case, not theory.
    """
    try:
        ctx.register_cli_command(
            "chromatophore",
            help="Session colour identity and state signalling",
            setup_fn=_cli_setup,
            handler_fn=_cli_handler,
            description="Ambient session identity and intervention signalling.",
        )
    except Exception:
        logger.debug("chromatophore: CLI registration unavailable", exc_info=True)

    for hook, fn in (("on_session_start", on_session_start),
                     ("on_session_end", on_session_end)):
        try:
            ctx.register_hook(hook, fn)
        except Exception:
            logger.debug("chromatophore: hook %s unavailable", hook, exc_info=True)
