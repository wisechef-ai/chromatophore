"""v7 body-pattern contract; each test was red on e643a9d."""
from __future__ import annotations

import inspect
import re
from itertools import pairwise

from cuttlefish_theme.color.terminal import quantize_256
from cuttlefish_theme.palette import dominant_pigments, pigment_hex
from cuttlefish_theme.seed import seed_for

HEX = re.compile(r"#[0-9A-Fa-f]{6}")

def _colours(markup):
    return HEX.findall(markup)


def test_input_rule_is_driven_by_body_pattern_field_not_modulo_pigment_rainbow():
    from cuttlefish_theme.linework import separator
    from cuttlefish_theme.patterns import field_for
    row = separator("zivyra", "resting", 120)
    assert field_for("zivyra", 120, 1)[0].name in {
        "uniform-fine-mottle", "coarse-mottle", "transverse-stripes-zebra",
        "passing-cloud-bands", "disruptive-patches", "pearl-scatter",
    }
    q = [quantize_256(c) for c in _colours(row)]
    from cuttlefish_theme.linework import _pigment_variants
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.pattern import render
    allowed = set()
    for name in dominant_pigments("zivyra"):
        allowed.update(_pigment_variants(name))
    allowed.add(render(allocate("zivyra")).ground_hex)
    assert set(_colours(row)) <= allowed
    assert len(set(q)) >= 3
    assert q != [q[i % 8] for i in range(len(q))]


def test_input_rule_has_dark_ground_dominance_and_sparse_chromatophores():
    from cuttlefish_theme.linework import separator
    from cuttlefish_theme.pattern import render
    from cuttlefish_theme.color.identity import allocate
    row = separator("zivyra", "resting", 200)
    q = [quantize_256(c) for c in _colours(row)]
    ground = quantize_256(render(allocate("zivyra")).ground_hex)
    assert q.count(ground) >= 0.45 * len(q)
    assert sum(i != ground for i in q) >= 2
    assert sum(i != ground for i in q) <= 0.55 * len(q)
    from cuttlefish_theme.linework import _pigment_variants
    allowed = {quantize_256(c) for n in dominant_pigments("zivyra") for c in _pigment_variants(n)}
    assert set(q) <= {ground} | allowed


def test_input_rule_quantised_pattern_has_clusters_not_cellwise_static():
    from cuttlefish_theme.linework import separator
    q = [quantize_256(c) for c in _colours(separator("zivyra", "resting", 240))]
    changes = sum(a != b for a, b in pairwise(q))
    runs = sum(1 for a, b, c in zip(q, q[1:], q[2:]) if a == c != b)
    assert changes < 0.72 * len(q)
    assert runs >= 8


def test_input_rule_uses_only_the_session_seed_and_existing_pattern_library():
    import cuttlefish_theme.linework as linework
    source = inspect.getsource(linework)
    assert "field_for" in source
    assert "random" not in source
    assert "hash(" not in source
    assert seed_for("zivyra") == seed_for("zivyra")


def test_input_rule_is_stable_but_sessions_and_signals_are_distinct():
    from cuttlefish_theme.linework import separator
    a = separator("zivyra", "resting", 160)
    assert a == separator("zivyra", "resting", 160)
    assert a != separator("tilola", "resting", 160)
    assert a != separator("zivyra", "needs-me", 160)
    assert a != separator("zivyra", "fault", 160)


def test_input_rule_preserves_width_and_rich_parseability_for_short_and_long_rows():
    from rich.console import Console
    from rich.text import Text
    from cuttlefish_theme.linework import separator
    for width in (0, 1, 7, 79, 200):
        text = Text.from_markup(separator("zivyra", "resting", width))
        assert text.cell_len == max(0, width)
        if width:
            assert all(text.get_style_at_offset(Console(), i).color for i in range(width))
            assert "field_for" in inspect.getsource(__import__("cuttlefish_theme.linework", fromlist=["separator"]))


def test_input_rule_pigments_are_from_palette_and_not_guessed_constants():
    from cuttlefish_theme.linework import separator
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.pattern import render
    from cuttlefish_theme.linework import _pigment_variants
    allowed = {render(allocate("zivyra")).ground_hex}
    for name in dominant_pigments("zivyra"):
        allowed.update(_pigment_variants(name))
    assert set(_colours(separator("zivyra", "resting", 120))) <= allowed
    assert len(set(_colours(separator("zivyra", "resting", 120))) & allowed) >= 3
