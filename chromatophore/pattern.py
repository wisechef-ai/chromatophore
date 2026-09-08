"""The chronic/acute renderer: turning an identity + a signal into a live palette.

Named for the biology. Hanlon & Messenger (1988) split cuttlefish body patterns into
CHRONIC patterns (minutes to hours; crypsis and identity) and ACUTE patterns (seconds
to minutes; communication). This module keeps that split literally:

    PATTERN = CHRONIC(identity) + [ACUTE(signal) if signal is not resting]

The chronic layer is the session's own colour and never changes for the life of the
session. The acute layer is layered ON TOP when the session needs the human, and is
RELEASED when it no longer does, revealing the chronic layer intact underneath.

That release behaviour is not a stylistic choice; it is what the animal does. Nature
(2023) measured blanching in Sepia officinalis: the response is fast, direct, converges
to the same appearance regardless of the starting camouflage, *retains a trace of the
prior pattern*, and the animal returns to that prior pattern afterwards in 16 of 17
trials. So: the acute signal may override identity, but it must never destroy it.

Three render layers, one per real dermal element type:

  leucophores   - passive broadband reflectors -> the neutral base (background,
                  surfaces). Adapts to the ambient terminal rather than fighting it.
  iridophores   - structural interference colour -> the sheen (accents, rules,
                  borders). This is the layer that carries the identity hue.
  chromatophores- active muscular pigment sacs -> the ink (text, glyphs, the one
                  live signal). The only layer the acute channel touches.

A flat single-hue tint is what makes most "session colour" tools look cheap. Depth
comes from these three layers behaving differently: the base stays quiet, the sheen
carries identity, the ink carries meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chromatophore.color.identity import IdentityColor
from chromatophore.color.oklab import OKLCh, oklch_to_hex
from chromatophore.session import Signal

__all__ = ["Palette", "render", "ACUTE_AMBER", "ACUTE_FAULT"]


# The two acute hues. These sit inside the ranges identity is forbidden to occupy
# (see identity.reserved_hue_ranges), which is what lets "needs me" and "fault" stay
# unambiguous no matter what colour a session was assigned.
ACUTE_AMBER = OKLCh(0.80, 0.165, 83.0)   # NEEDS_ME  — warm, high-luminance, insistent
ACUTE_FAULT = OKLCh(0.62, 0.190, 27.0)   # FAULT     — deep red, heavy, unmistakable


@dataclass(frozen=True)
class Palette:
    """A fully resolved appearance: every colour a surface needs, already hex.

    Frozen and complete rather than lazily computed, so a caller can diff two
    palettes to decide whether a repaint is even necessary. At 0.1-0.2 Hz that
    matters: the overwhelming majority of ticks produce an identical palette and
    must cost nothing.
    """

    session_id: str
    signal: Signal
    # chronic (identity) layer
    identity_hex: str
    sheen_hex: str
    sheen_dim_hex: str
    # active ink
    ink_hex: str
    # acute layer, None when resting
    acute_hex: str | None
    label: str
    # provenance, for honest reporting in `watch` and diagnostics
    meta: dict[str, Any] = field(default_factory=dict)

    def skin_colors(self) -> dict[str, str]:
        """Map onto Hermes skin keys.

        Deliberately narrow. We touch the accent/prompt/border family (the sheen) and
        leave `background` alone entirely: repainting the whole background per session
        forces contrast revalidation across ~40 inherited keys and fights whatever
        theme the user's terminal already has. A coloured edge reads as considered;
        a tinted background reads as broken.
        """
        sheen = self.acute_hex or self.sheen_hex
        return {
            "ui_accent": sheen,
            "banner_accent": sheen,
            "ui_border": self.sheen_dim_hex,
            "banner_border": self.sheen_dim_hex,
            "input_rule": sheen,
            "prompt": sheen,
            "ui_tool": self.ink_hex,
            "banner_title": self.sheen_hex,
        }


def _sheen(identity: OKLCh) -> OKLCh:
    """The iridophore layer: the identity hue at presentation lightness.

    Structural colour in the animal is brighter and cooler than the pigment beneath
    it, so the sheen is lifted in L and slightly reduced in C relative to the raw
    identity — it reads as a highlight rather than a block of paint.
    """
    return identity.with_(L=min(0.88, identity.L + 0.06), C=identity.C * 0.92)


def _sheen_dim(identity: OKLCh) -> OKLCh:
    """Borders and rules: the same hue, well back in the visual hierarchy.

    Same hue is the point — a dimmed variant of the identity keeps the frame
    coherent, where a neutral grey border would sever it.
    """
    return identity.with_(L=max(0.30, identity.L - 0.22), C=identity.C * 0.55)


def render(
    identity: IdentityColor,
    signal: Signal = Signal.RESTING,
    *,
    age_label: str = "",
) -> Palette:
    """Compose the chronic identity with the acute signal into one palette.

    `age_label` is passed through into the text label because colour cannot express
    duration. "It has been waiting 4 minutes" is not encodable in a hue, a rhythm, or
    a glyph; it is encodable in the characters `INPUT 4m`, so that is what we do.
    """
    base = identity.oklch
    sheen = _sheen(base)
    dim = _sheen_dim(base)

    if signal is Signal.NEEDS_ME:
        acute: OKLCh | None = ACUTE_AMBER
        label = f"INPUT {age_label}".strip()
    elif signal is Signal.FAULT:
        acute = ACUTE_FAULT
        label = f"ERROR {age_label}".strip()
    else:
        # Resting is visually silent. No badge, no label, no acute layer — the
        # session simply looks like itself. Anything else trains the user to
        # ignore the channel.
        acute = None
        label = ""

    return Palette(
        session_id=identity.session_id,
        signal=signal,
        identity_hex=identity.hex,
        sheen_hex=oklch_to_hex(sheen),
        sheen_dim_hex=oklch_to_hex(dim),
        ink_hex=oklch_to_hex(base.with_(L=min(0.92, base.L + 0.14), C=base.C * 0.75)),
        acute_hex=oklch_to_hex(acute) if acute is not None else None,
        label=label,
        meta={
            "separation": identity.separation,
            "crowded": identity.crowded,
            "hue": round(base.h, 1),
        },
    )
