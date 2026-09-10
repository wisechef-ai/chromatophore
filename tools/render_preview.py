"""Render the chromatophore field to PNG so a human (or a vision model) can judge it.

The terminal is the real target, but ANSI escapes do not survive a tool capture, and
"it probably looks fine" is not a verification. This rasterises exactly what
render_half_blocks() emits — same compositor, same colours, one image pixel per
chromatophore — so what you see here is what the terminal shows.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conftest  # noqa: F401,E402  # side-effect: binds the cuttlefish_theme package

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from cuttlefish_theme.color.identity import allocate  # noqa: E402
from cuttlefish_theme.field import (mottle, passing_cloud,  # noqa: E402
                                    render_half_blocks)
from cuttlefish_theme.morph import BLANCH, RECOVER, morph  # noqa: E402
from cuttlefish_theme.naming import session_name  # noqa: E402
from cuttlefish_theme.pattern import render  # noqa: E402
from cuttlefish_theme.session import Signal  # noqa: E402

ANSI = re.compile(r"\x1b\[38;2;(\d+);(\d+);(\d+)m\x1b\[48;2;(\d+);(\d+);(\d+)m\u2580")
SCALE = 8


def decode(lines):
    """ANSI half-block lines -> a grid of (r,g,b), two pixel rows per text row."""
    rows = []
    for line in lines:
        top, bottom = [], []
        for m in ANSI.finditer(line):
            v = [int(x) for x in m.groups()]
            top.append(tuple(v[0:3]))
            bottom.append(tuple(v[3:6]))
        rows.append(top)
        rows.append(bottom)
    return rows


def paste(img, rows, ox, oy, scale=SCALE):
    d = ImageDraw.Draw(img)
    for y, row in enumerate(rows):
        for x, colour in enumerate(row):
            d.rectangle([ox + x * scale, oy + y * scale,
                         ox + (x + 1) * scale - 1, oy + (y + 1) * scale - 1],
                        fill=colour)


def field_rows(session_id, width, height, t=None, signal=Signal.RESTING):
    ident = allocate(session_id)
    p = render(ident, signal)
    seed = abs(hash(session_id)) & 0xFFFFFFFF
    f = mottle(width, height, seed=seed)
    if t is not None:
        f = passing_cloud(f, t, seed=seed)
    return decode(render_half_blocks(
        f, pigment_hex=p.identity_hex, sheen_hex=p.sheen_hex,
        base_hex=p.ground_hex)), p


def font(size=13):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


W, H = 72, 14
SESSIONS = ["sess-alpha", "sess-beta", "sess-gamma", "sess-delta"]

# --- 1. four sessions, each its own skin ------------------------------------
img = Image.new("RGB", (W * SCALE + 260, len(SESSIONS) * (H * SCALE + 34) + 30),
                (14, 14, 16))
d = ImageDraw.Draw(img)
fnt = font()
for i, sid in enumerate(SESSIONS):
    rows, p = field_rows(sid, W, H)
    y = 20 + i * (H * SCALE + 34)
    paste(img, rows, 16, y)
    d.text((W * SCALE + 28, y + 4), session_name(sid), font=fnt, fill=(235, 230, 220))
    d.text((W * SCALE + 28, y + 24), f"id {p.identity_hex}", font=fnt, fill=(150, 145, 140))
    d.text((W * SCALE + 28, y + 42), f"bg {p.ground_hex}", font=fnt, fill=(150, 145, 140))
img.save("/tmp/cuttle_identities.png")

# --- 2. a passing cloud, frame by frame -------------------------------------
TS = [0.0, 0.15, 0.30, 0.45, 0.60, 0.75]
img = Image.new("RGB", (W * SCALE + 32, len(TS) * (H * SCALE + 26) + 30), (14, 14, 16))
d = ImageDraw.Draw(img)
for i, t in enumerate(TS):
    rows, _ = field_rows("sess-alpha", W, H, t=t)
    y = 20 + i * (H * SCALE + 26)
    paste(img, rows, 16, y)
    d.text((18, y - 14), f"t = {t:.2f}s", font=font(11), fill=(150, 145, 140))
img.save("/tmp/cuttle_wave.png")

# --- 3. the transition curves, as colour bars -------------------------------
ident = allocate("sess-alpha")
calm = render(ident, Signal.RESTING).skin_colors()
alarm = render(ident, Signal.FAULT).skin_colors()
keys = sorted(k for k in calm if k in alarm)
STEPS = 40
BAR = 26
img = Image.new("RGB", (STEPS * 22 + 200, 2 * (len(keys) * BAR + 46) + 30), (14, 14, 16))
d = ImageDraw.Draw(img)
for row, (label, traj, a, b) in enumerate((
        ("blanch  0.4s  fault arrives", BLANCH, calm, alarm),
        ("recover 2.4s  fault clears", RECOVER, alarm, calm))):
    oy = 20 + row * (len(keys) * BAR + 46)
    d.text((16, oy - 2), label, font=fnt, fill=(235, 230, 220))
    for s in range(STEPS):
        t = traj.duration * s / (STEPS - 1)
        frame = morph(a, b, traj, t, seed=label)
        for k, key in enumerate(keys):
            c = frame[key]
            d.rectangle([16 + s * 22, oy + 18 + k * BAR,
                         16 + (s + 1) * 22 - 2, oy + 18 + (k + 1) * BAR - 3],
                        fill=(int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)))
    for k, key in enumerate(keys):
        d.text((STEPS * 22 + 26, oy + 22 + k * BAR), key, font=font(11),
               fill=(150, 145, 140))
img.save("/tmp/cuttle_transitions.png")

# --- 4. v6 acceptance sheet: six sessions x three signals -------------------
# Keep this as an additive section: the three diagnostic previews above remain
# useful for comparing identities, waves, and transitions.
from cuttlefish_theme.patterns import field_for
from cuttlefish_theme.palette import pigment_hex, dominant_pigments

sheet_sessions = ["zivyra", "tilola", "nygoka", "brepen", "safira", "lumeko"]
sheet_signals = [Signal.RESTING, Signal.NEEDS_ME, Signal.FAULT]
cell_w, cell_h, gap = 180, 130, 18
sheet = Image.new("RGB", (len(sheet_signals) * cell_w + (len(sheet_signals) + 1) * gap,
                           len(sheet_sessions) * cell_h + (len(sheet_sessions) + 1) * gap), (8, 10, 20))
d = ImageDraw.Draw(sheet)
for iy, sid in enumerate(sheet_sessions):
    for ix, sig in enumerate(sheet_signals):
        x0 = gap + ix * (cell_w + gap)
        y0 = gap + iy * (cell_h + gap)
        rows, pal = field_rows(sid, 20, 12, signal=sig)
        paste(sheet, rows, x0, y0, scale=6)
        d.text((x0, y0 + 76), f"{sid} · {sig.value}", font=font(10), fill=(235, 230, 220))
        d.text((x0, y0 + 94), " / ".join(dominant_pigments(sid)), font=font(9), fill=(150, 145, 140))
sheet.save("docs/preview-v6.png")

print("wrote /tmp/cuttle_identities.png /tmp/cuttle_wave.png /tmp/cuttle_transitions.png docs/preview-v6.png")
