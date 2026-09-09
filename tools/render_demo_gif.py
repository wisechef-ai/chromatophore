"""Render the README demo GIF: what the theme actually does, in ~12 seconds.

Everything drawn here comes out of the REAL skin engine — the frames are built by
resolving `get_prompt_toolkit_style_overrides()` for each palette, exactly as a
running CLI does. Nothing is mocked up in a design tool, so the GIF cannot flatter
the implementation.

The story it tells, in order:
  1. three sessions side by side, each unmistakably its own skin
  2. a fault arrives  -> BLANCH   (0.4s, fast, synchronous)
  3. the fault clears -> RECOVER  (2.4s, slower, staggered) and the identity
     comes back exactly

which is the whole product: identity you can see, state you can see, and the
measured biology in how it moves.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))
import conftest  # noqa: F401,E402  # side-effect: binds the cuttlefish_theme package

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from cuttlefish_theme.color.identity import allocate  # noqa: E402
from cuttlefish_theme.field import mottle, render_half_blocks  # noqa: E402
from cuttlefish_theme.morph import BLANCH, RECOVER, morph  # noqa: E402
from cuttlefish_theme.naming import session_name  # noqa: E402
from cuttlefish_theme.pattern import render  # noqa: E402
from cuttlefish_theme.session import Signal  # noqa: E402
from hermes_cli import skin_engine as se  # noqa: E402

CW, CH = 8, 17
COLS = 78
ROWS = 22
SCALE = 1
ANSI = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m\x1b\[48;2;(\d+);(\d+);(\d+)m\u2580")

FONT = ImageFont.load_default()
FONT_B = FONT
for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",):
    if os.path.exists(p):
        FONT = ImageFont.truetype(p, 13)
        FONT_B = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 13) \
            if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf") else FONT


def rgb(h):
    h = (h or "#000000").lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def resolve(colors):
    """Push a colour dict through the REAL engine and get style classes back."""
    import pathlib
    d = pathlib.Path(os.environ["HERMES_HOME"]) / "skins"
    d.mkdir(parents=True, exist_ok=True)
    body = ["name: gifskin", "colors:"]
    for k, v in sorted(colors.items()):
        body.append(f'  {k}: "{v}"')
    (d / "gifskin.yaml").write_text("\n".join(body) + "\n")
    se.set_active_skin("gifskin")
    return se.get_prompt_toolkit_style_overrides()


def sty(ov, cls, i, default):
    spec = ov.get(cls, "") or ""
    fg = bg = None
    for tok in spec.split():
        if tok.startswith("bg:#"):
            bg = tok[3:]
        elif tok.startswith("#"):
            fg = tok
    return (fg if i == 0 else bg) or default


class Panel:
    """One terminal, drawn from resolved style classes."""

    def __init__(self, cols, rows, bg):
        self.img = Image.new("RGB", (cols * CW, rows * CH), rgb(bg))
        self.d = ImageDraw.Draw(self.img)
        self.cols = cols

    def text(self, r, c, s, fg, bg=None, bold=False):
        if bg:
            self.d.rectangle([c * CW, r * CH, (c + len(s)) * CW, (r + 1) * CH - 1], fill=rgb(bg))
        self.d.text((c * CW + 1, r * CH + 2), s, font=FONT_B if bold else FONT, fill=rgb(fg))

    def band(self, r, bg):
        self.d.rectangle([0, r * CH, self.cols * CW, (r + 1) * CH - 1], fill=rgb(bg))

    def pixels(self, r, c, lines):
        for i, line in enumerate(lines):
            for j, m in enumerate(ANSI.finditer(line)):
                v = [int(x) for x in m.groups()]
                x, y = (c + j) * CW, (r + i) * CH
                self.d.rectangle([x, y, x + CW - 1, y + CH // 2 - 1], fill=tuple(v[0:3]))
                self.d.rectangle([x, y + CH // 2, x + CW - 1, y + CH - 1], fill=tuple(v[3:6]))


def panel(colors, pal, caption, label_state):
    ov = resolve(colors)
    bg = colors.get("background", "#101014")
    p = Panel(COLS, ROWS, bg)

    bar_bg = sty(ov, "status-bar", 1, "#1a1a2e")
    bar_fg = sty(ov, "status-bar", 0, "#C0C0C0")
    strong = sty(ov, "status-bar-strong", 0, "#FFD700")
    dim = sty(ov, "hint", 0, "#555555")
    body = sty(ov, "completion-menu", 0, "#FFF8DC")
    rule = sty(ov, "input-rule", 0, "#CD7F32")
    title = sty(ov, "clarify-title", 0, "#FFD700")
    prompt = sty(ov, "prompt", 0, "#FFD700")
    badge_bg = sty(ov, "status-bar-session-title", 1, "#FFD700")
    badge_fg = sty(ov, "status-bar-session-title", 0, "#1a1a2e")
    menu_bg = sty(ov, "completion-menu", 1, "#1a1a2e")
    menu_cur = sty(ov, "completion-menu.completion.current", 1, "#333355")
    menu_cur_fg = sty(ov, "completion-menu.completion.current", 0, "#FFD700")
    dock_bg = sty(ov, "subagent-dock", 1, "#1a1a2e")
    dock_h = sty(ov, "subagent-dock.heading", 0, "#FFD700")
    good = sty(ov, "status-bar-good", 0, "#8FBC8F")
    warn = sty(ov, "status-bar-warn", 0, "#FFD700")
    crit = sty(ov, "status-bar-critical", 0, "#FF6B6B")
    lbl = sty(ov, "image-badge", 0, "#DAA520")

    r = 0
    sid = pal.session_id
    f = mottle(COLS - 4, 6, seed=abs(hash(sid)) & 0xFFFFFFFF)
    p.pixels(r, 2, render_half_blocks(f, pigment_hex=pal.identity_hex,
                                      sheen_hex=pal.sheen_hex,
                                      base_hex=colors.get("background", "#101014")))
    r += 3
    p.text(r, 2, "\u2500" * (COLS - 4), rule); r += 1
    p.text(r, 2, f"{session_name(sid)}  \u00b7  cuttlefish", title, bold=True)
    p.text(r, 52, f" {label_state} ", badge_fg, badge_bg, bold=True); r += 2
    p.text(r, 2, "> refactor the auth module", prompt); r += 1
    p.text(r, 2, "thinking about the token refresh path\u2026", dim); r += 1
    p.text(r, 2, "The handler validates the JWT before the DB call, so", body); r += 1
    p.text(r, 2, "the pool never sees an unauthenticated request.", body); r += 1
    p.text(r, 2, "\u25cf terminal  git status", lbl); r += 1
    p.text(r, 2, "\u2713 done", good)
    p.text(r, 16, "\u26a0 rate limited", warn)
    p.text(r, 38, "\u2717 failed", crit); r += 2
    p.text(r, 4, " /skills install    ", menu_cur_fg, menu_cur); r += 1
    p.text(r, 4, " /skills list       ", body, menu_bg); r += 1
    p.text(r, 4, " /model             ", body, menu_bg); r += 2
    p.band(r, dock_bg); p.text(r, 2, "SUBAGENTS", dock_h, dock_bg, bold=True); r += 1
    p.band(r, dock_bg); p.text(r, 2, "  sa-0  researching palette", bar_fg, dock_bg); r += 1
    p.text(r, 2, "\u2500" * (COLS - 4), rule); r += 1
    p.text(r, 2, "> ", prompt); p.text(r, 4, "type here\u2026", dim); r += 1
    p.band(r, bar_bg)
    p.text(r, 1, "cuttlefish", strong, bar_bg, bold=True)
    p.text(r, 13, "claude-opus-5", bar_fg, bar_bg)
    p.text(r, 29, "ctx 42%", good, bar_bg)
    p.text(r, 39, "$0.14", warn, bar_bg)
    p.text(r, 47, "2 errors", crit, bar_bg)

    return p.img


def stack(imgs, caption=""):
    """Stack the panels and put ONE caption under the set.

    A caption per panel repeated the same sentence three times and read as a
    rendering bug rather than as narration.
    """
    w = max(i.width for i in imgs)
    h = sum(i.height for i in imgs) + 6 * (len(imgs) - 1) + 30
    out = Image.new("RGB", (w, h), (10, 10, 12))
    y = 0
    for i in imgs:
        out.paste(i, (0, y)); y += i.height + 6
    ImageDraw.Draw(out).text((10, h - 22), caption, font=FONT, fill=(168, 166, 174))
    return out


if __name__ == "__main__":
    os.environ["HERMES_HOME"] = tempfile.mkdtemp(prefix="gif-")

    SESSIONS = ["sess-alpha", "sess-beta", "sess-gamma"]
    pals_rest = [render(allocate(s), Signal.RESTING) for s in SESSIONS]
    cols_rest = [p.skin_colors() for p in pals_rest]

    frames, durations = [], []

    def add(img, ms):
        frames.append(img); durations.append(ms)

    # --- ACT 1: three sessions, each its own skin ---------------------------
    hold = stack([panel(cols_rest[i], pals_rest[i], "", "resting") for i in range(3)],
                 "three sessions \u00b7 each gets its own colour, name and whole-UI skin")
    add(hold, 2200)

    # --- ACT 2: session C blanches (fault arrives) --------------------------
    pal_f = render(allocate(SESSIONS[2]), Signal.FAULT, age_label="2m")
    cols_f = pal_f.skin_colors()
    for t in [i * BLANCH.duration / 7 for i in range(1, 8)]:
        mid = morph(cols_rest[2], cols_f, BLANCH, t, seed="gif-blanch")
        img = stack([panel(cols_rest[0], pals_rest[0], "", "resting"),
                     panel(cols_rest[1], pals_rest[1], "", "resting"),
                     panel(mid, pal_f, "", "FAULT")],
                    "a fault arrives \u2192 BLANCH: 0.4s, fast and synchronous "
                    "(Woo et al., Nature 619, 2023)")
        add(img, 60)
    add(stack([panel(cols_rest[0], pals_rest[0], "", "resting"),
               panel(cols_rest[1], pals_rest[1], "", "resting"),
               panel(cols_f, pal_f, "", "FAULT")],
              "the WHOLE skin responds \u2014 status bar, menus, dock, borders, ground"), 1800)

    # --- ACT 3: it clears -> recover ----------------------------------------
    for t in [i * RECOVER.duration / 12 for i in range(1, 13)]:
        mid = morph(cols_f, cols_rest[2], RECOVER, t, seed="gif-recover")
        img = stack([panel(cols_rest[0], pals_rest[0], "", "resting"),
                     panel(cols_rest[1], pals_rest[1], "", "resting"),
                     panel(mid, pals_rest[2], "", "resting")],
                    "the fault clears \u2192 RECOVER: 2.4s, slower, decelerating, staggered")
        add(img, 110)
    add(stack([panel(cols_rest[i], pals_rest[i], "", "resting") for i in range(3)],
              "identity returns exactly \u2014 blanching COVERS it, never destroys it"), 2600)

    out = "/tmp/cuttlefish-demo.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    print(f"wrote {out}  ({len(frames)} frames, {sum(durations)/1000:.1f}s, "
          f"{os.path.getsize(out)/1024:.0f} KB)")
