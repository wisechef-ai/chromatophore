"""Behaviour contracts for chromatophore.session.

Every test asserts a RELATIONSHIP (how the reader responds to damaged input,
how labels map to durations, how liveness treats a reused pid), never a
snapshot of internal shapes. All registry I/O goes through tmp_path; the real
~/.hermes is never touched.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chromatophore.session import (
    LiveSession,
    Signal,
    collapse,
    is_alive,
    read_registry,
    signal_label,
    snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_session(**overrides: Any) -> LiveSession:
    """A LiveSession for the CURRENT process — genuinely alive on Linux."""
    now = time.time()
    base: dict[str, Any] = dict(
        session_id="s_test",
        pid=os.getpid(),
        surface="cli",
        started_at=now,
        updated_at=now,
        process_start_time=None,
    )
    base.update(overrides)
    return LiveSession(**base)


def write_registry(tmp_path: Path, payload) -> Path:
    p = tmp_path / "runtime" / "active_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# read_registry robustness — a cosmetic layer must never break the shell
# ---------------------------------------------------------------------------


def test_missing_file_yields_empty(tmp_path):
    # A fresh machine has no registry; absence is not an error.
    assert read_registry(tmp_path / "runtime" / "active_sessions.json") == []


def test_empty_file_yields_empty(tmp_path):
    p = tmp_path / "runtime" / "active_sessions.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"")
    assert read_registry(p) == []


def test_truncated_json_yields_empty_without_raising(tmp_path):
    # A file cut mid-write (torn JSON) must degrade to [], never raise.
    p = tmp_path / "runtime" / "active_sessions.json"
    p.parent.mkdir(parents=True)
    full = json.dumps({"entries": [{"session_id": "a", "pid": 1}]})
    p.write_text(full[: len(full) // 2], encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads(p.read_text())  # prove the fixture really is corrupt
    assert read_registry(p) == []


def test_valid_entries_are_parsed(tmp_path):
    p = write_registry(
        tmp_path,
        {
            "entries": [
                {
                    "lease_id": "abc",
                    "session_id": "20260906_190808_6bb5a2",
                    "pid": 828293,
                    "process_start_time": 1788714485.0,
                    "started_at": 1788714496.6,
                    "updated_at": 1788714497.0,
                    "surface": "cli",
                    "metadata": {"live_session_id": "20260906_190808_6bb5a2"},
                }
            ]
        },
    )
    (sessions,) = read_registry(p)
    assert sessions.session_id == "20260906_190808_6bb5a2"
    assert sessions.pid == 828293
    assert sessions.surface == "cli"
    assert sessions.process_start_time == 1788714485.0
    # lease_id/metadata are registry details this layer must not surface.
    assert not hasattr(sessions, "lease_id")


def test_bad_entries_skipped_individually(tmp_path):
    # One damaged row must not blank the healthy ones: colour is per-session.
    p = write_registry(
        tmp_path,
        {
            "entries": [
                "not a dict",
                {"pid": 123},  # no session_id
                {"session_id": "", "pid": 1},  # blank id is no identity either
                {"session_id": "good", "pid": 42},
            ]
        },
    )
    sessions = read_registry(p)
    assert [s.session_id for s in sessions] == ["good"]
    assert sessions[0].pid == 42


def test_unknown_extra_keys_ignored(tmp_path):
    # Forward compatibility: a newer Hermes adding fields must not break us.
    p = write_registry(
        tmp_path,
        {
            "entries": [
                {
                    "session_id": "s1",
                    "pid": 1,
                    "surface": "cli",
                    "started_at": 1.0,
                    "updated_at": 1.0,
                    "yet_unheard_of_field": {"nested": [1, 2, 3]},
                }
            ],
            "new_top_level_key": True,
        },
    )
    (s,) = read_registry(p)
    assert s.session_id == "s1"


def test_bare_list_shape_accepted(tmp_path):
    # Hermes' own reader accepts a bare list (older writers); we match it.
    p = write_registry(tmp_path, [{"session_id": "s1", "pid": 1}])
    assert [s.session_id for s in read_registry(p)] == ["s1"]


def test_default_path_honours_hermes_home(tmp_path, monkeypatch):
    # Profiles redirect HERMES_HOME; the reader must follow, not assume ~/.hermes.
    home = tmp_path / "profile-home"
    monkeypatch.setenv("HERMES_HOME", str(home))
    write_registry(home, {"entries": [{"session_id": "prof", "pid": 1}]})
    assert [s.session_id for s in read_registry()] == ["prof"]


# ---------------------------------------------------------------------------
# age_label — one unit, integer, no decimals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "age_seconds, expected",
    [
        (59.9, "59s"),
        (60.0, "1m"),
        (90.0 * 60, "1h"),  # 90 minutes -> 1h, one unit only
        (25 * 3600, "1d"),  # 25 hours -> 1d
        (3 * 86400 + 4000, "3d"),
        (0.0, "0s"),
    ],
)
def test_age_label_boundaries(age_seconds, expected):
    s = make_session(started_at=time.time() - age_seconds)
    assert s.age_label == expected


def test_age_label_is_integer_only():
    # 90 seconds and 90 minutes must never render decimals ('1.5m', '1.5h').
    s = make_session(started_at=time.time() - 90)
    assert s.age_label == "1m"
    s2 = make_session(started_at=time.time() - 5400)
    assert s2.age_label == "1h"


# ---------------------------------------------------------------------------
# collapse — the whole state vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "pet_state, expected",
    [
        ("idle", Signal.RESTING),
        ("run", Signal.RESTING),
        ("review", Signal.RESTING),
        ("wave", Signal.RESTING),
        ("jump", Signal.RESTING),
        ("waiting", Signal.NEEDS_ME),
        ("failed", Signal.FAULT),
        ("hoverboard", Signal.RESTING),  # unknown -> honest default
        (None, Signal.RESTING),  # no state recorded -> honest default
        ("", Signal.RESTING),
    ],
)
def test_collapse_all_pet_states(pet_state, expected):
    assert collapse(pet_state) is expected


def test_collapse_accepts_petstate_enum_values():
    # Hermes' PetState is a str Enum; its values must work directly.
    assert collapse("waiting") is Signal.NEEDS_ME


def test_signal_is_str_subclass():
    # Signal values are plain strings so renderers can splice them into text.
    assert Signal.NEEDS_ME == "needs_me"
    assert isinstance(Signal.FAULT, str)


def test_signal_labels():
    assert signal_label(Signal.RESTING, "4m") == ""  # resting is visually silent
    assert signal_label(Signal.NEEDS_ME, "4m") == "INPUT 4m"
    assert signal_label(Signal.FAULT, "2h") == "ERROR 2h"


# ---------------------------------------------------------------------------
# is_alive — PID-reuse safety and fail-alive bias
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "linux", reason="reads Linux /proc")
class TestIsAliveLinux:
    def test_current_process_alive(self):
        assert is_alive(make_session()) is True

    def test_genuinely_dead_pid(self):
        # Spawn and reap a real process so its pid is PROVABLY not reused
        # between exit and check (fresh pids are not immediately recycled).
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = dead.pid
        dead.wait()
        # Only trust our own signal 0 probe if the pid is still gone; pids are
        # only recycled after wrapping the range, so immediately post-exit it
        # is gone. If something recycled it already, skip rather than lie.
        try:
            os.kill(dead_pid, 0)
            pytest.skip("pid was recycled immediately; cannot test dead pid")
        except ProcessLookupError:
            pass
        s = make_session(pid=dead_pid, process_start_time=time.time() - 3600)
        assert is_alive(s) is False

    def test_pid_reuse_detected_via_start_time(self):
        # A DIFFERENT process now owns the pid: start time won't match the one
        # pinned in the registry, so the stale session must read dead even
        # though the pid exists.
        other = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        try:
            from chromatophore.session import _proc_start_time

            actual = _proc_start_time(other.pid)
            if actual is None:
                pytest.skip("could not read /proc start time")
            stale = make_session(pid=other.pid, process_start_time=actual - 3600.0)
            assert is_alive(stale) is False
            # Sanity: the SAME start time pins the same process as alive.
            fresh = make_session(pid=other.pid, process_start_time=actual)
            assert is_alive(fresh) is True
        finally:
            other.send_signal(signal.SIGKILL)
            other.wait()

    def test_same_start_time_within_tolerance(self):
        # Registry pins psutil-style floats; /proc quantises to ticks. A small
        # delta must still count as the same process.
        from chromatophore.session import _proc_start_time

        actual = _proc_start_time(os.getpid())
        if actual is None:
            pytest.skip("could not read /proc start time")
        s = make_session(process_start_time=actual - 0.2)
        assert is_alive(s) is True

    def test_unpinned_start_time_fails_alive(self):
        # No process_start_time recorded: unknowable, and a false 'dead'
        # would erase a real session's colour.
        assert is_alive(make_session(process_start_time=None)) is True


def test_zero_pid_is_dead():
    # pid 0 means the entry never carried a real pid; never report it alive.
    assert is_alive(make_session(pid=0)) is False


# ---------------------------------------------------------------------------
# snapshot — liveness filter + order stability
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_with_mixed_sessions(tmp_path):
    """Entries whose pids are the CURRENT process (alive) or provably dead."""
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    try:
        os.kill(dead.pid, 0)
        dead_pid = None  # recycled already; drop dead-entry coverage honestly
    except ProcessLookupError:
        dead_pid = dead.pid

    entries = [
        {"session_id": "newest", "pid": os.getpid(), "surface": "cli",
         "started_at": time.time() - 60, "updated_at": time.time()},
        {"session_id": "oldest", "pid": os.getpid(), "surface": "tui",
         "started_at": time.time() - 3600, "updated_at": time.time()},
    ]
    if dead_pid is not None:
        entries.append(
            {"session_id": "ghost", "pid": dead_pid, "surface": "cli",
             "started_at": time.time() - 7200, "updated_at": time.time()}
        )
    return write_registry(tmp_path, {"entries": entries}), dead_pid


def test_snapshot_filters_dead_and_sorts_oldest_first(
    tmp_path, registry_with_mixed_sessions
):
    p, dead_pid = registry_with_mixed_sessions
    live = snapshot(p)
    ids = [s.session_id for s in live]
    if dead_pid is None:
        assert ids == ["oldest", "newest"]
    else:
        assert "ghost" not in ids
        assert ids == ["oldest", "newest"]  # ascending started_at
    starts = [s.started_at for s in live]
    assert starts == sorted(starts)


def test_snapshot_order_independent_of_other_sessions(tmp_path):
    # Identity allocation is order-dependent: adding a session must not
    # permute the relative order of the pre-existing ones.
    base = [
        {"session_id": "a", "pid": os.getpid(), "surface": "cli",
         "started_at": 100.0, "updated_at": 100.0},
        {"session_id": "b", "pid": os.getpid(), "surface": "cli",
         "started_at": 200.0, "updated_at": 200.0},
    ]
    extra = {"session_id": "z", "pid": os.getpid(), "surface": "cli",
             "started_at": 150.0, "updated_at": 150.0}
    p1 = write_registry(tmp_path / "one", {"entries": base})
    p2 = write_registry(tmp_path / "two", {"entries": base + [extra]})
    before = [s.session_id for s in snapshot(p1)]
    after_full = [s.session_id for s in snapshot(p2)]
    # 'z' slots between a and b by start time; a and b keep relative order.
    assert before == ["a", "b"]
    assert after_full == ["a", "z", "b"]


def test_snapshot_stable_for_equal_start_times(tmp_path):
    # Equal started_at must fall back to registry order, stably across calls.
    entries = [
        {"session_id": "first", "pid": os.getpid(), "surface": "cli",
         "started_at": 100.0, "updated_at": 100.0},
        {"session_id": "second", "pid": os.getpid(), "surface": "cli",
         "started_at": 100.0, "updated_at": 100.0},
    ]
    p = write_registry(tmp_path, {"entries": entries})
    assert [s.session_id for s in snapshot(p)] == ["first", "second"]
    assert [s.session_id for s in snapshot(p)] == ["first", "second"]
