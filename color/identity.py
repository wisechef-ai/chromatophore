"""Identity allocation: an endless, never-doubling supply of session colours.

The requirement (Adam, 2026-09-08): "not from a fixed list as this would limit the
variety... I expect to have endless not doubling colourful profiles signalizing."

Two things are being asked for and they are in tension:

  1. ENDLESS — the supply must not run out, so no fixed palette of N swatches.
  2. NEVER-DOUBLING — two sessions must never look the same.

A hash of the session id satisfies (1) and fails (2): hashing into a bounded colour
space collides by the pigeonhole principle, and worse, it collides *perceptually*
long before it collides numerically — two hashes 8 degrees of hue apart are different
numbers and the same colour to a human.

The resolution is that (2) only has to hold for colours that are VISIBLE AT THE SAME
TIME. A cuttlefish does not need a unique pattern with respect to every cuttlefish
that has ever lived; it needs to be distinguishable from the ones in view. So:

  - the colour SPACE is continuous (endless: any point in a large 3-D volume),
  - allocation is resolved against the CURRENTLY LIVE set (never-doubling in practice),
  - and the choice is deterministic given the same live set, so a session keeps its
    colour across reconnects.

Concretely: farthest-point sampling in OKLab. Candidates are generated from the
session id (deterministic, well-spread via a golden-angle sequence), each is scored by
its perceptual distance to every live session's colour, and the best is taken. With
few sessions this yields maximally separated colours; as the live set grows the
achievable separation degrades gracefully rather than colliding abruptly, and the
guaranteed floor is reported so callers can tell the truth about it.
"""

from __future__ import annotations

import colorsys
import hashlib
from dataclasses import dataclass
from typing import Iterable, Sequence

from .oklab import (
    OKLCh,
    delta_e_ok,
    gamut_map,
    hex_to_oklch,
    in_srgb_gamut,
    oklch_to_hex,
)

__all__ = [
    "IdentityColor",
    "allocate",
    "allocate_many",
    "reserved_hue_ranges",
    "is_reserved_hue",
    "MIN_IDENTITY_DISTANCE",
]


# Below this OKLab distance two identities read as "the same colour" at a glance.
# Empirical anchor: 0.10 is a comfortable "different colour" step; we demand more
# between session identities because they are read in the periphery, not compared
# side by side. The allocator maximises distance and only warns when it cannot
# reach this floor — it never silently ships a collision.
MIN_IDENTITY_DISTANCE = 0.155

# Identity lives in a band of lightness/chroma chosen to stay legible on BOTH dark
# and light terminals and to survive 256-colour quantisation. Very dark or very
# desaturated colours become indistinguishable mud; very light ones vanish on white.
#
# Band WIDTH is what buys separation, not candidate count: measured at 8 concurrent
# sessions, going 96 -> 1024 candidates moved the worst pairwise distance by ~0.000
# (0.1362 -> 0.1362), while widening these bands moved it 0.1362 -> 0.1655, i.e. from
# below MIN_IDENTITY_DISTANCE to above it. The volume is the constraint; sampling it
# harder does not create room that isn't there.
_L_MIN, _L_MAX = 0.52, 0.86
_C_MIN, _C_MAX = 0.085, 0.20

# Hue ranges reserved for SEMANTIC state, which identity may never impersonate.
# A session whose identity colour was amber would be permanently unreadable as
# "this session needs you". Amber ~70-95 deg, fault red ~15-40 deg in OKLCh.
_RESERVED: tuple[tuple[float, float], ...] = ((15.0, 42.0), (68.0, 98.0))

# Golden angle: successive multiples land maximally far from all previous ones,
# which gives a low-discrepancy hue sequence rather than hash clumping.
_GOLDEN_ANGLE = 137.50776405003785


def reserved_hue_ranges() -> tuple[tuple[float, float], ...]:
    return _RESERVED


def is_reserved_hue(h: float) -> bool:
    x = h % 360.0
    return any(lo <= x <= hi for lo, hi in _RESERVED)


@dataclass(frozen=True)
class IdentityColor:
    """An allocated session identity.

    ``separation`` is the OKLab distance to the nearest concurrently-live identity
    (``inf`` when alone). ``crowded`` is True when we could not reach
    ``MIN_IDENTITY_DISTANCE`` — surfaced honestly rather than hidden, because the
    user's trust in the colour code depends on knowing when it is strained.
    """

    session_id: str
    oklch: OKLCh
    hex: str
    separation: float
    crowded: bool

    @property
    def hue(self) -> float:
        return self.oklch.h


def _seed_stream(session_id: str) -> tuple[int, ...]:
    """Deterministic 64-bit words from the session id.

    blake2b rather than ``hash()``: Python's string hash is randomised per process
    (PYTHONHASHSEED), so a session would change colour on reconnect — fatal for an
    identity channel.
    """
    digest = hashlib.blake2b(session_id.encode("utf-8"), digest_size=32).digest()
    return tuple(int.from_bytes(digest[i:i + 8], "big") for i in range(0, 32, 8))


def _candidates(session_id: str, count: int) -> list[OKLCh]:
    """Deterministic, well-spread candidate colours for this session id.

    The id fixes a starting point in the (hue, L, C) volume; successive candidates
    walk the golden angle in hue and a low-discrepancy sequence in L and C, so the
    candidate set explores the whole volume instead of clustering near the seed.
    """
    w0, w1, w2, _w3 = _seed_stream(session_id)
    h0 = (w0 % 360_000) / 1000.0
    l0 = (w1 % 1_000_000) / 1_000_000.0
    c0 = (w2 % 1_000_000) / 1_000_000.0

    out: list[OKLCh] = []
    i = 0
    # Over-generate: reserved-hue rejection and gamut mapping both drop candidates.
    while len(out) < count and i < count * 12:
        h = (h0 + i * _GOLDEN_ANGLE) % 360.0
        i += 1
        if is_reserved_hue(h):
            continue
        # Additive recurrences with irrational increments (van der Corput style)
        # spread L and C without correlating them to hue.
        L = _L_MIN + (_L_MAX - _L_MIN) * ((l0 + 0.6180339887498949 * i) % 1.0)
        C = _C_MIN + (_C_MAX - _C_MIN) * ((c0 + 0.7548776662466927 * i) % 1.0)
        cand = gamut_map(OKLCh(L, C, h))
        # Gamut mapping can crush chroma in the deep blues/violets; a washed-out
        # identity is a weak identity, so drop those rather than ship them.
        if cand.C >= _C_MIN * 0.72 and in_srgb_gamut(cand):
            out.append(cand)
    return out


def allocate(
    session_id: str,
    live: Iterable[str | OKLCh] = (),
    *,
    min_distance: float = MIN_IDENTITY_DISTANCE,
    candidate_count: int = 96,
) -> IdentityColor:
    """Allocate the identity colour for *session_id* given the *live* set.

    *live* holds the colours of other currently-visible sessions, as hex strings or
    ``OKLCh``. The result is deterministic for a given (session_id, live) pair, so a
    reconnecting session recovers its colour as long as its neighbours are unchanged.

    Raises ``ValueError`` on an empty session id — an unnamed identity is a bug we
    want loud, not a grey default we would ship silently.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")

    others: list[OKLCh] = [c if isinstance(c, OKLCh) else hex_to_oklch(c) for c in live]
    cands = _candidates(session_id, candidate_count)
    if not cands:  # pragma: no cover - only reachable if the bands are misconfigured
        raise RuntimeError("no in-gamut candidates; identity colour bands are invalid")

    if not others:
        # Alone: the first candidate is already deterministic and well-placed.
        best, sep = cands[0], float("inf")
    else:
        # Farthest-point selection: maximise the distance to the NEAREST neighbour.
        scored = [(min(delta_e_ok(c, o) for o in others), c) for c in cands]
        sep, best = max(scored, key=lambda t: (t[0], -t[1].h))

    return IdentityColor(
        session_id=session_id,
        oklch=best,
        hex=oklch_to_hex(best),
        separation=sep,
        crowded=sep < min_distance,
    )


def allocate_many(session_ids: Sequence[str], **kw) -> list[IdentityColor]:
    """Allocate for several sessions in order, each aware of the ones before it.

    Order-dependent by design: it mirrors reality, where sessions start one at a
    time and an existing session's colour must not be reassigned because a new
    one appeared.
    """
    out: list[IdentityColor] = []
    for sid in session_ids:
        out.append(allocate(sid, [c.oklch for c in out], **kw))
    return out
