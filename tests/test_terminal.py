"""Behaviour contracts for chromatophore.color.terminal.

These tests assert PROPERTIES, not pinned values: the point of the module is
to make promises (never emit theme-dependent indices, never lie about
contrast, collapse exactly the confusion axes CVD collapses), so the tests
state those promises and hold them across arbitrary inputs, not snapshots.
"""

from __future__ import annotations

import math
import random

import pytest

from cuttlefish_theme.color.oklab import OKLCh, hex_to_oklch, oklch_to_hex
from cuttlefish_theme.color.terminal import (
    contrast_ratio,
    distinguishable_under_cvd,
    ensure_contrast,
    ensure_contrast_detailed,
    quantize_16,
    quantize_256,
    simulate_cvd,
)

CUBE_LEVELS = (0x00, 0x5F, 0x87, 0xAF, 0xD7, 0xFF)  # 0,95,135,175,215,255
GREY_RAMP = tuple(8 + 10 * i for i in range(24))  # 8,18,...,238
CVD_KINDS = ("protan", "deutan", "tritan")


# --- quantize_256 -------------------------------------------------------------


def test_quantize_256_stays_out_of_system_colours():
    """Indices 0..15 are theme-dependent; emitting one would silently hand
    our colour choice to the user's palette. Must never happen."""
    rng = random.Random(1903)
    samples = ["#000000", "#FFFFFF", "#808080", "#FF00FF"]
    samples += [
        f"#{rng.randrange(256):02X}{rng.randrange(256):02X}{rng.randrange(256):02X}"
        for _ in range(300)
    ]
    for hex_color in samples:
        idx = quantize_256(hex_color)
        assert 16 <= idx <= 255, f"{hex_color} -> {idx}"


def test_quantize_256_is_exact_on_cube_entries():
    """A colour that IS a palette entry has distance zero to itself, so
    quantization must return exactly that entry — never a neighbour."""
    for r in range(6):
        for g in range(6):
            for b in range(6):
                hex_color = "#{:02X}{:02X}{:02X}".format(
                    CUBE_LEVELS[r], CUBE_LEVELS[g], CUBE_LEVELS[b]
                )
                assert quantize_256(hex_color) == 16 + 36 * r + 6 * g + b


# Greys the cube's own diagonal can legitimately attract: (16,59,102,145,188,231)
# are the entries where r==g==b as CUBE indices; a grey sitting exactly on one
# (e.g. #000000, #5F5F5F) has distance zero to it, exactly like a cube entry.
CUBE_GREY_INDICES = frozenset({16, 59, 102, 145, 188, 231})


def test_quantize_256_sends_greys_to_grey_palette_entries():
    """A pure grey must quantize to a grey PALETTE entry: the 24-step ramp
    (232..255) or one of the cube's six diagonal greys — never a chromatic
    entry. Mapping a grey onto a chromatic colour would mean the perceptual
    metric is preferring hue matches over the achromatic axis, which OKLab
    distance does not do."""
    for step in range(256):
        grey = "#{0:02X}{0:02X}{0:02X}".format(step)
        idx = quantize_256(grey)
        assert 232 <= idx <= 255 or idx in CUBE_GREY_INDICES, (grey, idx)


def test_quantize_256_mid_greys_prefer_the_ramp():
    """Away from the cube diagonal's exact entries, the finer 24-step ramp
    is always the closer grey, so mid-range greys land in 232..255."""
    for step in (0x28, 0x40, 0x55, 0x6E, 0x99, 0xB4, 0xC3, 0xE8):
        grey = "#{0:02X}{0:02X}{0:02X}".format(step)
        assert 232 <= quantize_256(grey) <= 255, grey


def test_quantize_256_ramp_entries_are_exact():
    for i, level in enumerate(GREY_RAMP):
        grey = "#{0:02X}{0:02X}{0:02X}".format(level)
        assert quantize_256(grey) == 232 + i


def test_quantize_256_uses_perceptual_not_rgb_distance():
    """RGB distance treats a 1/255 dark-channel change as equal to a 1/255
    light-channel change, but perceptually they are worlds apart. Property:
    quantization must map near-neighbour dark greys together — a perceptual
    metric cannot split #000000/#010101/#020202 across distant palette
    entries the way RGB counting would allow. All three must land on a
    grey entry (they are greys — covered above) AND agree on a tight set:
    the two nearest ramp/cube greys."""
    q = [quantize_256(c) for c in ("#000000", "#010101", "#020202")]
    assert set(q) <= {16, 232, 233}, q  # only black + first two ramp greys qualify


# --- quantize_16 ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("hex_color", "expected"),
    [
        ("#000000", 0),   # black
        ("#CD0000", 1),   # red (exact palette entry)
        ("#00CD00", 2),   # green
        ("#0000EE", 4),   # blue
        ("#E5E5E5", 7),   # white
        ("#7F7F7F", 8),   # bright black
        ("#FF0000", 9),   # bright red
        ("#00FF00", 10),  # bright green
        ("#5C5CFF", 12),  # bright blue
        ("#FFFFFF", 15),  # bright white
    ],
)
def test_quantize_16_exact_palette_entries(hex_color, expected):
    assert quantize_16(hex_color) == expected


def test_quantize_16_returns_valid_ansi_index():
    rng = random.Random(77)
    for _ in range(200):
        hex_color = "#{:06X}".format(rng.randrange(1 << 24))
        assert 0 <= quantize_16(hex_color) <= 15


# --- simulate_cvd ----------------------------------------------------------------


def test_simulate_cvd_rejects_unknown_kind():
    with pytest.raises(ValueError):
        simulate_cvd("#FF0000", "nope")


def test_simulate_cvd_leaves_greys_unchanged():
    """Machado matrices have unit row sums, so linear greys are fixed points
    of the simulation — grey carries no hue signal, hence no confusion-axis
    error. If greys move, the linear/gamma handling is broken."""
    for step in (0x00, 0x40, 0x80, 0xC0, 0xFF, 0x0A):
        grey = "#{0:02X}{0:02X}{0:02X}".format(step)
        for kind in CVD_KINDS:
            assert simulate_cvd(grey, kind) == grey


def test_simulate_cvd_is_idempotent_ish():
    """Simulating twice with the same kind must stay close to simulating
    once. Machado's severity-1.0 matrices are fitted approximations of the
    dichromatic projection, not exact projectors, so double application
    drifts a little — but far less than one identity-separation step. Bound
    is generous (measured worst ~0.07 over thousands of colours); if it is
    exceeded the gamma/linear handling has regressed."""
    rng = random.Random(4242)
    for _ in range(150):
        hex_color = "#{:06X}".format(rng.randrange(1 << 24))
        for kind in CVD_KINDS:
            once = simulate_cvd(hex_color, kind)
            twice = simulate_cvd(once, kind)
            drift = contrast_pair_distance(once, twice)
            assert drift < 0.08, (hex_color, kind, drift)


# Equiluminant (same OKLab L to ~0.01) red/green pair: equal lightness is
# what makes it a FAIR CVD probe — with different luminances a pair stays
# separable by lightness alone, which says nothing about hue confusion.
RED_EQUIL, GREEN_EQUIL = "#B41616", "#007400"


def test_simulate_cvd_protan_collapses_red_green():
    """The whole reason we simulate: an equiluminant red/green pair that is
    clearly distinct under normal vision must lose most of its separation
    for a protanope. Machado's protan matrix keeps a small residual (~0.13
    from ~0.30 here), so we assert a large shrink, not zero."""
    before = contrast_pair_distance(RED_EQUIL, GREEN_EQUIL)
    after = contrast_pair_distance(
        simulate_cvd(RED_EQUIL, "protan"), simulate_cvd(GREEN_EQUIL, "protan")
    )
    assert after < 0.6 * before, (before, after)


def test_simulate_cvd_deutan_collapses_red_green_to_collision():
    """Deutanopia removes the M-cone entirely: the same equiluminant pair
    collapses almost fully (~0.30 -> ~0.02), well below the 0.10 threshold
    the allocator treats as 'different colour at a glance'."""
    before = contrast_pair_distance(RED_EQUIL, GREEN_EQUIL)
    after = contrast_pair_distance(
        simulate_cvd(RED_EQUIL, "deutan"), simulate_cvd(GREEN_EQUIL, "deutan")
    )
    assert after < 0.10, (before, after)


def test_simulate_cvd_tritan_preserves_red_green():
    """Tritanopia removes the S-cone: red/green separation survives (the
    confusion axis is blue-yellow, not red-green). Asserting this keeps the
    simulation honest in both directions — it must not blur everything."""
    before = contrast_pair_distance(RED_EQUIL, GREEN_EQUIL)
    after = contrast_pair_distance(
        simulate_cvd(RED_EQUIL, "tritan"), simulate_cvd(GREEN_EQUIL, "tritan")
    )
    assert after > 0.8 * before, (before, after)


def test_simulate_cvd_preserves_luminance_order():
    """CVD shifts hue perception, not lightness ordering — a darker colour
    must stay darker after simulation, since CVD does not affect the
    luminance channel materially."""
    pairs = [("#FFFFFF", "#808080"), ("#FF0000", "#800000"), ("#00FF00", "#008000")]
    for light, dark in pairs:
        for kind in CVD_KINDS:
            sl = hex_to_oklch(simulate_cvd(light, kind))
            sd = hex_to_oklch(simulate_cvd(dark, kind))
            assert sl.L > sd.L, (light, dark, kind)


def contrast_pair_distance(a_hex: str, b_hex: str) -> float:
    from cuttlefish_theme.color.oklab import delta_e_ok

    return delta_e_ok(hex_to_oklch(a_hex), hex_to_oklch(b_hex))


# --- contrast_ratio ---------------------------------------------------------------


def test_contrast_ratio_white_black_is_21():
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=1e-9)


def test_contrast_ratio_identity_is_1():
    rng = random.Random(11)
    for _ in range(50):
        hex_color = "#{:06X}".format(rng.randrange(1 << 24))
        assert contrast_ratio(hex_color, hex_color) == pytest.approx(1.0, abs=1e-9)


def test_contrast_ratio_is_symmetric():
    assert contrast_ratio("#0B0B0F", "#FDFDF8") == pytest.approx(
        contrast_ratio("#FDFDF8", "#0B0B0F"), abs=1e-12
    )


def test_contrast_ratio_bounds():
    """WCAG ratios live in [1, 21]; anything outside means the formula or
    the luminance function is wrong."""
    rng = random.Random(5)
    for _ in range(200):
        a = "#{:06X}".format(rng.randrange(1 << 24))
        b = "#{:06X}".format(rng.randrange(1 << 24))
        r = contrast_ratio(a, b)
        assert 1.0 - 1e-9 <= r <= 21.0 + 1e-9, (a, b, r)


# --- ensure_contrast ---------------------------------------------------------------

BACKGROUNDS = ("#0B0B0F", "#FDFDF8")


def random_identities(seed: int, n: int) -> list[OKLCh]:
    """Identities across the plausible allocator space: any hue, moderate
    chroma, mid lightness — i.e. colours that will usually FAIL a 4.5
    contrast check before adjustment. Rejection-sampled to lie inside the
    sRGB gamut, because the allocator only emits displayable identities;
    out-of-gamut inputs would conflate ensure_contrast's behaviour with
    the gamut mapper's chroma trimming."""
    from cuttlefish_theme.color.oklab import in_srgb_gamut

    rng = random.Random(seed)
    out: list[OKLCh] = []
    while len(out) < n:
        c = OKLCh(
            L=rng.uniform(0.15, 0.85),
            C=rng.uniform(0.02, 0.15),
            h=rng.uniform(0.0, 360.0),
        )
        if in_srgb_gamut(c):
            out.append(c)
    return out


@pytest.mark.parametrize("bg", BACKGROUNDS)
def test_ensure_contrast_achieves_target_on_many_colours(bg):
    """The core promise: for a large random sample against a dark AND a
    light background, the adjusted colour must actually reach the target
    ratio once rendered to 8-bit hex — not merely in float space."""
    for fg in random_identities(seed=1234, n=300):
        adjusted = ensure_contrast(fg, bg, min_ratio=4.5)
        achieved = contrast_ratio(oklch_to_hex(adjusted), bg)
        assert achieved >= 4.5 - 1e-9, (fg, adjusted, achieved)


@pytest.mark.parametrize("bg", BACKGROUNDS)
def test_ensure_contrast_preserves_hue_and_chroma(bg):
    """Only lightness may move: hue is the identity, chroma is the
    recognisability. Small hue drift from 8-bit rendering is tolerated;
    identity drift is not."""
    for fg in random_identities(seed=99, n=200):
        adjusted = ensure_contrast(fg, bg, min_ratio=4.5)
        assert adjusted.h == pytest.approx(fg.h, abs=1e-9)  # the model object itself
        assert adjusted.C == pytest.approx(fg.C, abs=1e-9)
        # ... and the rendered hex agrees. Gamut mapping holds hue exactly,
        # so any hue difference in the rendering is 8-bit rounding — and
        # rounding error in DEGREES blows up at low chroma while its
        # perceptual size (the arc C * radians(dh)) stays at the sub-JND
        # quantization scale (~0.005, versus a JND of ~0.02). We measure
        # with the RENDERED chroma because that is the chroma the user
        # actually sees when judging the hue.
        rendered = hex_to_oklch(oklch_to_hex(adjusted))
        hue_delta = abs(rendered.h - fg.h)
        hue_delta = min(hue_delta, 360.0 - hue_delta)  # circular
        assert rendered.C * math.radians(hue_delta) < 0.008, (fg, adjusted, rendered)


def test_ensure_contrast_prefers_the_smaller_lightness_change():
    """Against a near-black background the fix should come from LIGHTENING,
    and vice versa — not from slamming every colour to the opposite extreme."""
    for fg in random_identities(seed=7, n=50):
        dark = ensure_contrast(fg, "#0B0B0F")
        light = ensure_contrast(fg, "#FDFDF8")
        # On dark bg the fix must be reachable by lightening; on light bg by
        # darkening. If the adjustment went the 'wrong way' it would need a
        # bigger |dL| than necessary.
        assert dark.L >= fg.L - 1e-9 or contrast_ratio(oklch_to_hex(fg), "#0B0B0F") >= 4.5
        assert light.L <= fg.L + 1e-9 or contrast_ratio(oklch_to_hex(fg), "#FDFDF8") >= 4.5


def test_ensure_contrast_noop_when_already_compliant():
    fg = OKLCh(0.95, 0.10, 200.0)
    assert contrast_ratio(oklch_to_hex(fg), "#0B0B0F") >= 4.5
    assert ensure_contrast(fg, "#0B0B0F") == fg


def test_ensure_contrast_detailed_reports_unreachable_targets():
    """Mid-luminance background + high target: 10:1 against a mid grey is
    physically impossible (the background itself caps the ratio). The
    result must say met=False rather than pretending — and must still
    return the best achievable colour."""
    mid_grey = "#808080"
    fg = OKLCh(0.5, 0.10, 30.0)
    result = ensure_contrast_detailed(fg, mid_grey, min_ratio=10.0)
    assert result.met is False
    assert result.achieved < 10.0
    # And it really is the best effort: neither pure white nor pure black
    # along this hue reaches 10:1 against mid grey.
    assert contrast_ratio("#FFFFFF", mid_grey) < 10.0
    assert contrast_ratio("#000000", mid_grey) < 10.0


def test_ensure_contrast_detailed_reports_success():
    fg = OKLCh(0.5, 0.10, 30.0)
    result = ensure_contrast_detailed(fg, "#0B0B0F", min_ratio=4.5)
    assert result.met is True
    assert result.achieved >= 4.5 - 1e-9
    assert contrast_ratio(oklch_to_hex(result.oklch), "#0B0B0F") >= 4.5 - 1e-9


# --- distinguishable_under_cvd ------------------------------------------------------


def test_distinguishable_report_structure():
    report = distinguishable_under_cvd("#FF0000", "#0000FF")
    assert set(report) == {"normal", "protan", "deutan", "tritan"}
    for kind, entry in report.items():
        assert isinstance(entry["distinguishable"], bool)
        assert entry["distance"] >= 0.0
        assert entry["distinguishable"] == (entry["distance"] >= 0.10)


def test_distinguishable_flags_deutan_red_green_collision():
    """The honest-reporting contract, measured on the equiluminant pair:
    fine under normal vision and for tritan users, a genuine collision for a
    deutanope, and a large (but not total) loss for a protanope. The report
    must surface exactly that gradient, with real numbers."""
    report = distinguishable_under_cvd(RED_EQUIL, GREEN_EQUIL)
    assert report["normal"]["distinguishable"] is True
    assert report["tritan"]["distinguishable"] is True
    assert report["deutan"]["distinguishable"] is False
    assert report["deutan"]["distance"] < 0.10
    # protan shrinks the separation substantially (the confusion axis is
    # real) but the Machado residual keeps it just above the threshold —
    # which is precisely the kind of nuance the distances are exposed for.
    assert report["protan"]["distance"] < 0.5 * report["normal"]["distance"]
    for kind in ("protan", "deutan"):
        assert report[kind]["distance"] < report["normal"]["distance"]


def test_distinguishable_respects_custom_threshold():
    blue_pair = ("#0000FF", "#00FFFF")
    strict = distinguishable_under_cvd(*blue_pair, min_distance=10.0)
    assert all(not entry["distinguishable"] for entry in strict.values())
