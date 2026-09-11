"""v10 chromatophore class contracts."""
from __future__ import annotations

from cuttlefish_theme.color.identity import allocate
from cuttlefish_theme.color.oklab import hex_to_oklch
from cuttlefish_theme.mantle import chromatophore_set, mantle_rows
from cuttlefish_theme.pattern import render, ACUTE_FAULT
from cuttlefish_theme.session import Signal


def test_resting_set_has_two_dark_classes_iridophore_and_leucophore():
    classes = chromatophore_set(render(allocate("20260911_121040_cd024d")))
    assert [c.name for c in classes] == ["pigment-a", "pigment-b", "iridophore", "leucophore"]
    assert classes[0].oklch.L <= .45 and classes[1].oklch.L <= .45
    assert classes[0].family != classes[1].family
    assert classes[2].family == "cool"
    assert classes[3].oklch.L >= .85


def test_acute_sets_are_fixed_and_signal_specific():
    identity = render(allocate("20260911_121040_cd024d"))
    needs = chromatophore_set(identity, Signal.NEEDS_ME)
    fault = chromatophore_set(identity, Signal.FAULT)
    assert tuple(c.oklch for c in needs) == tuple(c.oklch for c in chromatophore_set(render(allocate("other")), Signal.NEEDS_ME))
    assert tuple(c.oklch for c in fault) == tuple(c.oklch for c in chromatophore_set(render(allocate("other")), Signal.FAULT))
    assert needs[0].family == needs[1].family == "amber"
    assert fault[0].family == fault[1].family == "red"


def test_rendered_classes_are_multi_hued_and_acute_dominance_changes():
    p = render(allocate("20260911_121040_cd024d"))
    calm = mantle_rows(p.session_id, p.identity_hex, p.sheen_hex, p.ground_hex, markup=False)
    hot = mantle_rows(p.session_id, p.identity_hex, p.sheen_hex, p.ground_hex, acute_hex=render(allocate("x"), Signal.FAULT).acute_hex, markup=False)
    assert calm != hot
    assert len({round(hex_to_oklch(c).h / 30) for c in _colours(calm) if hex_to_oklch(c).C > .03}) >= 3


def _colours(text):
    import re
    return [f"#{int(r):02x}{int(g):02x}{int(b):02x}" for r, g, b in re.findall(r"\x1b\[38;2;(\d+);(\d+);(\d+)m", text)]


def test_acute_sets_survive_quantisation_as_distinct_readable_hues():
    """An alarm must reach the terminal as two distinct classes of the RIGHT hue.

    Both needs_me pigments once quantised onto #5F5F00 -- a single olive at hue
    110, which reads green and says the opposite of "needs you". The design
    values were fine; only the quantised output showed it.
    """
    from cuttlefish_theme.chrome import _mantle_classes
    from cuttlefish_theme.color.oklab import hex_to_oklch

    for signal, low, high in (("needs_me", 40, 115), ("fault", 340, 45)):
        pigments = _mantle_classes("any-session", signal)[:2]
        assert len(set(pigments)) == 2, f"{signal} pigments collapsed to {pigments}"
        for pigment in pigments:
            hue = hex_to_oklch(pigment).h
            warm = low <= hue <= high if low < high else hue >= low or hue <= high
            assert warm, f"{signal} pigment {pigment} sits at hue {hue:.0f}"


def test_every_acute_class_stays_readable_behind_body_text():
    from cuttlefish_theme.chrome import _mantle_classes
    from cuttlefish_theme.color.terminal import contrast_ratio

    for signal in ("resting", "needs_me", "fault"):
        for pigment in _mantle_classes("any-session", signal):
            assert contrast_ratio("#E8E6EA", pigment) >= 4.5, (signal, pigment)


_CORPUS = tuple(f"s{n}" for n in range(200))


def test_resting_classes_stay_four_distinct_colours_across_many_sessions():
    """One session id is not coverage.

    The suite asserted readability for a single id and slept through 77 of 1000
    sessions whose classes quantised onto a shared cube entry — s10 rendered
    three colours where four were designed. A collapsed class is a session that
    looks like another session.
    """
    from cuttlefish_theme.chrome import _mantle_classes

    collapsed = [sid for sid in _CORPUS if len(set(_mantle_classes(sid, "resting"))) < 4]
    assert not collapsed, f"{len(collapsed)} sessions lost a class, e.g. {collapsed[:3]}"


def test_every_visible_background_is_readable_in_every_signal():
    from cuttlefish_theme.chrome import _mantle_classes
    from cuttlefish_theme.color.terminal import contrast_ratio

    for sid in _CORPUS:
        for signal in ("resting", "needs_me", "fault"):
            for pigment in _mantle_classes(sid, signal):
                ratio = contrast_ratio("#E8E6EA", pigment)
                assert ratio >= 4.5, f"{sid}/{signal} {pigment} at {ratio:.2f}:1"


def test_acute_status_bar_carries_a_foreground_it_is_readable_with():
    """The bar paints OVER fragments that bring their own colours.

    Emitting only a background left prompt_toolkit using the stock #C0C0C0 text,
    which measured 1.01:1 on quantised amber: the status bar went blank exactly
    when it had something to say. The plugin owns both halves of the pair.
    """
    import re

    from cuttlefish_theme.chrome import chrome_renderer
    from cuttlefish_theme.color.terminal import _index_to_hex, contrast_ratio, quantize_256

    for state in ("waiting", "failed"):
        fragments = chrome_renderer("status_bar_bg", 40, {"session_id": "x", "pet_state": state})
        style = fragments[0][0]
        background = re.search(r"bg:(#[0-9A-Fa-f]{6})", style).group(1)
        foreground = [token for token in style.split() if not token.startswith("bg:")]
        assert foreground, f"{state} emitted a background with no foreground: {style!r}"
        rendered = _index_to_hex(quantize_256(background))
        ratio = contrast_ratio(foreground[0], rendered)
        assert ratio >= 4.5, f"{state}: {foreground[0]} on {rendered} is {ratio:.2f}:1"


def test_acute_status_bar_is_the_same_alarm_in_every_session():
    from cuttlefish_theme.chrome import chrome_renderer

    for state in ("waiting", "failed"):
        styles = {chrome_renderer("status_bar_bg", 40, {"session_id": sid, "pet_state": state})[0][0]
                  for sid in _CORPUS[:20]}
        assert len(styles) == 1, f"{state} alarm differs between sessions: {styles}"


def test_bars_and_mantle_are_drawn_from_one_session_palette():
    """Adam: "there should be a general colour palette per session."

    The bars once ramped a single hue by lightness while the mantle painted four
    hue families, so the two surfaces shared a session but looked unrelated. Both
    now read `chromatophore_set`, so every bar colour traces to a class the
    mantle also uses. Exact hue equality is NOT the contract — the bars drop
    alarm-band classes — but a bar hue must never be foreign to the session.
    """
    from cuttlefish_theme.linework import _identity_variants
    from cuttlefish_theme.chrome import _mantle_classes
    from cuttlefish_theme.color.oklab import hex_to_oklch

    for session in ("chef", "tori-main", "zivyra", "koralen"):
        mantle = {round(hex_to_oklch(c).h / 30) * 30 for c in _mantle_classes(session, "resting")}
        bar = {round(hex_to_oklch(c).h / 30) * 30 for c in _identity_variants(session)}
        assert bar, f"{session} produced no bar palette"
        assert bar.intersection(mantle), (
            f"{session}: bar hues {sorted(bar)} share nothing with mantle {sorted(mantle)}")


def test_resting_bars_never_wear_the_alarm_colours():
    """A one-row bar has no room for ambiguity with the alert.

    Sessions legitimately own hues near 100, which quantise onto the same cube
    entries as the amber alarm (#AF8700). On the mantle that is tolerable — an
    alarm repaints the whole background — but on a thin bar it makes "needs you"
    unreadable, so alarm-band classes are dropped from the resting ramp.
    """
    from cuttlefish_theme.linework import _acute_variants, _identity_variants
    from cuttlefish_theme.color.terminal import quantize_256

    for signal in ("needs_me", "fault"):
        alarm = {quantize_256(c) for c in _acute_variants(signal)}
        for session in ("chef", "tori-main", "zivyra", "koralen", "tilola"):
            resting = {quantize_256(c) for c in _identity_variants(session)}
            shared = resting.intersection(alarm)
            assert not shared, f"{session} resting bar wears {signal} colours {shared}"


def test_the_acute_bar_is_bright_and_carries_white_text():
    """Adam: "the bars should be bright and the text is white."

    Pure white on a bright bar is not reachable at AA — #FFAF00 carries white at
    1.84:1 — so the bar takes the brightest cube entry that still holds white.
    """
    import re

    from cuttlefish_theme.chrome import chrome_renderer
    from cuttlefish_theme.color.oklab import hex_to_oklch
    from cuttlefish_theme.color.terminal import _index_to_hex, contrast_ratio, quantize_256

    for state in ("waiting", "failed"):
        style = chrome_renderer("status_bar_bg", 40, {"session_id": "x", "pet_state": state})[0][0]
        background = re.search(r"bg:(#[0-9A-Fa-f]{6})", style).group(1)
        foreground = [token for token in style.split() if not token.startswith("bg:")]
        assert foreground == ["#FFFFFF"], f"{state} text is {foreground}, not white"
        rendered = _index_to_hex(quantize_256(background))
        assert hex_to_oklch(rendered).L >= 0.50, f"{state} bar L={hex_to_oklch(rendered).L:.2f} is not bright"
        assert contrast_ratio("#FFFFFF", rendered) >= 4.5
