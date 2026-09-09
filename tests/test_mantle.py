"""Behaviour contracts for the multi-pigment mantle.

The mantle is the theme's identity channel. A flat background cannot be one: one
hex has three numbers and two are spent on "dark enough to read on" and "not pure
black". Six sessions measured 0.0148 OKLab apart that way — six blacks. A 30x30
grid has 900 cells, and (since 2026-09-09) three pigment classes per session, so
it has room to be an identity AND a state display at once.
"""

from __future__ import annotations

import re

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.mantle import (MANTLE_HEIGHT, MANTLE_WIDTH, mantle_rows,
                                     pigment_set)

IDENTITY = "#8F6BE1"
SHEEN = "#B79BFF"
GROUND = "#140F22"
AMBER = "#F1B200"
FAULT = "#E24942"

_MARKUP = re.compile(r"\[/?[^\]]*\]")
_ANSI = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m\x1b\[48;2;(\d+);(\d+);(\d+)m\u2580")


def _visible(markup: str) -> list[str]:
    return [_MARKUP.sub("", line) for line in markup.split("\n")]


def _fg_colours(ansi: str) -> list[str]:
    return ["#%02X%02X%02X" % tuple(int(v) for v in m.group(1, 2, 3))
            for m in _ANSI.finditer(ansi)]


# --- geometry ---------------------------------------------------------------

def test_mantle_fits_the_caduceus_slot_it_replaces():
    """`banner_hero` is the LEFT COLUMN of banner.py's two-column layout, and the
    art it replaces (HERMES_CADUCEUS) is 30 wide by 15 tall.

    REGRESSION: an earlier hero was rendered 92 columns wide. It did not error —
    it silently broke the banner layout, and the pixel field never appeared on
    screen at all. "Missing" and "overflowing" look identical from the outside,
    which is why this is pinned to a number rather than left to judgement.
    """
    lines = _visible(mantle_rows("s1", IDENTITY, SHEEN, GROUND))
    assert len(lines) == 15, f"{len(lines)} text rows, caduceus is 15"
    assert max(len(line) for line in lines) == 30
    assert MANTLE_HEIGHT == 2 * 15, "pixel rows are half-blocks: 2 per text row"
    assert MANTLE_WIDTH == 30


# --- identity ---------------------------------------------------------------

def test_every_session_gets_a_DIFFERENT_pattern_not_just_a_different_hue():
    """The point of pixels over a flat colour: two sessions with similar hues are
    still told apart by the ARRANGEMENT of their chromatophores."""
    assert mantle_rows("session-a", IDENTITY, SHEEN, GROUND) != \
        mantle_rows("session-b", IDENTITY, SHEEN, GROUND)


def test_a_session_keeps_its_pattern_across_restarts():
    assert mantle_rows("s1", IDENTITY, SHEEN, GROUND) == \
        mantle_rows("s1", IDENTITY, SHEEN, GROUND)


# --- multi-pigment ----------------------------------------------------------

def test_the_mantle_uses_several_pigment_classes():
    """A cuttlefish carries THREE chromatophore classes — yellow, red and brown
    (Cloney & Florey 1968) — stacked in layers over blue-green iridophores.

    Adam, 2026-09-09: "is it possible to have the multi color vibrant imitation
    of the cuttlefish ... so it looks kinda like astral photos of cosmos/nebulas".
    That is MORE biologically correct than the single-pigment field it replaced.
    """
    classes = pigment_set(IDENTITY)
    assert len(classes) >= 4, "three pigments plus a structural (cool) class"
    # Spread is measured on the WARM classes; the fourth is deliberately far
    # away, because the animal's pigments sit OVER blue-green iridophores and
    # that warm/cool contrast is what stops the field reading as a gradient.
    # An earlier 65-degree all-warm spread was analogous and looked like one
    # colour with tonal variation, which is not what was asked for.
    warm = sorted(c.h for c in classes[:3])
    assert 60 < (warm[-1] - warm[0]) < 130, f"warm spread {warm[-1]-warm[0]:.0f}"
    cool = classes[3]
    separation = abs(((cool.h - warm[1] + 180) % 360) - 180)
    assert separation > 100, f"the structural class is not cool: {separation:.0f}"


def test_pigment_classes_differ_in_more_than_hue():
    """Real classes differ in density too. A set varying only in hue renders as a
    gradient rather than as distinct cell populations."""
    classes = pigment_set(IDENTITY)
    assert len({round(c.L, 3) for c in classes}) > 1
    assert len({round(c.C, 3) for c in classes}) > 1


def test_the_rendered_field_actually_shows_multiple_hues():
    """The classes must reach the SCREEN, not just the palette."""
    hues = {round(hex_to_oklch(c).h / 15) * 15
            for c in _fg_colours(mantle_rows("s1", IDENTITY, SHEEN, GROUND,
                                             markup=False))
            if hex_to_oklch(c).C > 0.04}
    assert len(hues) >= 3, f"only {len(hues)} hue families on screen: {hues}"


# --- state ------------------------------------------------------------------

def test_a_signal_recolours_the_whole_field():
    """Adam asked for a pattern "which changes it's colors when the session
    progresses (on issues/errors etc)". The acute layer must move the pigment,
    not just an accent line."""
    calm = mantle_rows("s1", IDENTITY, SHEEN, GROUND, markup=False)
    hot = mantle_rows("s1", IDENTITY, SHEEN, GROUND, acute_hex=FAULT,
                      markup=False)
    assert calm != hot
    calm_hue = sum(hex_to_oklch(c).h for c in _fg_colours(calm)) / len(_fg_colours(calm))
    hot_hue = sum(hex_to_oklch(c).h for c in _fg_colours(hot)) / len(_fg_colours(hot))
    assert abs(calm_hue - hot_hue) > 20, "the field barely moved"


def test_the_arrangement_survives_a_state_change():
    """Blanching COVERS identity, it never destroys it (Nature 619, 2023): the
    animal returns to its exact prior pattern. So a fault may recolour every
    cell, but the SHAPE of the pattern must be the session's own."""
    calm = _visible(mantle_rows("s1", IDENTITY, SHEEN, GROUND))
    hot = _visible(mantle_rows("s1", IDENTITY, SHEEN, GROUND, acute_hex=FAULT))
    assert [len(a) for a in calm] == [len(b) for b in hot]
    assert len(calm) == len(hot)


def test_no_pigment_class_contradicts_the_signal_it_announces():
    """A warm signal must never render a cell that reads as "ok".

    REGRESSION, and a subtle one. The first implementation dragged each class
    toward the acute hue independently; a class ~180 degrees away has no good
    short path, so a violet session blanching to amber produced hue 132 — a GREEN
    chromatophore inside a fault display. Fixed by rebuilding the spread AROUND
    the acute hue and narrowing it.

    The right test is not "avoid hue 90-180" (amber's own reserved band runs to
    102) but "is any class nearer to the GOOD anchor than to the signal it is
    announcing?" — which is what a human actually misreads.
    """
    from cuttlefish_theme.color.oklab import OKLCh, oklch_to_hex
    from cuttlefish_theme.palette import SEMANTIC

    good = SEMANTIC["good"].h
    for identity_hue in range(0, 360, 15):
        identity = oklch_to_hex(OKLCh(0.62, 0.17, identity_hue))
        for anchor_key, acute in (("warn", AMBER), ("error", FAULT)):
            signal = SEMANTIC[anchor_key].h
            for c in pigment_set(identity, acute):
                to_signal = abs(((c.h - signal + 180) % 360) - 180)
                to_good = abs(((c.h - good + 180) % 360) - 180)
                assert to_good > to_signal, (
                    f"identity h{identity_hue} + {anchor_key}: class at h{c.h:.0f} "
                    f"is nearer green ({to_good:.0f}) than its signal ({to_signal:.0f})")


# --- rendering --------------------------------------------------------------

def test_markup_mode_emits_rich_not_raw_escapes():
    """`banner_hero` is handed to a Rich console. Raw ANSI would be escaped and
    printed literally — which is how a wall of `?[38;2;...` reaches a transcript."""
    out = mantle_rows("s1", IDENTITY, SHEEN, GROUND, markup=True)
    assert "\x1b[" not in out
    assert " on " in out and "[/]" in out


def test_ansi_mode_emits_escapes_and_always_resets():
    out = mantle_rows("s1", IDENTITY, SHEEN, GROUND, markup=False)
    assert _ANSI.search(out)
    for line in out.split("\n"):
        assert line.endswith("\x1b[0m")


def test_the_mantle_is_dark_with_bright_spots():
    """Cuttlefish skin, not a colour block: most cells near the ground, a
    minority strongly expressed."""
    lightness = [hex_to_oklch(c).L for c in
                 _fg_colours(mantle_rows("s1", IDENTITY, SHEEN, GROUND,
                                         markup=False))]
    assert lightness
    dark = sum(1 for v in lightness if v < 0.30) / len(lightness)
    bright = sum(1 for v in lightness if v > 0.55) / len(lightness)
    assert dark > 0.4, f"only {dark:.0%} of the mantle is dark"
    assert bright > 0.02, f"no highlights: {bright:.1%} bright cells"


def test_mantle_is_written_into_the_skin_as_banner_hero(tmp_path, monkeypatch):
    """End-to-end: the mantle must reach the skin file, or none of the above
    matters."""
    import yaml

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.pattern import render
    from cuttlefish_theme.skinio import write_skin

    path = write_skin(render(allocate("s1")), name="cuttlefish")
    data = yaml.safe_load(path.read_text())
    hero = data["banner_hero"].rstrip("\n").split("\n")
    assert len(hero) == 15
    assert max(len(_MARKUP.sub("", line)) for line in hero) == 30
