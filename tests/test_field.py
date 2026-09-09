"""Behaviour contracts for cuttlefish_theme.field — the pixel grid.

The claims under test are the ones that separate "a grid of coloured squares" from
"skin": spatial correlation, layered compositing, single-band waves, and a blink.
"""

from __future__ import annotations

import re

import pytest

from cuttlefish_theme.field import (WAVE_AGONISTIC_HZ, WAVE_HUNTING_HZ, Field,
                                    mottle, passing_cloud,
                                    render_half_blocks, render_rows)

PIGMENT = "#2F9C9F"
SHEEN = "#7FD4D6"
GROUND = "#0B1516"


# --- the field itself -------------------------------------------------------

def test_states_are_clamped_to_what_a_chromatophore_can_hold():
    """Expansion is a physical sac size in 0..1. A caller must never be able to
    observe a state outside that, or the compositor would extrapolate colours."""
    f = Field.blank(4, 4)
    f.set(0, 0, 5.0)
    f.set(1, 0, -3.0)
    assert f.get(0, 0) == 1.0
    assert f.get(1, 0) == 0.0


def test_field_wraps_rather_than_raising():
    """Wave maths indexes past the edges constantly; wrapping keeps that cheap and
    keeps a band continuous instead of clipping at the mantle edge."""
    f = Field.blank(3, 3)
    f.set(0, 0, 1.0)
    assert f.get(3, 3) == 1.0
    assert f.get(-3, -3) == 1.0


def test_blend_requires_matching_geometry():
    with pytest.raises(ValueError):
        Field.blank(4, 4).blend(Field.blank(5, 4), 0.5)


# --- texture ----------------------------------------------------------------

def test_mottle_is_spatially_correlated_not_static():
    """Real skin texture is correlated: neighbouring chromatophores are recruited
    together into components. Uncorrelated per-cell noise reads as dead pixels.

    Measured as: adjacent cells differ far less than distant ones.
    """
    f = mottle(40, 40, seed=7, scale=3.0)
    adjacent = sum(abs(f.get(x, y) - f.get(x + 1, y))
                   for y in range(40) for x in range(39)) / (40 * 39)
    distant = sum(abs(f.get(x, y) - f.get((x + 17) % 40, y))
                  for y in range(40) for x in range(40)) / (40 * 40)
    assert adjacent < distant * 0.6, "texture is not spatially correlated"


def test_mottle_is_deterministic_per_seed():
    """A session's resting pattern must be the same every time it is drawn, or the
    field stops being an identity and becomes decoration."""
    assert mottle(12, 8, seed=3).cells == mottle(12, 8, seed=3).cells
    assert mottle(12, 8, seed=3).cells != mottle(12, 8, seed=4).cells


def test_mottle_uses_the_available_range():
    """A texture squeezed into a narrow band of expansion is invisible."""
    f = mottle(30, 20, seed=11)
    assert max(f.cells) - min(f.cells) > 0.35


# --- the passing cloud ------------------------------------------------------

def test_only_one_band_is_visible_at_a_time():
    """Laan et al. 2014: "the wavelength of each wave corresponds roughly to its
    length of travel, so that usually only one band is visible in each region at a
    time." A zebra of repeating stripes is the classic wrong implementation.

    Measured on a column: the expansion profile has a single local maximum.
    """
    base = Field.blank(8, 40, 0.0)
    wave = passing_cloud(base, 0.5, hz=WAVE_HUNTING_HZ, blink=False, seed=0)
    column = [wave.get(0, y) for y in range(40)]
    peaks = [i for i in range(1, 39)
             if column[i] > column[i - 1] and column[i] >= column[i + 1]]
    assert len(peaks) <= 1, f"expected one band, found {len(peaks)} peaks"


def test_the_band_travels():
    """It is a *travelling* wave; a band that pulses in place is a different
    display entirely."""
    base = Field.blank(8, 40, 0.0)

    def peak_at(t: float) -> int:
        wave = passing_cloud(base, t, hz=WAVE_HUNTING_HZ, blink=False, seed=0)
        column = [wave.get(0, y) for y in range(40)]
        return column.index(max(column))

    early, late = peak_at(0.30), peak_at(0.60)
    assert early != late, "the band did not move"


def test_wave_frequency_is_honoured():
    """One full traversal per 1/hz seconds: the display frequency is a measured
    quantity (1 Hz hunting, 0.38 Hz agonistic), not a vibe."""
    base = Field.blank(6, 30, 0.0)
    for hz in (WAVE_HUNTING_HZ, WAVE_AGONISTIC_HZ):
        a = passing_cloud(base, 0.13, hz=hz, blink=False, seed=0)
        b = passing_cloud(base, 0.13 + 1.0 / hz, hz=hz, blink=False, seed=0)
        assert a.cells == pytest.approx(b.cells, abs=1e-9), f"not periodic at {hz}Hz"


def test_the_wave_only_ever_expands_chromatophores():
    """A passing cloud is a wave of EXPANSION superimposed on the resting pattern;
    it must never subtract from the base, which would punch holes in the identity."""
    base = mottle(10, 24, seed=5)
    wave = passing_cloud(base, 0.4, hz=WAVE_HUNTING_HZ, seed=5)
    for i, (b, w) in enumerate(zip(base.cells, wave.cells)):
        assert w >= b - 1e-9, f"cell {i} was suppressed below the base"


def test_blink_suppresses_some_band_cells_without_stopping_it():
    """Metasepia's "blink": a transient LOCAL intensity drop while the band keeps
    propagating underneath (Laan et al. 2014). So the blinking field must differ
    from the non-blinking one, but still carry a band."""
    base = Field.blank(24, 24, 0.0)
    plain = passing_cloud(base, 0.5, blink=False, seed=99)
    blinked = passing_cloud(base, 0.5, blink=True, seed=99)
    assert blinked.cells != plain.cells, "blink had no effect"
    assert max(blinked.cells) > 0.3, "blink erased the band entirely"
    dimmed = sum(1 for a, b in zip(plain.cells, blinked.cells) if b < a - 1e-9)
    assert dimmed < len(plain.cells) * 0.5, "blink should be local, not global"


# --- compositing and rendering ----------------------------------------------

_ANSI = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m\x1b\[48;2;(\d+);(\d+);(\d+)m\u2580")


def test_retracted_cells_reveal_the_layer_beneath_not_black():
    """Cephalopod skin is stratified: retracting the pigment sac exposes the
    iridophore/leucophore layers (Froesch & Messenger 1978). Retracted skin is a
    DIFFERENT COLOUR, not merely a darker one — this is most of the difference
    between "coloured squares" and "skin"."""
    retracted = render_half_blocks(Field.blank(1, 2, 0.0), pigment_hex=PIGMENT,
                                   sheen_hex=SHEEN, base_hex=GROUND)[0]
    expanded = render_half_blocks(Field.blank(1, 2, 1.0), pigment_hex=PIGMENT,
                                  sheen_hex=SHEEN, base_hex=GROUND)[0]
    r_fg = _ANSI.search(retracted).group(1, 2, 3)
    e_fg = _ANSI.search(expanded).group(1, 2, 3)
    assert r_fg != e_fg
    # The retracted cell is lifted toward the sheen, so it is not the flat ground.
    assert r_fg != ("11", "21", "22")


def test_fully_expanded_cells_expose_leucophore_white():
    """Past the leucophore onset a cell brightens toward broadband white.

    This is the third dermal layer (Froesch & Messenger 1978): the bright patches
    on a displaying cuttlefish are leucophores, NOT more pigment. Modelling only
    pigment+iridophore capped the field at the pigment's own lightness (L~0.62)
    and produced 0% bright pixels where the real animal measures 16.4%.
    """
    from cuttlefish_theme.color.oklab import hex_to_oklch

    pig = hex_to_oklch(PIGMENT)
    full = hex_to_oklch(_one_fg(Field.blank(1, 2, 1.0)))
    assert full.L > pig.L, "full expansion must be brighter than the pigment alone"
    assert full.C < pig.C, "a leucophore is broadband white, so chroma drops"


def test_pigment_shows_at_the_leucophore_onset():
    """Just below the onset, the cell IS the identity pigment.

    The onset must not swallow the pigment entirely, or the field would never
    show the session's actual colour — only its ground and its highlights.
    """
    from cuttlefish_theme.color.oklab import hex_to_oklch

    from cuttlefish_theme.field import _LEUCO_ONSET

    at_onset = hex_to_oklch(_one_fg(Field.blank(1, 2, _LEUCO_ONSET)))
    pig = hex_to_oklch(PIGMENT)
    assert abs(at_onset.L - pig.L) < 0.06
    assert abs(((at_onset.h - pig.h + 180) % 360) - 180) < 12


def _one_fg(field) -> str:
    """The foreground hex of the first rendered cell."""
    line = render_half_blocks(field, pigment_hex=PIGMENT, sheen_hex=SHEEN,
                              base_hex=GROUND)[0]
    r, g, b = (int(v) for v in _ANSI.search(line).group(1, 2, 3))
    return "#%02X%02X%02X" % (r, g, b)


def test_two_pixels_per_character_cell():
    """The half-block trick is what buys the vertical resolution; a renderer that
    silently emitted one pixel per cell would halve the grid without saying so."""
    field = Field.blank(6, 8)
    lines = render_half_blocks(field, pigment_hex=PIGMENT, sheen_hex=SHEEN,
                               base_hex=GROUND)
    assert len(lines) == 4 == render_rows(field)
    assert len(_ANSI.findall(lines[0])) == 6


def test_odd_height_still_renders_every_row():
    """An odd final row must not be dropped — the grid would report a height it
    does not have."""
    field = Field.blank(4, 7)
    lines = render_half_blocks(field, pigment_hex=PIGMENT, sheen_hex=SHEEN,
                               base_hex=GROUND)
    assert len(lines) == 4 == render_rows(field)


def test_every_line_resets_its_colour():
    """An unterminated SGR run bleeds the background across the rest of the
    terminal — the single most common way a pixel renderer ruins a session."""
    lines = render_half_blocks(mottle(8, 6, seed=1), pigment_hex=PIGMENT,
                               sheen_hex=SHEEN, base_hex=GROUND)
    for line in lines:
        assert line.endswith("\x1b[0m")


def test_rendered_channels_are_valid_bytes():
    lines = render_half_blocks(mottle(10, 6, seed=2), pigment_hex=PIGMENT,
                               sheen_hex=SHEEN, base_hex=GROUND)
    for line in lines:
        for match in _ANSI.finditer(line):
            for value in match.groups():
                assert 0 <= int(value) <= 255
