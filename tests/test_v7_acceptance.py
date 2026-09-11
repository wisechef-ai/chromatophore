"""Measured v7 acceptance contract on xterm-256 quantised output."""
from __future__ import annotations

import inspect
import re
from collections import Counter
from itertools import pairwise

import pytest

from cuttlefish_theme.color.identity import allocate
from cuttlefish_theme.color.terminal import quantize_256
from cuttlefish_theme.linework import separator
from cuttlefish_theme.pattern import render
from cuttlefish_theme.seed import seed_for

CELL = re.compile(r"\[(#[0-9A-Fa-f]{6}) on (#[0-9A-Fa-f]{6})\]")
SESSIONS = ("tori-main", "zivyra", "tilola", "chef", "wise", "session-six")
SIGNALS = ("resting", "needs-me", "fault")
WIDTHS = (40, 80, 200)


def quantised_row(session: str, signal: str, width: int) -> list[int]:
    return [quantize_256(foreground) for foreground, _ in CELL.findall(separator(session, signal, width))]


def mean_run(row: list[int]) -> float:
    runs = 1 + sum(a != b for a, b in pairwise(row))
    return len(row) / runs


@pytest.mark.parametrize("session", SESSIONS)
@pytest.mark.parametrize("signal", SIGNALS)
@pytest.mark.parametrize("width", WIDTHS)
def test_quantised_rule_meets_measured_grammar(session: str, signal: str, width: int) -> None:
    row = quantised_row(session, signal, width)
    ground = quantize_256(render(allocate(session)).ground_hex)
    modal_share = Counter(row).most_common(1)[0][1] / width
    vivid_share = sum(colour != ground for colour in row) / width

    assert len(row) == width
    assert modal_share >= 0.55
    assert 0.08 <= vivid_share <= 0.20
    assert mean_run(row) >= 2.0


def test_fault_is_never_a_flat_line_and_has_sparse_vivid_cells() -> None:
    row = quantised_row("tori-main", "fault", 80)
    ground = quantize_256(render(allocate("tori-main")).ground_hex)
    assert len(set(row)) >= 3
    assert sum(colour != ground for colour in row) / len(row) >= 0.08


def test_input_rule_is_driven_by_body_pattern_field_not_modulo_rainbow() -> None:
    import cuttlefish_theme.linework as linework
    from cuttlefish_theme.patterns import field_for

    assert field_for("zivyra", 120, 1)[0].name in {
        "uniform-fine-mottle", "coarse-mottle", "transverse-stripes-zebra",
        "passing-cloud-bands", "disruptive-patches", "pearl-scatter",
    }
    source = inspect.getsource(linework)
    assert "field_for" in source
    assert "% len(" not in source


def test_sessions_and_signals_remain_distinguishable_and_stable() -> None:
    resting_a = quantised_row("zivyra", "resting", 160)
    assert resting_a == quantised_row("zivyra", "resting", 160)
    assert resting_a != quantised_row("tilola", "resting", 160)
    assert resting_a != quantised_row("zivyra", "needs-me", 160)
    assert resting_a != quantised_row("zivyra", "fault", 160)
    assert seed_for("zivyra") == seed_for("zivyra")


def test_rule_preserves_width_and_rich_parseability() -> None:
    from rich.text import Text

    for width in (0, 1, 7, 79, 200):
        text = Text.from_markup(separator("zivyra", "resting", width))
        assert text.cell_len == width
