"""v6 acceptance contract — written BEFORE the implementation, by the supervisor.

Every test here must be RED on v5 and GREEN on v6. The implementer's job is to
turn them green without editing this file. Where a number appears it is a
requirement from PLAN-v6.md, not a snapshot of whatever the code happens to do.
"""

from __future__ import annotations

import math
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.color.terminal import contrast_ratio
from cuttlefish_theme.seed import seed_for

_ROOT = Path(__file__).resolve().parents[1]
_IDS = [f"session-{i:03d}" for i in range(200)]
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


# --------------------------------------------------------------------- (1) patterns
def _autocorr(vals, width, height, dx, dy):
    """Lag-(dx,dy) autocorrelation of a row-major grid."""
    mean = statistics.fmean(vals)
    var = sum((v - mean) ** 2 for v in vals) or 1e-9
    acc = 0.0
    for y in range(height - dy):
        for x in range(width - dx):
            acc += (vals[y * width + x] - mean) * (vals[(y + dy) * width + x + dx] - mean)
    return acc / var


def _grid(field):
    return [field.get(x, y) for y in range(field.height) for x in range(field.width)]


def test_patterns_six_classes_are_all_reachable_and_stable():
    from cuttlefish_theme.patterns import PATTERN_CLASSES, pattern_for, field_for

    assert len(PATTERN_CLASSES) >= 6
    names = {pattern_for(sid).name for sid in _IDS}
    assert len(names) >= 6, names
    # every class actually gets used, none is a dead entry
    assert names >= {cls().name for cls in PATTERN_CLASSES}
    a = _grid(field_for("zivyra", 30, 30)[1])
    b = _grid(field_for("zivyra", 30, 30)[1])
    assert a == b
    assert _grid(field_for("tilola", 30, 30)[1]) != a


def test_patterns_are_statistically_distinct_body_patterns():
    from cuttlefish_theme import patterns as P

    W = H = 30
    seed = seed_for("acceptance")
    stripes = _grid(P.TransverseStripes().field(W, H, seed=seed))
    # transverse stripes: strongly correlated along a row, weakly down a column
    along = _autocorr(stripes, W, H, 1, 0)
    across = _autocorr(stripes, W, H, 0, 1)
    assert along > across + 0.25, (along, across)

    pearl = _grid(P.PearlScatter().field(W, H, seed=seed))
    bright = sum(v > 0.8 for v in pearl) / len(pearl)
    assert 0.08 <= bright <= 0.18, bright

    fine = _grid(P.UniformFineMottle().field(W, H, seed=seed))
    coarse = _grid(P.CoarseMottle().field(W, H, seed=seed))
    # coarse patches: neighbours agree far more than in fine grain
    assert _autocorr(coarse, W, H, 2, 0) > _autocorr(fine, W, H, 2, 0) + 0.15

    disruptive = _grid(P.DisruptivePatches().field(W, H, seed=seed))
    # disruptive = bimodal: most cells at the extremes, few in the middle
    mid = sum(0.35 < v < 0.65 for v in disruptive) / len(disruptive)
    assert mid < 0.25, mid

    # no pattern is a flat field or a wash
    for cls in P.PATTERN_CLASSES:
        g = _grid(cls().field(W, H, seed=seed))
        assert statistics.pstdev(g) > 0.12, cls.__name__
        assert 0.02 < statistics.fmean(g) < 0.75, cls.__name__


def test_patterns_use_coherent_noise_not_random():
    """A field seeded from the repo's value-noise is smooth at lag 1 in at
    least one axis; white noise is ~0 in both."""
    from cuttlefish_theme.patterns import PATTERN_CLASSES

    for cls in PATTERN_CLASSES:
        g = _grid(cls().field(30, 30, seed=7))
        assert max(_autocorr(g, 30, 30, 1, 0), _autocorr(g, 30, 30, 0, 1)) > 0.2, cls.__name__


# ---------------------------------------------------------------------- (2) palette
def test_ground_is_one_navy_for_every_session():
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.pattern import render

    grounds = {render(allocate(sid)).ground_hex for sid in _IDS[:40]}
    assert len(grounds) == 1, grounds
    g = hex_to_oklch(grounds.pop())
    assert 0.14 <= g.L <= 0.17, g
    assert g.C <= 0.02, g
    assert 240 <= g.h <= 300, g  # navy/indigo


def test_session_has_two_or_three_dominant_neon_pigments_placed_where_srgb_holds_chroma():
    from cuttlefish_theme.palette import PIGMENTS, dominant_pigments, pigment_hex

    assert {"cyan", "teal", "electric-blue", "violet", "magenta", "amber", "orange", "pearl-white"} <= set(PIGMENTS)
    counts = set()
    seen = set()
    for sid in _IDS:
        names = dominant_pigments(sid)
        assert dominant_pigments(sid) == names  # stable
        counts.add(len(names))
        seen.update(names)
        assert len(set(names)) == len(names)
    assert counts <= {2, 3} and 2 in counts
    assert len(seen) >= 6  # the weighting actually spreads sessions across hues
    for name in PIGMENTS:
        if name == "pearl-white":
            continue
        c = hex_to_oklch(pigment_hex(name))
        assert c.C >= 0.12, (name, c)          # vivid, not pastel
        assert 0.50 <= c.L <= 0.72, (name, c)  # where sRGB actually holds it
    assert hex_to_oklch(pigment_hex("pearl-white")).L >= 0.85


# ---------------------------------------------------------------------- (3) mantle
def test_hero_is_exactly_30x15_and_carries_session_pigments():
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.mantle import mantle_rows
    from cuttlefish_theme.pattern import render
    from rich.text import Text

    p = render(allocate("zivyra"))
    art = mantle_rows("zivyra", p.identity_hex, p.sheen_hex, p.ground_hex)
    rows = art.split("\n")
    assert len(rows) == 15
    for r in rows:
        assert Text.from_markup(r).cell_len == 30, Text.from_markup(r).cell_len
    assert len(set(_HEX.findall(art))) >= 12


# ------------------------------------------------------------------ (4) banner_logo
def test_logo_is_per_cell_chromatophores_not_a_row_gradient():
    from cuttlefish_theme.banner import banner_logo

    logo = banner_logo("#20C9B8", session_id="zivyra")
    rows = logo.split("\n")
    assert len(rows) >= 6
    # a gradient has one colour per row; chromatophores have several
    for r in rows[:6]:
        assert len(set(_HEX.findall(r))) >= 3, r[:80]
    assert banner_logo("#20C9B8", session_id="zivyra") == logo
    assert banner_logo("#20C9B8", session_id="tilola") != logo
    # letterforms survive re-inking
    from rich.text import Text
    assert Text.from_markup(rows[0]).plain.startswith("██╗  ██╗")


# --------------------------------------------------------- (5) separator + hook
def test_separator_is_a_row_of_chromatophores_of_terminal_width():
    from cuttlefish_theme.linework import separator
    from rich.text import Text

    row = separator("zivyra", "resting", 100)
    txt = Text.from_markup(row)
    assert txt.cell_len == 100
    assert len(set(_HEX.findall(row))) >= 8
    # not a smooth ramp: adjacent cells must change colour often
    cells = _HEX.findall(row)
    changes = sum(a != b for a, b in zip(cells, cells[1:]))
    assert changes >= 30, changes
    assert separator("zivyra", "resting", 100) == row
    assert separator("zivyra", "needs-me", 100) != row


def test_stream_end_hook_prints_through_rich_only_on_a_tty(monkeypatch, capsys):
    from cuttlefish_theme import plugin

    printed = []

    class FakeConsole:
        is_terminal = True
        no_color = False
        width = 64
        def print(self, *a, **k):
            printed.append((a, k))

    monkeypatch.setattr(plugin, "_console", lambda: FakeConsole())
    # exact payload the core sends (agent/stream_delivery.py::_emit_stream_end)
    plugin.on_stream_end(turn_id="t1", iteration=1, session_id="zivyra", model="m",
                         provider="p", surface="cli", final_text="hi", finished=True, error=None)
    assert len(printed) == 1
    assert "\x1b[" not in capsys.readouterr().out  # never raw ANSI on stdout

    printed.clear()
    class NoTTY(FakeConsole):
        is_terminal = False
    monkeypatch.setattr(plugin, "_console", lambda: NoTTY())
    plugin.on_stream_end(session_id="zivyra", surface="cli", finished=True, error=None)
    assert printed == []

    printed.clear()
    monkeypatch.setattr(plugin, "_console", lambda: FakeConsole())
    plugin.on_stream_end(session_id="zivyra", surface="discord", finished=True, error=None)
    assert printed == []  # only the classic CLI has a screen


# ----------------------------------------------------------------- (6) chrome tier B
def test_chrome_renderer_contract_and_tier_a_fallback():
    from cuttlefish_theme import plugin
    from cuttlefish_theme.chrome import chrome_renderer

    for surface in ("input_rule_top", "input_rule_bot", "status_bar_bg"):
        frags = chrome_renderer(surface, 80, {"session_id": "zivyra", "skin": "cuttlefish"})
        assert frags is not None
        assert sum(len(t) for _s, t in frags) == 80
        styles = {s for s, _t in frags}
        assert len(styles) >= 8
        assert all(re.search(r"bg:#[0-9A-Fa-f]{6}", s) for s in styles)
    assert chrome_renderer("input_rule_top", 80, {"session_id": None}) is None
    assert chrome_renderer("unknown", 80, {"session_id": "x"}) is None

    class TierACtx:
        def __init__(self):
            self.hooks = []
        def register_hook(self, name, fn):
            self.hooks.append(name)
        def register_cli_command(self, *a, **k):
            pass
        def get_config(self, k, d=None):
            return d

    class TierBCtx(TierACtx):
        def __init__(self):
            super().__init__()
            self.renderer = None
        def register_chrome_renderer(self, fn):
            self.renderer = fn

    a, b = TierACtx(), TierBCtx()
    plugin.register(a)
    plugin.register(b)
    assert b.renderer is chrome_renderer
    assert set(a.hooks) == set(b.hooks)  # tier A loses nothing, gains nothing


# ---------------------------------------------------------------------- (7) contrast
def test_every_text_colour_reads_on_its_surface():
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.pattern import render
    from cuttlefish_theme.session import Signal

    text_on_status = ("status_bar_text", "status_bar_strong", "status_bar_good",
                      "status_bar_warn", "status_bar_bad", "status_bar_critical")
    text_on_ground = ("banner_text", "banner_title", "ui_primary", "ui_accent",
                      "ui_error", "ui_warning", "ui_success", "session_label")
    for sid in _IDS[:30]:
        for sig in Signal:
            colors = render(allocate(sid), sig).skin_colors()
            for k in text_on_status:
                if k in colors:
                    assert contrast_ratio(colors[k], colors["status_bar_bg"]) >= 4.5, (sid, sig, k)
            for k in text_on_ground:
                if k in colors:
                    assert contrast_ratio(colors[k], colors["background"]) >= 4.5, (sid, sig, k)


# ------------------------------------------------------------------- (8) performance
def test_render_cost_is_within_budget_and_cached():
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.mantle import mantle_rows
    from cuttlefish_theme.banner import banner_logo
    from cuttlefish_theme.linework import separator
    from cuttlefish_theme.pattern import render

    p = render(allocate("perf-session"))
    t0 = time.perf_counter()
    mantle_rows("perf-session", p.identity_hex, p.sheen_hex, p.ground_hex)
    banner_logo(p.identity_hex, session_id="perf-session")
    cold = time.perf_counter() - t0
    t0 = time.perf_counter()
    mantle_rows("perf-session", p.identity_hex, p.sheen_hex, p.ground_hex)
    banner_logo(p.identity_hex, session_id="perf-session")
    warm = time.perf_counter() - t0
    assert cold < 0.25, cold          # generous: CI box
    assert warm < cold / 4, (cold, warm)  # cached
    t0 = time.perf_counter()
    separator("perf-session", "resting", 200)
    assert time.perf_counter() - t0 < 0.03


# ------------------------------------------------------------------ (10) metadata
def test_release_metadata():
    import yaml
    meta = yaml.safe_load((_ROOT / "plugin.yaml").read_text())
    assert meta["version"] == "0.5.0"
    changelog = (_ROOT / "CHANGELOG.md").read_text()
    assert "0.5.0" in changelog
    readme = (_ROOT / "README.md").read_text()
    assert "scrollback" in readme.lower()  # the VTE honesty statement
    for name in ("fine mottle", "coarse mottle", "stripes", "passing cloud", "disruptive", "pearl"):
        assert name in readme.lower(), name
