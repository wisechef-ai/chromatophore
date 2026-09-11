"""v8 chrome-renderer acceptance tests."""
from __future__ import annotations

import re
from collections import Counter

from cuttlefish_theme import plugin
from cuttlefish_theme.chrome import rich_to_prompt_toolkit
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
        fg = re.search(r"fg:(#[0-9a-f]{6})", style).group(1)
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


def test_renderer_cache_avoids_recomputing_separator(monkeypatch):
    plugin.chrome_renderer("input_rule_top", 80, ctx("idle"))
    calls = 0
    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("separator recomputed")
    import cuttlefish_theme.chrome as chrome
    monkeypatch.setattr(chrome, "separator_markup", fail)
    assert plugin.chrome_renderer("input_rule_top", 80, ctx("idle"))
    assert calls == 0


def test_renderer_degrades_to_identity_without_pet_state():
    rendered = plugin.chrome_renderer("input_rule_top", 80, {"session_id": "zivyra", "skin": {}})
    resting = plugin.chrome_renderer("input_rule_top", 80, ctx("idle"))
    assert rendered == resting


def test_rich_converter_rejects_malformed_markup_and_parses_multiple_cells():
    assert rich_to_prompt_toolkit("[#112233 on #000000]─[/][#445566 on #000000]━[/]") == [
        ("fg:#112233 bg:#000000", "─"),
        ("fg:#445566 bg:#000000", "━"),
    ]
    import pytest
    with pytest.raises(ValueError):
        rich_to_prompt_toolkit("not rich markup")
