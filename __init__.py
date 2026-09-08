"""chromatophore — ambient session identity and state signalling for Hermes.

Modelled on cuttlefish, which layer two kinds of pattern: CHRONIC (minutes to hours,
identity and crypsis) and ACUTE (seconds, communication). Each Hermes session gets a
unique colour and a pronounceable name that persist for its life; when the session
needs you, an acute signal layers on top and is released again afterwards, leaving
the identity intact.

The plugin entrypoint Hermes looks for is `register(ctx)`, re-exported here from
`chromatophore.plugin`.
"""

from chromatophore.plugin import register

__all__ = ["register"]
__version__ = "0.1.0"
