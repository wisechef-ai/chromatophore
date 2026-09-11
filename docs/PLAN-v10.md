# v10 — chromatophore classes: many colours, and colour as the signal

## What Adam saw

> "the pattern and color is identical in 2 new sessions... now we do have only
> one color for the background pattern... cuttlefishes are using their color to
> communicate to each other and this is the similar idea to inform the user
> about the state by combining the colors and patterns."

Both halves are correct, and they share one root cause: **the mantle has exactly
one pigment**, so it can neither separate sessions nor carry a signal.

## Measured: why sessions collide

A background behind readable text must stay dark (L <= 0.45) and chromatic
(C > 0.03). The xterm-256 colour cube contains **13 such entries, total**:

| family | count | indices |
|---|---|---|
| red / orange | 3 | 52, 88, 89 |
| brown / violet | 4 | 53, 54, 55, 90 |
| blue | 4 | 17, 18, 19, 20 |
| green / teal | 2 | 22, 23 |
| yellow / amber | 0 | (yellow is intrinsically light; none survive at L <= 0.45) |

Measured on six real-shaped session ids: **4 distinct pigments of 6**, two
collisions. With 13 slots and a hash, collisions are expected, not bad luck.

**One pigment = 13 identities. A 3-pigment SET = 286.** That is the fix, and it
is also the biology.

## The biology (the repo's own sources, plus the primary literature)

Cuttlefish skin is a **vertically layered system**, not one pigment:

- **Chromatophores**, uppermost, in 2-3 discrete PIGMENT CLASSES — *"layered
  yellow over red over brown"* (Deravi et al., J. R. Soc. Interface 11:20130942).
  Each class is an independently actuated organ; the brain expands them
  separately within hundreds of milliseconds.
- **Iridophores**, beneath, structural reflectors producing *"primarily
  short-wavelength colours that complement the long-wavelength colours of the
  chromatophores"* — the blues and greens.
- **Leucophores**, basal, passive diffuse white; *"a backdrop against which
  chromatophores and iridophores create highly contrasting patterns"*
  (Mäthger et al., Phil. Trans. R. Soc. B).

Two consequences we can use directly:

1. **Colour comes from WHICH CLASSES ARE EXPANDED**, not from one pigment being
   swapped. *"Three colour classes of pigments (yellow, red and brown), combined
   with a single type of reflective cell, produce colours that encompass the
   whole of the visible spectrum"* (Mäthger & Hanlon 2007).
2. **That is the communication channel.** Hanlon & Messenger catalogue 34
   chromatic components; the Zebra display uses bright white *"as the
   high-contrast complement to the dark brown bands"* during agonistic
   signalling. The animal signals by changing WHICH class dominates.

## The design

**A session is a chromatophore SET, not a colour.** Allocate three pigments per
session, one from each of three different hue families, seeded by blake2b:

    session -> (class_a, class_b, iridophore)
               class_a, class_b : two dark chromatic cube entries, different families
               iridophore       : the short-wavelength complement (blue/green/teal)

Identity is then the SET, giving 286 combinations instead of 13, and two
sessions that happen to share one pigment still differ in the other two.

**The field decides WHICH CLASS EXPANDS per cell** — differential expansion,
exactly as in the animal. The existing `cells()` already yields a per-column
intensity; map bands of it onto classes rather than onto one on/off pigment:

    retracted (ground)      -> near-black ground, unchanged
    low expansion           -> iridophore (the cool complement)
    mid expansion           -> class_b
    high expansion          -> class_a
    rare, top few percent   -> leucophore pearl (bright, sparse)

**State = which class dominates.** The acute layer already exists
(`session.collapse` -> RESTING / NEEDS_ME / FAULT); wire it to the class ratio
rather than to a single hue swap:

| signal | display | biology |
|---|---|---|
| resting | the session's own class balance | the animal's resting pattern |
| needs me | amber/yellow class dominant | the bright signalling classes expand |
| fault | red class dominant | high-contrast agonistic display |

The acute state must be recognisable ACROSS sessions — a user with six terminals
open must read "that one needs me" without knowing which session it is. So the
acute classes are shared and fixed; only the resting set is per-session.

## Outcomes (each needs a test that FAILS first)

1. **A session yields >= 3 distinct pigment indices**, all non-grey (16..231).
2. **Identity separation**: over 20 real-shaped session ids, no two sessions
   share their full pigment SET, and >= 90% differ in at least two of three.
   (Today: 4 distinct of 6. Assert on the QUANTISED indices.)
3. **Differential expansion**: a rendered row contains >= 3 distinct background
   indices (ground + at least two classes), not 2.
4. **Leucophore sparsity**: the bright class occupies 2-6% of cells — it is an
   accent, never a texture.
5. **Acute states are cross-session recognisable**: for ANY session, NEEDS_ME's
   dominant non-ground hue is amber-family and FAULT's is red-family, and each
   shares < 20% of its pigment set with that session's resting set.
6. **Contrast holds**: every emitted background keeps >= 4.5:1 against body text,
   and every pigment stays L <= 0.45.
7. **Density unchanged**: the v7/v9 properties still hold — 30% pigment share,
   max dark gap <= 14, mean run >= 2.0, stable per (session, row_key).
8. **Cost**: the renderer stays cached; steady-state <= 10 us/line.

## Out of scope

- No new core changes. The `transcript_line` surface is done and deployed.
- No change to the input rule's density grammar (v7) or the row-stability
  contract (v9).
- Do not widen the lightness ceiling to grab more colours: text readability is
  the constraint that outranks palette size.

## Gate

`PYTHONPATH=~/.hermes/hermes-agent make test` green (256 today), plus the eight
above, plus a rendered ASCII preview showing >= 3 classes in play, plus the
measured per-session pigment sets for 20 sessions.
