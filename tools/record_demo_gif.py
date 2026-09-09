"""Build the README GIF from REAL terminal bytes, never from a mock.

WHY THIS REPLACES THE OLD GENERATOR

Adam, on the previous GIF: "i see that those recordings of live action could be
on some older hermes agent?" He was right, and the reason is a design flaw in how
it was made: `render_demo_gif.py` composed a MOCK chat layout from the palette.
It could look perfect while the real terminal painted stock gold — which is
exactly what was happening for four releases.

So this captures the actual thing. It spawns `hermes` on a pty, records every
byte, replays the escape sequences through a tiny terminal emulator, and
rasterises the resulting cell grid. If a colour is not on screen it is not in the
GIF, and a screenshot of a broken build looks broken.

WHAT THE EMULATOR SUPPORTS

Only what the banner and prompt actually emit: SGR colour (truecolor, 256-index,
reset), cursor motion, erase, and newline handling. That is deliberately narrow —
a general terminal emulator is a large project, and every feature beyond what
Hermes emits is untested code that can only lie to us.
"""
import os
import pty
import re
import select
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conftest  # noqa: F401,E402  # side-effect: binds the cuttlefish_theme package

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

CW, CH = 8, 16
COLS, ROWS = 118, 44
FONT = ImageFont.load_default()
for _p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",):
    if os.path.exists(_p):
        FONT = ImageFont.truetype(_p, 13)

# 256-colour cube, for the few places Hermes falls back to indexed colour.
_CUBE = (0, 95, 135, 175, 215, 255)


def _idx_rgb(i: int):
    if i < 16:
        v = 0 if i < 8 else 128
        return (255 if i in (9, 11, 13, 15) else v,) * 3
    if i < 232:
        i -= 16
        return (_CUBE[i // 36], _CUBE[(i // 6) % 6], _CUBE[i % 6])
    g = 8 + (i - 232) * 10
    return (g, g, g)


class Screen:
    """The minimum terminal needed to replay a Hermes banner faithfully."""

    def __init__(self, cols=COLS, rows=ROWS, bg=(12, 12, 14)):
        self.cols, self.rows, self.default_bg = cols, rows, bg
        self.cells = {}
        self.x = self.y = 0
        self.fg, self.bg = (200, 200, 200), None

    def _sgr(self, code):
        parts = (code or "0").split(";")
        i = 0
        while i < len(parts):
            p = parts[i] or "0"
            if p in ("38", "48") and i + 1 < len(parts):
                if parts[i + 1] == "2" and i + 4 < len(parts):
                    rgb = tuple(int(v or 0) for v in parts[i + 2:i + 5])
                    if p == "38":
                        self.fg = rgb
                    else:
                        self.bg = rgb
                    i += 5
                    continue
                if parts[i + 1] == "5" and i + 2 < len(parts):
                    rgb = _idx_rgb(int(parts[i + 2] or 0))
                    if p == "38":
                        self.fg = rgb
                    else:
                        self.bg = rgb
                    i += 3
                    continue
            if p == "0":
                self.fg, self.bg = (200, 200, 200), None
            i += 1

    def feed(self, text):
        i = 0
        while i < len(text):
            m = re.match(r"\x1b\[([0-9;]*)m", text[i:])
            if m:
                self._sgr(m.group(1))
                i += m.end()
                continue
            m = re.match(r"\x1b\[([0-9;]*)([A-HJKSTfsu])", text[i:])
            if m:
                arg = m.group(1)
                cmd = m.group(2)
                n = int(arg.split(";")[0]) if arg and arg.split(";")[0] else 1
                if cmd == "A":
                    self.y = max(0, self.y - n)
                elif cmd == "B":
                    self.y += n
                elif cmd == "C":
                    self.x += n
                elif cmd == "D":
                    self.x = max(0, self.x - n)
                elif cmd in "Hf":
                    bits = (arg or "1;1").split(";")
                    self.y = max(0, int(bits[0] or 1) - 1)
                    self.x = max(0, int(bits[1] if len(bits) > 1 and bits[1] else 1) - 1)
                elif cmd == "J":
                    self.cells.clear()
                    self.x = self.y = 0
                elif cmd == "K":
                    for cx in range(self.x, self.cols):
                        self.cells.pop((cx, self.y), None)
                i += m.end()
                continue
            m = re.match(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)", text[i:])
            if m:
                i += m.end()
                continue
            m = re.match(r"\x1b[\[\]?][0-9;?]*[a-zA-Z<>]", text[i:])
            if m:
                i += m.end()
                continue
            ch = text[i]
            i += 1
            if ch == "\n":
                self.y += 1
                self.x = 0
            elif ch == "\r":
                self.x = 0
            elif ch == "\x1b":
                continue
            elif ch == "\b":
                self.x = max(0, self.x - 1)
            else:
                if 0 <= self.x < self.cols:
                    self.cells[(self.x, self.y)] = (ch, self.fg, self.bg)
                self.x += 1

    def image(self, y0=0, rows=None):
        rows = rows or self.rows
        img = Image.new("RGB", (self.cols * CW, rows * CH), self.default_bg)
        d = ImageDraw.Draw(img)
        for (cx, cy), (ch, fg, bg) in self.cells.items():
            yy = cy - y0
            if not (0 <= yy < rows) or cx >= self.cols:
                continue
            if bg:
                d.rectangle([cx * CW, yy * CH, (cx + 1) * CW - 1, (yy + 1) * CH - 1], fill=bg)
            if ch.strip():
                d.text((cx * CW, yy * CH), ch, font=FONT, fill=fg)
        return img


def record(cmd, seconds, feed=b"", env_extra=None):
    """Run *cmd* on a pty, returning (bytes, [(t, bytes), ...]) for replay."""
    env = dict(os.environ)
    env.update({"TERM": "xterm-256color", "COLORTERM": "truecolor",
                "LINES": str(ROWS), "COLUMNS": str(COLS)})
    env.update(env_extra or {})
    master, slave = pty.openpty()
    proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave,
                            env=env, close_fds=True, preexec_fn=os.setsid)
    os.close(slave)
    out, chunks = bytearray(), []
    began = time.time()
    deadline = began + seconds
    sent = False
    try:
        while time.time() < deadline:
            r, _, _ = select.select([master], [], [], 0.2)
            if r:
                try:
                    c = os.read(master, 65536)
                except OSError:
                    break
                if not c:
                    break
                out.extend(c)
                chunks.append((time.time() - began, bytes(c)))
            if feed and not sent and time.time() - began > seconds * 0.45:
                try:
                    os.write(master, feed)
                except OSError:
                    pass
                sent = True
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), 9)
            except Exception:
                pass
        try:
            os.close(master)
        except OSError:
            pass
    return bytes(out), chunks


def caption(img, text):
    out = Image.new("RGB", (img.width, img.height + 26), (10, 10, 12))
    out.paste(img, (0, 0))
    ImageDraw.Draw(out).text((10, img.height + 6), text, font=FONT, fill=(170, 168, 176))
    return out


if __name__ == "__main__":
    if shutil.which("hermes") is None:
        print("SKIP: hermes not on PATH")
        sys.exit(0)

    print("recording a real `hermes` session (this takes ~30s)...")
    raw, chunks = record(["hermes"], seconds=26, feed=b"\x04")
    text = raw.decode("utf-8", "replace")
    print(f"  captured {len(raw)} bytes in {len(chunks)} chunks")
    print(f"  half-block pixels on screen: {text.count(chr(0x2580))}")

    # Replay progressively so the GIF shows the banner ARRIVING, not just a still.
    # Pick frames that ACTUALLY CONTAIN THE BANNER, not frames by wall-clock.
    #
    # Two earlier cuts sampled by chunk index and both produced a GIF of an empty
    # prompt: the banner scrolls, and the final chunk is the exit screen-clear, so
    # "the last frame" is by definition the least interesting thing on screen.
    # Replay incrementally, keep every state whose mantle is on screen, then take
    # an even spread of those. A frame with no pixels in it cannot be a frame of
    # this theme.
    states = []
    sc = Screen()
    for _, chunk in chunks:
        sc.feed(chunk.decode("utf-8", "replace"))
        pixel_rows = sorted({cy for (_, cy), (ch, _, _) in sc.cells.items()
                             if ch == "\u2580"})
        if pixel_rows:
            states.append((dict(sc.cells), pixel_rows))
    if not states:
        print("FAIL: the banner never painted a mantle — nothing to record.")
        sys.exit(1)
    print(f"  {len(states)} of {len(chunks)} states show the mantle")

    caps = [
        "a real Hermes session, recorded on a pty \u2014 no mockups",
        "the wordmark takes this session's colour",
        "the mantle: 900 chromatophore cells, a different pattern per session",
        "neutral black ground \u2014 the identity lives in the pixels",
    ]
    picks = [states[min(len(states) - 1, int(len(states) * f))]
             for f in (0.0, 0.34, 0.67, 0.999)]

    frames, durations = [], []
    for (cells, pixel_rows), cap in zip(picks, caps):
        shot = Screen()
        shot.cells = cells
        y0 = max(0, pixel_rows[0] - 4)
        height = min(ROWS, pixel_rows[-1] - y0 + 18)
        frames.append(caption(shot.image(y0=y0, rows=height), cap))
        durations.append(2600)

    w = max(f.width for f in frames)
    h = max(f.height for f in frames)
    frames = [f if f.size == (w, h) else
              (lambda c: (c.paste(f, (0, 0)), c)[1])(Image.new("RGB", (w, h), (10, 10, 12)))
              for f in frames]

    out = "/tmp/cuttlefish-demo.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=durations, loop=0, optimize=True)
    print(f"wrote {out}  ({len(frames)} frames, {os.path.getsize(out)/1024:.0f} KB)")
