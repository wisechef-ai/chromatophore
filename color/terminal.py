"""Terminal-rendering safety layer: quantization, CVD simulation, WCAG contrast.

Why this module exists: everything else in `cuttlefish_theme` reasons about exact,
float-precision OKLCh colours — but a terminal can only *display* a small fixed
palette (256 colours at best) through the eyes of a human, some of whom have
colour-vision deficiency (CVD), on backgrounds we do not control. This module
is the honesty layer between "the identity we allocated" and "what a user
actually sees":

- ``quantize_256`` / ``quantize_16`` — what the nearest palette entry REALLY is,
  measured perceptually, so quantization never silently collapses two allocated
  identities into the same glyph colour.
- ``simulate_cvd`` — what a colour-blind user sees, so separation claims can be
  checked under protan/deutan/tritan vision, not just normal vision.
- ``contrast_ratio`` / ``ensure_contrast`` — the identity stays readable against
  whatever background a theme paints behind it, by moving lightness only
  (hue is the identity; lightness is presentation).
- ``distinguishable_under_cvd`` — an honest per-CVD-kind verdict for any pair,
  so callers can report collisions instead of discovering them from users.

Standard library only at runtime; all colour math lives in :mod:`oklab`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .oklab import (
    OKLCh,
    _linear_to_srgb,
    _srgb_to_linear,
    delta_e_ok,
    hex_to_oklch,
    hex_to_rgb,
    oklch_to_hex,
    relative_luminance,
    rgb_to_hex,
    srgb_to_oklab,
)

__all__ = [
    "quantize_256",
    "quantize_16",
    "simulate_cvd",
    "contrast_ratio",
    "ensure_contrast",
    "ensure_contrast_detailed",
    "ContrastResult",
    "distinguishable_under_cvd",
]


# --- xterm-256 palette geometry ----------------------------------------------

# Component levels of the 6x6x6 colour cube at indices 16..231. Index maths:
# 16 + 36*r + 6*g + b, with r,g,b each selecting from these levels.
_CUBE_LEVELS = (0, 95, 135, 175, 215, 255)

# Greyscale ramp at indices 232..255: 8, 18, 28, ..., 238.
_GREY_FIRST, _GREY_COUNT, _GREY_STEP = 8, 24, 10


def _index_to_hex(index: int) -> str:
    """xterm-256 palette index (16..255) -> the hex colour a faithful terminal
    shows for it. Indices 0..15 are system colours whose RGB is chosen by the
    theme; this module never emits them, so they are intentionally unreachable
    here (callers wanting ANSI-16 go through :func:`quantize_16`)."""
    if index < 16 + 216:  # 6x6x6 cube
        cube_index = index - 16
        r = _CUBE_LEVELS[cube_index // 36]
        g = _CUBE_LEVELS[(cube_index // 6) % 6]
        b = _CUBE_LEVELS[cube_index % 6]
        return rgb_to_hex(r / 255.0, g / 255.0, b / 255.0)
    grey = _GREY_FIRST + _GREY_STEP * (index - 232)  # greyscale ramp
    return rgb_to_hex(grey / 255.0, grey / 255.0, grey / 255.0)


# OKLab coordinates of every quantizable palette entry, computed once at import:
# quantization is a hot path (every repaint of every session colour) and 240
# lab triples is trivially cheap to keep around.
_PALETTE_256 = tuple(
    srgb_to_oklab(*hex_to_rgb(_index_to_hex(i))) for i in range(16, 256)
)


def quantize_256(hex_color: str) -> int:
    """Map a hex colour to the nearest xterm-256 palette index in 16..255.

    Nearest is measured with perceptual distance (Euclidean in OKLab), NOT
    naive RGB Euclidean distance. RGB distance is wrong here for two reasons:

    1. sRGB is gamma-encoded, so RGB distance weights dark-channel errors far
       more than light-channel errors — #010101 vs #000000 (invisible) scores
       the same as #FEFEFE vs #FFFFFF (visible). Perceptual distance must be
       computed after the nonlinearity is undone, which OKLab does.
    2. Even in linear RGB, the axes are far from perceptually orthogonal
       (the eye resolves green differences far better than blue). OKLab's
       whitening rotation makes Euclidean distance a good proxy for perceived
       difference, which is the property that matters: two identities that
       quantize to *different* palette entries must also LOOK different.

    Indices 0..15 (system colours) are never returned: their actual RGB is
    theme-dependent, so a "nearest" claim about them would be a guess.
    """
    lab = srgb_to_oklab(*hex_to_rgb(hex_color))
    best_index, best_d2 = 16, math.inf
    for offset, entry in enumerate(_PALETTE_256):
        d2 = (lab[0] - entry[0]) ** 2 + (lab[1] - entry[1]) ** 2 + (lab[2] - entry[2]) ** 2
        if d2 < best_d2:
            best_d2, best_index = d2, 16 + offset
    return best_index


# --- ANSI-16 ------------------------------------------------------------------

# Standard xterm default RGB values for the 16 ANSI colours, indexed 0..15.
# There is no single standard — themes remap these — but xterm's defaults are
# the de-facto reference terminal values, so they are what "nearest ANSI
# colour" is measured against. Users of quantize_16 have explicitly opted into
# theme-dependent rendering (e.g. to respect a user's hand-tuned scheme);
# everyone else should use quantize_256.
#
#   idx  name          hex        idx  name               hex
#   ---  ------------  --------   ---  -----------------  --------
#    0   black         #000000     8   bright black       #7F7F7F
#    1   red           #CD0000     9   bright red         #FF0000
#    2   green         #00CD00    10   bright green       #00FF00
#    3   yellow        #CDCD00    11   bright yellow      #FFFF00
#    4   blue          #0000EE    12   bright blue        #5C5CFF
#    5   magenta       #CD00CD    13   bright magenta     #FF00FF
#    6   cyan          #00CDCD    14   bright cyan        #00FFFF
#    7   white        #E5E5E5    15   bright white        #FFFFFF

_ANSI16_HEX = (
    "#000000", "#CD0000", "#00CD00", "#CDCD00",
    "#0000EE", "#CD00CD", "#00CDCD", "#E5E5E5",
    "#7F7F7F", "#FF0000", "#00FF00", "#FFFF00",
    "#5C5CFF", "#FF00FF", "#00FFFF", "#FFFFFF",
)

_PALETTE_16 = tuple(srgb_to_oklab(*hex_to_rgb(h)) for h in _ANSI16_HEX)


def quantize_16(hex_color: str) -> int:
    """Map a hex colour to the nearest of the 16 ANSI colours (0..15).

    Perceptual (OKLab) distance, for the same reasons as :func:`quantize_256`:
    the decision must match what an observer perceives, and RGB distance is
    dominated by the gamma curve rather than by visible difference. Returned
    index follows the standard ANSI ordering (see the table above), so it can
    be fed straight into a SGR escape sequence.
    """
    lab = srgb_to_oklab(*hex_to_rgb(hex_color))
    best_index, best_d2 = 0, math.inf
    for index, entry in enumerate(_PALETTE_16):
        d2 = (lab[0] - entry[0]) ** 2 + (lab[1] - entry[1]) ** 2 + (lab[2] - entry[2]) ** 2
        if d2 < best_d2:
            best_d2, best_index = d2, index
    return best_index


# --- Colour-vision-deficiency simulation --------------------------------------

# Machado, Oliveira & Fernandes (2009), "A Physiologically-based Model for
# Simulation of Color Vision Deficiency", IEEE TVCG 15(6). Severity 1.0
# (dichromacy) matrices, widely reused (e.g. by GIMP/Ixion and Color Oracle
# derivatives) and easy to cite. Rows sum to 1, which is what makes greys
# (r == g == b) invariant — a useful correctness property, tested below.
#
# CRITICAL: these matrices act on LINEAR RGB. Applying them to gamma-encoded
# sRGB is the single most common bug in CVD code — it computes a linear blend
# of *perceptual* code values, which is not a linear blend of light, and the
# resulting simulation both over-saturates and misplaces the confusion axes.
# We therefore linearize on the way in and re-encode on the way out.
_CVD_MATRICES = {
    "protan": (
        # Protanopia: no L-cones; red-green separation collapses.
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        # Deuteranopia: no M-cones; the most common CVD (~5% of men).
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritan": (
        # Tritanopia: no S-cones; rare, blue-yellow separation collapses.
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}


def simulate_cvd(hex_color: str, kind: str) -> str:
    """Simulate how *hex_color* appears under dichromatic vision.

    ``kind`` is one of ``'protan'``, ``'deutan'``, ``'tritan'``.

    Method: linearize the sRGB channels, apply the Machado et al. (2009)
    severity-1.0 simulation matrix for *kind* (a Brettel/Vienot-style
    projection of the deficient cone response onto the dichromat's reduced
    colour space), clamp to [0, 1] — the matrices can produce small
    out-of-range values — and re-encode to sRGB.

    Why this direction matters for the product: we do not simulate to make
    output "CVD-safe" (recolouring) but to MEASURE whether two identity
    colours remain distinct for a colour-blind user. That means the simulator
    only has to be directionally faithful — it must preserve greys exactly
    and collapse the right confusion axis, which is exactly what the
    row-normalized linear-RGB matrices guarantee.
    """
    try:
        m = _CVD_MATRICES[kind]
    except KeyError:
        raise ValueError(
            f"kind must be one of {sorted(_CVD_MATRICES)}, got {kind!r}"
        ) from None

    r, g, b = hex_to_rgb(hex_color)
    # Gamma-decode FIRST — see the comment block above _CVD_MATRICES.
    lr, lg, lb = _srgb_to_linear(r), _srgb_to_linear(g), _srgb_to_linear(b)

    sr = m[0][0] * lr + m[0][1] * lg + m[0][2] * lb
    sg = m[1][0] * lr + m[1][1] * lg + m[1][2] * lb
    sb = m[2][0] * lr + m[2][1] * lg + m[2][2] * lb

    return rgb_to_hex(
        _linear_to_srgb(max(0.0, min(1.0, sr))),
        _linear_to_srgb(max(0.0, min(1.0, sg))),
        _linear_to_srgb(max(0.0, min(1.0, sb))),
    )


# --- WCAG contrast -------------------------------------------------------------

def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.x contrast ratio between two hex colours: (L1+0.05)/(L2+0.05)
    with L1 the lighter of the two relative luminances.

    Order of arguments is irrelevant — the ratio is symmetric by definition,
    so callers never need to know which of fg/bg is lighter. Luminance comes
    from :func:`oklab.relative_luminance`, i.e. the exact WCAG formula on
    linearized sRGB, not OKLab L: an accessibility number must be computed
    the way the standard computes it or it cannot be cited.
    """
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# --- Contrast enforcement -------------------------------------------------------

@dataclass(frozen=True)
class ContrastResult:
    """Full truth about what :func:`ensure_contrast` did, for callers that
    must report honestly (or log) when a target was unreachable. The plain
    :func:`ensure_contrast` returns just the colour; this record adds the
    achieved ratio and whether the target was met, so "best effort" is
    discoverable instead of silently wrong.

    Why a frozen record and not an exception: an unreachable target is a
    normal outcome (a mid-grey background caps the achievable ratio), and
    raising would force callers into try/except for an expected condition.
    """

    oklch: OKLCh
    achieved: float
    target: float
    met: bool


# Search resolution for ensure_contrast. 0.002 in L is ~a fifth of a
# just-noticeable difference, so a finer grid buys nothing perceptually while
# doubling the cost. The grid is a scan rather than a bisection because
# contrast as a function of L is monotone in practice but NOT provably so
# (gamut mapping may trim chroma near the extremes, nudging luminance), and a
# scan only ever returns a candidate we have actually verified.
_L_STEP = 0.002


def _ratio_at(c: OKLCh, bg_hex: str) -> float:
    # Measured on the 8-bit hex that would actually be emitted, so the found
    # L meets the target in *rendered* pixels, not just in float space where
    # rounding could shave the ratio just below the threshold.
    return contrast_ratio(oklch_to_hex(c), bg_hex)


def ensure_contrast_detailed(fg: OKLCh, bg_hex: str, *,
                             min_ratio: float = 4.5) -> ContrastResult:
    """Return *fg* with only its lightness adjusted to reach *min_ratio*
    against *bg_hex*, plus the full :class:`ContrastResult`.

    Hue and chroma are never touched: hue is the session's identity (the
    allocator's non-collision guarantee lives on the hue circle), and chroma
    is what keeps the identity recognisable rather than washed out. Lightness
    is presentation — the one axis that changes contrast monotonically
    without touching identity.

    Strategy: scan L upward and downward from the input L in small steps and
    take the first candidate in each direction that meets the target (each
    candidate is verified against the quantized hex, see ``_ratio_at``), then
    keep whichever direction needed the smaller |dL|. If the input already
    meets the target, |dL| = 0. If neither direction can reach it (possible
    against mid-luminance backgrounds with high targets), the best achievable
    endpoint is returned with ``met=False`` in the result — never a lie.
    """
    def scan(l_from: float, l_to: float) -> tuple[float, float] | None:
        """First L strictly between l_from and l_to (stepping toward l_to)
        whose rendered colour meets the target, as (L, achieved_ratio)."""
        step = _L_STEP if l_to > l_from else -_L_STEP
        steps = int(round((l_to - l_from) / step))
        for i in range(1, steps + 1):
            L = l_from + step * i
            ratio = _ratio_at(fg.with_(L=L), bg_hex)
            if ratio >= min_ratio:
                return L, ratio
        return None

    start_ratio = _ratio_at(fg, bg_hex)
    if start_ratio >= min_ratio:
        return ContrastResult(fg, start_ratio, min_ratio, True)

    up = scan(fg.L, 1.0)
    down = scan(fg.L, 0.0)
    candidates: list[tuple[float, float]] = []
    if up is not None:
        candidates.append(up)
    if down is not None:
        candidates.append(down)

    if candidates:
        L, ratio = min(candidates, key=lambda c: abs(c[0] - fg.L))
        return ContrastResult(fg.with_(L=L), ratio, min_ratio, True)

    # Unreachable: return the better endpoint (white L=1 / black L=0) and say
    # so via met=False. Endpoints are where contrast is maximized because
    # luminance is monotone in L along a fixed hue/chroma line.
    best = max(
        (fg.with_(L=1.0), _ratio_at(fg.with_(L=1.0), bg_hex)),
        (fg.with_(L=0.0), _ratio_at(fg.with_(L=0.0), bg_hex)),
        key=lambda pair: pair[1],
    )
    return ContrastResult(best[0], best[1], min_ratio, False)


def ensure_contrast(fg: OKLCh, bg_hex: str, *,
                    min_ratio: float = 4.5) -> OKLCh:
    """Adjust only the lightness of *fg* until it contrasts with *bg_hex* by
    at least *min_ratio* (WCAG). See :func:`ensure_contrast_detailed` for the
    full contract; this convenience form returns just the adjusted colour.

    If the target is physically unreachable against *bg_hex* (mid-luminance
    background), the best-achievable colour is returned — callers that need
    to know should use :func:`ensure_contrast_detailed` or simply re-measure
    with :func:`contrast_ratio`; the colour never silently masquerades as
    compliant in the number we can compute.
    """
    return ensure_contrast_detailed(fg, bg_hex, min_ratio=min_ratio).oklch


# --- CVD-aware distinguishability ----------------------------------------------

def distinguishable_under_cvd(a_hex: str, b_hex: str, *,
                              min_distance: float = 0.10) -> dict:
    """Report whether *a_hex* and *b_hex* stay distinct under each kind of
    colour-vision deficiency, with the measured perceptual distances.

    Returns a dict with one entry per CVD kind plus ``'normal'`` for
    reference, each mapping to ``{'distinguishable': bool, 'distance': d}``
    where *d* is delta_e_ok between the SIMULATED pair (OKLab Euclidean;
    ~0.10 reads as 'a different colour at a glance', matching the threshold
    the identity allocator uses for normal vision).

    Why distances are exposed alongside the booleans: a bare False cannot
    tell 'collides badly' from 'a hair under the threshold', and callers
    building UI want to report honestly which pairs collide for which users
    rather than receiving a single misleading all-clear.
    """
    report: dict = {}
    for kind in ("normal", "protan", "deutan", "tritan"):
        if kind == "normal":
            a, b = a_hex, b_hex
        else:
            a, b = simulate_cvd(a_hex, kind), simulate_cvd(b_hex, kind)
        d = delta_e_ok(hex_to_oklch(a), hex_to_oklch(b))
        report[kind] = {"distinguishable": d >= min_distance, "distance": round(d, 6)}
    return report
