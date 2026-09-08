"""OKLab / OKLCh colour science, sRGB gamut mapping, and perceptual distance.

Why OKLab and not HSL: equal steps in HSL are NOT equal perceptual steps — a 30 degree
hue rotation near yellow is a far larger visual jump than the same rotation near blue.
Session identities assigned by HSL hue angle therefore look bunched and collide
perceptually even when their numbers are far apart. OKLab (Bjorn Ottosson, 2020) is
designed so Euclidean distance approximates perceived difference, which is exactly the
property the identity allocator needs.

Reference: https://bottosson.github.io/posts/oklab/
All conversions here are exact ports of the published matrices; `test_oklab.py` pins
them against Ottosson's own reference values plus round-trip invariants.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

__all__ = [
    "OKLCh",
    "srgb_to_oklab",
    "oklab_to_srgb",
    "oklab_to_oklch",
    "oklch_to_oklab",
    "hex_to_rgb",
    "rgb_to_hex",
    "oklch_to_hex",
    "hex_to_oklch",
    "in_srgb_gamut",
    "gamut_map",
    "delta_e_ok",
    "relative_luminance",
]


# --- sRGB transfer function -------------------------------------------------

def _srgb_to_linear(c: float) -> float:
    """Undo the sRGB gamma encoding. The 0.04045 knee is part of the spec, not an
    approximation — using a plain 2.2 power here shifts dark colours noticeably."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


# --- OKLab core -------------------------------------------------------------

def srgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """sRGB (each channel 0..1, gamma-encoded) -> OKLab (L, a, b)."""
    lr, lg, lb = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)

    l = 0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb
    m = 0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb
    s = 0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb

    # The cube root is the perceptual compression step; it must be sign-safe because
    # tiny negative values appear from floating point on near-black inputs.
    l_, m_, s_ = _cbrt(l), _cbrt(m), _cbrt(s)

    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_srgb(L: float, a: float, b: float) -> tuple[float, float, float]:
    """OKLab -> sRGB (0..1, gamma-encoded). May return out-of-gamut values; callers
    that need a displayable colour must go through :func:`gamut_map` first."""
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b

    l, m, s = l_ * l_ * l_, m_ * m_ * m_, s_ * s_ * s_

    lr = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    lg = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    lb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    return (_linear_to_srgb(lr), _linear_to_srgb(lg), _linear_to_srgb(lb))


def _cbrt(x: float) -> float:
    """Sign-preserving cube root (``math.pow`` raises on negative bases)."""
    return math.copysign(abs(x) ** (1 / 3), x)


# --- Polar form -------------------------------------------------------------

@dataclass(frozen=True)
class OKLCh:
    """Polar OKLab: L in 0..1, C >= 0, h in degrees 0..360.

    Frozen because an identity's colour must never be mutated in place — the whole
    design depends on identity being byte-stable across state changes.
    """

    L: float
    C: float
    h: float

    def with_(self, *, L: float | None = None, C: float | None = None,
              h: float | None = None) -> "OKLCh":
        return OKLCh(
            self.L if L is None else L,
            self.C if C is None else C,
            (self.h if h is None else h) % 360.0,
        )


def oklab_to_oklch(L: float, a: float, b: float) -> OKLCh:
    return OKLCh(L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360.0)


def oklch_to_oklab(c: OKLCh) -> tuple[float, float, float]:
    rad = math.radians(c.h)
    return (c.L, c.C * math.cos(rad), c.C * math.sin(rad))


# --- Hex helpers ------------------------------------------------------------

def hex_to_rgb(value: str) -> tuple[float, float, float]:
    """``#rrggbb`` -> three 0..1 floats. Shorthand ``#rgb`` is expanded."""
    s = value.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"expected #rrggbb, got {value!r}")
    try:
        n = int(s, 16)
    except ValueError as exc:
        raise ValueError(f"expected #rrggbb, got {value!r}") from exc
    return (((n >> 16) & 0xFF) / 255.0, ((n >> 8) & 0xFF) / 255.0, (n & 0xFF) / 255.0)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Three 0..1 floats -> ``#rrggbb``, clamped. Rounding is half-up via ``+0.5``
    so 0.5/255 boundaries do not drift downward under banker's rounding."""
    def ch(v: float) -> int:
        return max(0, min(255, int(max(0.0, min(1.0, v)) * 255.0 + 0.5)))

    return f"#{ch(r):02X}{ch(g):02X}{ch(b):02X}"


def oklch_to_hex(c: OKLCh) -> str:
    """Gamut-map then encode. Always returns a displayable sRGB colour."""
    return rgb_to_hex(*oklab_to_srgb(*oklch_to_oklab(gamut_map(c))))


def hex_to_oklch(value: str) -> OKLCh:
    return oklab_to_oklch(*srgb_to_oklab(*hex_to_rgb(value)))


# --- Gamut ------------------------------------------------------------------

_GAMUT_EPS = 1e-4


def in_srgb_gamut(c: OKLCh) -> bool:
    r, g, b = oklab_to_srgb(*oklch_to_oklab(c))
    return all(-_GAMUT_EPS <= v <= 1.0 + _GAMUT_EPS for v in (r, g, b))


def gamut_map(c: OKLCh, *, iterations: int = 24) -> OKLCh:
    """Bring *c* into sRGB by reducing chroma, holding L and h fixed.

    Holding hue is what makes this safe for identity: a naive per-channel clamp
    shifts hue (clipping red first turns orange into yellow), which would let two
    sessions that were allocated far apart collide after clipping. Bisection on
    chroma keeps the hue promise the allocator relies on.
    """
    if in_srgb_gamut(c):
        return c
    # An out-of-range L cannot be fixed by chroma reduction; clamp it first.
    L = max(0.0, min(1.0, c.L))
    if not in_srgb_gamut(OKLCh(L, 0.0, c.h)):
        # Even achromatic is out of range => L is at an extreme; snap to black/white.
        return OKLCh(0.0 if L < 0.5 else 1.0, 0.0, c.h)

    lo, hi = 0.0, c.C
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if in_srgb_gamut(OKLCh(L, mid, c.h)):
            lo = mid
        else:
            hi = mid
    return OKLCh(L, lo, c.h)


# --- Distance ---------------------------------------------------------------

def delta_e_ok(a: OKLCh, b: OKLCh) -> float:
    """Perceptual distance between two colours (Euclidean in OKLab).

    This is the number the identity allocator maximises. Roughly: < 0.02 is a
    just-noticeable difference on adjacent patches, ~0.10 reads as 'a different
    colour' at a glance, and we require considerably more than that between
    concurrently visible sessions (see identity.MIN_IDENTITY_DISTANCE).
    """
    l1, a1, b1 = oklch_to_oklab(a)
    l2, a2, b2 = oklch_to_oklab(b)
    return math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2)


def min_distance(c: OKLCh, others: Iterable[OKLCh]) -> float:
    """Distance from *c* to the nearest of *others*; ``inf`` when empty."""
    return min((delta_e_ok(c, o) for o in others), default=math.inf)


# --- Luminance (for WCAG contrast) ------------------------------------------

def relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance from a hex colour.

    Deliberately NOT OKLab L: WCAG defines contrast on this specific linear-light
    formula, and accessibility claims must be computed the way the standard says.
    """
    r, g, b = hex_to_rgb(hex_color)
    lr, lg, lb = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb
