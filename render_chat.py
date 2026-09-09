"""Render a mock Hermes chat screen from a REAL resolved style dict.

The point of this file: "only 2 stripes change" was a visual claim, and the only
honest way to check a visual claim is to look. This drives the REAL skin engine —
writes the skin, activates it, reads back `get_prompt_toolkit_style_overrides()` —
and paints every style class the CLI actually uses onto a mock chat screen.

Nothing here is drawn from what we THINK the palette is; every colour comes back
out of the engine, so an ignored key shows up as stock gold and is impossible to
miss.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))
import conftest  # noqa: F401,E402

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from cuttlefish_theme.color.identity import allocate  # noqa: E402
from cuttlefish_theme.field import mottle, render_half_blocks  # noqa: E402
from cuttlefish_theme.naming import session_name  # noqa: E402
from cuttlefish_theme.pattern import render  # noqa: E402
from cuttlefish_theme.session import Signal  # noqa: E402
from cuttlefish_theme.skinio import session_skin_name, write_skin  # noqa: E402
from hermes_cli import skin_engine as se  # noqa: E402

CW, CH = 9, 20          # character cell
COLS = 92
FONT = None
for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",):
    if os.path.exists(path):
        FONT = ImageFont.truetype(path, 15)
FONT = FONT or ImageFont.load_default()


def rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def style_of(ov, cls):
    """(fg, bg, bold) for a prompt_toolkit style class, as the engine resolved it."""
    spec = ov.get(cls, "") or ""
    fg, bg, bold = None, None, False
    for tok in spec.split():
        if tok.startswith("bg:#"):
            bg = tok[3:]
        elif tok.startswith("#"):
            fg = tok
        elif tok == "bold":
            bold = True
    return fg, bg, bold


class Screen:
    def __init__(self, cols, rows, base):
        self.img = Image.new("RGB", (cols * CW, rows * CH), rgb(base))
        self.d = ImageDraw.Draw(self.img)
        self.cols, self.rows = cols, rows

    def band(self, row, bg, cols=None):
        self.d.rectangle([0, row * CH, (cols or self.cols) * CW, (row + 1) * CH - 1],
                         fill=rgb(bg))

    def text(self, row, col, s, fg, bg=None):
        if bg:
            self.d.rectangle([col * CW, row * CH, (col + len(s)) * CW, (row + 1) * CH - 1],
                             fill=rgb(bg))
        self.d.text((col * CW + 1, row * CH + 2), s, font=FONT, fill=rgb(fg))

    def pixels(self, row, col, lines):
        """Paint half-block field rows as real 2-pixel-per-cell blocks."""
        import re
        A = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m\x1b\[48;2;(\d+);(\d+);(\d+)m\u2580")
        for i, line in enumerate(lines):
            for j, m in enumerate(A.finditer(line)):
                v = [int(x) for x in m.groups()]
                x = (col + j) * CW
                y = (row + i) * CH
                self.d.rectangle([x, y, x + CW - 1, y + CH // 2 - 1], fill=tuple(v[0:3]))
                self.d.rectangle([x, y + CH // 2, x + CW - 1, y + CH - 1], fill=tuple(v[3:6]))


def paint(ov, palette, label, term_bg="#101014"):
    """A mock chat screen using ONLY colours the engine gave back."""
    sc = Screen(COLS, 26, term_bg)
    g = lambda c, i, d: (style_of(ov, c)[i] or d)  # noqa: E731

    bar_bg = g("status-bar", 1, "#1a1a2e")
    bar_fg = g("status-bar", 0, "#C0C0C0")
    strong = g("status-bar-strong", 0, "#FFD700")
    dimc = g("hint", 0, "#555555")
    textc = g("completion-menu", 0, "#FFF8DC")
    rule = g("input-rule", 0, "#CD7F32")
    title = g("clarify-title", 0, "#FFD700")
    prompt = g("prompt", 0, "#FFD700")
    badge_bg = g("status-bar-session-title", 1, "#FFD700")
    badge_fg = g("status-bar-session-title", 0, "#1a1a2e")
    menu_bg = g("completion-menu", 1, "#1a1a2e")
    menu_cur = g("completion-menu.completion.current", 1, "#333355")
    menu_cur_fg = g("completion-menu.completion.current", 0, "#FFD700")
    meta_bg = g("completion-menu.meta.completion", 1, "#1a1a2e")
    dock_bg = g("subagent-dock", 1, "#1a1a2e")
    dock_head = g("subagent-dock.heading", 0, "#FFD700")
    good = g("status-bar-good", 0, "#8FBC8F")
    warn = g("status-bar-warn", 0, "#FFD700")
    bad = g("status-bar-critical", 0, "#FF6B6B")
    err = style_of(ov, "sudo-title")[0] or "#FF6B6B"
    lbl = g("image-badge", 0, "#DAA520")

    r = 0
    sc.text(r, 1, label, strong); r += 1
    # session pixel field
    sid = palette.session_id
    f = mottle(COLS - 4, 6, seed=abs(hash(sid)) & 0xFFFFFFFF)
    sc.pixels(r, 2, render_half_blocks(f, pigment_hex=palette.identity_hex,
                                       sheen_hex=palette.sheen_hex,
                                       base_hex=palette.ground_hex))
    r += 3
    sc.text(r, 2, "\u2500" * (COLS - 4), rule); r += 1
    sc.text(r, 2, f"{session_name(sid)}  \u00b7  cuttlefish", title)
    sc.text(r, 60, " session ", badge_fg, badge_bg); r += 2

    sc.text(r, 2, "> refactor the auth module", prompt); r += 1
    sc.text(r, 2, "thinking about the token refresh path\u2026", dimc); r += 1
    sc.text(r, 2, "The handler validates the JWT before the DB call, so the", textc); r += 1
    sc.text(r, 2, "pool never sees an unauthenticated request.", textc); r += 1
    sc.text(r, 2, "\u25cf terminal  git status", lbl); r += 1
    sc.text(r, 2, "\u2713 done", good)
    sc.text(r, 22, "\u26a0 rate limited", warn)
    sc.text(r, 46, "\u2717 failed", err); r += 2

    # completion menu
    sc.text(r, 4, " /skills install     ", menu_cur_fg, menu_cur)
    sc.text(r, 25, " install a skill ", dimc, meta_bg); r += 1
    sc.text(r, 4, " /skills list        ", textc, menu_bg)
    sc.text(r, 25, " list skills     ", dimc, meta_bg); r += 1
    sc.text(r, 4, " /model              ", textc, menu_bg)
    sc.text(r, 25, " switch model    ", dimc, meta_bg); r += 2

    # subagent dock
    sc.band(r, dock_bg); sc.text(r, 2, "SUBAGENTS", dock_head); r += 1
    sc.band(r, dock_bg); sc.text(r, 2, "  sa-0  researching palette", bar_fg); r += 2

    sc.text(r, 2, "\u2500" * (COLS - 4), rule); r += 1
    sc.text(r, 2, "> ", prompt); sc.text(r, 4, "type here\u2026", dimc); r += 2

    # status bar
    sc.band(r, bar_bg)
    sc.text(r, 1, "cuttlefish", strong, bar_bg)
    sc.text(r, 13, "claude-opus-5", bar_fg, bar_bg)
    sc.text(r, 29, "ctx 42%", good, bar_bg)
    sc.text(r, 39, "$0.14", warn, bar_bg)
    sc.text(r, 47, "2 errors", bad, bar_bg)
    sc.text(r, 58, "idle 4m", g("status-bar-dim", 0, "#8A7A4A"), bar_bg)
    return sc.img


def shot(session_id, signal, vivid=1.0, label=""):
    ident = allocate(session_id)
    pal = render(ident, signal, age_label="2m")
    write_skin(pal, tint_background=True)
    se.set_active_skin(session_skin_name(session_id))
    ov = se.get_prompt_toolkit_style_overrides()
    return paint(ov, pal, label)


if __name__ == "__main__":
    os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="chatshot-")

    # AFTER: three sessions + a fault
    tiles = [
        shot("sess-alpha", Signal.RESTING, label="session A \u2014 resting"),
        shot("sess-beta", Signal.RESTING, label="session B \u2014 resting"),
        shot("sess-gamma", Signal.FAULT, label="session C \u2014 FAULT (blanched)"),
    ]
    W = max(t.width for t in tiles)
    out = Image.new("RGB", (W, sum(t.height for t in tiles) + 20), (8, 8, 10))
    y = 0
    for t in tiles:
        out.paste(t, (0, y)); y += t.height + 10
    out.save("/tmp/chat_after.png")

    # BEFORE: what v2 actually produced (only the 8 keys it set, 9 of them bogus)
    se.set_active_skin("default")
    d = se.get_active_skin()
    ident = allocate("sess-alpha")
    pal = render(ident, Signal.RESTING)
    ov = dict(se.get_prompt_toolkit_style_overrides())
    # v2 set input_rule/prompt/banner_title only among REAL keys
    for cls in ("input-rule", "clarify-border", "clarify-countdown"):
        ov[cls] = pal.sheen_hex
    ov["prompt"] = pal.sheen_hex
    before = paint(ov, pal, "BEFORE (v2) \u2014 8 keys, 9 of them nonexistent")
    before.save("/tmp/chat_before.png")
    print("wrote /tmp/chat_before.png /tmp/chat_after.png")
