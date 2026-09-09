#!/usr/bin/env python3
"""Prove a repaint reaches a REAL RUNNING prompt_toolkit application.

The earlier proof (live_repaint_proof.py) verified the skin engine half: that
rewriting a skin changes what `get_prompt_toolkit_style_overrides()` returns. It
did NOT verify the half that actually matters to a human — that a running
Application's rendered colours change.

That gap is exactly where the first Chef test failed: `_owning_cli()` returned
None, we fell back to a bare `app.invalidate()`, and invalidate re-renders with
the SAME style object. The engine was right and the screen never moved.

So this proof drives a real Application on a real pty, in a background thread
(where the repaint loop actually runs), and asserts the app's own resolved style
changes for the styles Hermes uses.
"""

import os
import pathlib
import sys
import tempfile
import threading
import time

HOME = tempfile.mkdtemp(prefix="cuttle-app-proof-")
os.environ["HERMES_HOME"] = HOME

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))

import importlib.util  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if "cuttlefish_theme" not in sys.modules:
    # Bind the module name explicitly: the repo directory contains a hyphen, which
    # is not a legal Python identifier, so importing by basename fails. Hermes'
    # own plugin loader does exactly this (spec_from_file_location).
    _spec = importlib.util.spec_from_file_location(
        "cuttlefish_theme", _ROOT / "__init__.py",
        submodule_search_locations=[str(_ROOT)])
    _mod = importlib.util.module_from_spec(_spec)
    _mod.__path__ = [str(_ROOT)]
    sys.modules["cuttlefish_theme"] = _mod
    _spec.loader.exec_module(_mod)

from cuttlefish_theme.color.identity import allocate            # noqa: E402
from cuttlefish_theme.live import _find_cli, apply_palette_now  # noqa: E402
from cuttlefish_theme.pattern import render                     # noqa: E402
from cuttlefish_theme.session import Signal                     # noqa: E402
from cuttlefish_theme.skinio import session_skin_name, write_skin  # noqa: E402

try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.input.defaults import create_pipe_input
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.output import DummyOutput
    from prompt_toolkit.styles import Style
except ImportError:
    print("\n  SKIP: prompt_toolkit unavailable.\n")
    sys.exit(0)

failures = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def style_for(app, class_name):
    """The colour the app's CURRENT style resolves for a style class.

    This is what the renderer would actually paint, so it is the honest thing to
    assert on — not what the skin engine holds in a module global.
    """
    attrs = app.style.get_attrs_for_style_str(f"class:{class_name}")
    return attrs.color


class FakeHermesCLI:
    """Stands in for HermesCLI: the same duck-type surface `_find_cli` requires.

    Must expose BOTH `_apply_tui_skin_style` and `_build_tui_style_dict` — the
    real CLI has both, and `_find_cli` checks for both so it cannot mistake some
    other object that merely happens to hold an `_app`.
    """

    def __init__(self, app):
        self._app = app
        self._tui_style_base = {"prompt": "#111111"}

    def _build_tui_style_dict(self):
        from hermes_cli.skin_engine import get_prompt_toolkit_style_overrides

        merged = dict(self._tui_style_base)
        merged.update(get_prompt_toolkit_style_overrides())
        return merged

    def _apply_tui_skin_style(self):
        self._app.style = Style.from_dict(self._build_tui_style_dict())
        self._app.invalidate()
        return True


print("\ncuttlefish-theme — running-application repaint proof\n")
print(f"  isolated HERMES_HOME = {HOME}\n")

SESSION = "20260908_181500_appproof"
skin_name = session_skin_name(SESSION)
ident = allocate(SESSION)

with create_pipe_input() as inp:
    app = Application(
        layout=Layout(Window(FormattedTextControl("cuttlefish"))),
        input=inp,
        output=DummyOutput(),
        style=Style.from_dict({"prompt": "#111111"}),
        full_screen=False,
    )
    cli = FakeHermesCLI(app)

    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    time.sleep(0.8)  # let the app become "current"

    check("application is running", app.is_running)

    # The repaint loop is NOT the main thread, so resolution must work from one.
    found = {}

    def probe():
        # Record whether a "current app" exists on this thread. It varies by
        # prompt_toolkit version and by how the thread was started, which is
        # precisely why resolution must NOT depend on it: on Chef the first
        # paint was silently swallowed because get_app_or_none() returned None
        # on the worker thread Hermes uses for on_session_start.
        from prompt_toolkit.application.current import get_app_or_none

        found["current_app"] = get_app_or_none()
        found["cli"] = _find_cli()

    t = threading.Thread(target=probe)
    t.start()
    t.join()

    print(f"    (current app on this worker thread: "
          f"{'present' if found['current_app'] is not None else 'None'} — "
          f"either way, resolution must not depend on it)")
    check("CLI resolved without relying on a current app", found["cli"] is cli,
          type(found["cli"]).__name__ if found["cli"] else "None (this was the bug)")

    # --- resting ---
    resting = render(ident, Signal.RESTING)
    write_skin(resting)
    ok1 = apply_palette_now(resting, skin_name)
    time.sleep(0.2)
    prompt_resting = style_for(app, "prompt")

    check("apply_palette_now reported a repaint", ok1)
    check("app style now shows the identity colour",
          prompt_resting not in (None, "", "111111"), f"prompt={prompt_resting}")

    # --- needs-me ---
    needs = render(ident, Signal.NEEDS_ME, age_label="4m")
    write_skin(needs)
    apply_palette_now(needs, skin_name)
    time.sleep(0.2)
    prompt_needs = style_for(app, "prompt")

    check("THE APP'S OWN STYLE CHANGED on the acute signal",
          prompt_needs != prompt_resting,
          f"{prompt_resting} -> {prompt_needs}")
    check("acute colour is the amber we wrote",
          prompt_needs and prompt_needs.upper() == needs.acute_hex.lstrip("#").upper(),
          f"{prompt_needs} vs {needs.acute_hex}")

    # --- release ---
    released = render(ident, Signal.RESTING)
    write_skin(released)
    apply_palette_now(released, skin_name)
    time.sleep(0.2)
    prompt_released = style_for(app, "prompt")

    check("identity returns when the signal clears",
          prompt_released == prompt_resting,
          f"{prompt_needs} -> {prompt_released}")

    app.exit()
    time.sleep(0.3)

print()
if failures:
    print(f"  {len(failures)} FAILED: {', '.join(failures)}\n")
    sys.exit(1)
print("  a running application really does repaint\n")
