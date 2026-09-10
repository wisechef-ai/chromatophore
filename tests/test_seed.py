import subprocess, sys
from pathlib import Path

from cuttlefish_theme.seed import seed_for

_ROOT = Path(__file__).resolve().parents[1]
_BOOT = (
    "import importlib.util, sys; r=%r; "
    "s=importlib.util.spec_from_file_location('cuttlefish_theme', r+'/__init__.py', submodule_search_locations=[r]); "
    "m=importlib.util.module_from_spec(s); sys.modules['cuttlefish_theme']=m; s.loader.exec_module(m); "
    "from cuttlefish_theme.seed import seed_for; print(seed_for('20260909_122403_d1fe77'))"
) % str(_ROOT)


def test_seed_is_stable_across_processes():
    # hash() is randomised per interpreter; blake2b must not be. Two fresh processes, one answer.
    runs = {subprocess.check_output([sys.executable, "-c", _BOOT], text=True).strip() for _ in range(2)}
    assert len(runs) == 1
    assert int(runs.pop()) == seed_for("20260909_122403_d1fe77")


def test_seed_separates_sessions():
    assert seed_for("a") != seed_for("b")
