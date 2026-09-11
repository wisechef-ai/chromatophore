# v11 — make it look like the animal

## Why the current mantle does not look like a cuttlefish

Two independent vision readings of real photographs (URLs below), plus the
measurements in `/tmp/audit_smoothness.py`, agree on three gaps. None of them is
a colour problem — the palette is fine. All three are *spatial*.

### Gap 1 — hard edges where nature has soft ones

Vision reading, *Sepia officinalis* (camouflaging):

> "The patches are **soft-edged and blended**, not hard pixel-like squares."

Measured, current code:

    mean run length        2.09 cells
    runs of one cell       274 of 447   (61%)
    biggest neighbour jump 0.38 OKLab L  (a JND is ~0.01)

A 38-JND step between physically adjacent cells is the definition of
salt-and-pepper. The animal never does this.

Root cause is in `field.py::mottle`, and it is deliberate:

    # Per-cell grain, so the grid reads as discrete chromatophores rather
    # than a smooth interpolated surface.

`grain=.35` plus `contrast=2.0` exist to force cells to read as on/off. That is
correct for the input rule — a one-row bar wants crisp ticks — and wrong for a
mantle, which is a 2D surface.

### Gap 2 — uniform noise where nature has large-scale structure

Vision reading, *S. officinalis*:

> "There is clear **large-scale structure**, not uniform noise: a lighter,
> finely speckled underside, a dark stripe/band along the lower edge... So the
> body is **zoned, not random**."

Vision reading, *Metasepia pfefferi* (signalling):

> "organised into large bold shapes — white bands running down the arms,
> magenta saddle patches... It is *not* a uniform mottle."

The current mantle applies one noise field homogeneously to every row. Real
skin has a coarse zone map (saddles, bands, a pale ventral region) with fine
mottle *inside* each zone. Two scales, not one.

This also matches the literature already cited in the repo: Hanlon & Messenger
catalogue discrete *body patterns* assembled from components — Mottle, Disruptive,
Uniform — not a single texture applied everywhere.

### Gap 3 — the proportion is close but the distribution is wrong

Vision reading: "roughly **70% dark** base versus **30% lighter** spots", and the
light spots are "**clustered into small blotches and short rows**, not isolated
single points."

`_VIVID_FRACTION = 0.30` is therefore *correct* and must not be changed. The
defect is purely that our 30% is scattered as singles instead of clustered as
blotches. Any fix that improves smoothness by reducing coverage is wrong — an
earlier attempt reached beautiful long runs at 5% coverage, which is not a
smoother pattern, it is an absent one.

## What changes

### 1. The mantle gets its own field (Adam's decision required — see Open questions)

`mottle()` gains nothing; the CALLER changes. The mantle asks for a field tuned
for a surface rather than a rule:

| parameter | rule (unchanged) | mantle |
|---|---|---|
| `scale`   | 1.5–5.0 | 7.0 — blotches spanning several cells |
| `grain`   | .15–.35 | .05 — near-zero; grain is the speckle generator |
| `contrast`| 2.0–2.5 | 1.15 — keep the midtones the ramp needs |

Cost: the bars and the background stop sharing one generator, so they drift
slightly apart visually. Benefit: the mantle can be smooth while the rule stays
crisp. They still share the palette, the ground, and the signal, which is where
the family resemblance actually lives.

### 2. A coarse zone map multiplies the fine mottle

A second, very-low-frequency field (`scale` ~24, i.e. a handful of features
across the whole screen) modulates the fine one:

    value = fine * (0.55 + 0.45 * zone)

Dark zones stay quiet, lit zones bloom. This is the saddles-and-bands structure
both photographs show, and it is what stops the surface reading as TV static.

### 3. Class assignment follows the value ramp, not rank

Already implemented and measured on `wip/mantle-smoothing`: mean run 2.09 → 4.6–8.4,
single-cell runs 274 → 0, coverage held at 30.8%. That branch is red only
because it lacks changes 1 and 2 — on sessions whose field has flat rows it
produces banding. With its own field those flat rows disappear.

## Acceptance — measured, on a corpus, not one session

Every threshold below is checked across ≥ 200 session ids and all three signals.

| # | contract | threshold | why this number |
|---|---|---|---|
| 1 | mean run length | ≥ 5.0 cells | blotches, not speckle. Prototyped: 6.37 |
| 2 | single-cell runs | ≤ 12% of runs | see note below — 0 is not reachable |
| 3 | pigment coverage | 0.22–0.38 | photo says 30%; must not drift |
| 4 | max neighbour ΔL | ≤ 0.15 | soft edges; was 0.38 |
| 5 | consecutive rows identical | **never** | banding is the opposite failure |
| 6 | consecutive row similarity | ≥ 0.55 | a surface, not independent lines |
| 7 | zone structure present | ≥ 2 distinct density bands per screen | "zoned, not random" |
| 8 | every colour vs #E8E6EA | ≥ 4.5:1 post-quantisation | unchanged contract |
| 9 | resting classes distinct | 4 of 4 | unchanged contract |
| 10 | acute sets identical across sessions | 1 set each | unchanged contract |
| 11 | per-line cost | ≤ 15 µs | currently 6.8 µs; mustn't regress |

Contracts 8–11 are REGRESSION guards: they already hold and the smoothing work
must not break them.

**Note on contract 2 — measured, not assumed.** I prototyped the recipe before
writing this plan (six seeds, 78x14):

    current rule field   scale1.5 grain.35 c2.0   mean run 2.45   singles 240
    fine s7 g.05 c1.15   (no zone)                mean run 4.68   singles  98
    fine s9  + zone s24                           mean run 5.58   singles  71
    fine s11 + zone s28  w.55                     mean run 6.37   singles  63

Coverage stayed at 30.8% throughout. Singles fall by 74% but do NOT reach zero,
and it is worth being exact about why: a continuous field quantised into five
discrete levels will always produce isolated cells where a smooth gradient
crosses a level boundary. That is an artefact of having five paint levels, not
of the noise. Demanding zero would force either fewer levels (losing the
four-class structure that carries identity) or a coverage collapse (the 5%
failure already seen). 63 singles out of ~170 runs is ~12%, down from 61%.

Zero singles IS reachable in one specific way — dropping to 2 paint levels —
and that trade is Adam's to make, not mine. It is listed as open question 3.

## What is NOT changing

- The palette, the four chromatophore classes, `_VIVID_FRACTION`.
- The signal semantics: resting = identity, needs_me = fixed amber,
  fault = fixed red, identical in every session.
- The input rule. Its crispness is correct for a one-row bar.

## Open questions for Adam

1. **May the mantle have its own field generator?** (Change 1.) The visual cost
   is that bars and background no longer share a texture.
2. `sample_photos.py` is cited in four comments as the source of the "measured
   against the real animal" figures, but it is not in the repo. Those numbers
   are currently unreproducible. Rebuild it as a real tool, or drop the claim
   from the comments?
3. **Four paint levels or two?** Four classes carry session identity but
   guarantee ~12% single-cell runs at level boundaries. Two levels (ground +
   one pigment) would reach zero singles and look smoothest, at the cost of the
   multi-hue identity introduced in v10. My recommendation is to keep four —
   the remaining singles are boundary cells inside a blotch, not isolated dots
   on black, which is a different visual thing from what you objected to.
4. **The status bar.** `0ccd55e` changed the acute bar from bright amber
   (#F1B200) to dark olive (#5F5F00) because the bright version left its own
   text at 1.01:1 — invisible. If the "worse on Chef" you saw is the status
   bar rather than the mantle, the fix is a bright bar with a DARK foreground
   rather than a dark bar with a light one. Say the word and I will flip it.

## Sources

- Vision reading, *Sepia officinalis*, Arrábida, Portugal (Wikimedia Commons):
  `Sepia_común_(Sepia_officinalis),_Parque_natural_de_la_Arrábida,_Portugal,_2020-07-21,_DD_62.jpg`
- Vision reading, *Ascarosepion (Metasepia) pfefferi* in display (Wikimedia Commons):
  `Ascarosepion_pfefferi_(14519167637).jpg`
- Barbosa et al., *Mottle camouflage patterns in cuttlefish: quantitative
  characterization*, J. Exp. Biol. 213(2):187 — mottle is defined by patch SCALE,
  not by per-pixel noise.
- Reiter et al. / OIST, *The dynamics of pattern matching in camouflaging
  cuttlefish*, Nature 2023 — camouflage occupies a structured "pattern space"
  of discrete body patterns.
