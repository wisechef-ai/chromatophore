"""Sample the real palette from real cuttlefish photographs.

Adam: "please use zai websearch/image/page read to see how those cuttlefish
looks - im looking for the vivid bright accents."

A model eyeballing hex codes from a photo is a guess. This measures. It reads the
actual pixels, converts to OKLCh, and reports the distribution the way the theme
reasons about colour, so the numbers drop straight into palette.py.

The key question is not "what colours appear" (a JPEG of a reef has thousands)
but "what is the STRUCTURE": how dark is the ground, how vivid are the accents,
and what FRACTION of the animal is bright. That ratio is what makes a cuttlefish
read as vivid without being exhausting, and it is exactly what the theme needs.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import conftest  # noqa: F401,E402  # side-effect: binds the cuttlefish_theme package

from PIL import Image  # noqa: E402

from cuttlefish_theme.color.oklab import hex_to_oklch, oklch_to_hex, OKLCh  # noqa: E402


def px_hex(p):
    return "#%02X%02X%02X" % p[:3]


def sample(path, *, crop=None, bins=24):
    """Quantise an image and report its OKLCh structure."""
    im = Image.open(path).convert("RGB")
    if crop:
        im = im.crop(crop)
    im = im.resize((220, int(220 * im.height / im.width)))
    px = list(im.getdata())

    cols = []
    for p in px:
        c = hex_to_oklch(px_hex(p))
        cols.append(c)

    Ls = sorted(c.L for c in cols)
    Cs = sorted(c.C for c in cols)
    n = len(cols)

    # "Accent" = the vivid minority: top decile of chroma.
    thresh = Cs[int(0.90 * n)]
    accents = [c for c in cols if c.C >= thresh]
    # "Ground" = the dark majority: bottom third of lightness.
    ground = [c for c in cols if c.L <= Ls[int(0.33 * n)]]

    def avg(cs):
        if not cs:
            return None
        import math
        x = sum(math.cos(math.radians(c.h)) for c in cs) / len(cs)
        y = sum(math.sin(math.radians(c.h)) for c in cs) / len(cs)
        return OKLCh(sum(c.L for c in cs) / len(cs),
                     sum(c.C for c in cs) / len(cs),
                     math.degrees(math.atan2(y, x)) % 360)

    # Dominant accent hues, clustered into bins
    hues = Counter()
    for c in accents:
        hues[int(c.h // (360 / bins)) * (360 // bins)] += 1

    return {
        "n": n,
        "L_p10": Ls[n // 10], "L_median": Ls[n // 2], "L_p90": Ls[9 * n // 10],
        "C_median": Cs[n // 2], "C_p90": Cs[9 * n // 10], "C_max": Cs[-1],
        "accent_avg": avg(accents),
        "ground_avg": avg(ground),
        "bright_fraction": sum(1 for c in cols if c.L > 0.65) / n,
        "vivid_fraction": sum(1 for c in cols if c.C > 0.10) / n,
        "top_accent_hues": hues.most_common(6),
        "accent_examples": [oklch_to_hex(c) for c in
                            sorted(accents, key=lambda c: -c.C)[:8]],
    }


if __name__ == "__main__":
    # Crops isolate the ANIMAL from the sand, so the sand's grey does not
    # dominate the statistics and flatten exactly the contrast we are measuring.
    targets = [
        ("walking.jpg", (60, 30, 830, 620)),
        ("bold.jpg", None),
        ("feisty.jpg", None),
        ("hero.jpg", None),
    ]
    for name, crop in targets:
        path = f"/tmp/cfphotos/{name}"
        if not os.path.exists(path):
            continue
        r = sample(path, crop=crop)
        print(f"\n=== {name} ===")
        print(f"  L   p10 {r['L_p10']:.3f}   median {r['L_median']:.3f}   p90 {r['L_p90']:.3f}")
        print(f"  C   median {r['C_median']:.4f}  p90 {r['C_p90']:.4f}  max {r['C_max']:.4f}")
        a, g = r["accent_avg"], r["ground_avg"]
        if g:
            print(f"  GROUND  L {g.L:.3f}  C {g.C:.4f}  h {g.h:.0f}   {oklch_to_hex(g)}")
        if a:
            print(f"  ACCENT  L {a.L:.3f}  C {a.C:.4f}  h {a.h:.0f}   {oklch_to_hex(a)}")
        print(f"  bright fraction (L>0.65): {r['bright_fraction']:.1%}")
        print(f"  vivid  fraction (C>0.10): {r['vivid_fraction']:.1%}")
        print(f"  accent hue clusters: {r['top_accent_hues']}")
        print(f"  most saturated pixels: {' '.join(r['accent_examples'])}")
