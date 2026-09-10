"""Hermes plugin entrypoint for cuttlefish-theme.

Everything here goes through the documented plugin surface — `register_cli_command`,
`register_hook`, `ctx.get_config`. No Hermes core file is modified, which is both
the owner's constraint and upstream's own rule (plugins/AGENTS.md: "Plugins never
touch core").

Lifecycle:

  session start -> allocate an identity against the currently-live sessions, paint
                   the mantle, SETTLE into it (the tortuous camouflage search), start
                   the slow watcher, and sweep skins orphaned by an earlier crash.
  during        -> the watcher checks every 2s and does nothing at all unless the
                   state changed; when it does, the transition is ANIMATED
                   (blanch on a new signal, recover on its release) and then the
                   session is perfectly still again.
  session end   -> stop the animator, restore the previous skin if we still own the
                   current one (compare-and-set), and delete our file.

The compare-and-set on restore matters: if the user ran /skin themselves while we
were active, blindly reverting would stomp their choice. We only put back what we
took if nothing else has changed it since.
"""

from __future__ import annotations

import logging
from typing import Any

from .bootstrap import ensure_configured
from .color.identity import allocate
from .live import DEFAULT_FPS, WATCH_INTERVAL, Animator, apply_palette_now
from .pattern import render
from .session import Signal, snapshot
from .skinio import remove_skin, stable_skin_name, sweep_orphans, write_skin
from .termbg import reset_terminal_background, set_terminal_background

logger = logging.getLogger(__name__)


PLUGIN_NAME = "cuttlefish-theme"

# Module state: one session per process, so a single slot is honest here rather
# than a registry that implies multi-tenancy we do not have in the classic CLI.
_state: dict[str, Any] = {
    "session_id": None,
    "animator": None,
    "previous_skin": None,
    "identity": None,
}

# Defaults are the answers Adam gave on 2026-09-09. Every one is overridable via
# `plugins.entries.cuttlefish-theme.settings.<key>` — a theme that cannot be turned
# down is a theme people uninstall.
_DEFAULTS = {
    "animate": True,          # animate transitions (False = v1 snap behaviour)
    "tint_background": True,  # per-session near-black mantle
    "fps": DEFAULT_FPS,
    "watch_interval": WATCH_INTERVAL,
    # Paint the TERMINAL's own background via OSC 11. The classic CLI cannot set
    # an app background (its `input-area` style is deliberately empty so typed
    # text keeps your terminal's colours), so this is the only honest way to make
    # the window itself carry the session's near-black.
    "terminal_background": True,
}


def _settings(ctx=None) -> dict[str, Any]:
    """Resolve settings, falling back to defaults for anything unset or malformed.

    A bad value in config must not break the session — it degrades to the default
    and logs. This runs inside session start, where an exception is very expensive.
    """
    values = dict(_DEFAULTS)
    if ctx is None:
        return values
    for key, default in _DEFAULTS.items():
        try:
            raw = ctx.get_config(key, default)
        except Exception:
            continue
        if raw is None:
            continue
        try:
            if isinstance(default, bool):
                values[key] = bool(raw)
            elif isinstance(default, int) and not isinstance(default, bool):
                values[key] = int(raw)
            elif isinstance(default, float):
                values[key] = float(raw)
            else:
                values[key] = raw
        except (TypeError, ValueError):
            logger.debug("cuttlefish: bad config for %s: %r", key, raw)
    return values


def _current_skin_name() -> str | None:
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


def on_session_start(session_id: str = "", _ctx=None, **_kw) -> None:
    """Claim an identity and settle into it."""
    if not session_id:
        return
    settings = _settings(_ctx or _state.get("ctx"))
    _state["session_id"] = session_id
    _state["previous_skin"] = _current_skin_name()

    # Reclaim files left behind by sessions that died without cleanup (kill -9,
    # power loss). Cheap, and it keeps the skins directory from growing forever.
    try:
        sweep_orphans({s.session_id for s in snapshot()} | {session_id})
    except Exception:
        logger.debug("cuttlefish: orphan sweep failed", exc_info=True)

    # THE ACTIVE SKIN IS THE STABLE ONE, not a per-session name. `display.skin`
    # is resolved at CLI startup before any session exists, so a session-scoped
    # name resolves to nothing and the CLI falls back to stock gold. bootstrap.py
    # documents the whole failure.
    skin_name = stable_skin_name()
    try:
        report = ensure_configured()
        if report["state"] not in ("configured", "already-configured"):
            logger.debug("cuttlefish: display.skin not ours: %s", report)
    except Exception:
        logger.debug("cuttlefish: ensure_configured failed", exc_info=True)

    animator = Animator(
        compute=lambda: _compute_palette(session_id),
        skin_name=skin_name,
        fps=settings["fps"],
        watch_interval=settings["watch_interval"],
        tint_background=settings["tint_background"],
        animate=settings["animate"],
    )
    _state["animator"] = animator

    # Paint once synchronously so the session is already itself on the first
    # prompt, rather than plain until the first watch tick.
    try:
        palette = _compute_palette(session_id)
        # Write BOTH: the stable skin (what the CLI resolves) and the per-session
        # file (what `watch` reads for other sessions).
        write_skin(palette, tint_background=settings["tint_background"],
                   name=skin_name)
        write_skin(palette, tint_background=settings["tint_background"])
        apply_palette_now(palette, skin_name)
        if settings["terminal_background"]:
            set_terminal_background(palette.skin_colors(
                tint_background=True).get("background"))
    except Exception:
        logger.debug("cuttlefish: initial paint failed", exc_info=True)

    animator.start()


def on_session_end(session_id: str = "", **_kw) -> None:
    """Stop the animator and hand the terminal back exactly as we found it."""
    animator = _state.get("animator")
    if animator is not None:
        animator.stop()
    _state["animator"] = None

    sid = session_id or _state.get("session_id")
    if not sid:
        return

    # The STABLE skin is deliberately NOT removed and `display.skin` is NOT
    # reverted. v4 deleted the active skin here, so the next CLI startup resolved
    # a name whose file no longer existed and silently fell back to stock gold —
    # the whole reason the theme looked like it "did nothing". The stable skin is
    # this install's theme now; uninstalling is `hermes config set display.skin
    # default`, which `legend` and `doctor` both state.
    #
    # Hand the terminal's own background back. OSC 11 is a real change to the
    # emulator's state, not a repaint we own, so leaving it set would follow the
    # user out of Hermes into their shell.
    try:
        reset_terminal_background()
    except Exception:
        logger.debug("cuttlefish: terminal background reset failed", exc_info=True)

    # Only the PER-SESSION file is cleaned up; it exists for the `watch` board.
    try:
        remove_skin(sid)
    except Exception:
        logger.debug("cuttlefish: skin cleanup failed", exc_info=True)
    _state["session_id"] = None


def _cli_setup(parser) -> None:
    sub = parser.add_subparsers(dest="cuttle_cmd")
    watch = sub.add_parser("watch", help="Live board of every session and what it needs")
    watch.add_argument("--once", action="store_true", help="Render once and exit")
    watch.add_argument("--interval", type=float, default=2.0, help="Refresh seconds")
    sub.add_parser("legend", help="Explain the colour language")
    sub.add_parser("doctor", help="Diagnose terminal capability and current state")
    demo = sub.add_parser("demo", help="Play the transition trajectories in the terminal")
    demo.add_argument("--seconds", type=float, default=0.0,
                      help="Cap the demo runtime (0 = play all trajectories once)")
    skin = sub.add_parser("skin", help="Print this session's chromatophore field")
    skin.add_argument("--height", type=int, default=16, help="Pixel rows")
    skin.add_argument("--wave", action="store_true", help="Animate a passing cloud")


def _cli_handler(args) -> int:
    from .cli import run_demo, run_doctor, run_legend, run_skin, run_watch

    cmd = getattr(args, "cuttle_cmd", None) or "watch"
    if cmd == "legend":
        return run_legend()
    if cmd == "doctor":
        return run_doctor()
    if cmd == "demo":
        return run_demo(seconds=getattr(args, "seconds", 0.0))
    if cmd == "skin":
        return run_skin(height=getattr(args, "height", 16),
                        wave=getattr(args, "wave", False))
    return run_watch(once=getattr(args, "once", False),
                     interval=getattr(args, "interval", 2.0))


def register(ctx) -> None:
    """Wire the plugin into Hermes.

    Each registration is guarded independently: an older Hermes missing one surface
    should lose that one feature, not the whole plugin. Chef runs a different
    version from the workstation, so this is a real case, not theory.
    """
    _state["ctx"] = ctx
    try:
        ctx.register_cli_command(
            "cuttlefish",
            help="Session colour identity and state signalling",
            setup_fn=_cli_setup,
            handler_fn=_cli_handler,
            description="Ambient session identity and intervention signalling.",
        )
    except Exception:
        logger.debug("cuttlefish: CLI registration unavailable", exc_info=True)

    for hook, fn in (("on_session_start", on_session_start),
                     ("on_session_end", on_session_end)):
        try:
            ctx.register_hook(hook, fn)
        except Exception:
            logger.debug("cuttlefish: hook %s unavailable", hook, exc_info=True)
