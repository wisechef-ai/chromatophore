"""v9 transcript mantle acceptance tests."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import pytest

from cuttlefish_theme import plugin
from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import contrast_ratio
from cuttlefish_theme.pattern import render
from cuttlefish_theme.color.identity import allocate


def test_transcript_line_returns_filled_background_fragments():
    fragments = plugin.chrome_renderer(
        "transcript_line", 80, {"session_id": "zivyra", "row_key": 7}
    )
    assert fragments
    assert sum(len(text) for style, text in fragments) == 80
    assert all(re.fullmatch(r"bg:#[0-9A-Fa-f]{6}", style) for style, _ in fragments)


def test_transcript_mantle_is_stable_by_row_and_varies_between_rows():
    ctx = {"session_id": "zivyra", "row_key": 12}
    first = plugin.chrome_renderer("transcript_line", 80, ctx)
    assert first == plugin.chrome_renderer("transcript_line", 80, ctx)
    assert first != plugin.chrome_renderer(
        "transcript_line", 80, {"session_id": "zivyra", "row_key": 13}
    )


def test_transcript_mantle_is_process_stable():
    code = """
import importlib.util, json, sys
from pathlib import Path
root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('cuttlefish_theme', root/'__init__.py', submodule_search_locations=[str(root)])
m = importlib.util.module_from_spec(spec); sys.modules['cuttlefish_theme'] = m; spec.loader.exec_module(m)
print(json.dumps(m.plugin.chrome_renderer('transcript_line', 80, {'session_id':'zivyra','row_key':12})))
"""
    root = str(__import__("cuttlefish_theme").__path__[0])
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "random"
    out = subprocess.check_output([sys.executable, "-c", code, root], text=True, env=env)
    assert [tuple(row) for row in json.loads(out)] == plugin.chrome_renderer(
        "transcript_line", 80, {"session_id": "zivyra", "row_key": 12}
    )


def test_transcript_backgrounds_keep_wcag_aa_against_normal_foreground():
    normal_foreground = "#E8E6EA"
    fragments = plugin.chrome_renderer(
        "transcript_line", 120, {"session_id": "zivyra", "row_key": 12}
    )
    ratios = [contrast_ratio(normal_foreground, style.split(":", 1)[1]) for style, _ in fragments]
    assert min(ratios) >= 4.5
    # Readability is the contrast assertion above. The lightness bound is the
    # design ceiling for a background: 0.32 was written when the mantle had ONE
    # near-black pigment, and the four-class set needs headroom for the
    # iridophore and the pearl. 0.52 is the cap the renderer enforces; measured,
    # 30 chromatic cube entries clear AA and the highest sits at L 0.538.
    assert all(hex_to_oklch(style.split(":", 1)[1]).L <= 0.52 for style, _ in fragments)


def test_transcript_mantle_has_about_thirty_percent_pigment():
    ground = render(allocate("zivyra")).ground_hex.lower()
    fragments = plugin.chrome_renderer(
        "transcript_line", 200, {"session_id": "zivyra", "row_key": 12}
    )
    pigment = sum(style.split(":", 1)[1].lower() != ground for style, _ in fragments)
    assert 0.22 <= pigment / 200 <= 0.38


@pytest.mark.parametrize("session_id", [
    "zivyra", "koralen", "tori-main", "chef", "wise", "mantis", "tilola", "sepia"])
def test_mantle_pigment_survives_terminal_quantisation(session_id):
    """The mantle must still read as COLOUR on the terminal, not grey.

    prompt_toolkit renders at DEPTH_8_BIT: our truecolor `48;2;r;g;b` is
    quantised to an xterm-256 index before it reaches the screen. The 256-cube
    is sparse in the dark region, so a low-chroma near-black pigment collapses
    onto the GREYSCALE ramp (232-255) and the mantle reads as flat grey — which
    is exactly what a user reported while every byte-level test passed.

    Assert on the QUANTISED index, the way the terminal actually sees it.
    """
    from cuttlefish_theme.chrome import _mantle_classes, _mantle_palette
    from cuttlefish_theme.color.terminal import quantize_256

    ground_index = quantize_256(_mantle_palette(session_id))
    for pigment in _mantle_classes(session_id, "resting"):
        pigment_index = quantize_256(pigment)
        assert pigment_index != ground_index, "pigment collapsed onto the ground"
        # 232-255 is the greyscale ramp: landing there means the hue is gone.
        assert not 232 <= pigment_index <= 255, (
            f"pigment quantised to grey index {pigment_index} — the mantle has no colour")
