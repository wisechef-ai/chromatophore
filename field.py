"""The chromatophore field: a real grid of pixels, rendered as text.

WHY A GRID EXISTS AT ALL

The skin gives us 28 *semantic* colour keys — `ui_error`, `banner_border` and so on.
That is a palette, not a canvas: `ui_error` must stay red or the signal channel is
destroyed, so you cannot address it as a pixel. Any honest "pixel-style" rendering
therefore has to happen in text WE emit, at truecolor, where every cell is ours.

This module is that canvas. Each cell is one chromatophore with an expansion state
in 0..1, exactly as in the animal: "the expansion state of each chromatophore depends
on a radial array of muscles controlling the size of a central pigment sac"
(Messenger 2001). Expansion 0 = retracted, revealing the reflective layer beneath
(leucophore/iridophore); expansion 1 = fully expanded pigment.

WHY HALF-BLOCKS

We render with U+2580 UPPER HALF BLOCK and a background colour, so one character cell
carries TWO independently coloured pixels. That doubles vertical resolution for free
and makes the grid square-ish given typical ~1:2 character aspect. This is the same
trick `hermes_cli/pets.py` uses for its truecolor fallback, so it is a proven path on
this terminal rather than a hopeful one.

WHY LAYERS

Cephalopod skin is vertically stratified — chromatophores on top, then iridophores,
then leucophores (Froesch & Messenger 1978, Fig. 15). The colour you see is pigment
composited OVER structural reflection, not pigment alone. So a retracted cell here
does not go to black; it reveals the iridophore sheen underneath. That single detail
is most of the difference between "coloured squares" and "skin".

THE WAVES

`passing_cloud` reproduces the travelling band documented in Sepia officinalis: "broad
transverse bands of chromatophore expansion moving rapidly forward from the posterior
mantle tip across the dorsal body surface" at about 1 Hz (Hanlon & Messenger 1988;
Gonzalez-Bellido et al., Front. Physiol. 2017). The agonistic variant is slower —
0.38 +/- 0.08 Hz, 7.0 +/- 1.0 s per band — and both are offered, because the fast one
is a hunting display and the slow one is a warning, which is exactly our
resting/needs-attention split.

Metasepia tullbergi supports several wave regions with independent directions and a
"blink" (a transient local intensity drop revealing ongoing but invisible propagation)
— `blink` implements that, and it is the detail that stops a wave looking like a CSS
gradient sweep.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex

__all__ = [
    "Field",
    "passing_cloud",
    "mottle",
    "render_half_blocks",
    "WAVE_HUNTING_HZ",
    "WAVE_AGONISTIC_HZ",
]

# Measured display frequencies (see module docstring).
WAVE_HUNTING_HZ = 1.0      # S. officinalis passing wave, hunting
WAVE_AGONISTIC_HZ = 0.38   # S. apama agonistic display, 7s per band

# Expansion above which a cell starts exposing leucophore white rather than more
# pigment. CALIBRATED, not guessed: at the default density only ~2% of cells
# exceed 0.72, so an onset there produced a 0.5% bright fraction against the
# animal's measured 16.4%. 0.52 puts the onset near the mottle's p90 and lands
# the bright fraction in the right band. Check with sample_photos.py after any
# change to the mottle distribution — the two are coupled.
_LEUCO_ONSET = 0.52


@dataclass
class Field:
    """A grid of chromatophore expansion states in 0..1.

    Stored row-major. Values outside 0..1 are clamped on write rather than on read
    so a caller can never observe a state the animal could not hold.
    """

    width: int
    height: int
    cells: list[float]

    @classmethod
    def blank(cls, width: int, height: int, value: float = 0.0) -> "Field":
        width = max(1, width)
        height = max(1, height)
        return cls(width, height, [_clamp(value)] * (width * height))

    def get(self, x: int, y: int) -> float:
        return self.cells[(y % self.height) * self.width + (x % self.width)]

    def set(self, x: int, y: int, value: float) -> None:
        self.cells[(y % self.height) * self.width + (x % self.width)] = _clamp(value)

    def map(self, fn: Callable[[int, int, float], float]) -> "Field":
        out = Field.blank(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                out.set(x, y, fn(x, y, self.get(x, y)))
        return out

    def blend(self, other: "Field", t: float) -> "Field":
        """Linear blend toward *other*. Sizes must match."""
        if (other.width, other.height) != (self.width, self.height):
            raise ValueError("field size mismatch")
        t = _clamp(t)
        out = Field.blank(self.width, self.height)
        out.cells = [a + (b - a) * t for a, b in zip(self.cells, other.cells)]
        return out


def _clamp(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _hash01(*parts: int) -> float:
    """Cheap deterministic value noise in [0,1). Integer mixing, no allocation.

    A full hashlib call per cell per frame would dominate the frame budget; this
    is a standard integer avalanche and is entirely adequate for texture.

    MEMOISED because the noise samplers hit the same lattice corners repeatedly:
    profiling the nebula field showed 30,608 calls for a 900-cell image, and this
    function was 63% of the total runtime (172ms, against a budget of a few ms at
    session start). The cache is bounded and the function is pure, so this is
    free correctness-wise; `maxsize` is generous because a 30x30 field with
    several octaves touches a few thousand distinct keys.
    """
    return _hash01_cached(parts)


@lru_cache(maxsize=65536)
def _hash01_cached(parts: tuple) -> float:
    h = 0x9E3779B97F4A7C15
    for p in parts:
        h ^= (p + 0x9E3779B9 + (h << 6) + (h >> 2)) & 0xFFFFFFFFFFFFFFFF
        h = (h * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        h ^= h >> 31
    return (h & 0xFFFFFFFF) / 4294967296.0


def _smooth_noise(x: float, y: float, seed: int) -> float:
    """Bilinearly-interpolated value noise — smooth blobs, not TV static.

    Real skin texture is spatially correlated: neighbouring chromatophores are
    recruited together into components. Uncorrelated per-cell noise looks like
    dead pixels, which is the opposite of the intent.
    """
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    # Smoothstep the interpolants so the blobs have no visible grid seams.
    sx = fx * fx * (3 - 2 * fx)
    sy = fy * fy * (3 - 2 * fy)
    n00 = _hash01(x0, y0, seed)
    n10 = _hash01(x0 + 1, y0, seed)
    n01 = _hash01(x0, y0 + 1, seed)
    n11 = _hash01(x0 + 1, y0 + 1, seed)
    top = n00 + (n10 - n00) * sx
    bottom = n01 + (n11 - n01) * sx
    return top + (bottom - top) * sy


def mottle(width: int, height: int, *, seed: int, scale: float = 3.0,
           contrast: float = 1.0, density: float = 0.46,
           grain: float = 0.40, peak: float = 1.0) -> Field:
    """A static resting texture: the animal's own mottled base pattern.

    THE SHAPE OF THE DISTRIBUTION IS THE POINT. A field of smoothly-varying
    mid-range expansion renders as a bright pastel wash — which is what the first
    version did, and it looked like coloured noise, not skin. Real cuttlefish skin
    is a DARK GROUND carrying DISCRETE pigment spots: most chromatophores retracted
    at any moment, a minority strongly expanded, with sharp boundaries between them
    because each sac is an individual cell rather than a gradient.

    Three parameters produce that:

      density   the fraction of cells that carry significant pigment. Below 0.5 the
                ground dominates and the field reads as near-black, which is what
                Adam asked for ("like the cuttlefish - black, and a lot of pixels").
      contrast  gamma on the noise: pushes the distribution to its extremes so
                cells are mostly ON or OFF rather than all lukewarm.
      grain     per-cell jitter that breaks up the smooth interpolation, so
                individual chromatophores are visible as cells.

    The underlying noise stays spatially correlated (neighbouring chromatophores
    are recruited together into components), so the spots cluster into patches
    rather than scattering uniformly.
    """
    field = Field.blank(width, height)
    # Threshold chosen so that ~`density` of the smooth-noise distribution ends up
    # above zero. The noise is roughly uniform, so the quantile is the complement.
    cut = 1.0 - _clamp(density)
    for y in range(height):
        for x in range(width):
            coarse = _smooth_noise(x / scale, y / scale, seed)
            fine = _smooth_noise(x / (scale * 0.45), y / (scale * 0.45), seed ^ 0x5BF03)
            v = coarse * 0.68 + fine * 0.32
            # Everything below the cut is ground; above it, rescale to the full
            # range so the spots that DO appear are strongly expressed.
            if v <= cut:
                # The retracted floor. It must be very close to the ground: this
                # is what makes the field read as "black with pigment spots"
                # rather than a uniform haze. Kept slightly non-zero and varying
                # so the dark areas still have life instead of being a dead
                # rectangle, but well under the level at which they register as a
                # colour of their own.
                v = (v / cut if cut > 0 else 0.0) * 0.05
            else:
                # Above the cut, ease IN: a linear ramp puts most spots at
                # mid-expansion, which is exactly the washed-out midtone we are
                # avoiding. Squaring pushes the bulk down and lets a few cells
                # reach full pigment, which is the distribution real skin shows.
                # MEASURED against the real animal (sample_photos.py): a
                # flamboyant cuttlefish in display has ~16% of pixels at L>0.65
                # and ~11% above chroma 0.10. The previous curve produced 0% and
                # 2.4% — every spot stalled in the midtone, which is why the
                # field looked washed out next to the photographs. Easing OUT
                # (exponent < 1) pushes the spots that clear the cut TOWARD full
                # pigment instead of bunching them just above the floor.
                u = (v - cut) / (1.0 - cut) if cut < 1 else 1.0
                v = 0.04 + (u ** 0.62) * 0.96 * peak
            # Gamma toward the extremes: individual cells read as on or off.
            if contrast != 1.0:
                v = v ** (1.0 / max(0.05, contrast)) if v > 0 else 0.0
            # Per-cell grain, so the grid reads as discrete chromatophores rather
            # than a smooth interpolated surface.
            if grain:
                # Scaled by (1-v) so grain roughens the ground and the mid
                # expansions but leaves fully-expanded chromatophores at full
                # pigment. Without this the brightest cells never reach the
                # identity colour and every spot lands in the midtone.
                v *= 1.0 - grain * 0.5 * _hash01(x, y, seed ^ 0x2F1A) * (1.0 - v)
            field.set(x, y, v)
    return field


def passing_cloud(
    base: Field,
    t: float,
    *,
    hz: float = WAVE_HUNTING_HZ,
    direction: tuple[float, float] = (0.0, -1.0),
    width_cells: float = 0.0,
    depth: float = 0.85,
    blink: bool = True,
    seed: int = 0,
) -> Field:
    """Superimpose a travelling band of expansion on *base* at time *t* seconds.

    `direction` is a unit-ish vector in grid space; the default travels posterior to
    anterior (upward on screen), matching S. officinalis. The band is a raised
    cosine rather than a hard edge because chromatophore recruitment across the wave
    is graded, and a hard edge reads as a scanline artifact.

    `width_cells` defaults to the full travel length, per Laan et al. (2014): "the
    wavelength of each wave corresponds roughly to its length of travel, so that
    usually only one band is visible in each region at a time." One band, not a
    zebra of them — that single constant is what makes it look biological.
    """
    dx, dy = direction
    norm = math.hypot(dx, dy) or 1.0
    dx, dy = dx / norm, dy / norm
    travel = abs(dx) * base.width + abs(dy) * base.height
    band = width_cells if width_cells > 0 else max(2.0, travel)

    # Project onto the direction of travel, then shift so the near edge of the grid
    # sits at s=0. Without this offset a negative component (the default (0,-1),
    # posterior-to-anterior) puts every cell at a negative coordinate while the
    # band sweeps a positive range, and the wave never touches the grid at all —
    # a silently blank animation.
    origin = min(0.0, dx) * base.width + min(0.0, dy) * base.height

    phase = (t * hz) % 1.0
    # Band centre sweeps from just outside one edge to just outside the other.
    head = -band * 0.5 + phase * (travel + band)

    out = Field.blank(base.width, base.height)
    for y in range(base.height):
        for x in range(base.width):
            # Distance along the direction of travel.
            s = x * dx + y * dy - origin
            d = abs(s - head)
            if d >= band * 0.5:
                out.set(x, y, base.get(x, y))
                continue
            # Raised cosine: 1 at the band centre, 0 at its edges.
            w = 0.5 * (1.0 + math.cos(math.pi * d / (band * 0.5)))
            amp = depth * w
            if blink:
                # Metasepia's "blink": a transient, local intensity drop while the
                # band keeps propagating underneath. Modulated by slow noise in
                # space and time so it never lands in the same place twice.
                b = _smooth_noise(x * 0.35, y * 0.35 + t * 0.9, seed ^ 0x11D)
                if b > 0.72:
                    amp *= 0.25
            out.set(x, y, base.get(x, y) + amp * (1.0 - base.get(x, y)))
    return out


def _composite(expansion: float, pigment: OKLCh, sheen: OKLCh, base: OKLCh) -> str:
    """Pigment over structural colour, as the skin is actually stacked.

    THREE layers, because the animal has three (Froesch & Messenger 1978, Fig. 15):

        chromatophore   pigment sac, expansion 0..1   — the identity colour
        iridophore      structural interference       — the cool sheen beneath
        leucophore      broadband white reflector     — the bright highlights

    v3 modelled only the first two, and the field measured 0% of pixels above
    L 0.65 where a real cuttlefish in display has 16.4% (sample_photos.py). The
    reason is structural: the pigment itself sits at L~0.62, so NOTHING composited
    from it can be brighter than the pigment. Real skin gets its highlights from
    the leucophores — the white patches on Sepia's fin spots and Metasepia's arm
    tips — which are not pigment at all.

    So the top of the expansion range is re-read as leucophore exposure rather
    than more pigment: past `_LEUCO_ONSET` the cell brightens toward a broadband
    white tinted by the identity hue. That is what puts real highlights in the
    field, and it is why the animal reads as vivid rather than merely coloured.

    The reflective floor brightens only SLIGHTLY as expansion drops (0.045 of the
    gap to the sheen). Two earlier versions lifted it at 0.55 and 0.16 and both
    washed the field to a flat midtone haze: ~89% of cells are retracted, so even
    a small-looking fraction raises everything at once.
    """
    e = _clamp(expansion)
    reveal = OKLCh(
        base.L + (sheen.L - base.L) * (1.0 - e) * 0.045,
        base.C + (sheen.C - base.C) * (1.0 - e) * 0.30,
        sheen.h,
    )
    # Pigment saturates AT the leucophore onset, not at expansion 1.0. Otherwise
    # the two ramps overlap: a cell at the onset would be only ~52% of the way to
    # the pigment and would start turning white before it had ever shown the
    # session's actual colour. The layers are stacked in the skin, so they stack
    # here: pigment fills first, then leucophore is revealed on top of it.
    p = min(1.0, e / _LEUCO_ONSET) if _LEUCO_ONSET > 0 else 1.0
    dh = (pigment.h - reveal.h + 180.0) % 360.0 - 180.0
    out = OKLCh(
        reveal.L + (pigment.L - reveal.L) * p,
        reveal.C + (pigment.C - reveal.C) * p,
        (reveal.h + dh * p) % 360.0,
    )
    if e > _LEUCO_ONSET:
        # Leucophore exposure: broadband white, keeping a trace of the hue so a
        # highlight still belongs to this session rather than reading as a grey
        # dead pixel.
        k = (e - _LEUCO_ONSET) / (1.0 - _LEUCO_ONSET)
        out = OKLCh(
            out.L + (0.95 - out.L) * k * 0.85,
            out.C * (1.0 - 0.55 * k),
            out.h,
        )
    return oklch_to_hex(out)


def render_half_blocks(
    field: Field,
    *,
    pigment_hex: str,
    sheen_hex: str,
    base_hex: str,
) -> list[str]:
    """Render *field* to ANSI truecolor lines, two pixel rows per text row.

    Uses U+2580 (upper half block): the glyph's foreground paints the upper pixel
    and the cell's background paints the lower one. An odd final row pairs with the
    base colour so the grid never reports a height it does not have.
    """
    pigment = hex_to_oklch(pigment_hex)
    sheen = hex_to_oklch(sheen_hex)
    base = hex_to_oklch(base_hex)

    def rgb(hex_color: str) -> tuple[int, int, int]:
        return (int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16))

    lines: list[str] = []
    for y in range(0, field.height, 2):
        parts: list[str] = []
        for x in range(field.width):
            top = _composite(field.get(x, y), pigment, sheen, base)
            if y + 1 < field.height:
                bottom = _composite(field.get(x, y + 1), pigment, sheen, base)
            else:
                bottom = base_hex
            tr, tg, tb = rgb(top)
            br, bg_, bb = rgb(bottom)
            parts.append(f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg_};{bb}m\u2580")
        parts.append("\x1b[0m")
        lines.append("".join(parts))
    return lines


def render_rows(field: Field, **kw) -> int:
    """Number of TEXT rows :func:`render_half_blocks` will produce."""
    return (field.height + 1) // 2
