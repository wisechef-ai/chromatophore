"""Rich-safe input-rule chromatophores driven by the body-pattern field.

WHY THIS IS TEXT: a plugin cannot paint arbitrary terminal pixels through semantic
skin keys. Rich markup is ours to emit, so each cell can carry one measured pigment.
The rule therefore samples the same coherent, seeded body grammar as the mantle
instead of cycling a palette by x-coordinate (the old output was terminal tinsel).
"""
from __future__ import annotations

from functools import lru_cache

from .color.identity import allocate
from .color.oklab import OKLCh, oklch_to_hex
from .pattern import render
from .patterns import field_for

# Share of columns that carry a pigment. Real Metasepia display measures 11-16%
# vivid over a 2D patch, but a 2D fraction re-read on ONE row leaves voids the
# eye reads as emptiness: at 0.16 the longest dark gap on an 80-column rule was
# 33 cells. 0.30 restores the density a single row needs to read as skin.
_VIVID_FRACTION = 0.30

# A bar is a LIT strip, not a background behind text, so it ramps bright. These
# are the bands the pre-v11 bars used; only the hue source changed.
_BAR_L = (0.50, 0.80)
_ACUTE_BAR_L = (0.62, 0.78)


def _identity_variants(session_id: str) -> tuple[str, ...]:
    """The bars' ramp, drawn from the SAME four chromatophore classes as the mantle.

    Adam, 2026-09-11: "there should be a general colour palette per session and
    this should reflect that." The bars used to ramp one hue by lightness while
    the mantle painted four hue families, so the two surfaces shared a session
    but not a look. Drawing both from `chromatophore_set` gives one palette per
    session across both surfaces.

    Classes whose hue falls in the ALARM bands are dropped. A session can
    legitimately own hue 99-106, which quantises into the same cube entries as
    the amber alert (#AF8700 at hue 88) — measured, one session's resting bar
    shared a quarter of its palette with the alarm. The mantle can afford that
    ambiguity because an alarm repaints the whole background; a one-row bar
    cannot, so it gives up a hue rather than the signal.
    """
    from .mantle import chromatophore_set
    from .session import Signal
    classes = chromatophore_set(allocate(session_id), Signal.RESTING)
    calm = [c for c in classes if not _reserved_for_alarm(c.oklch.h)]
    return _class_ramp(calm or list(classes), _BAR_L)


def _reserved_for_alarm(hue: float) -> bool:
    """Hues the acute bars own, widened for the quantiser's reach."""
    return 55 <= hue <= 115 or hue >= 350 or hue <= 50


def _class_ramp(classes, lightness: tuple[float, float]) -> tuple[str, ...]:
    """16 steps across the class set, darkest to brightest.

    Lightness is re-spread across `lightness` while each step keeps ITS OWN
    class's hue and chroma. The two surfaces share a palette but not a
    brightness: the mantle sits BEHIND TEXT and must stay dark, whereas a bar is
    a lit strip and should read bright.

    Hue is NOT interpolated between classes. Blending a violet class into an
    amber one walks the whole colour circle and lands the resting bar on the
    alarm hues — measured, a resting bar hit 14 distinct hues and collided with
    the amber alarm on half its palette. The animal shows its classes side by
    side; it does not cross-fade them.
    """
    ordered = sorted(classes, key=lambda c: c.oklch.L)
    floor, ceiling = lightness
    steps = []
    for index in range(16):
        fraction = index / 15
        source = ordered[min(len(ordered) - 1, int(fraction * len(ordered)))].oklch
        steps.append(oklch_to_hex(source.with_(L=floor + (ceiling - floor) * fraction)))
    return tuple(steps)


def _oklch_variants(base: OKLCh) -> tuple[str, ...]:
    return tuple(oklch_to_hex(base.with_(L=0.50 + 0.30 * fraction))
                 for fraction in (i / 15 for i in range(16)))


def _acute_variants(signal: str) -> tuple[str, ...]:
    """The bars under an acute signal — the SAME fixed classes the mantle uses.

    Sharing `chromatophore_set` means the bars and the background change together
    and change hard: a session's own hues vanish and the fixed amber or red takes
    the whole surface, identically in every terminal.

    The cool iridophore and the pale leucophore are both dropped here. On the
    mantle they are the backdrop the pigments sit above, but a one-row bar has no
    room for a backdrop: ramping through the iridophore dragged the amber alarm
    to hue 205 (teal), and the leucophore is a near-grey pearl (C 0.03) whose
    ends quantise to C 0.000 — a grey bar where an alarm should be. `family` is
    exactly the channel naming which classes carry the state, so the bar keeps
    only those and ramps lightness across them.
    """
    from .mantle import chromatophore_set
    from .session import Signal
    collapsed = Signal.FAULT if signal in ("fault", "error") else Signal.NEEDS_ME
    classes = chromatophore_set(allocate("acute"), collapsed)
    return _class_ramp([c for c in classes if c.family in ("amber", "red")], _ACUTE_BAR_L)


def _signal_time(signal: str) -> float:
    if signal in ("needs-me", "needs_me"):
        return 0.35
    if signal in ("fault", "error"):
        return 0.70
    return 0.0


@lru_cache(maxsize=32)
def _body_field(session_id: str, signal: str, width: int, height: int):
    """The session's body patch, built once and shared by every row.

    Building a 64-row field costs ~45ms; the transcript asks for one row per
    printed line, so rebuilding per row_key put that on every line of output.
    """
    return field_for(session_id, width, height, t=_signal_time(signal))[1]


@lru_cache(maxsize=512)
def cells(session_id: str, signal: str, width: int,
          row_key: int | None = None) -> tuple[tuple[str, str, str], ...]:
    """(fg, bg, glyph) per column — the one source every formatter renders from.

    ``row_key`` selects a stable body-field row for transcript painting.  The
    default keeps the original one-row projection used by the input rule.
    """
    width = max(0, int(width))
    if not width:
        return ()

    # A one-cell-high rule is a projection of a small body patch: take the local
    # maximum, then pick by rank per 10-column segment. Rank (not an absolute
    # threshold) gives every seed the same budget, including degenerate fields.
    # Segments (not a global top-N) stop the 2D field's clustering from leaving
    # voids — globally it lit 3 clumps around a 33-cell dead gap.
    field = _body_field(session_id, signal, width, 64 if row_key is not None else 3)
    if row_key is None:
        values = [max(field.get(x, y) for y in range(field.height)) for x in range(width)]
    else:
        values = [field.get(x, int(row_key) % field.height) for x in range(width)]
    hottest = lambda columns, n: sorted(columns, key=lambda x: (values[x], x), reverse=True)[:n]
    segment = 10
    vivid = {x for start in range(0, width, segment)
             for x in hottest(range(start, min(width, start + segment)),
                              max(1, round(_VIVID_FRACTION * segment)))}

    ground = render(allocate(session_id)).ground_hex
    variants = (_acute_variants(signal) if signal in ("fault", "error", "needs-me", "needs_me")
                else _identity_variants(session_id))
    rank = {x: i for i, x in enumerate(hottest(vivid, len(vivid)))}
    out: list[tuple[str, str, str]] = []
    for x, value in enumerate(values):
        if x not in vivid:
            out.append((ground, ground, "─"))
        else:
            # Brightest cell gets the palest pigment — retracted skin reveals
            # the layer beneath, it does not simply go dark.
            step = int((rank[x] + 1) * len(variants) / len(vivid))
            out.append((variants[min(len(variants) - 1, step)], ground,
                        "━" if value >= 0.70 else "─"))
    return tuple(out)


def separator_markup(session_id: str, signal: str, width: int) -> str:
    return "".join(f"[{fg} on {bg}]{glyph}[/]"
                   for fg, bg, glyph in cells(session_id, signal, width))


def separator(session_id: str, signal: str, width: int) -> str:
    return separator_markup(session_id, str(signal), int(width))


__all__ = ["cells", "separator", "separator_markup"]
