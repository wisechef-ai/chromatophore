"""The persistent mantle: chromatophore pixels that stay on screen.

ADAM'S ACTUAL REQUIREMENT, and why the two earlier attempts were wrong

  "the background has to take-over the work of differentiation between sessions"
  "the color is too far - should be near black but there should be pixels too
   there as in the cuttlefish to make it differentiable"

Attempt 1 was a startup banner. It works, and then it scrolls out of the
transcript and the session is anonymous again for the rest of its life.

Attempt 2 was a brighter background. Measured 0.0384 OKLab between six sessions
and Adam rejected it on sight: too coloured, and still barely differentiable.
That failure is informative — a FLAT COLOUR CARRIES ALMOST NO INFORMATION. Six
near-blacks are six near-blacks no matter how you tune them, because a single
hex value has three numbers in it and two of them are spoken for by "dark" and
"readable".

The animal solves this the way that actually works: a near-black mantle carrying
a PATTERN. Two cuttlefish are told apart by the arrangement of their
chromatophores, not by the shade of their skin. A 6x40 grid of half-blocks is
480 independently coloured pixels — orders of magnitude more identity than one
background hex, at the same lightness.

WHERE IT LIVES

`hermes_cli/skin_engine.py` exposes `banner_hero`, rendered by `banner.py` on
every banner draw. So the mantle appears at session start AND on `/clear`, and it
is part of the skin rather than something the plugin prints — which matters,
because a plugin printing raw ANSI into the conversation stream is precisely the
bug that put a wall of `?[38;2;4;28;0m` in Adam's transcript.

DENSITY IS THE IDENTITY CHANNEL

Every session gets a different pattern, not just a different hue: the mottle seed
is the session id, so cell placement differs. Two sessions with similar hues are
still distinguishable by their spot arrangement — which is exactly the property a
flat background could never have.
"""

from __future__ import annotations

from .color.oklab import hex_to_oklch

__all__ = ["mantle_rows", "MANTLE_WIDTH", "MANTLE_HEIGHT"]

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


def mantle_rows(
    session_id: str,
    identity_hex: str,
    sheen_hex: str,
    ground_hex: str,
    *,
    width: int = MANTLE_WIDTH,
    height: int = MANTLE_HEIGHT,
    markup: bool = True,
) -> str:
    """The session's chromatophore pattern, as Rich markup or raw ANSI.

    `markup=True` (the default) targets `banner_hero`, which Rich renders — raw
    escape sequences would be escaped and printed literally there.
    `markup=False` gives ANSI for direct terminal writes.
    """
    from .field import _composite, mottle

    seed = abs(hash(session_id)) & 0xFFFFFFFF
    field = mottle(width, height, seed=seed)
    pigment, sheen = hex_to_oklch(identity_hex), hex_to_oklch(sheen_hex)
    base = hex_to_oklch(ground_hex)

    lines = []
    for y in range(0, field.height, 2):
        parts = []
        for x in range(field.width):
            top = _composite(field.get(x, y), pigment, sheen, base)
            bottom = (_composite(field.get(x, y + 1), pigment, sheen, base)
                      if y + 1 < field.height else ground_hex)
            if markup:
                parts.append(f"[{top} on {bottom}]\u2580[/]")
            else:
                tr, tg, tb = (int(top[i:i + 2], 16) for i in (1, 3, 5))
                br, bg, bb = (int(bottom[i:i + 2], 16) for i in (1, 3, 5))
                parts.append(f"\x1b[38;2;{tr};{tg};{tb}m"
                             f"\x1b[48;2;{br};{bg};{bb}m\u2580")
        if not markup:
            parts.append("\x1b[0m")
        lines.append("".join(parts))
    return "\n".join(lines)
