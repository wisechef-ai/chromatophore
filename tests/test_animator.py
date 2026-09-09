"""Behaviour contracts for cuttlefish_theme.live.Animator.

The invariants that matter operationally rather than aesthetically:

  - idle costs NOTHING (no write, no repaint) — this is the whole "transition-only"
    cadence Adam chose, and a regression here is a permanent tax on every session;
  - a transition always LANDS exactly on its target, whatever happens mid-flight;
  - the final frame is durable and the in-flight frames are not (a deliberate,
    measured trade — see skinio.write_colors);
  - a failing frame degrades to a still image rather than killing the session.

All I/O is injected, so these run in milliseconds with no disk and no live CLI.
"""

from __future__ import annotations

import threading
import time

import pytest

from cuttlefish_theme.color.identity import allocate
from cuttlefish_theme.live import Animator, trajectory_for
from cuttlefish_theme.morph import BLANCH, RECOVER, SETTLE
from cuttlefish_theme.pattern import render
from cuttlefish_theme.session import Signal
from cuttlefish_theme.skinio import BASE_DIALECT

SESSION = "sess-anim-1"


def _palette(signal: Signal = Signal.RESTING):
    return render(allocate(SESSION), signal, age_label="4m")


class Recorder:
    """Captures every write and repaint the animator performs."""

    def __init__(self, fail_frames: int = 0):
        self.writes: list[tuple[str, dict, bool]] = []
        self.applies = 0
        self.fail_frames = fail_frames
        self.lock = threading.Lock()

    def write_colors(self, session_id, colors, *, description="", durable=True, **kw):
        with self.lock:
            if self.fail_frames and not durable:
                self.fail_frames -= 1
                raise OSError("simulated disk hiccup")
            self.writes.append((session_id, dict(colors), durable))

    def apply(self, skin_name: str) -> bool:
        with self.lock:
            self.applies += 1
        return True

    @property
    def durable_writes(self):
        return [w for w in self.writes if w[2]]

    @property
    def frame_writes(self):
        return [w for w in self.writes if not w[2]]


def _animator(recorder: Recorder, palettes, **kw) -> Animator:
    seq = list(palettes)
    state = {"i": 0}

    def compute():
        i = min(state["i"], len(seq) - 1)
        state["i"] += 1
        return seq[i]

    kw.setdefault("fps", 120.0)
    return Animator(
        compute=compute,
        skin_name="cuttle-test",
        write_colors=recorder.write_colors,
        apply_fn=recorder.apply,
        **kw,
    )


# --- trajectory selection ---------------------------------------------------

def test_first_paint_settles():
    """A new session is doing the camouflage search: finding out who it is."""
    assert trajectory_for(None, _palette()) is SETTLE


def test_signal_arriving_is_a_blanch():
    """Threat response: fast, direct, open-loop."""
    assert trajectory_for(_palette(Signal.RESTING), _palette(Signal.FAULT)) is BLANCH
    assert trajectory_for(_palette(Signal.RESTING), _palette(Signal.NEEDS_ME)) is BLANCH


def test_signal_clearing_is_a_recovery():
    """The identity comes BACK — slower, staggered — rather than snapping on."""
    assert trajectory_for(_palette(Signal.FAULT), _palette(Signal.RESTING)) is RECOVER


def test_escalating_between_signals_is_still_a_blanch():
    assert trajectory_for(_palette(Signal.NEEDS_ME), _palette(Signal.FAULT)) is BLANCH


# --- the steady state is free ----------------------------------------------

def test_an_unchanged_world_costs_nothing():
    """THE cadence contract. v1 wrote the skin file and repainted on a fixed timer
    forever; this must do literally no work while the session sits still."""
    recorder = Recorder()
    animator = _animator(recorder, [_palette()] * 8)
    assert animator.tick_once() is True          # first paint
    before_writes = len(recorder.writes)
    before_applies = recorder.applies
    for _ in range(6):
        assert animator.tick_once() is False
    assert len(recorder.writes) == before_writes
    assert recorder.applies == before_applies
    assert animator.transitions == 0


def test_first_paint_does_not_animate():
    """There is nothing to animate FROM, and a session that faded in from the
    previous user's colours would be a lie about where it came from."""
    recorder = Recorder()
    animator = _animator(recorder, [_palette()])
    animator.tick_once()
    assert recorder.frame_writes == []
    assert len(recorder.durable_writes) == 1


# --- transitions ------------------------------------------------------------

def test_a_state_change_animates_and_lands_on_target():
    recorder = Recorder()
    calm, alarmed = _palette(Signal.RESTING), _palette(Signal.FAULT)
    animator = _animator(recorder, [calm, alarmed])
    animator.tick_once()
    animator.tick_once()

    assert animator.transitions == 1
    assert recorder.frame_writes, "no in-flight frames were emitted"
    final_colors = recorder.durable_writes[-1][1]
    expected = dict(BASE_DIALECT)
    expected.update(alarmed.skin_colors())
    assert final_colors == expected


def test_intermediate_frames_are_not_fsynced_but_the_last_one_is():
    """Measured trade: fsync is ~4ms of an ~11.7ms frame. Atomicity comes from
    os.replace, so dropping it in flight is safe; the FINAL frame must still be
    durable because that is the state a crash should leave behind."""
    recorder = Recorder()
    animator = _animator(recorder, [_palette(Signal.RESTING), _palette(Signal.FAULT)])
    animator.tick_once()
    animator.tick_once()
    assert all(not w[2] for w in recorder.frame_writes)
    assert recorder.writes[-1][2] is True


def test_every_frame_carries_a_complete_palette():
    """A partial frame would be merged over Hermes' DEFAULT skin, not over ours
    (skinio HAZARD 2), flashing the stock gold palette mid-transition."""
    recorder = Recorder()
    animator = _animator(recorder, [_palette(Signal.RESTING), _palette(Signal.FAULT)])
    animator.tick_once()
    keys = set(recorder.durable_writes[0][1])
    animator.tick_once()
    for _, colors, _ in recorder.writes:
        assert set(colors) == keys


def test_a_failing_frame_does_not_abort_the_transition():
    """One dropped frame is invisible; a transition that aborts mid-fade latches a
    half-interpolated palette, which is a permanently wrong colour."""
    recorder = Recorder(fail_frames=3)
    alarmed = _palette(Signal.FAULT)
    animator = _animator(recorder, [_palette(Signal.RESTING), alarmed])
    animator.tick_once()
    animator.tick_once()
    expected = dict(BASE_DIALECT)
    expected.update(alarmed.skin_colors())
    assert recorder.durable_writes[-1][1] == expected


def test_animation_can_be_disabled_entirely():
    """`animate: false` restores the v1 snap. A theme that cannot be turned down is
    a theme people uninstall."""
    recorder = Recorder()
    animator = _animator(recorder, [_palette(Signal.RESTING), _palette(Signal.FAULT)],
                         animate=False)
    animator.tick_once()
    animator.tick_once()
    assert recorder.frame_writes == []
    assert len(recorder.durable_writes) == 2


def test_transition_respects_its_measured_duration():
    """A blanch that took two seconds would not read as a threat response."""
    recorder = Recorder()
    animator = _animator(recorder, [_palette(Signal.RESTING), _palette(Signal.FAULT)],
                         fps=60.0)
    animator.tick_once()
    began = time.monotonic()
    animator.tick_once()
    elapsed = time.monotonic() - began
    assert elapsed < BLANCH.duration * 2.5, f"blanch took {elapsed:.2f}s"


def test_stop_interrupts_an_in_flight_transition_promptly():
    """Session end must not block on a 2.4s recovery; a cosmetic layer must never
    be the reason a shell hesitates to exit."""
    recorder = Recorder()
    animator = _animator(recorder, [_palette(Signal.FAULT), _palette(Signal.RESTING)],
                         fps=60.0)
    animator.tick_once()

    done = threading.Event()

    def run():
        animator.tick_once()
        done.set()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    time.sleep(0.05)
    began = time.monotonic()
    animator.stop()
    done.wait(timeout=2.0)
    assert time.monotonic() - began < RECOVER.duration


def test_background_tint_can_be_switched_off():
    recorder = Recorder()
    animator = _animator(recorder, [_palette()], tint_background=False)
    animator.tick_once()
    assert "background" not in recorder.durable_writes[0][1]


def test_background_tint_is_on_by_default_and_is_near_black():
    """Adam, 2026-09-09: the session background should be cuttlefish-black. Near
    black means low luminance; "this session's" means it is not pure #000000."""
    from cuttlefish_theme.color.oklab import hex_to_oklch

    recorder = Recorder()
    animator = _animator(recorder, [_palette()])
    animator.tick_once()
    ground = recorder.durable_writes[0][1]["background"]
    assert hex_to_oklch(ground).L < 0.25
    assert ground.lower() != "#000000"


def test_two_sessions_get_distinguishable_grounds():
    """The point of a per-session ground: two terminals side by side must not be
    the same black."""
    a = render(allocate("alpha", []), Signal.RESTING)
    b = render(allocate("beta", [a.identity_hex]), Signal.RESTING)
    assert a.ground_hex != b.ground_hex


def test_watch_interval_must_be_positive():
    with pytest.raises(ValueError):
        Animator(compute=_palette, skin_name="x", watch_interval=0)
