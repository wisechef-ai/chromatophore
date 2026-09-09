"""Trajectories through pattern space: how one appearance becomes another.

The v1 theme cross-faded nothing — it snapped between two static palettes. That is
not what the animal does, and the difference is the whole point of this module.

WHY THE CURVES ARE SHAPED THE WAY THEY ARE

Every constant here is a reading of measured cuttlefish behaviour, not a designer's
easing preference. Three findings from Woo et al., *The dynamics of pattern matching
in camouflaging cuttlefish*, Nature 619 (2023), doi:10.1038/s41586-023-06259-2:

1. BLANCHING IS FAST AND DIRECT. "Pattern motion during blanching was direct and
   fast, consistent with open-loop motion in low-dimensional pattern space." The
   animal is not searching; it has one destination and goes there. So `Blanch` is
   monotonic, synchronous across all components, and short. No overshoot, no
   wandering: a threat response that meandered would be a dead animal.

2. RECOVERY IS SLOWER, DECELERATING, AND STAGGERED. "The blanching motion was fast;
   recovery was slower with gradual deceleration" (Fig. 5b). Critically, Fig. 5g
   orders chromatophores *by expansion onset* and finds they "formed reliable
   non-random patterns" — the skin does not come back all at once. Different
   components restart at different times, reproducibly. So `Recover` staggers each
   component's onset and decelerates into the target.

3. CAMOUFLAGE SEARCH IS TORTUOUS AND INTERMITTENT. "Each search meanders through
   skin-pattern space, decelerating and accelerating repeatedly before stabilizing",
   and "the number of successive low-velocity regions increased as the animal skin
   approached its target pattern, as did the dwell time in each such region."
   So `Settle` alternates motion with pauses, and the pauses get longer and more
   frequent as it converges. That is why it reads as *alive* rather than as an
   animation: nothing in a tween library produces that profile.

THE COMPONENT REORGANISATION

Finding 4 in the same paper: pattern components "are not stable entities and can be
defined only over specific segments of activity" — the same chromatophores group
differently on each traversal, even between identical start and end patterns. We
reproduce that literally: `components()` re-partitions the palette keys on every
transition, seeded by (session, transition ordinal). Two identical blanch/recover
cycles in the same session therefore recruit *different* groupings, so the motion
never looks like a loop of the same canned animation. This costs one hash.

WHAT THIS MODULE IS NOT

It has no I/O, no timers and no Hermes imports. It maps time to colour, and that is
all — which is what makes the trajectory shapes testable as behaviour contracts
rather than as screenshots.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from typing import Iterator, Mapping, Sequence

from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex

__all__ = [
    "Trajectory",
    "BLANCH",
    "RECOVER",
    "SETTLE",
    "components",
    "lerp_oklch",
    "morph",
    "frames",
]


# --- deterministic per-transition randomness --------------------------------

def _stream(*parts: object) -> Iterator[float]:
    """An endless, reproducible float stream in [0, 1) keyed by *parts*.

    blake2b rather than `random.Random`: this must be identical across processes
    and Python builds. `hash()` is randomised per process (PYTHONHASHSEED) and
    would give a session a different personality on every restart — the exact bug
    the identity layer already avoids.
    """
    seed = "\x1f".join(str(p) for p in parts).encode("utf-8")
    counter = 0
    while True:
        digest = hashlib.blake2b(seed + struct.pack("<Q", counter), digest_size=64).digest()
        for offset in range(0, 64, 8):
            word = struct.unpack("<Q", digest[offset:offset + 8])[0]
            yield (word >> 11) / float(1 << 53)
        counter += 1


def components(keys: Sequence[str], *, seed: object, count: int = 0) -> list[list[str]]:
    """Partition *keys* into covarying pattern components for ONE transition.

    Deliberately re-derived per transition (see module docstring, finding 4): the
    same key belongs to a different component on the next traversal, so repeated
    state changes never replay an identical animation.

    Every component is non-empty and every key appears exactly once — a key that
    fell out of the partition would freeze mid-transition and never reach its
    target colour, which is a latched wrong colour, not a cosmetic glitch.
    """
    keys = list(keys)
    if not keys:
        return []
    rng = _stream("components", seed)
    if count <= 0:
        # 3-6 components. The paper's own decomposition ran to ~30 over millions of
        # cells; over ~14 palette keys, more than 6 makes every component a
        # singleton and the staggering degenerates into noise.
        count = 3 + int(next(rng) * 4)
    count = max(1, min(count, len(keys)))

    # Shuffle then deal round-robin: guarantees non-empty components without a
    # rejection loop, and guarantees the "exactly once" invariant structurally.
    order = list(keys)
    for i in range(len(order) - 1, 0, -1):
        j = int(next(rng) * (i + 1))
        order[i], order[j] = order[j], order[i]
    buckets: list[list[str]] = [[] for _ in range(count)]
    for index, key in enumerate(order):
        buckets[index % count].append(key)
    return buckets


# --- trajectory shapes ------------------------------------------------------

@dataclass(frozen=True)
class Trajectory:
    """A named path through pattern space.

    ``progress(t, phase)`` returns how far along a component is at time *t*, in
    0..1, where *phase* is that component's position in the stagger order (0 =
    first to move, 1 = last).
    """

    name: str
    duration: float
    stagger: float          # fraction of duration spread across component onsets
    intermittent: bool      # alternate motion with dwell (camouflage search)
    decelerate: float       # >1 eases out harder into the target

    def progress(self, t: float, phase: float = 0.0, *, seed: object = 0) -> float:
        if self.duration <= 0:
            return 1.0
        if t <= 0.0:
            return 0.0
        if t >= self.duration:
            return 1.0

        # Component onset stagger (finding 2): later components start later and
        # then have less time, so everything still lands exactly on `duration`.
        onset = self.stagger * self.duration * max(0.0, min(1.0, phase))
        span = self.duration - onset
        if span <= 0 or t <= onset:
            return 0.0
        u = (t - onset) / span

        if self.intermittent:
            u = _intermittent(u, seed=seed)
        # Clamp before the power. `_intermittent` sums per-segment fractions and
        # can land on 1.0000000000000002 (measured: ~3% of samples), which makes
        # (1 - u) a tiny NEGATIVE number — and in Python a negative base to a
        # fractional exponent returns a COMPLEX number rather than raising. That
        # complex then propagates silently into `morph`, where the first
        # comparison against a float raises TypeError and takes the whole command
        # down. `hermes cuttlefish demo` crashed exactly this way.
        u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
        # Deceleration into the target. exponent > 1 on (1-u) => ease-out.
        return 1.0 - (1.0 - u) ** self.decelerate


# Dwell fractions rise toward the end (finding 3: pauses grow as convergence nears).
_DWELL_STEPS = 5


def _intermittent(u: float, *, seed: object) -> float:
    """Re-time *u* so motion alternates with dwell, pauses lengthening near the end.

    Monotonic by construction — a non-monotonic remap would make the colour walk
    backwards, which the animal does not do (its heading at every motion onset
    points at the target).
    """
    rng = _stream("dwell", seed)
    # Segment boundaries in normalised time, plus per-segment dwell fraction that
    # grows with index. Jitter keeps two transitions from sharing a rhythm.
    dwells = []
    for i in range(_DWELL_STEPS):
        base = 0.15 + 0.55 * (i / (_DWELL_STEPS - 1))
        dwells.append(min(0.85, base * (0.75 + 0.5 * next(rng))))

    seg = 1.0 / _DWELL_STEPS
    index = min(_DWELL_STEPS - 1, int(u / seg))
    local = (u - index * seg) / seg           # 0..1 within this segment

    # Distance already covered by completed segments, in OUTPUT space.
    moved_per_seg = [(1.0 - d) for d in dwells]
    total = sum(moved_per_seg) or 1.0
    covered = sum(moved_per_seg[:index]) / total

    # Inside a segment: move first, then dwell.
    active = 1.0 - dwells[index]
    if active <= 0:
        return covered
    local_moved = min(1.0, local / active) if active > 0 else 1.0
    return covered + (moved_per_seg[index] / total) * local_moved


# Durations: blanch ~0.4s (fast/direct), recover ~6x longer with deceleration and
# strong stagger, settle in between and intermittent. The RATIO is the measured
# claim ("blanching motion was fast; recovery was slower"); the absolute seconds
# are a UI choice tuned to stay under the ~2s attention budget for a terminal.
BLANCH = Trajectory("blanch", duration=0.40, stagger=0.00, intermittent=False, decelerate=1.15)
RECOVER = Trajectory("recover", duration=2.40, stagger=0.55, intermittent=False, decelerate=2.60)
SETTLE = Trajectory("settle", duration=1.60, stagger=0.30, intermittent=True, decelerate=1.80)


# --- colour interpolation ---------------------------------------------------

def lerp_oklch(a: OKLCh, b: OKLCh, t: float) -> OKLCh:
    """Interpolate perceptually, taking the SHORT way around the hue circle.

    In OKLCh, not sRGB: a naive hex lerp from teal to amber passes through a muddy
    grey because it cuts through the middle of the colour solid. Going around in
    hue keeps every intermediate frame a colour the palette could plausibly have
    contained, which is what makes the motion read as one skin changing rather
    than as two colours dissolving.
    """
    t = max(0.0, min(1.0, t))
    dh = (b.h - a.h + 180.0) % 360.0 - 180.0
    return OKLCh(
        a.L + (b.L - a.L) * t,
        a.C + (b.C - a.C) * t,
        (a.h + dh * t) % 360.0,
    )


def morph(
    start: Mapping[str, str],
    target: Mapping[str, str],
    trajectory: Trajectory,
    t: float,
    *,
    seed: object = 0,
) -> dict[str, str]:
    """The palette at time *t* along *trajectory* from *start* to *target*.

    Keys present in *target* but not in *start* appear immediately at their target
    value: there is nothing to interpolate from, and holding them back would leave
    a hole in a fully-materialised skin file (see skinio's HAZARD 2).
    """
    groups = components(sorted(target), seed=seed)
    phase_of: dict[str, float] = {}
    denominator = max(1, len(groups) - 1)
    for index, group in enumerate(groups):
        phase = index / denominator
        for key in group:
            phase_of[key] = phase

    out: dict[str, str] = {}
    for key, target_hex in target.items():
        start_hex = start.get(key)
        if start_hex is None:
            out[key] = target_hex
            continue
        p = trajectory.progress(t, phase_of.get(key, 0.0), seed=(seed, key))
        if p >= 1.0:
            out[key] = target_hex
        elif p <= 0.0:
            out[key] = start_hex
        else:
            out[key] = oklch_to_hex(
                lerp_oklch(hex_to_oklch(start_hex), hex_to_oklch(target_hex), p)
            )
    return out


def frames(
    start: Mapping[str, str],
    target: Mapping[str, str],
    trajectory: Trajectory,
    *,
    fps: float = 12.0,
    seed: object = 0,
) -> Iterator[tuple[float, dict[str, str]]]:
    """Yield ``(t, palette)`` across the whole trajectory, ending exactly on target.

    The final frame is emitted at exactly ``duration`` regardless of *fps*, so a
    transition can never leave the skin a hair short of its destination — a
    permanently-almost-right colour is worse than no animation at all.
    """
    if fps <= 0:
        yield trajectory.duration, dict(target)
        return
    step = 1.0 / fps
    t = 0.0
    while t < trajectory.duration:
        yield t, morph(start, target, trajectory, t, seed=seed)
        t += step
    yield trajectory.duration, morph(start, target, trajectory, trajectory.duration, seed=seed)


def frame_count(trajectory: Trajectory, fps: float = 12.0) -> int:
    """How many frames :func:`frames` will emit. Used to budget repaint cost."""
    if fps <= 0:
        return 1
    return int(math.ceil(trajectory.duration * fps)) + 1
