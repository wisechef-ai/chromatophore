"""Make the repo importable as the `cuttlefish_theme` package during tests.

Hermes loads a plugin directory AS the package, so the package root is this repo
root. Tests need the PARENT directory on sys.path to `import cuttlefish_theme`, and
the repo directory itself may be named anything (a clone, a worktree), so we bind
the module name explicitly rather than trusting the directory basename.
"""

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent))

if "cuttlefish_theme" not in sys.modules:
    _spec = importlib.util.spec_from_file_location(
        "cuttlefish_theme", _ROOT / "__init__.py",
        submodule_search_locations=[str(_ROOT)],
    )
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        _mod.__path__ = [str(_ROOT)]
        sys.modules["cuttlefish_theme"] = _mod
        _spec.loader.exec_module(_mod)
