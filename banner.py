"""The startup banner, painted in this session's colours.

WHY THIS IS SEPARATE FROM THE PALETTE

The banner ASCII art does NOT read the colour keys. `hermes_cli/banner.py:60`
hardcodes a gold gradient into the Rich markup itself — `[bold #FFD700]`,
`[#FFBF00]`, `[#CD7F32]` — so a skin can set all 23 colour keys correctly and the
biggest thing on the screen stays stock gold. Measured on Chef: after the palette
fix the terminal painted our greens AND still painted #FFD700/#CD7F32/#FFBF00,
all of it from the logo and the caduceus.

The escape hatch is `banner_logo` / `banner_hero` in the skin: whole-string
overrides that `banner.py:916` prefers over the built-in art. So we generate both
per session, in the session's own hues.

WHAT WE DRAW

`banner_hero` becomes a real chromatophore field — the same `field.py` renderer
as `hermes cuttlefish skin`, converted from ANSI to Rich markup. That means the
first thing you see when a session opens IS its skin, at full pixel resolution,
rather than a wordmark in a new colour.

The wordmark keeps Hermes' letterforms (this is a Hermes theme, not a rebrand)
but takes a three-stop gradient down the identity hue, mirroring how the real
gradient runs light-to-dark.
"""

from __future__ import annotations

from typing import Optional

from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex

__all__ = ["banner_logo", "banner_hero"]


# Hermes' own letterforms, with the colour stripped out so we can re-ink them.
# Kept verbatim from hermes_cli/banner.py so the wordmark stays recognisably
# Hermes — we are theming it, not replacing the product's identity.
_LOGO_ROWS = (
    "██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗       █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
    "██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝      ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
    "███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗█████╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║",
    "██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║╚════╝██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║",
    "██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║      ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║",
    "╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝",
)


def _ramp(identity: OKLCh, rows: int) -> list[str]:
    """A light-to-dark ramp down the identity hue.

    Mirrors the direction of Hermes' own gold gradient (bright at the top,
    bronze at the bottom) so the banner keeps its familiar shape while changing
    its colour. Chroma rises slightly as lightness falls, because sRGB holds more
    chroma at lower L — the same constraint that governs the accent colours.
    """
    out = []
    for i in range(rows):
        t = i / max(1, rows - 1)
        L = 0.80 - 0.26 * t
        C = min(0.24, identity.C * (1.05 + 0.35 * t))
        out.append(oklch_to_hex(OKLCh(L, C, identity.h)))
    return out


def banner_logo(identity_hex: str) -> str:
    """The Hermes wordmark, inked in this session's hue. Rich markup."""
    identity = hex_to_oklch(identity_hex)
    ramp = _ramp(identity, len(_LOGO_ROWS))
    lines = []
    for i, row in enumerate(_LOGO_ROWS):
        bold = "bold " if i < 2 else ""
        lines.append(f"[{bold}{ramp[i]}]{row}[/]")
    return "\n".join(lines)


def banner_hero(
    identity_hex: str,
    sheen_hex: str,
    ground_hex: str,
    *,
    width: int = 92,
    height: int = 12,
    seed: int = 0,
    wave_t: Optional[float] = None,
) -> str:
    """A live chromatophore field as the banner hero image, in Rich markup.

    Uses the SAME renderer as `hermes cuttlefish skin`, so the banner is not an
    illustration of the theme — it is the theme, at pixel resolution, and it
    cannot drift from what the rest of the session shows.

    Rich markup rather than raw ANSI because `banner.py` hands this string to a
    Rich console, which would escape raw escape sequences.
    """
    from .field import _composite, mottle, passing_cloud

    field = mottle(width, height, seed=seed)
    if wave_t is not None:
        field = passing_cloud(field, wave_t, seed=seed)

    pigment, sheen = hex_to_oklch(identity_hex), hex_to_oklch(sheen_hex)
    base = hex_to_oklch(ground_hex)

    def cell(x: int, y: int) -> str:
        # Rich paints the glyph's foreground over the cell's background, so one
        # half-block carries two independently coloured pixels — same trick as
        # render_half_blocks(), in Rich markup instead of raw ANSI.
        top = _composite(field.get(x, y), pigment, sheen, base)
        bottom = (_composite(field.get(x, y + 1), pigment, sheen, base)
                  if y + 1 < field.height else ground_hex)
        return f"[{top} on {bottom}]\u2580[/]"

    return "\n".join(
        "".join(cell(x, y) for x in range(field.width))
        for y in range(0, field.height, 2)
    )
