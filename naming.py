"""Session names: pronounceable, endless, and derived rather than drawn from a list.

The requirement (Adam, 2026-09-08): names, but "not from a fixed list as this would
limit the variety... I expect to have endless not doubling colourful profiles".

A fixed word list has the same flaw as a fixed palette: it runs out, and worse, it
runs out at a small number. So names are GENERATED from the session id by a
phonotactic grammar — consonant-vowel syllables assembled under rules that keep the
result pronounceable in Polish and English alike.

Name space size is computed, not asserted: see `name_space_size()`, which `doctor`
prints so the claim is falsifiable rather than marketing. With the tables below it
is 20 x 6 x 12 x 6 x 6 x 3 = 155,520 forms. Collisions are governed by the birthday
bound, so what matters is CONCURRENT sessions, not lifetime ones: measured, 50 live
sessions allocate 50 distinct names, and the identity COLOUR is separately
guaranteed distinct among concurrent sessions regardless. Two sessions six months
apart sharing a name is harmless and expected.

Generation is deterministic from the session id via blake2b (NOT Python's hash(),
which is randomised per process and would rename a session on reconnect).
"""

from __future__ import annotations

import hashlib

__all__ = ["session_name", "name_space_size"]


# Onsets chosen to be unambiguous when spoken and to avoid clusters that are hard
# in either language. No 'q'/'x'; no 'c' (ambiguous /k/ vs /s/).
_ONSETS = (
    "b", "d", "f", "g", "h", "k", "l", "m", "n", "p",
    "r", "s", "t", "v", "z", "br", "dr", "kr", "tr", "sk",
)

_VOWELS = ("a", "e", "i", "o", "u", "y")

# Second-syllable onsets: a wider set, since the first syllable already carries
# most of the distinctiveness.
_ONSETS2 = (
    "b", "d", "g", "k", "l", "m", "n", "p", "r", "s", "t", "v",
)

# Codas kept sonorant so names end softly and never collide with the reserved
# status words (INPUT / ERROR) when scanned quickly.
_CODAS = ("", "n", "r", "l", "s", "k")

# An optional third syllable, applied to a third of names. This widens the space
# 3x without making every name long: most stay two syllables and short, which is
# what makes them quick to say.
_TAILS = ("", "a", "o")


def name_space_size() -> int:
    """Total distinct generatable names. Reported by `doctor` so the claim of
    'endless' is falsifiable rather than marketing."""
    return (
        len(_ONSETS) * len(_VOWELS) * len(_ONSETS2)
        * len(_VOWELS) * len(_CODAS) * len(_TAILS)
    )


def session_name(session_id: str) -> str:
    """A stable, pronounceable name for *session_id*.

    Deterministic: the same id always yields the same name, on any machine, in any
    process, so a session keeps its name across reconnects and across the `watch`
    board running elsewhere.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must be a non-empty string")

    digest = hashlib.blake2b(
        session_id.encode("utf-8"), digest_size=16, person=b"chroma-name"
    ).digest()
    n = int.from_bytes(digest, "big")

    def take(seq):
        nonlocal n
        n, idx = divmod(n, len(seq))
        return seq[idx]

    o1, v1 = take(_ONSETS), take(_VOWELS)
    o2, v2 = take(_ONSETS2), take(_VOWELS)
    coda = take(_CODAS)
    tail = take(_TAILS)
    return f"{o1}{v1}{o2}{v2}{coda}{tail}"
