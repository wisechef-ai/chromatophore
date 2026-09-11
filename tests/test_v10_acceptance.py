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
