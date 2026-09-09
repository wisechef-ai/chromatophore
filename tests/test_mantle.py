"""Behaviour contracts for the persistent mantle.

The mantle is the theme's answer to "the background has to differentiate
sessions". A flat background cannot: one hex value has three numbers in it and
two are spoken for by "dark enough to read on" and "not pure black". Six sessions
measured 0.0148 OKLab apart that way — six blacks.

A 30x30 pixel grid has 900 cells. These tests pin the properties that make it an
identity channel rather than decoration.
"""

from __future__ import annotations

import re

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.mantle import MANTLE_HEIGHT, MANTLE_WIDTH, mantle_rows

IDENTITY = "#8F6BE1"
SHEEN = "#B79BFF"
GROUND = "#140F22"

_MARKUP = re.compile(r"\[/?[^\]]*\]")
_ANSI = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m\x1b\[48;2;(\d+);(\d+);(\d+)m\u2580")


def _visible(markup: str) -> list[str]:
    return [_MARKUP.sub("", line) for line in markup.split("\n")]


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


def test_every_session_gets_a_DIFFERENT_pattern_not_just_a_different_hue():
    """The point of pixels over a flat colour.

    Two sessions with similar hues must still be told apart by the ARRANGEMENT of
    their chromatophores — that is the information a background hex cannot carry,
    and the reason the flat-colour approach was rejected.
    """
    a = mantle_rows("session-a", IDENTITY, SHEEN, GROUND)
    b = mantle_rows("session-b", IDENTITY, SHEEN, GROUND)
    assert a != b, "same identity colour produced an identical pattern"


def test_a_session_keeps_its_pattern_across_restarts():
    """Deterministic: reconnecting must not reshuffle your session's skin."""
    assert mantle_rows("s1", IDENTITY, SHEEN, GROUND) == \
        mantle_rows("s1", IDENTITY, SHEEN, GROUND)


def test_markup_mode_emits_rich_not_raw_escapes():
    """`banner_hero` is handed to a Rich console. Raw ANSI would be escaped and
    printed literally — which is exactly how a wall of `?[38;2;...` reaches a
    transcript."""
    out = mantle_rows("s1", IDENTITY, SHEEN, GROUND, markup=True)
    assert "\x1b[" not in out
    assert " on " in out and "[/]" in out


def test_ansi_mode_emits_escapes_and_always_resets():
    """The direct-write path. An unterminated SGR run bleeds colour across the
    rest of the terminal."""
    out = mantle_rows("s1", IDENTITY, SHEEN, GROUND, markup=False)
    assert _ANSI.search(out)
    for line in out.split("\n"):
        assert line.endswith("\x1b[0m")


def test_the_mantle_is_dark_with_bright_spots():
    """Cuttlefish skin, not a colour block: most cells near the ground, a
    minority strongly expressed."""
    out = mantle_rows("s1", IDENTITY, SHEEN, GROUND, markup=False)
    lightness = []
    for match in _ANSI.finditer(out):
        r, g, b = (int(v) for v in match.group(1, 2, 3))
        lightness.append(hex_to_oklch("#%02X%02X%02X" % (r, g, b)).L)
    assert lightness
    dark = sum(1 for value in lightness if value < 0.30) / len(lightness)
    bright = sum(1 for value in lightness if value > 0.55) / len(lightness)
    assert dark > 0.4, f"only {dark:.0%} of the mantle is dark"
    assert bright > 0.02, f"no highlights: {bright:.1%} bright cells"


def test_mantle_is_written_into_the_skin_as_banner_hero(tmp_path, monkeypatch):
    """End-to-end: the mantle must actually reach the skin file, or none of the
    above matters."""
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
