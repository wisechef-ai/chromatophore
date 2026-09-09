"""The persistent mantle: a multi-pigment chromatophore field.

ADAM'S REQUIREMENT (2026-09-09)

  "is it possible to have the cuttlefish like patterns on black/gray? as of now
   its one color but is it possible to have the multi color vibrant imitation of
   the cuttlefish ... which changes it's colors when the session progresses (on
   issues/errors etc)? so it looks kinda like astral photos of cosmos/nebulas"

He is asking for something MORE biologically correct than what I built, not less.

WHY MULTI-PIGMENT IS THE ACCURATE MODEL

A cuttlefish does not have one pigment. It has THREE chromatophore classes —
yellow, red and brown (Cloney & Florey 1968; Hanlon & Messenger 1988) — and they
are stacked in vertical layers: "the most superficial chromatophores are black;
below them lie red, then orange then yellow" (Messenger 2001, on Octopus
vulgaris; Sepia follows the same plan). Beneath those sit iridophores producing
structural blue-green, and leucophores producing broadband white.

So the skin of a real animal is genuinely multi-hued at any instant: warm pigment
spots of several classes, over a cool structural sheen, with white highlights.
That is exactly the nebula look Adam is describing, and my earlier single-hue
field was the simplification — the palette had one pigment where the animal has
three plus two structural layers.

HOW IT WORKS

Two independent noise fields:

  EXPANSION  (fine, existing)   how open each chromatophore is -> the pattern
  CLASS      (coarse, new)      WHICH pigment class that cell belongs to

The class field is deliberately coarser than the expansion field, because
chromatophores of the same class cluster in the skin rather than interleaving
per-cell — Packard's wandering-cloud work found waves propagate "mainly through
populations of chromatophores of the same age/size/colour class". Coarse class
noise gives patches of related hue; fine expansion noise gives the texture inside
them. That combination is what reads as a nebula rather than as confetti.

STATE CHANGES RECOLOUR THE FIELD

`acute` shifts the pigment set toward the signalling hue: on a fault the warm
classes rotate toward red and the field visibly runs hot, while the structural
sheen and the arrangement stay put. The session is still recognisably itself —
blanching covers identity, it never destroys it — but the whole mantle answers,
which is what makes it a state channel and not decoration.
"""

from __future__ import annotations

from .color.oklab import OKLCh, hex_to_oklch

__all__ = ["mantle_rows", "pigment_set", "MANTLE_WIDTH", "MANTLE_HEIGHT"]

# MEASURED against the art it replaces: `banner.py`'s HERMES_CADUCEUS is 30
# columns wide and 15 lines tall, and it is the LEFT COLUMN of a two-column
# banner (`banner.py:855`). An earlier hero at 92 columns simply broke that
# layout, which is why the pixel field never appeared on Adam's screen at all —
# it was not missing, it was overflowing.
#
# 30 pixel rows render as 15 text rows (two pixels per character cell), so the
# mantle occupies exactly the caduceus' slot.
MANTLE_WIDTH = 30
MANTLE_HEIGHT = 30

# Hue offsets, in degrees, for the pigment classes around the identity hue.
#
# WIDENED after looking at the render. The first cut used (-38, 0, +26) — a 65
# degree spread, taken from the fact that the animal's yellow/red/brown classes
# are adjacent. But 65 degrees is ANALOGOUS: it reads as one colour family with
# tonal variation, not as the multi-hued field Adam asked for ("multi color
# vibrant imitation ... like astral photos of cosmos/nebulas").
#
# The biology supports going wider, and I had modelled only half of it. The
# animal is not just three warm pigments: those sit OVER blue-green iridophores
# (Froesch & Messenger 1978), so real skin shows warm spots against a cool
# structural field at once. A nebula looks the way it does for the same reason —
# emission and reflection in the same frame. So the fourth class is COOL, placed
# opposite the warm ones, which is what puts genuine colour contrast on screen
# rather than a gradient.
_CLASS_OFFSETS = (-52.0, -18.0, +34.0, +150.0)

# The cool (iridophore) class is structural, not pigment: brighter, less
# saturated, and rarer. Applied to the last offset above.
_IRIDOPHORE_INDEX = 3

# How far a signalling state drags each pigment class toward the acute hue.
# Not 1.0: the identity must survive underneath (blanching retains a trace of the
# prior pattern, Nature 619 2023), so even a full fault keeps the arrangement and
# some of the original cast.
_ACUTE_PULL = 0.72


def pigment_set(
    identity_hex: str,
    acute_hex: str | None = None,
) -> tuple[OKLCh, ...]:
    """The pigment classes this session's chromatophores are drawn from.

    Three warm-ish classes spread around the identity hue, mirroring the animal's
    yellow / red / brown stack. When `acute_hex` is present each class is pulled
    toward it, so a fault runs visibly hot without flattening the field to one
    colour.
    """
    base = hex_to_oklch(identity_hex)
    acute = hex_to_oklch(acute_hex) if acute_hex else None

    classes = []
    # When signalling, the class spread is REBUILT AROUND THE ACUTE HUE rather
    # than each class being dragged toward it independently.
    #
    # Dragging was the obvious implementation and it is wrong: a class sitting
    # ~180 degrees from the acute hue has no good short path, so it swings
    # through the far side of the wheel. Measured: a violet session (classes at
    # 257/295/321) blanching to amber (83) produced hue 132 — a GREEN
    # chromatophore in a fault display, which is both ugly and a lie about the
    # state. Anchoring the spread on the acute hue keeps every class inside the
    # signalling family, and identity survives in the ARRANGEMENT and in the
    # residual lightness/chroma differences between classes.
    anchor = acute.h if acute is not None else base.h
    # A signalling display must not leak into the neighbouring semantic hue.
    # The +26 offset off amber (83) lands at 109 — green, which reads as "ok" and
    # directly contradicts the state the display is announcing. When signalling,
    # the spread is halved and re-centred so every class stays inside the
    # signal's own family; identity is carried by the pattern, not by width.
    offsets = _CLASS_OFFSETS if acute is None else tuple(
        o * 0.45 for o in _CLASS_OFFSETS)
    for i, offset in enumerate(offsets):
        hue = (anchor + offset) % 360.0
        # Vary lightness and chroma per class as well as hue: real pigment
        # classes differ in density, and a set that varies only in hue looks
        # like a gradient rather than distinct cell populations.
        lightness = base.L + (0.06 if i == 0 else (-0.05 if i == 2 else 0.0))
        chroma = base.C * (1.0 if i == 1 else 0.88)
        if i == _IRIDOPHORE_INDEX:
            # Structural colour, not pigment: brighter and cooler, and less
            # saturated because interference colour is broader-band than a
            # pigment absorption peak.
            lightness = min(0.88, base.L + 0.18)
            chroma = base.C * 0.70
            if acute is not None:
                # DURING A SIGNAL THE COOL CLASS COLLAPSES. At rest its +150
                # offset is the point — warm spots against a cool field is what
                # makes the mantle read as skin rather than a gradient. But in a
                # fault display that same offset lands on green, which a human
                # reads as "ok" while the session is announcing failure.
                # Measured: 48 of 48 semantic collisions across 24 identity hues
                # came from this one class. So when signalling it folds back to a
                # near-neighbour of the acute hue and keeps only its brightness,
                # which preserves the highlight without the contradiction.
                hue = (anchor - 16.0) % 360.0
                chroma = base.C * 0.55
        if acute is not None:
            chroma = chroma + (acute.C - chroma) * _ACUTE_PULL * 0.8
            lightness = lightness + (acute.L - lightness) * _ACUTE_PULL * 0.5
        classes.append(OKLCh(max(0.30, min(0.86, lightness)),
                             max(0.05, min(0.26, chroma)), hue))
    return tuple(classes)


def mantle_rows(
    session_id: str,
    identity_hex: str,
    sheen_hex: str,
    ground_hex: str,
    *,
    acute_hex: str | None = None,
    width: int = MANTLE_WIDTH,
    height: int = MANTLE_HEIGHT,
    markup: bool = True,
) -> str:
    """The session's chromatophore pattern, as Rich markup or raw ANSI.

    `markup=True` (the default) targets `banner_hero`, which Rich renders — raw
    escape sequences would be escaped and printed literally there.
    `markup=False` gives ANSI for direct terminal writes.
    """
    from .field import _composite, _smooth_noise, mottle

    seed = abs(hash(session_id)) & 0xFFFFFFFF
    field = mottle(width, height, seed=seed)
    pigments = pigment_set(identity_hex, acute_hex)
    sheen = hex_to_oklch(sheen_hex)
    base = hex_to_oklch(ground_hex)

    # Coarse class noise: patches of same-class cells, not per-cell confetti.
    # scale 7 against the expansion field's 3 keeps class regions clearly larger
    # than the texture inside them.
    #
    # The distribution is WEIGHTED, not uniform. Iridophore patches are sparse in
    # real skin — they are a structural underlayer showing through, not a fourth
    # pigment in equal measure — and a cool class at 25% would read as two-tone
    # rather than as warm skin with cool glints. Cumulative weights put the cool
    # class on ~12% of cells.
    weights = (0.30, 0.32, 0.26, 0.12)
    cutoffs = []
    running = 0.0
    for w in weights[:len(pigments)]:
        running += w
        cutoffs.append(running)
    total = cutoffs[-1]
    cutoffs = [c / total for c in cutoffs]

    def pigment_at(x: int, y: int) -> OKLCh:
        n = _smooth_noise(x / 7.0, y / 7.0, seed ^ 0x9E37)
        for index, cut in enumerate(cutoffs):
            if n <= cut:
                return pigments[index]
        return pigments[-1]

    def cell(x: int, y: int) -> str:
        top = _composite(field.get(x, y), pigment_at(x, y), sheen, base)
        if y + 1 < field.height:
            bottom = _composite(field.get(x, y + 1), pigment_at(x, y + 1),
                                sheen, base)
        else:
            bottom = ground_hex
        if markup:
            return f"[{top} on {bottom}]\u2580[/]"
        tr, tg, tb = (int(top[i:i + 2], 16) for i in (1, 3, 5))
        br, bg, bb = (int(bottom[i:i + 2], 16) for i in (1, 3, 5))
        return f"\x1b[38;2;{tr};{tg};{tb}m\x1b[48;2;{br};{bg};{bb}m\u2580"

    lines = []
    for y in range(0, field.height, 2):
        row = "".join(cell(x, y) for x in range(field.width))
        lines.append(row if markup else row + "\x1b[0m")
    return "\n".join(lines)
