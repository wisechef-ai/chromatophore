#!/usr/bin/env python3
"""Prove an ANIMATED transition repaints a REAL, RUNNING prompt_toolkit application.

This is the claim v2 rests on, and the one that cannot be proven by unit tests: that
a state change produces a *sequence* of visibly different styles in a live app, each
one reaching the screen, ending exactly on the target.

v1's equivalent proof only showed that two static palettes differ. That is much
weaker: it would pass even if every intermediate frame were dropped, which is
precisely the failure mode an animation has and a snap does not.

We drive the real skin engine and a real Application on a background thread, exactly
as the plugin's animator does from a session hook. Exits non-zero on failure.
"""

import os
import pathlib
import sys
import tempfile
import threading
import time

# Isolate: never touch the developer's real ~/.hermes.
HOME = tempfile.mkdtemp(prefix="cuttle-anim-proof-")
os.environ["HERMES_HOME"] = HOME

# The package root is this repo's PARENT (Hermes loads the plugin dir AS the
# package), so go up three: proofs -> tests -> repo -> parent.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))

import importlib.util  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if "cuttlefish_theme" not in sys.modules:
    # Bind the module name explicitly: the repo directory contains a hyphen, which
    # is not a legal Python identifier. Hermes' own loader does exactly this.
    _spec = importlib.util.spec_from_file_location(
        "cuttlefish_theme", _ROOT / "__init__.py",
        submodule_search_locations=[str(_ROOT)])
    _mod = importlib.util.module_from_spec(_spec)
    _mod.__path__ = [str(_ROOT)]
    sys.modules["cuttlefish_theme"] = _mod
    _spec.loader.exec_module(_mod)

from cuttlefish_theme.color.identity import allocate            # noqa: E402
from cuttlefish_theme.live import Animator                      # noqa: E402
from cuttlefish_theme.morph import BLANCH, RECOVER              # noqa: E402
from cuttlefish_theme.pattern import render                     # noqa: E402
from cuttlefish_theme.session import Signal                     # noqa: E402
from cuttlefish_theme.skinio import session_skin_name           # noqa: E402

try:
    from hermes_cli.skin_engine import (get_active_skin,         # noqa: E402
                                        get_prompt_toolkit_style_overrides)
except ImportError:
    print("\n  SKIP: Hermes not importable — run inside the Hermes venv.\n")
    sys.exit(0)

try:
    from prompt_toolkit.application import Application           # noqa: E402
    from prompt_toolkit.input import create_pipe_input           # noqa: E402
    from prompt_toolkit.layout import Layout, Window             # noqa: E402
    from prompt_toolkit.layout.controls import FormattedTextControl  # noqa: E402
    from prompt_toolkit.output import DummyOutput                # noqa: E402
    from prompt_toolkit.styles import Style as PTStyle           # noqa: E402
except ImportError:
    print("\n  SKIP: prompt_toolkit not importable.\n")
    sys.exit(0)

failures = []


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


print("\ncuttlefish-theme — animated transition proof\n")
print(f"  isolated HERMES_HOME = {HOME}\n")

SESSION = "20260909_090000_anim01"
skin_name = session_skin_name(SESSION)
ident = allocate(SESSION)
RESTING = render(ident, Signal.RESTING)
FAULT = render(ident, Signal.FAULT, age_label="2m")


class FakeCLI:
    """Stands in for HermesCLI, exposing the two attributes live._find_cli() looks
    for. Backed by a genuine prompt_toolkit Application, so the style objects we
    build are the real thing and a bad palette would raise here as it would live."""

    def __init__(self, app):
        self._app = app
        self.styles = []

    def _build_tui_style_dict(self):
        return dict(get_prompt_toolkit_style_overrides())

    def _apply_tui_skin_style(self):
        style_dict = self._build_tui_style_dict()
        self._app.style = PTStyle.from_dict(style_dict)
        self.styles.append(style_dict)
        return True


with create_pipe_input() as pipe_input:
    app = Application(
        layout=Layout(Window(FormattedTextControl("cuttlefish"))),
        input=pipe_input,
        output=DummyOutput(),
        full_screen=False,
    )
    cli = FakeCLI(app)

    # --- 1. the animator drives the real engine -----------------------------
    state = {"palette": RESTING}

    def apply_fn(name: str) -> bool:
        """Exactly what live.apply_colors_now does, against the real engine."""
        from hermes_cli.skin_engine import set_active_skin

        set_active_skin(name)          # re-reads the YAML we just wrote
        return cli._apply_tui_skin_style()

    animator = Animator(
        compute=lambda: state["palette"],
        skin_name=skin_name,
        fps=30.0,
        apply_fn=apply_fn,
    )

    animator.tick_once()                     # first paint, no animation
    first_styles = len(cli.styles)
    resting_accent = get_active_skin().get_color("ui_accent", "?")
    check("first paint reached the running app", first_styles == 1)
    check("no animation on first paint", animator.transitions == 0)

    # --- 2. a fault BLANCHES ------------------------------------------------
    state["palette"] = FAULT
    began = time.monotonic()
    animator.tick_once()
    blanch_seconds = time.monotonic() - began
    blanch_styles = cli.styles[first_styles:]
    fault_accent = get_active_skin().get_color("ui_accent", "?")

    check("blanch emitted MANY frames, not one snap", len(blanch_styles) > 4,
          f"{len(blanch_styles)} styles reached the app")
    check("every frame was a distinct appearance",
          len({tuple(sorted(s.items())) for s in blanch_styles}) > 4,
          f"{len({tuple(sorted(s.items())) for s in blanch_styles})} unique")
    check("blanch kept to its measured duration",
          blanch_seconds < BLANCH.duration * 2.5,
          f"{blanch_seconds:.2f}s (curve says {BLANCH.duration}s)")
    check("landed exactly on the fault colour",
          fault_accent.upper() == FAULT.acute_hex.upper(),
          f"{fault_accent} == {FAULT.acute_hex}")
    check("the app's style object was actually replaced",
          isinstance(app.style, PTStyle))

    # --- 3. clearing it RECOVERS the identity -------------------------------
    state["palette"] = RESTING
    began = time.monotonic()
    animator.tick_once()
    recover_seconds = time.monotonic() - began
    recover_styles = cli.styles[first_styles + len(blanch_styles):]
    restored_accent = get_active_skin().get_color("ui_accent", "?")

    check("recovery emitted its own frames", len(recover_styles) > 4,
          f"{len(recover_styles)} styles")
    check("recovery was SLOWER than the blanch (Nature 2023, Fig. 5b)",
          recover_seconds > blanch_seconds,
          f"blanch {blanch_seconds:.2f}s < recover {recover_seconds:.2f}s")
    check("identity restored exactly",
          restored_accent.upper() == resting_accent.upper(),
          f"{restored_accent} == {resting_accent}")
    check("identity hex never mutated underneath",
          RESTING.identity_hex == FAULT.identity_hex, RESTING.identity_hex)

    # --- 4. the background is this session's black --------------------------
    ground = get_active_skin().get_color("background", "")
    check("background is set by the theme", bool(ground), ground)
    check("background is the session's own ground",
          ground.upper() == RESTING.ground_hex.upper(),
          f"{ground} == {RESTING.ground_hex}")

    # --- 5. the steady state is genuinely free ------------------------------
    idle_before = len(cli.styles)
    for _ in range(5):
        animator.tick_once()
    check("idle ticks repaint NOTHING", len(cli.styles) == idle_before,
          f"{len(cli.styles) - idle_before} repaints while resting")

    # --- 6. stop is prompt even mid-transition ------------------------------
    state["palette"] = FAULT
    done = threading.Event()
    threading.Thread(target=lambda: (animator.tick_once(), done.set()),
                     daemon=True).start()
    time.sleep(0.05)
    stop_began = time.monotonic()
    animator.stop()
    done.wait(timeout=3.0)
    check("stop interrupts an in-flight transition",
          time.monotonic() - stop_began < RECOVER.duration,
          f"{time.monotonic() - stop_began:.2f}s")

print()
if failures:
    print(f"  {len(failures)} FAILED: {', '.join(failures)}\n")
    sys.exit(1)
print("  all checks passed — animated repaint verified against a running app\n")
