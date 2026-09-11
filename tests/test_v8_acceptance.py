"""v8 chrome-renderer acceptance tests."""
from __future__ import annotations

import re

import pytest
from collections import Counter

from cuttlefish_theme import plugin
from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import quantize_256, _index_to_hex
from cuttlefish_theme.linework import separator_markup
from cuttlefish_theme.pattern import render
from cuttlefish_theme.color.identity import allocate

CELL = re.compile(r"\[(#[0-9A-Fa-f]{6}) on (#[0-9A-Fa-f]{6})\]")


def ctx(state="idle", sid="zivyra"):
    return {"session_id": sid, "skin": {}, "pet_state": state}


def vivid_hues(fragments):
    ground = quantize_256(render(allocate("zivyra")).ground_hex)
    hues = []
    for style, text in fragments:
        fg = re.search(r"fg:(#[0-9a-fA-F]{6})", style).group(1)
        if quantize_256(fg) != ground:
            hues.append(hex_to_oklch(_index_to_hex(quantize_256(fg))).h)
    return hues


def test_register_chrome_renderer_is_guarded_without_hook():
    hooks = []
    class Ctx:
        def register_hook(self, name, fn): hooks.append(name)
        def register_cli_command(self, *args, **kwargs): pass
    plugin.register(Ctx())
    assert hooks == ["on_session_start", "on_session_end"]


def test_input_rule_chrome_converts_rich_markup_to_prompt_toolkit_fragments():
    fragments = plugin.chrome_renderer("input_rule_top", 80, ctx())
    assert fragments
    assert sum(len(text) for _, text in fragments) == 80
    assert all(style.startswith("fg:#") and " bg:#" in style for style, _ in fragments)
    assert all("[" not in text and "]" not in text for _, text in fragments)


def test_live_pet_state_selects_resting_amber_and_red_hue_families():
    idle = plugin.chrome_renderer("input_rule_top", 120, ctx("idle"))
    run = plugin.chrome_renderer("input_rule_top", 120, ctx("run"))
    waiting = plugin.chrome_renderer("input_rule_top", 120, ctx("waiting"))
    failed = plugin.chrome_renderer("input_rule_top", 120, ctx("failed"))
    assert idle == run
    assert all(62 <= h <= 105 for h in vivid_hues(waiting))
    assert all(5 <= h <= 48 for h in vivid_hues(failed))
    assert idle != waiting and idle != failed
    assert plugin.chrome_renderer("input_rule_top", 120, ctx("mystery")) == idle
    assert plugin.chrome_renderer("input_rule_top", 120, {"session_id": "zivyra"}) == idle


def test_identity_layer_separates_two_session_ids():
    a = plugin.chrome_renderer("input_rule_top", 120, ctx("idle", "zivyra"))
    b = plugin.chrome_renderer("input_rule_top", 120, ctx("idle", "tilola"))
    assert a != b


def test_status_bar_bg_carries_only_acute_signal():
    assert plugin.chrome_renderer("status_bar_bg", 20, ctx("idle")) is None
    amber = plugin.chrome_renderer("status_bar_bg", 20, ctx("waiting"))
    red = plugin.chrome_renderer("status_bar_bg", 20, ctx("failed"))
    assert amber and red and amber != red
    assert "#" in amber[0][0] and "#" in red[0][0]


@pytest.mark.parametrize("width", [20, 80, 200])
def test_status_bar_tint_covers_every_cell(width):
    """The acute tint must fill the bar, not one cell.

    The core pads a short fragment list to `width` with the EMPTY style, so
    returning a single space paints 1 cell and leaves the other width-1 stock —
    an alarm the user cannot see. Measured before this test: 1 of 80 cells.
    """
    from hermes_cli.plugins_dispatch import _normalize_chrome_fragments

    for state in ("waiting", "failed"):
        frags = plugin.chrome_renderer("status_bar_bg", width, ctx(state))
        normalised = _normalize_chrome_fragments(frags, width)
        styled = sum(len(text) for style, text in normalised if style)
        assert styled == width, (
            f"{state}: only {styled} of {width} status-bar cells carry the tint")


def test_renderer_cache_avoids_recomputing_the_field():
    """The renderer runs on the repaint path, so a repeat call must be served
    from cache — the field walk is the expensive part, not the formatting."""
    from cuttlefish_theme.linework import cells

    cells.cache_clear()
    plugin.chrome_renderer("input_rule_top", 80, ctx("idle"))
    after_first = cells.cache_info()
    assert after_first.misses == 1
    assert plugin.chrome_renderer("input_rule_top", 80, ctx("idle"))
    assert cells.cache_info().misses == 1, "field recomputed on repaint"
    assert cells.cache_info().hits >= 1


def test_renderer_degrades_to_identity_without_pet_state():
    rendered = plugin.chrome_renderer("input_rule_top", 80, {"session_id": "zivyra", "skin": {}})
    resting = plugin.chrome_renderer("input_rule_top", 80, ctx("idle"))
    assert rendered == resting


def test_fragments_are_prompt_toolkit_styles_not_rich_markup():
    """Rich markup handed to a PT control renders styleless, so the styles must
    be PT's own `fg:#rrggbb bg:#rrggbb` grammar and one glyph per cell."""
    frags = plugin.chrome_renderer("input_rule_top", 12, ctx("idle"))
    assert len(frags) == 12
    for style, text in frags:
        assert re.fullmatch(r"fg:#[0-9a-fA-F]{6} bg:#[0-9a-fA-F]{6}", style), style
        assert len(text) == 1 and text in "─━"
        assert "[" not in style and "/" not in style


def test_markup_and_fragments_come_from_one_source():
    """Both formatters render the same cells, so the rule cannot drift between
    the skin-data path (Rich) and the live chrome path (prompt_toolkit)."""
    from cuttlefish_theme.linework import cells, separator_markup

    grid = cells("zivyra", "resting", 12)
    frags = plugin.chrome_renderer("input_rule_top", 12, ctx("idle"))
    markup = separator_markup("zivyra", "resting", 12)
    assert [g for _, _, g in grid] == [t for _, t in frags]
    assert markup.count("[/]") == len(grid)
