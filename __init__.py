"""cuttlefish-theme — animated, pixel-level session identity for Hermes.

Modelled on cuttlefish skin, which layers two kinds of pattern: CHRONIC (minutes to
hours, identity and crypsis) and ACUTE (seconds, communication). Each Hermes session
gets a unique colour, a near-black mantle of its own, and a pronounceable name that
persist for its life; when the session needs you, an acute signal layers on top and
is released again afterwards, leaving the identity intact.

Transitions between those states are ANIMATED along curves measured in the animal
(Woo et al., Nature 619, 2023) — fast direct blanching, slower staggered recovery —
and the session is perfectly still in between.

The plugin entrypoint Hermes looks for is `register(ctx)`, re-exported here from
`cuttlefish_theme.plugin`.
"""

from .plugin import register

__all__ = ["register"]
__version__ = "0.4.0"
