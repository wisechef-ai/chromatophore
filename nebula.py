"""Nebula structure: turning a texture into an OBJECT.

WHY THIS EXISTS

Reviewed by gpt-5.6-sol and glm-5.3 (2026-09-09), and they converged on the same
diagnosis independently:

  sol:  "the current construction gives cuttlefish-like mottling, but it lacks
         the large-scale organization needed to read as a nebula ... Do not let
         full-field noise emit substantial light outside the envelope. That is a
         major distinction between an organized nebula and generic cloudy noise."

  glm:  "currently the 30x30 field is statistically homogeneous, so it looks like
         texture, not like an object. Nebula reads as object because of
         asymmetry: bright core off-center, fading edge."

That is the whole problem in one sentence. Value noise is STATIONARY — its
statistics are the same everywhere — so however pretty the colours are, the eye
reads a swatch of material rather than a thing sitting in space.

FOUR STRUCTURES, in the priority both reviewers gave:

  1. CORE ENVELOPE   an off-centre, rotated, noise-perturbed ellipse. Light is
                     confined to it, so the field becomes an object with a
                     silhouette instead of wall-to-wall cloud.
  2. FILAMENTS       ridged noise (`1 - |2n-1|`) has thin creases along its zero
                     set, which is what a tendril is. Domain-warping curves them.
  3. STARS           sparse isolated bright points. Both reviewers called this
                     the cheapest high-impact cue; glm added the detail that
                     matters — place them only where the cloud is THIN, or they
                     read as noise inside the nebula rather than as stars behind
                     it, and give them a magnitude distribution (many dim, few
                     bright) rather than uniform brightness.
  4. DARK LANE       an absorption lane crossing the bright region. Nebulae are
                     interrupted by dust; an uninterrupted glow looks synthetic.

COST

Everything is integer-hash value noise and arithmetic over 900 cells — a handful
of milliseconds, no dependencies. That budget is a hard constraint: this runs at
session start, in front of the user.
"""

from __future__ import annotations

import math

from .field import Field, _hash01, _smooth_noise

__all__ = ["nebula"]


def _fbm(x: float, y: float, seed: int, octaves=((12.0, 0.55), (6.0, 0.30), (3.0, 0.15))) -> float:
    """Fractal value noise: a few octaves at decreasing amplitude.

    Three octaves is sol's recommendation and it is the right call at this size —
    a fourth octave's features land below one cell and only add grain.
    """
    return sum(amp * _smooth_noise(x / scale, y / scale, seed ^ int(scale * 977))
               for scale, amp in octaves)


def _core_params(seed: int) -> tuple:
    """The envelope's shape, computed ONCE per field rather than per cell.

    These are constant for a session, and recomputing them 900 times (five
    hashes and two trig calls each) was measurable. Profiling discipline: the
    whole field must render in a few milliseconds because it runs at session
    start, in front of the user.
    """
    cx = 0.32 + 0.36 * _hash01(seed, 11)
    cy = 0.30 + 0.40 * _hash01(seed, 12)
    angle = math.radians(20.0 + 130.0 * _hash01(seed, 13))
    rx = 0.40 + 0.28 * _hash01(seed, 14)
    ry = 0.20 + 0.20 * _hash01(seed, 15)
    return cx, cy, math.cos(angle), math.sin(angle), rx, ry


def _core_mask(x: float, y: float, w: int, h: int, params: tuple) -> float:
    """An off-centre, rotated elliptical envelope.

    Every parameter is deliberately asymmetric. A centred, axis-aligned ellipse
    reads as a vignette — a rendering artefact — where an off-axis one reads as an
    object that happens to be in frame. sol: "never exactly centered", and avoid
    within ~10 degrees of horizontal or vertical.
    """
    cx, cy, ca, sa, rx, ry = params
    nx = (x / max(1, w - 1)) - cx
    ny = (y / max(1, h - 1)) - cy
    u = ca * nx + sa * ny
    v = -sa * nx + ca * ny
    return math.exp(-1.1 * ((u / rx) ** 2 + (v / ry) ** 2))


def _ridge(x: float, y: float, seed: int, scale: float) -> float:
    """Ridged noise: thin creases where the underlying field crosses its midpoint.

    `1 - |2n - 1|` peaks along the n=0.5 contour, and a contour is a line — which
    is why this produces filaments where plain value noise produces blobs.
    """
    n = _smooth_noise(x / scale, y / scale, seed)
    return 1.0 - abs(2.0 * n - 1.0)


def nebula(width: int, height: int, *, seed: int,
           star_rate: float = 0.018) -> Field:
    """A nebula-structured expansion field: core, filaments, dust lane, stars.

    Returns the same 0..1 expansion `Field` the flat mottle produced, so the
    pigment/compositing layers above are unchanged — this replaces only the
    question of WHERE light is, not what colour it is.
    """
    field = Field.blank(width, height)
    params = _core_params(seed)

    # Domain warp: displace the sample point by another noise field so filaments
    # curve and swirl instead of running straight. Cheap, and it is most of the
    # difference between "procedural" and "photographed".
    def warped(x: int, y: int, scale: float, s: int) -> float:
        wx = x + 6.0 * (_smooth_noise(x / 9.0, y / 9.0, seed ^ 0x51ED) - 0.5)
        wy = y + 6.0 * (_smooth_noise(x / 9.0, y / 9.0, seed ^ 0x2B7C) - 0.5)
        return _ridge(wx, wy, s, scale)

    for y in range(height):
        for x in range(width):
            core = _core_mask(x, y, width, height, params)
            cloud = _fbm(x, y, seed ^ 0x1234)
            # Light lives INSIDE the envelope. Without this the field is
            # wall-to-wall cloud and the silhouette never forms.
            v = core * (0.30 + 0.95 * cloud)

            # Filaments, strongest at the cloud's edge where real tendrils are.
            fil = warped(x, y, 4.5, seed ^ 0x77A1)
            v += 0.42 * core * (fil ** 3.0)

            # Absorption lane: a dark band cutting the bright region. Squaring
            # the complement keeps it narrow rather than a general dimming.
            lane = _ridge(x * 0.8, y * 1.6, seed ^ 0x3C0D, 7.0)
            v *= 1.0 - 0.55 * (lane ** 4.0)

            field.set(x, y, v)

    # Stars last, so nothing dims them. Placed only where the cloud is THIN
    # (glm's point): a bright point inside the glow reads as noise, the same
    # point against dark sky reads as a star behind the nebula.
    for y in range(height):
        for x in range(width):
            if _hash01(x, y, seed ^ 0xA17E) >= star_rate:
                continue
            if field.get(x, y) > 0.30:
                continue
            # Magnitude distribution: mostly faint, a few bright. Uniform
            # brightness reads as a grid of dots, not as a star field.
            mag = _hash01(x, y, seed ^ 0xB92F)
            field.set(x, y, 0.55 + 0.45 * (mag ** 2.4))
    return field


def stats(field: Field) -> dict:
    """Measurements used by the tests: is this an object, or a texture?"""
    cells = field.cells
    n = len(cells)
    lit = [v for v in cells if v > 0.25]
    # Centre of mass of the light: an object's light is off-centre, a texture's
    # sits at the middle of the frame.
    tx = ty = tw = 0.0
    for y in range(field.height):
        for x in range(field.width):
            w = field.get(x, y)
            tx += x * w
            ty += y * w
            tw += w
    cx = (tx / tw) / max(1, field.width - 1) if tw else 0.5
    cy = (ty / tw) / max(1, field.height - 1) if tw else 0.5
    return {
        "lit_fraction": len(lit) / n,
        "centroid": (round(cx, 3), round(cy, 3)),
        "offset_from_centre": round(math.hypot(cx - 0.5, cy - 0.5), 3),
        "max": round(max(cells), 3),
        "p50": round(sorted(cells)[n // 2], 3),
        "p90": round(sorted(cells)[9 * n // 10], 3),
    }
