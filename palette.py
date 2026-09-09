"""The full skin palette: one identity hue -> every colour key the engine actually has.

WHY THIS MODULE EXISTS (the v2 bug, stated plainly)

v2 set 8 keys. Probing the live engine showed the truth:

  * 9 of the keys v2 set DO NOT EXIST in this engine's schema (`background`,
    `ui_tool`, `ui_text`, `ui_border`, `syntax_*`). They were taken from the
    themes documentation rather than from `skin_engine.py`, and a key the engine
    does not know is silently ignored. That is Adam's "bunch of undefined symbols".
  * 17 keys that DO exist were never set, so ~33 of the engine's 44 style classes
    kept Hermes' stock gold. That is Adam's "only those 2 stripes change".

So this module is built from a PROBE of the engine, not from prose. `KEY_FANOUT`
below records how many style classes each key drives, measured by writing a
sentinel colour into one key at a time and counting which classes changed.

THE ARCHITECTURE (reviewed by gpt-5.6-sol and glm-5.3, 2026-09-09)

Three layers, mapped onto the biology rather than onto a design system:

  PIGMENT ARC (hue ~20-100 deg: red, amber, yellow) is SEMANTIC and never
  identity. This is not an arbitrary reservation: cuttlefish chromatophore
  pigment is *only* yellow, red and brown (Cloney & Florey 1968), so the warm arc
  is exactly the part of the wheel the animal uses to signal with. We use it the
  same way — error, warning, critical.

  STRUCTURAL ARC (everything else) carries IDENTITY. Every blue, green, cyan and
  white in a cuttlefish is structural — iridophores and leucophores under the
  pigment layer — which is why those colours look electric rather than painted,
  and why they are the right place for "which session am I looking at".

  GROUND is a near-black carrying the identity hue at very low chroma. The
  animal's mantle is not neutral grey; it takes the cast of what it is wearing.

WHERE CHROMA IS ALLOWED (the readability contract)

Adam wants vivid, and also reads in this terminal for hours. Those are only in
tension if you saturate the wrong things. Text that is READ stays near-neutral;
surfaces that are GLANCED AT go vivid:

  role                     L            C          why
  body text                0.88-0.93    <= 0.030   read for hours; chroma fatigues
  dim text                 0.58-0.62    <= 0.035   secondary, must stay legible
  bar background           0.20-0.26    <= 0.045   large area; chroma here tints
                                                   everything sitting on it
  bar text                 derived      <= 0.030   contrast-locked to its own bg
  borders / rules          0.62-0.70    0.10-0.14  thin: chroma reads as colour,
                                                   not as glare
  accents / titles         0.78-0.84    0.14-0.19  small, bright, the signal
  badge (paints fg AND bg) 0.80 / 0.20  0.16       maximum identity, both sides

CONTRAST IS RE-DERIVED PER SESSION, NEVER ASSUMED

Measured on this box: two backgrounds at IDENTICAL OKLab L=0.42 but different
identity hue give WCAG ratios from 7.39 to 7.90 against the same foreground — a
0.51 spread. OKLab L is perceptual lightness; WCAG uses relative luminance Y, and
they disagree by hue. So every foreground that lands on a tinted background is
passed through `ensure_contrast()` against the FINAL tinted hex of *that*
session. Validating once against a neutral and then tinting is the exact trap
glm-5.3 flagged, and the numbers above confirm it.
"""

from __future__ import annotations

from typing import Mapping

from .color.oklab import OKLCh, oklch_to_hex
from .color.terminal import contrast_ratio, ensure_contrast

__all__ = [
    "build_palette",
    "SEMANTIC",
    "KEY_FANOUT",
    "ENGINE_KEYS",
    "PIGMENT_ARC",
    "identity_is_safe",
]


# Measured by probing the live engine: key -> number of prompt_toolkit style
# classes it colours. Recorded because it is the honest priority order for
# "immersive" — status_bar_bg alone paints 10 classes, so leaving it unset (as v2
# did) leaves a quarter of the UI stock-gold no matter what else you do.
KEY_FANOUT: Mapping[str, int] = {
    "status_bar_bg": 10, "banner_dim": 7, "banner_text": 6, "banner_title": 5,
    "input_rule": 5, "completion_menu_bg": 3, "completion_menu_current_bg": 3,
    "status_bar_strong": 3, "ui_error": 3, "ui_label": 3, "status_bar_text": 2,
    "voice_status_bg": 2, "prompt": 1, "ui_warn": 1, "status_bar_good": 1,
    "status_bar_warn": 1, "status_bar_bad": 1, "status_bar_critical": 1,
    "status_bar_dim": 1, "completion_menu_meta_bg": 1,
    "completion_menu_meta_current_bg": 1,
    # Real keys read DIRECTLY via skin.get_color() rather than through a style
    # class. The first probe counted style classes only and therefore scored
    # these 0, which read as "dead key" — and dropping `ui_accent` on that basis
    # left the session panel painting stock gold. The live-repaint proof caught
    # it. Two ways to be reachable: a style-class template, or a direct read.
    "ui_accent": 0,        # cli_session_mixin.py:231 — session panel accent
    "ui_primary": 0,       # journey.py:29
    "response_border": 0,  # cli_chat_turn_mixin.py:602
    "session_border": 0, "session_label": 0,
    "selection_bg": 0, "shell_dollar": 0, "ui_ok": 0, "banner_accent": 0,
    # Desktop/TUI only: the classic CLI's `input-area` is deliberately unstyled,
    # so this cannot tint the classic CLI window. It is still set, because the
    # desktop app reads it (apps/desktop/src/themes/skin.ts).
    "background": 0,
}

ENGINE_KEYS = frozenset(KEY_FANOUT)

# The pigment arc, in OKLCh hue degrees. Identity must never be allocated here.
PIGMENT_ARC = (18.0, 105.0)

# Fixed semantic anchors. Deliberately differing in LIGHTNESS as well as hue:
# under deuteranopia red and green converge in hue, so lightness is what keeps
# them apart (error L 0.58 vs good L 0.74). glm-5.3 raised this; the CVD check
# below enforces it rather than trusting it.
SEMANTIC = {
    "error": OKLCh(0.58, 0.190, 27.0),
    "warn": OKLCh(0.78, 0.165, 83.0),
    "critical": OKLCh(0.52, 0.200, 22.0),
    "good": OKLCh(0.74, 0.140, 152.0),
}


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def _mix_hue(a: float, b: float, t: float) -> float:
    """Blend two hue angles the SHORT way round the circle.

    Naive numeric averaging of 350 and 10 gives 180 — the opposite colour — so a
    blanching red session would wash its bars green. That bug is invisible for
    most hue pairs and catastrophic for the few that wrap.
    """
    d = (b - a + 180.0) % 360.0 - 180.0
    return (a + d * t) % 360.0


def identity_is_safe(identity: OKLCh) -> dict:
    """Is this identity hue distinguishable from every semantic anchor?

    Checked in NORMAL vision and under all three CVD simulations, because a hue
    band reserved in normal vision can still collapse onto amber under
    deuteranopia — the reserved arc alone is not sufficient.

    Returns a report rather than a bool: a crowded identity should be reported
    honestly by `doctor`, not silently corrected into something else.
    """
    from .color.terminal import distinguishable_under_cvd

    ident_hex = oklch_to_hex(identity)
    worst = 1e9
    offenders = []
    for name, anchor in SEMANTIC.items():
        report = distinguishable_under_cvd(ident_hex, oklch_to_hex(anchor))
        for kind, data in report.items():
            if not isinstance(data, dict) or "distance" not in data:
                continue
            if data["distance"] < worst:
                worst = data["distance"]
            if not data.get("distinguishable", True):
                offenders.append(f"{name}/{kind}")
    in_pigment = PIGMENT_ARC[0] <= identity.h <= PIGMENT_ARC[1]
    return {
        "safe": not offenders and not in_pigment,
        "worst_distance": None if worst > 1e8 else round(worst, 4),
        "collisions": offenders,
        "in_pigment_arc": in_pigment,
    }


def _on(bg_hex: str, fg: OKLCh, ratio: float) -> str:
    """A foreground guaranteed to clear *ratio* against THIS EXACT background.

    Always against the final tinted hex, never a neutral stand-in: at identical
    OKLab L, different identity hues span 0.51 in WCAG ratio (measured), so a
    contrast validated pre-tint is not a contrast.
    """
    return oklch_to_hex(ensure_contrast(fg, bg_hex, min_ratio=ratio))


def build_palette(
    identity: OKLCh,
    *,
    acute: OKLCh | None = None,
    vivid: float = 1.0,
    tint_background: bool = True,
    calm_text: bool = True,
) -> dict[str, str]:
    """Expand one identity hue into EVERY key the engine actually reads.

    `acute` overrides the accent family when a session is signalling (the
    blanch). It never touches text, ground or semantics: the acute layer covers
    the identity, it does not destroy it.

    `vivid` scales chroma on the glanced-at roles only (0.0 muted .. 1.0 full
    signalling display). `calm_text` keeps read-for-hours text near-neutral even
    at vivid=1.0; setting it False lets the body text take the identity tint too.
    """
    h = identity.h
    v = _clamp(vivid, 0.0, 1.5)
    sheen = acute if acute is not None else identity
    signalling = acute is not None

    # --- ground: the mantle -------------------------------------------------
    # When signalling, the GROUND itself takes a wash of the acute hue. This is
    # the blanch: in the animal the whole skin responds, not a highlight on it.
    # v3 shipped the acute layer on 7 accent keys only, which left the bars and
    # menus resting-coloured and made a fault look like a slightly different
    # shade of calm. The wash is partial (the identity hue still shows through
    # in the ground and the borders) because blanching COVERS identity, it never
    # destroys it — the animal recovers its exact prior pattern afterwards.
    ground_h, ground_c = h, _clamp(identity.C * 0.16, 0.022, 0.034)
    bar_h, bar_c = h, _clamp(identity.C * 0.22, 0.028, 0.055)
    if signalling:
        ground_h = _mix_hue(h, sheen.h, 0.55)
        ground_c = _clamp(ground_c * 1.8, 0.020, 0.045)
        bar_h = _mix_hue(h, sheen.h, 0.70)
        bar_c = _clamp(bar_c * 2.0, 0.030, 0.075)

    # L 0.20: the photographs measure a ground of L 0.245-0.310, but that
    # includes lit sand and the animal's mid-tones. The DARKEST third of the
    # mantle is what a terminal background is analogous to, so we sit just under
    # the measured floor - dark enough to read as black on any terminal, light
    # enough that the identity hue is actually visible in it.
    ground = OKLCh(0.200, ground_c, ground_h)
    ground_hex = oklch_to_hex(ground)

    # Bars sit slightly above the ground so they read as a surface ON the skin
    # rather than a hole in it.
    bar = OKLCh(0.225 if not signalling else 0.245, bar_c, bar_h)
    bar_hex = oklch_to_hex(bar)
    menu = OKLCh(0.205, _clamp(bar_c * 0.85, 0.018, 0.060), bar_h)
    menu_hex = oklch_to_hex(menu)
    menu_sel = OKLCh(0.315, _clamp(bar_c * 1.5, 0.030, 0.090), bar_h)
    menu_sel_hex = oklch_to_hex(menu_sel)
    menu_meta = OKLCh(0.185, _clamp(bar_c * 0.7, 0.014, 0.050), bar_h)
    menu_meta_hex = oklch_to_hex(menu_meta)

    # --- text: read for hours, so chroma stays low --------------------------
    text_c = 0.018 if calm_text else _clamp(0.05 * v, 0.0, 0.07)
    body = OKLCh(0.905, text_c, h)
    dim = OKLCh(0.600, min(0.035, text_c * 1.6), h)

    # --- glanced-at roles: this is where the vivid lives --------------------
    # Chroma ceiling 0.24: MEASURED from four photographs of Metasepia pfefferi
    # in full display (sample_photos.py). The most saturated real pixels are
    # #C70F5F, #E6187B, #D31B7C, #E51020 — electric magenta and scarlet.
    #
    # THE LIGHTNESS IS THE WHOLE TRICK. Those pixels sit at L 0.538-0.605, NOT
    # at 0.78 where v3 put its accents. sRGB simply cannot hold high chroma at
    # high lightness — measured at hue 300: L 0.55 allows C 0.293, L 0.80 allows
    # only 0.118. So v3's "brighter = more vivid" instinct was backwards: raising
    # L forced the gamut mapper to strip the chroma back out, and the accent came
    # back pale. Sitting at the animal's own lightness is what makes it electric.
    accent = OKLCh(_clamp(sheen.L, 0.56, 0.68),
                   _clamp(sheen.C * (1.35 + 0.65 * v), 0.16, 0.24), sheen.h)
    rule = OKLCh(_clamp(identity.L - 0.02, 0.60, 0.72),
                 _clamp(identity.C * (0.90 + 0.45 * v), 0.10, 0.19), h)
    border = OKLCh(_clamp(identity.L - 0.16, 0.44, 0.60),
                   _clamp(identity.C * 0.55, 0.05, 0.11), h)

    accent_hex = oklch_to_hex(accent)

    # --- assemble, contrast-locking everything that lands on a tinted bg ----
    colors: dict[str, str] = {
        # bar family (status_bar_bg alone drives 10 style classes)
        "status_bar_bg": bar_hex,
        "status_bar_text": _on(bar_hex, body, 7.0),
        "status_bar_strong": _on(bar_hex, accent, 4.5),
        "status_bar_dim": _on(bar_hex, dim, 4.5),
        "status_bar_good": _on(bar_hex, SEMANTIC["good"], 4.5),
        "status_bar_warn": _on(bar_hex, SEMANTIC["warn"], 4.5),
        "status_bar_bad": _on(bar_hex, SEMANTIC["error"], 4.5),
        "status_bar_critical": _on(bar_hex, SEMANTIC["critical"], 4.5),

        # completion menu family
        "completion_menu_bg": menu_hex,
        "completion_menu_current_bg": menu_sel_hex,
        "completion_menu_meta_bg": menu_meta_hex,
        "completion_menu_meta_current_bg": oklch_to_hex(
            OKLCh(menu_sel.L - 0.04, menu_sel.C, h)),

        # voice
        "voice_status_bg": bar_hex,

        # banner / text family
        "banner_text": oklch_to_hex(body),
        "banner_dim": oklch_to_hex(dim),
        "banner_title": accent_hex,
        "banner_accent": accent_hex,
        "ui_accent": accent_hex,
        "ui_primary": oklch_to_hex(body),
        "input_rule": oklch_to_hex(rule),
        "prompt": accent_hex,
        "ui_label": _on(bar_hex, OKLCh(accent.L - 0.04, accent.C * 0.85, sheen.h), 4.5),

        # CLI surfaces that read the skin directly
        "response_border": oklch_to_hex(border),
        "session_border": oklch_to_hex(border),
        "session_label": accent_hex,
        "selection_bg": menu_sel_hex,
        "shell_dollar": accent_hex,

        # semantics: FIXED. Never derived from identity, so red stays error
        # whatever colour this session happens to be.
        "ui_error": oklch_to_hex(SEMANTIC["error"]),
        "ui_warn": oklch_to_hex(SEMANTIC["warn"]),
        "ui_ok": oklch_to_hex(SEMANTIC["good"]),
    }

    if tint_background:
        # Desktop/TUI only — the classic CLI's input-area is deliberately
        # unstyled so typed text keeps the user's terminal colours.
        colors["background"] = ground_hex

    return colors


def audit_palette(colors: Mapping[str, str]) -> dict:
    """Verify a built palette: no unknown keys, and every fg/bg pair legible.

    Exists because the v2 failure was *silent* — unknown keys are ignored without
    warning, so nothing told us a third of the UI was unthemed. This turns that
    class of mistake into a visible number.
    """
    unknown = sorted(set(colors) - ENGINE_KEYS)
    missing = sorted(k for k in ENGINE_KEYS if k not in colors)
    pairs = [
        ("status_bar_text", "status_bar_bg"), ("status_bar_strong", "status_bar_bg"),
        ("status_bar_dim", "status_bar_bg"), ("status_bar_good", "status_bar_bg"),
        ("status_bar_warn", "status_bar_bg"), ("status_bar_bad", "status_bar_bg"),
        ("status_bar_critical", "status_bar_bg"), ("ui_label", "status_bar_bg"),
    ]
    ratios = {}
    for fg, bg in pairs:
        if fg in colors and bg in colors:
            ratios[f"{fg}/{bg}"] = round(contrast_ratio(colors[fg], colors[bg]), 2)
    return {
        "unknown_keys": unknown,
        "missing_keys": missing,
        "contrast": ratios,
        "worst_contrast": min(ratios.values()) if ratios else None,
        "style_classes_covered": sum(KEY_FANOUT.get(k, 0) for k in colors),
    }
