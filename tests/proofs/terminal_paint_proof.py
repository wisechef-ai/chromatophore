#!/usr/bin/env python3
"""THE proof that matters: does a real `hermes` terminal PAINT our colours?

WHY THIS EXISTS

Four releases in a row passed every test and every proof while Adam still saw an
unthemed gold terminal. The reason: every check tested the skin ENGINE's API —
write a skin, read back `get_prompt_toolkit_style_overrides()`, count the keys.
All of that was green and all of it was true, and none of it was the claim we
cared about.

The actual failure was startup ordering (see bootstrap.py): `display.skin` was
never set, so `init_skin_from_config()` resolved `default` at CLI launch, painted
stock gold, and our later `set_active_skin()` had no running application to
repaint. The engine did exactly what it was asked. Nobody had asked the terminal.

So this proof spawns the REAL `hermes` binary on a REAL pty and counts the
DISTINCT COLOURS IN THE BYTES IT WRITES TO THE SCREEN. It cannot be satisfied by
a correct API; only by paint.

Run: python3 tests/proofs/terminal_paint_proof.py
Exits non-zero if the terminal is still painting stock Hermes gold.
"""

import os
import pty
import re
import select
import shutil
import subprocess
import sys
import time

# Stock Hermes `default` palette. If these are what the terminal paints, our skin
# never reached the screen no matter what the engine reports.
STOCK = {
    "#FFD700",  # banner_title  (gold)
    "#CD7F32",  # banner_border (bronze)
    "#B8860B",  # banner_dim
    "#FFF8DC",  # banner_text   (cornsilk)
    "#FFBF00",  # ui_accent
    "#1A1A2E",  # status_bar_bg
}

CAPTURE_SECONDS = float(os.environ.get("PAINT_CAPTURE_SECONDS", "25"))


def capture(cmd, seconds=CAPTURE_SECONDS):
    """Run *cmd* on a pty and return every byte it wrote."""
    env = dict(os.environ)
    env.update({"TERM": "xterm-256color", "COLORTERM": "truecolor",
                "LINES": "40", "COLUMNS": "120"})
    master, slave = pty.openpty()
    proc = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave,
                            env=env, close_fds=True, preexec_fn=os.setsid)
    os.close(slave)
    out = bytearray()
    deadline = time.time() + seconds
    quit_sent = False
    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.4)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                out.extend(chunk)
            if not quit_sent and time.time() > deadline - 6:
                try:
                    os.write(master, b"\x04")   # Ctrl-D
                except OSError:
                    pass
                quit_sent = True
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
    return bytes(out)


def truecolors(buf: bytes) -> set:
    """Every distinct 24-bit colour in a terminal byte stream."""
    found = set()
    for code in re.findall(r"\x1b\[([0-9;]*)m", buf.decode("utf-8", "replace")):
        parts = code.split(";")
        i = 0
        while i < len(parts):
            if parts[i] in ("38", "48") and i + 4 < len(parts) and parts[i + 1] == "2":
                try:
                    found.add("#%02X%02X%02X" % (int(parts[i + 2]), int(parts[i + 3]),
                                                 int(parts[i + 4])))
                except ValueError:
                    pass
                i += 5
                continue
            i += 1
    return found


failures = []


def check(label, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


print("\ncuttlefish-theme — terminal paint proof\n")

if shutil.which("hermes") is None:
    print("  SKIP: `hermes` is not on PATH — nothing to paint.\n")
    sys.exit(0)

buf = capture(["hermes"])
painted = truecolors(buf)
stock_hits = sorted(painted & STOCK)
ours = sorted(painted - STOCK)

print(f"  captured {len(buf)} bytes, {len(painted)} distinct truecolor values\n")

check("the terminal painted SOMETHING in truecolor", bool(painted),
      f"{len(painted)} colours")
check("the terminal is NOT painting stock Hermes gold", not stock_hits,
      f"stock hits: {stock_hits}" if stock_hits else "no stock palette colours")
check("colours beyond the stock palette are present", len(ours) >= 4,
      f"{len(ours)} non-stock: {ours[:8]}")

# The theme's signature: a near-black ground and a vivid accent, both carrying
# one hue. Checked structurally rather than against fixed hexes, because the
# colours are per-session by design.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", ".."))
    import importlib.util
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    if "cuttlefish_theme" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "cuttlefish_theme", root / "__init__.py",
            submodule_search_locations=[str(root)])
        mod = importlib.util.module_from_spec(spec)
        mod.__path__ = [str(root)]
        sys.modules["cuttlefish_theme"] = mod
        spec.loader.exec_module(mod)
    from cuttlefish_theme.color.oklab import hex_to_oklch

    dark = [c for c in ours if hex_to_oklch(c).L < 0.32]
    vivid = [c for c in ours if hex_to_oklch(c).C > 0.12]
    check("a near-black ground is on screen", bool(dark), f"{dark[:4]}")
    check("a vivid accent is on screen", bool(vivid), f"{vivid[:4]}")
except Exception as exc:  # pragma: no cover
    check("palette structure check ran", False, str(exc))

print()
if failures:
    print(f"  {len(failures)} FAILED: {', '.join(failures)}")
    print("  The engine may be correct and the terminal still unthemed — check")
    print("  `display.skin` in config.yaml and see bootstrap.py.\n")
    sys.exit(1)
print("  the real terminal paints this session's skin\n")
