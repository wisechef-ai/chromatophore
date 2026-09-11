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
