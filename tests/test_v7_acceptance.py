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
    # 0.08-0.20 was read off a 2D Metasepia patch. Re-applied to ONE row it
    # leaves voids the eye reads as emptiness (measured: a 33-cell dark gap on
    # an 80-column rule; Adam: "very scattered with a lot of black spaces").
    # A single row needs ~0.30 to read as skin; the ceiling stays low enough
    # that ground still dominates.
    assert 0.22 <= vivid_share <= 0.38
    assert mean_run(row) >= 2.0
    # No void may swallow the pattern. The bound is structural: with 10-column
    # segments, two picks at opposite ends of adjacent segments sit at most
    # ~18 apart, and measured worst case across every session/signal/width is 13.
    gap = max(len(run) for run in "".join(
        "." if colour == ground else "#" for colour in row).split("#")) if any(
        colour != ground for colour in row) else width
    assert gap <= 14, f"longest dark gap {gap} reads as emptiness"


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


def _vivid_indices(session: str, signal: str, width: int = 200) -> set[int]:
    pairs = CELL.findall(separator(session, signal, width))
    ground = quantize_256(pairs[0][1])
    return {quantize_256(fg) for fg, _ in pairs if quantize_256(fg) != ground}


def _xterm_oklch(index: int):
    from cuttlefish_theme.color.oklab import hex_to_oklch
    from cuttlefish_theme.color.terminal import _index_to_hex
    return hex_to_oklch(_index_to_hex(index))


def test_acute_input_rule_uses_quantised_amber_and_red_without_identity_mix() -> None:
    for session in ("zivyra", "tilola", "chef"):
        resting = _vivid_indices(session, "resting")
        needs_me = _vivid_indices(session, "needs-me")
        fault = _vivid_indices(session, "fault")
        assert needs_me and fault
        assert all(62 <= _xterm_oklch(i).h <= 105 for i in needs_me)
        assert all(5 <= _xterm_oklch(i).h <= 48 for i in fault)
        assert len(needs_me & resting) / len(needs_me) <= 0.20
        assert len(fault & resting) / len(fault) <= 0.20


def test_ten_sessions_have_distinct_vivid_pigment_sets_and_separated_accents() -> None:
    sessions = ("tori-main", "zivyra", "tilola", "chef", "wise", "session-six",
                "mantis", "adam-chef-01", "alpha", "beta")
    sets = [_vivid_indices(session, "resting") for session in sessions]
    assert len({frozenset(colours) for colours in sets}) == len(sessions)
    from cuttlefish_theme.color.oklab import delta_e_ok
    assert min(max(delta_e_ok(_xterm_oklch(a), _xterm_oklch(b))
                   for a in left for b in right)
               for i, left in enumerate(sets) for right in sets[i + 1:]) >= 0.170


def test_rule_preserves_width_and_rich_parseability() -> None:
    from rich.text import Text

    for width in (0, 1, 7, 79, 200):
        text = Text.from_markup(separator("zivyra", "resting", width))
        assert text.cell_len == width
