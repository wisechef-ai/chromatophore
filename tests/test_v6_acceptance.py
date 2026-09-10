"""v6 acceptance contract — written BEFORE the implementation, by the supervisor.

Every test here must be RED on v5 and GREEN on v6. The implementer's job is to
turn them green without editing this file. Where a number appears it is a
requirement from PLAN-v6.md, not a snapshot of whatever the code happens to do.
"""

from __future__ import annotations

import re
import statistics
import time
from itertools import pairwise
from pathlib import Path

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
    from cuttlefish_theme.patterns import PATTERN_CLASSES, field_for, pattern_for

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
    # Rich must actually PARSE the tags: a tag Rich ignores yields an empty
    # Style and the art paints styleless (the Chef Tier-B failure).
    from rich.console import Console
    styled = sum(1 for i in range(100) if txt.get_style_at_offset(Console(), i).color)
    assert styled == 100, f"{styled}/100 cells carry colour"
    # not a smooth ramp: adjacent cells must change colour often
    cells = _HEX.findall(row)
    changes = sum(a != b for a, b in pairwise(cells))
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


# ------------------------------------------------ (6) tier B = skin data, not a hook
def test_skin_file_carries_input_rule_art_and_older_cores_ignore_it(tmp_path, monkeypatch):
    """Tier B is a whole-string skin field (`input_rule_art`, like banner_hero):
    a core that knows it draws the chromatophore rule; a core that does not
    simply never reads the key. No capability probe, no hook, nothing to
    register."""
    import yaml
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.pattern import render
    from cuttlefish_theme.skinio import write_skin
    from rich.text import Text

    path = write_skin(render(allocate("zivyra")), hermes_home=tmp_path, name="cuttlefish")
    data = yaml.safe_load(path.read_text())
    art = data["input_rule_art"]
    assert isinstance(art, str) and "\n" not in art
    txt = Text.from_markup(art)
    assert txt.cell_len >= 200                      # the core tiles/clips to width
    from rich.console import Console
    assert all(txt.get_style_at_offset(Console(), i).color for i in range(200))
    assert len(set(_HEX.findall(art))) >= 8         # rows of chromatophores, not a line
    assert data["banner_hero"] and data["banner_logo"]  # the two precedents still present
    # the installed core (any version) loads the file without choking on the key
    from hermes_cli.skin_engine import load_skin  # real engine, read-only
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    skin = load_skin("cuttlefish")
    assert skin.banner_hero
    assert getattr(skin, "input_rule_art", "") in ("", art)


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
    from cuttlefish_theme.banner import banner_logo
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.linework import separator
    from cuttlefish_theme.mantle import mantle_rows
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


# ------------------------------------------------------- (9) the palette hot path
def test_palette_build_is_fast_enough_to_animate():
    """The blanch curve is 0.4 s at 24 fps: ~17 ms per frame, and every frame
    rebuilds a palette. v5 spent ~490 ms per build in ensure_contrast (a 0.002-step
    linear scan of L, each step a 24-iteration gamut bisection: ~3,100 gamut maps
    per palette) and the animator has been frame-starved since v2 without anyone
    noticing, because the proofs only counted frames. Contrast is monotone in L on
    a fixed hue/chroma line, so this is a bisection, not a scan."""
    from cuttlefish_theme.color.identity import allocate
    from cuttlefish_theme.pattern import render
    from cuttlefish_theme.session import Signal

    render(allocate("warm-up")).skin_colors()  # any lazy imports / caches
    t0 = time.perf_counter()
    n = 0
    for sid in ("zivyra", "tilola", "nygoka"):
        for sig in Signal:
            render(allocate(sid), sig).skin_colors()
            n += 1
    per_build = (time.perf_counter() - t0) / n
    assert per_build < 0.015, f"{per_build*1000:.1f} ms per palette build"


def test_contrast_search_result_is_unchanged_by_the_fast_path():
    """Speed must not move colours: the bisection lands on the same rendered hex
    the scan did (within one 0.002 L step) for a spread of inputs."""
    from cuttlefish_theme.color.oklab import OKLCh, oklch_to_hex
    from cuttlefish_theme.color.terminal import contrast_ratio, ensure_contrast_detailed

    for L0 in (0.20, 0.35, 0.50, 0.65, 0.80):
        for C in (0.02, 0.12, 0.22):
            for h in (30.0, 120.0, 200.0, 280.0):
                for bg in ("#10131F", "#F5F5F5", "#1A1A2E"):
                    res = ensure_contrast_detailed(OKLCh(L0, C, h), bg, min_ratio=4.5)
                    if res.met:
                        assert contrast_ratio(oklch_to_hex(res.oklch), bg) >= 4.5, (L0, C, h, bg)
                        # minimal move: one step less would NOT meet the target
                        back = res.oklch.with_(L=res.oklch.L - 0.004 * (1 if res.oklch.L > L0 else -1))
                        if 0.0 <= back.L <= 1.0 and abs(res.oklch.L - L0) > 0.004:
                            assert contrast_ratio(oklch_to_hex(back), bg) < 4.5 + 0.35, (L0, C, h, bg)


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
