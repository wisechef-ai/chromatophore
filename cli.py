"""`hermes chromatophore watch|legend|doctor` — the human-facing surfaces.

`watch` is the multiplexer: one line per live session, its identity colour, its
short name, what it needs, and for how long. It is the surface where the whole
design pays off, because it is the only place all sessions are visible at once.

It is strictly READ-ONLY. It reads the session registry and prints; it never writes
a skin, never touches config, and cannot disturb a running session. That is what
makes it safe to run anywhere, including against a production box.
"""

from __future__ import annotations

import os
import sys
import time

from .color.identity import allocate
from .naming import session_name
from .session import Signal, snapshot

__all__ = ["run_watch", "run_legend", "run_doctor"]

_RESET = "\033[0m"


def _truecolor(hex_color: str, *, bg: bool = False) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"\033[{48 if bg else 38};2;{r};{g};{b}m"


def _supports_color() -> bool:
    """Honour NO_COLOR and non-tty output.

    Piping `watch` into a file or a pager must produce clean text; a wall of escape
    codes in a log is worse than no colour at all.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    return os.environ.get("TERM", "") not in ("", "dumb")


def _signal_for(_session_id: str) -> Signal:
    """Resolve a session's signal.

    HONEST LIMITATION: Hermes' session registry records lease information only —
    pid, surface, timestamps — not the agent's activity state. There is no
    supported way for an outside process to read another session's live pet/turn
    state today (`usePet` in the TUI derives it from client-local stores). So every
    session reads as RESTING here, and this function is the single seam where a
    real source plugs in once one exists.

    We would rather show a truthful RESTING than invent a state we cannot observe.
    """
    return Signal.RESTING


def _render_rows(color: bool) -> list[str]:
    sessions = snapshot()
    if not sessions:
        return ["  no live sessions"]

    # Allocate in registry order so colours match what each session actually shows.
    identities: list = []
    rows: list[str] = []
    for sess in sessions:
        ident = allocate(sess.session_id, [i.oklch for i in identities])
        identities.append(ident)

        name = session_name(sess.session_id)
        sig = _signal_for(sess.session_id)
        if sig is Signal.NEEDS_ME:
            status = f"INPUT {sess.age_label}"
        elif sig is Signal.FAULT:
            status = f"ERROR {sess.age_label}"
        else:
            status = ""

        swatch = f"{_truecolor(ident.hex)}\u2588\u2588{_RESET}" if color else "##"
        tint = _truecolor(ident.hex) if color else ""
        reset = _RESET if color else ""
        crowded = " ~" if ident.crowded else "  "

        rows.append(
            f"  {swatch} {tint}{name:<14}{reset}"
            f"{sess.surface:<7}{sess.age_label:>6}{crowded}"
            f"{status}"
        )
    return rows


def run_watch(*, once: bool = False, interval: float = 2.0) -> int:
    color = _supports_color()
    if once:
        print("\n".join(_render_rows(color)))
        return 0

    try:
        while True:
            rows = _render_rows(color)
            # Redraw in place rather than scrolling: this is a dashboard, and a
            # scrolling one is unreadable.
            sys.stdout.write("\033[H\033[2J" if color else "\n")
            print(f"  chromatophore \u2014 {len(rows)} live\n")
            print("\n".join(rows))
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0


def run_legend() -> int:
    """The one-screen teaching surface.

    The language is only real if it can be learned in a minute; if this page needs
    to be longer than a screen, the design is too complicated and should be cut.
    """
    color = _supports_color()

    def swatch(hex_color: str) -> str:
        return f"{_truecolor(hex_color)}\u2588\u2588\u2588{_RESET}" if color else "###"

    print(f"""
  chromatophore \u2014 the language

  Modelled on cuttlefish, which layer two kinds of pattern:

    CHRONIC  lasts minutes to hours   \u2192  who this session is
    ACUTE    lasts seconds            \u2192  what it needs from you

  Every appearance is:  CHRONIC(identity) + ACUTE(signal, only when needed)

  YOUR IDENTITY
    Each session gets its own colour and its own name, allocated so that no two
    sessions visible at the same time look alike. It never changes while the
    session lives \u2014 that is what makes it recognisable.

  THE THREE SIGNALS
    {swatch('#3BA8C4')}  resting      the session's own colour, no badge.
                     Working, thinking, or idle \u2014 all mean "leave it alone",
                     so all look the same. Nothing to do.

    {swatch('#FFC061')}  INPUT 4m     amber. It is blocked ON YOU, and has been
                     for 4 minutes. The number is text because a colour
                     cannot tell you how long.

    {swatch('#D2544F')}  ERROR 2m     red. It failed and cannot continue.
                     The identity colour survives underneath and returns
                     when the fault clears \u2014 exactly as a cuttlefish
                     blanches at a threat and then recovers its pattern.

  That is the entire language: one identity, three signals, one composition rule.

  hermes chromatophore watch    every session at once
""")
    return 0


def run_doctor() -> int:
    """Report what this terminal can actually do, and what we would do about it."""
    color = _supports_color()
    term = os.environ.get("TERM", "(unset)")
    colorterm = os.environ.get("COLORTERM", "(unset)")
    truecolor = colorterm in ("truecolor", "24bit")
    sessions = snapshot()

    print("\n  chromatophore doctor\n")
    print(f"    TERM                {term}")
    print(f"    COLORTERM           {colorterm}")
    print(f"    truecolor           {'yes' if truecolor else 'no (256-colour fallback)'}")
    print(f"    stdout is a tty     {'yes' if sys.stdout.isatty() else 'no'}")
    print(f"    NO_COLOR            {'set (colour disabled)' if os.environ.get('NO_COLOR') else 'unset'}")
    print(f"    colour output       {'enabled' if color else 'disabled'}")
    print(f"    HERMES_HOME         {os.environ.get('HERMES_HOME', '(default ~/.hermes)')}")
    print(f"    live sessions       {len(sessions)}")

    if sessions:
        idents: list = []
        for s in sessions:
            idents.append(allocate(s.session_id, [i.oklch for i in idents]))
        worst = min((i.separation for i in idents if i.separation != float("inf")),
                    default=float("inf"))
        crowded = sum(1 for i in idents if i.crowded)
        shown = "n/a (single session)" if worst == float("inf") else f"{worst:.3f}"
        print(f"    worst separation    {shown}")
        print(f"    crowded identities  {crowded}")
        if crowded:
            print("      note: with this many concurrent sessions some colours sit closer")
            print("            than the comfortable floor. Names remain unique.")
    print()
    return 0
