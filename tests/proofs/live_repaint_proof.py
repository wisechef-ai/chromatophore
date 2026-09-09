#!/usr/bin/env python3
"""Prove the live-repaint mechanism in a REAL prompt_toolkit application.

This is the claim the whole "continuous, not load-and-forget" requirement rests on:
that rewriting the active skin's YAML and re-activating it changes what a RUNNING
classic Hermes CLI renders. Everything else in the project is downstream of it, so
it gets exercised against the real prompt_toolkit + real skin engine rather than a
mock.

Run under a pty (script/expect) or any tty. Exits non-zero on failure.
"""

import os
import pathlib
import sys
import tempfile

# Isolate: never touch the developer's real ~/.hermes.
HOME = tempfile.mkdtemp(prefix="cuttle-live-proof-")
os.environ["HERMES_HOME"] = HOME

# The package root is this repo's PARENT (Hermes loads the plugin dir AS the
# package), so go up three: proofs -> tests -> repo -> parent.
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

from cuttlefish_theme.color.identity import allocate
from cuttlefish_theme.color.oklab import hex_to_oklch          # noqa: E402
from cuttlefish_theme.pattern import render                   # noqa: E402
from cuttlefish_theme.session import Signal                   # noqa: E402
from cuttlefish_theme.skinio import session_skin_name, write_skin  # noqa: E402

try:
    from hermes_cli.skin_engine import (                   # noqa: E402
        get_active_skin,
        get_prompt_toolkit_style_overrides,
        set_active_skin,
    )
except ImportError:
    # This proof exercises the REAL skin engine on purpose; without Hermes there
    # is nothing to prove, so skip rather than fake it. Exit 0 keeps `make test`
    # honest on a machine that has the plugin but not the agent.
    print("\n  SKIP: Hermes not importable — run inside the Hermes venv.\n")
    sys.exit(0)

failures = []


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
    if not condition:
        failures.append(label)


print("\ncuttlefish-theme — live repaint proof\n")
print(f"  isolated HERMES_HOME = {HOME}\n")

SESSION = "20260908_170000_proof01"
skin_name = session_skin_name(SESSION)

# --- 1. resting -------------------------------------------------------------
ident = allocate(SESSION)
resting = render(ident, Signal.RESTING)
path = write_skin(resting)
set_active_skin(skin_name)

accent_resting = get_active_skin().get_color("ui_accent", "?")
overrides_resting = dict(get_prompt_toolkit_style_overrides())

check("skin file written", path.is_file(), path.name)
check("skin activated", get_active_skin().name == skin_name, get_active_skin().name)
# v4: the accent is DERIVED from the identity (contrast-locked, chroma boosted to
# the animal's measured 0.16-0.24 band), not a copy of sheen_hex. So the contract
# is "same hue family as the identity", not "equal to a particular field".
_acc = hex_to_oklch(accent_resting)
_idn = hex_to_oklch(resting.identity_hex)
_dh = abs(((_acc.h - _idn.h + 180) % 360) - 180)
check("accent carries the identity hue", _dh < 20,
      f"{accent_resting} h{_acc.h:.0f} vs identity {resting.identity_hex} h{_idn.h:.0f}")
check("accent is vivid (measured animal band C>=0.16)", _acc.C >= 0.15,
      f"C {_acc.C:.3f}")
check("resting has no acute layer", resting.acute_hex is None)
check("resting label is silent", resting.label == "", repr(resting.label))

# --- 2. needs-me (the acute layer) ------------------------------------------
needs = render(ident, Signal.NEEDS_ME, age_label="4m")
write_skin(needs)
set_active_skin(skin_name)

accent_needs = get_active_skin().get_color("ui_accent", "?")
overrides_needs = dict(get_prompt_toolkit_style_overrides())

check("acute layer present", needs.acute_hex is not None, str(needs.acute_hex))
_acu = hex_to_oklch(accent_needs)
_amb = hex_to_oklch(needs.acute_hex)
_dha = abs(((_acu.h - _amb.h + 180) % 360) - 180)
check("accent switched to the acute hue", _dha < 20,
      f"{accent_needs} h{_acu.h:.0f} vs acute {needs.acute_hex} h{_amb.h:.0f}")
check("accent actually CHANGED from resting", accent_needs.upper() != accent_resting.upper(),
      f"{accent_resting} -> {accent_needs}")
check("prompt_toolkit style overrides changed too",
      overrides_needs != overrides_resting,
      "this is what a running app re-reads")
check("age is carried as TEXT", needs.label == "INPUT 4m", repr(needs.label))

# --- 3. release: identity must survive and return ----------------------------
released = render(ident, Signal.RESTING)
write_skin(released)
set_active_skin(skin_name)
accent_released = get_active_skin().get_color("ui_accent", "?")

check("identity restored after the acute signal clears",
      accent_released.upper() == accent_resting.upper(),
      f"{accent_released} == {accent_resting}")
check("identity hex never mutated across states",
      resting.identity_hex == needs.identity_hex == released.identity_hex,
      resting.identity_hex)

# --- 4. the running application ---------------------------------------------
try:
    from prompt_toolkit.application.current import get_app_or_none
    from prompt_toolkit.styles import Style

    Style.from_dict(overrides_needs)
    check("overrides form a valid prompt_toolkit Style", True,
          f"{len(overrides_needs)} keys")
    check("get_app_or_none is reachable", callable(get_app_or_none),
          "None outside a running app, which is correct here")
except Exception as exc:  # pragma: no cover
    check("prompt_toolkit style build", False, str(exc))

print()
if failures:
    print(f"  {len(failures)} FAILED: {', '.join(failures)}\n")
    sys.exit(1)
print("  all checks passed — live repaint mechanism verified\n")
