"""Read Hermes' live-session registry and reduce it to a colour-signal model.

Chromatophore is a peripheral-display layer: it gives each terminal session a
unique colour identity plus a three-level state signal, in the spirit of a
cuttlefish's skin. This module owns the read side of that — everything the
plugin knows about *which sessions are live* — and the entire state vocabulary
the product can express.

HONESTY NOTE — WHERE THE SIGNAL COMES FROM (read this before extending):
    The Hermes registry (``<HERMES_HOME>/runtime/active_sessions.json``, writer:
    ``hermes_cli/active_sessions.py``) records only LEASE information:
    session_id, pid, surface, timestamps, and the owner's process start time.
    It does NOT record the agent's pet/activity state (idle/run/review/waiting/
    failed/...). Therefore a :class:`Signal` CANNOT be derived from the registry
    alone today, and this module refuses to invent one. The API is shaped so a
    caller who DOES know the state (e.g. an in-process hook, or a future Hermes
    that publishes state into the registry) supplies it via
    :func:`collapse(pet_state)`; absent/unknown state collapses to RESTING, the
    visually silent default. Do not fake a state source: a wrong NEEDS_ME is
    worse than an honest RESTING, because it trains the user to ignore colour.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Registry reading
# ---------------------------------------------------------------------------

_REGISTRY_RELATIVE = Path("runtime") / "active_sessions.json"


def _default_registry_path() -> Path:
    """Resolve the registry path the same way Hermes does.

    ``HERMES_HOME`` is honoured first because profiles depend on it: a profile
    run redirects the agent's entire state dir, and hardcoding ``~/.hermes``
    would read the ROOT registry while colouring a PROFILE session (the exact
    bug class Hermes' own AGENTS.md bans). Only when no override is set do we
    fall back to the default home.
    """
    home = os.environ.get("HERMES_HOME")
    root = Path(home) if home else Path.home() / ".hermes"
    return root / _REGISTRY_RELATIVE


def _as_float(value: Any, default: float) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    """Float or None — None means "not recorded", which is meaningful downstream."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class LiveSession:
    """One live chat-surface lease, as recorded by Hermes.

    Immutable on purpose: sessions are compared and ordered across redraws, and
    a mutating model would make colour allocation non-reproducible.
    """

    session_id: str
    pid: int
    surface: str
    started_at: float
    updated_at: float
    # Owner process's start time (epoch seconds) when Hermes pinned it at lease
    # acquisition; None when the writer could not read it. The pair
    # (pid, process_start_time) is what makes liveness PID-REUSE-safe.
    process_start_time: float | None

    @property
    def age_seconds(self) -> float:
        return time.time() - self.started_at

    @property
    def age_label(self) -> str:
        """Compact one-unit, integer age: '45s', '4m', '2h', '3d'.

        Load-bearing text: colour cannot encode duration (a hue held for 10
        seconds looks identical to one held for 10 hours), so the label must
        carry it. Exactly ONE unit, always an integer — a two-unit string like
        '1h 05m' is unreadable in peripheral vision, and a decimal ('1.2h')
        adds precision nobody across a room can use.
        """
        age = self.age_seconds
        if age < 0.0:
            # Registry written on a machine whose clock is ahead of ours;
            # "slightly in the future" is presented as "just started".
            age = 0.0
        if age < 60.0:
            return f"{int(age)}s"
        if age < 3600.0:
            return f"{int(age // 60)}m"
        if age < 86400.0:
            return f"{int(age // 3600)}h"
        return f"{int(age // 86400)}d"


def read_registry(path: Path | None = None) -> list[LiveSession]:
    """Parse the active-session registry into LiveSessions; NEVER raises.

    We are a cosmetic layer inside someone's shell prompt: any registry problem
    must degrade to "no sessions to show", not to a traceback in their face.
    """
    registry = Path(path) if path is not None else _default_registry_path()
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
    except FileNotFoundError:
        # A machine where Hermes has never run (or no lease was ever taken) has
        # no registry file; a fresh machine is not an error.
        return []
    except (OSError, ValueError):
        # Covers: 0-byte file, a registry truncated mid-write (the writer's
        # tmp+rename makes this rare, not impossible to observe), and outright
        # malformed JSON. All reduce to "nothing to display, keep the shell
        # alive" rather than raising.
        return []

    # The writer emits {"entries": [...]}; accept a bare list too, matching
    # Hermes' own _read_entries leniency for the same reason (older writers).
    entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return []

    sessions: list[LiveSession] = []
    for entry in entries:
        # Skip damaged entries INDIVIDUALLY: one non-dict row or row missing
        # session_id (a torn write under the flock) must not blank the colour
        # of every other healthy session in the list.
        if not isinstance(entry, dict):
            continue
        session_id = entry.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        sessions.append(_session_from_entry(session_id, entry))
    return sessions


def _session_from_entry(session_id: str, entry: dict[str, Any]) -> LiveSession:
    # Unknown extra keys are dropped here deliberately: forward compatibility
    # with newer Hermes versions that add fields this reader has never heard
    # of. Missing/invalid optional fields degrade to inert defaults (pid 0 is
    # treated as dead by is_alive; zero timestamps read as "age unknown").
    raw_surface = entry.get("surface")
    return LiveSession(
        session_id=session_id,
        pid=_as_int(entry.get("pid"), 0),
        surface=raw_surface if isinstance(raw_surface, str) else "",
        started_at=_as_float(entry.get("started_at"), 0.0),
        updated_at=_as_float(entry.get("updated_at"), 0.0),
        process_start_time=_optional_float(entry.get("process_start_time")),
    )


# ---------------------------------------------------------------------------
# PID-reuse-safe liveness
# ---------------------------------------------------------------------------

# /proc/<pid>/stat's starttime is quantised to clock ticks (typically 100 Hz =
# 10 ms) while psutil-derived process_start_time in the registry is
# float-epoch; a 1 s window absorbs both that quantisation and btime rounding
# without ever accepting a *different* process (starts differ by seconds+).
_START_TIME_TOLERANCE_S = 1.0


def _boot_time() -> float | None:
    """Kernel boot time (epoch s) from /proc/stat's 'btime' line, or None."""
    try:
        with open("/proc/stat", "r", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("btime"):
                    return float(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def _proc_start_time(pid: int) -> float | None:
    """The process's actual start time (epoch s) from /proc, or None.

    Field 22 of /proc/<pid>/stat is 'starttime' in clock ticks since boot; we
    convert with SC_CLK_TCK and add btime to get epoch seconds — the same
    quantity psutil reports as create_time(), which is what the Hermes writer
    pins into the registry. Stays consistent with the writer so the comparison
    in is_alive compares like with like.
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            stat = fh.read()
    except OSError:
        return None
    try:
        # comm (field 2) may contain spaces and parens, so fields are counted
        # AFTER the last ')'; field 3 (state) lands at index 0, hence 22 -> 19.
        after_comm = stat[stat.rindex(b")") + 2:].split()
        ticks = int(after_comm[19])
    except (ValueError, IndexError):
        return None
    boot = _boot_time()
    if boot is None:
        return None
    return boot + ticks / os.sysconf("SC_CLK_TCK")


def is_alive(session: LiveSession) -> bool:
    """True if the session's owner process is (very likely) still running.

    PID-REUSE-SAFE: a pid alone proves nothing — Linux recycles pids, and a
    recycled pid would keep a long-dead session's colour alive forever. When
    the registry pinned process_start_time, we require the pid's CURRENT start
    time to match it; a mismatch means the pid now belongs to a different,
    unrelated process.

    Fail-alive bias: where liveness is genuinely unknowable (no pinned start
    time, /proc unreadable on this platform, permission denied), we report
    ALIVE. This is a cosmetic layer: a false 'dead' erases a real session's
    colour — a visible, confusing regression — while a false 'alive' merely
    shows one stale colour until the writer's own reaper prunes the lease.
    """
    if session.pid <= 0:
        return False
    try:
        os.kill(session.pid, 0)  # signal 0: existence probe, no delivery
    except ProcessLookupError:
        return False
    except PermissionError:
        pass  # Exists but is another user's; keep probing start time below.

    if session.process_start_time is None:
        # Nothing pinned to compare against: unverifiable, so prefer alive.
        return True
    actual = _proc_start_time(session.pid)
    if actual is None:
        # /proc unreadable (non-Linux, or raced exit between probe and read):
        # unknowable, so prefer alive.
        return True
    return abs(actual - session.process_start_time) <= _START_TIME_TOLERANCE_S


# ---------------------------------------------------------------------------
# Signal model — the product's ENTIRE state vocabulary
# ---------------------------------------------------------------------------


class Signal(str, Enum):
    """Three levels is the whole vocabulary, by design.

    Peripheral colour discrimination supports roughly three reliably
    distinguishable levels at a glance (calm / attention / error); seven hues
    would collapse into noise exactly when the user looks away.
    """

    RESTING = "resting"
    NEEDS_ME = "needs_me"
    FAULT = "fault"


# idle/run/review/wave/jump all collapse to RESTING: run and review both mean
# "autonomous work in progress, do not interrupt" — the distinction between
# executing a tool and reasoning about results is invisible and useless from
# across a room. wave/jump are momentary beats (turn done / celebration), not
# sustained states worth a colour of their own. waiting is the ONE state that
# needs the user; failed is the one that needs them even more.
_COLLAPSE: dict[str, Signal] = {
    "idle": Signal.RESTING,
    "run": Signal.RESTING,
    "review": Signal.RESTING,
    "wave": Signal.RESTING,
    "jump": Signal.RESTING,
    "waiting": Signal.NEEDS_ME,
    "failed": Signal.FAULT,
}


def collapse(pet_state: str | None) -> Signal:
    """Map a Hermes PetState name onto a Signal.

    Accepts None and unknown names (returning RESTING) because the registry
    carries no state today (see module docstring): RESTING is the honest
    default, not a guess. PetState enum values work directly — they are str.
    """
    return _COLLAPSE.get(pet_state or "", Signal.RESTING)


_LABEL_FORMATS: dict[Signal, str] = {
    # RESTING must be VISUALLY SILENT: a resting session is the normal case,
    # and persistent text on the normal case is noise that hides the signals.
    Signal.RESTING: "",
    Signal.NEEDS_ME: "INPUT {}",
    Signal.FAULT: "ERROR {}",
}


def signal_label(sig: Signal, age: str) -> str:
    """Persistent text label for a signal, embedding the age label.

    The age rides along because colour alone cannot express duration (see
    LiveSession.age_label): 'INPUT 4m' says both WHAT and HOW LONG.
    """
    return _LABEL_FORMATS[sig].format(age)


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def snapshot(path: Path | None = None) -> list[LiveSession]:
    """Live sessions only, oldest first.

    Ordering is load-bearing: identity allocation (which session gets which
    colour) is order-dependent, so the sort key must depend only on each
    session's OWN start time — a session must not change colour because
    another session appeared or vanished. sorted() is stable, so sessions
    sharing a start time keep their registry order across redraws.
    """
    return sorted(
        (s for s in read_registry(path) if is_alive(s)),
        key=lambda s: s.started_at,
    )
