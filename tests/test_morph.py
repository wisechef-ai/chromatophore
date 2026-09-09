"""Behaviour contracts for cuttlefish_theme.morph.

Every assertion here is a claim about the ANIMAL, taken from Woo et al., Nature 619
(2023), and enforced against our implementation. They are contracts, not snapshots:
none of them pins a magic constant that a tuning change would legitimately move.
The one exception is the blanch/recover duration ORDERING, which is itself the
paper's finding and must not be "tuned" away.
"""

from __future__ import annotations

import pytest

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.morph import (BLANCH, RECOVER, SETTLE, Trajectory,
                                    components, frame_count, frames,
                                    lerp_oklch, morph)

START = {
    "ui_accent": "#2F9C9F",
    "banner_accent": "#2F9C9F",
    "ui_border": "#1E5F61",
    "prompt": "#2F9C9F",
    "ui_tool": "#7FD4D6",
    "background": "#0B1516",
}
TARGET = {
    "ui_accent": "#F1B200",
    "banner_accent": "#F1B200",
    "ui_border": "#8A6600",
    "prompt": "#F1B200",
    "ui_tool": "#FFD46A",
    "background": "#161008",
}


# --- the measured findings --------------------------------------------------

def test_blanching_is_faster_than_recovery():
    """Nature 2023, Fig. 5b: "blanching motion was fast; recovery was slower".

    This is the paper's result, not a taste call, so it is a hard contract.
    """
    assert BLANCH.duration < RECOVER.duration


def test_blanching_is_synchronous_and_recovery_is_staggered():
    """Blanching is a general inhibition (all cells release together); recovery
    "reveals components with different dynamics" (Fig. 5g orders chromatophores by
    expansion onset and finds reliable, non-random patterns)."""
    assert BLANCH.stagger == 0.0
    assert RECOVER.stagger > 0.0


def test_blanching_is_direct_and_camouflage_search_is_intermittent():
    """"Pattern motion during blanching was direct and fast, consistent with
    open-loop motion" vs camouflage, which "meanders ... decelerating and
    accelerating repeatedly before stabilizing"."""
    assert BLANCH.intermittent is False
    assert SETTLE.intermittent is True


def test_recovery_decelerates_into_the_target():
    """"recovery was slower with gradual deceleration". Measured as: the second
    half of the trajectory covers less ground than the first."""
    first_half = RECOVER.progress(RECOVER.duration * 0.5)
    assert first_half > 0.5, "a decelerating curve is past halfway at half time"


def test_intermittent_trajectory_actually_pauses():
    """The distinguishing feature of the camouflage search is dwell: there must be
    stretches of time where progress does not advance. A smooth ease would pass
    every other test in this file while looking nothing like the animal."""
    samples = [SETTLE.progress(SETTLE.duration * i / 200.0, seed="pause") for i in range(201)]
    deltas = [b - a for a, b in zip(samples, samples[1:])]
    moving = [d for d in deltas if d > 1e-9]
    still = [d for d in deltas if d <= 1e-9]
    assert still, "an intermittent trajectory must have low-velocity regions"
    assert moving, "...and must also move"
    # Speed varies substantially between motion segments (Extended Data Fig. 5g:
    # "note the large speed variations"). Measured max/mean is a stable ~1.83
    # across seeds, and max/min exceeds 100 — so 1.5 is a floor the shape clears
    # comfortably while still failing outright for any constant-velocity ramp,
    # which would score exactly 1.0.
    assert max(moving) / (sum(moving) / len(moving)) > 1.5


def test_pauses_lengthen_as_convergence_nears():
    """"The number of successive low-velocity regions increased as the animal skin
    approached its target pattern, as did the dwell time in each such region"."""
    samples = [SETTLE.progress(SETTLE.duration * i / 400.0, seed="dwell-growth")
               for i in range(401)]
    deltas = [b - a for a, b in zip(samples, samples[1:])]
    half = len(deltas) // 2
    early_still = sum(1 for d in deltas[:half] if d <= 1e-9)
    late_still = sum(1 for d in deltas[half:] if d <= 1e-9)
    assert late_still > early_still


@pytest.mark.parametrize("trajectory", [BLANCH, RECOVER, SETTLE])
def test_progress_is_monotonic(trajectory: Trajectory):
    """The animal's heading at every motion onset points AT the target; it never
    walks backwards. A non-monotonic remap would show as a colour visibly
    reversing mid-transition."""
    last = -1.0
    for i in range(0, 501):
        p = trajectory.progress(trajectory.duration * i / 500.0, seed="mono")
        assert p >= last - 1e-12, f"went backwards at t={i}"
        last = p


@pytest.mark.parametrize("trajectory", [BLANCH, RECOVER, SETTLE])
def test_every_trajectory_starts_at_zero_and_lands_exactly(trajectory: Trajectory):
    """A transition that stops at 0.99 leaves a permanently-almost-right colour,
    which is worse than not animating at all."""
    assert trajectory.progress(0.0) == 0.0
    assert trajectory.progress(trajectory.duration) == 1.0
    assert trajectory.progress(trajectory.duration * 10) == 1.0
    # Every phase must also land, including the last component to start.
    assert trajectory.progress(trajectory.duration, phase=1.0) == 1.0


# --- component reorganisation -----------------------------------------------

def test_components_partition_exactly():
    """Every key in exactly one component. A key dropped from the partition would
    freeze mid-transition and latch a wrong colour."""
    keys = sorted(TARGET)
    for seed in range(25):
        groups = components(keys, seed=seed)
        flat = [k for g in groups for k in g]
        assert sorted(flat) == keys
        assert len(flat) == len(set(flat))
        assert all(g for g in groups), "no empty components"


def test_components_reorganise_between_transitions():
    """Nature 2023, finding 4: components "are not stable entities and can be
    defined only over specific segments of activity" — the same chromatophores
    group differently on each traversal, even between identical pattern pairs.

    Concretely: two runs of the SAME transition must not produce the same grouping
    every time, or the animation is a canned loop.
    """
    keys = sorted(TARGET) + ["a", "b", "c", "d", "e", "f"]
    shapes = {tuple(tuple(sorted(g)) for g in components(keys, seed=i)) for i in range(20)}
    assert len(shapes) > 1, "components never reorganised across transitions"


def test_components_are_deterministic_for_one_transition():
    """Reproducible for a given seed: two processes animating the same transition
    (a reconnect, a replay) must agree, exactly as identity allocation does."""
    keys = sorted(TARGET)
    assert components(keys, seed="x7") == components(keys, seed="x7")


def test_components_handles_degenerate_inputs():
    assert components([], seed=1) == []
    assert components(["only"], seed=1) == [["only"]]


# --- colour interpolation ---------------------------------------------------

def test_hue_takes_the_short_way_round():
    """Interpolating 350deg -> 10deg must pass through 0, not sweep back through
    180 (which would put a green frame in the middle of a red fade)."""
    from cuttlefish_theme.color.oklab import OKLCh

    a = OKLCh(0.6, 0.1, 350.0)
    b = OKLCh(0.6, 0.1, 10.0)
    mid = lerp_oklch(a, b, 0.5)
    assert mid.h > 355.0 or mid.h < 5.0, f"took the long way: {mid.h}"


def test_interpolation_never_passes_through_grey():
    """The reason for OKLCh rather than a hex lerp: a naive sRGB blend from teal to
    amber cuts through the middle of the colour solid and desaturates. Every
    intermediate frame must stay a colour the palette could have contained."""
    a = hex_to_oklch("#2F9C9F")
    b = hex_to_oklch("#F1B200")
    floor = min(a.C, b.C) * 0.75
    for i in range(1, 20):
        assert lerp_oklch(a, b, i / 20.0).C >= floor


def test_morph_endpoints_are_exact():
    at_zero = morph(START, TARGET, RECOVER, 0.0, seed=1)
    at_end = morph(START, TARGET, RECOVER, RECOVER.duration, seed=1)
    assert at_zero == START
    assert at_end == TARGET


def test_morph_keeps_every_key_and_valid_hex():
    """A fully-materialised skin file needs every key present at every instant;
    a hole would inherit Hermes' default palette (skinio HAZARD 2)."""
    for i in range(0, 25):
        frame = morph(START, TARGET, SETTLE, SETTLE.duration * i / 24.0, seed="k")
        assert set(frame) == set(TARGET)
        for value in frame.values():
            assert len(value) == 7 and value[0] == "#"
            int(value[1:], 16)


def test_morph_passes_through_new_keys_immediately():
    """A key with nothing to interpolate FROM appears at its target value rather
    than being withheld, which would leave the skin file incomplete."""
    frame = morph({}, TARGET, RECOVER, 0.0, seed=1)
    assert frame == TARGET


def test_frames_always_end_exactly_on_target():
    """Whatever the fps, the last frame is the target — not one step short."""
    for fps in (1.0, 7.5, 24.0, 60.0):
        last_t, last = list(frames(START, TARGET, BLANCH, fps=fps, seed=2))[-1]
        assert last_t == pytest.approx(BLANCH.duration)
        assert last == TARGET


def test_frames_are_budgeted_honestly():
    emitted = len(list(frames(START, TARGET, RECOVER, fps=24.0, seed=3)))
    assert emitted == frame_count(RECOVER, 24.0)


def test_zero_fps_degrades_to_a_single_final_frame():
    """The no-animation path must still deliver the target, not nothing."""
    got = list(frames(START, TARGET, RECOVER, fps=0.0, seed=4))
    assert len(got) == 1 and got[0][1] == TARGET
