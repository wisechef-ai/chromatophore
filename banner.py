"""Chromatophore-coloured Hermes wordmark."""
from __future__ import annotations
from .color.oklab import OKLCh, hex_to_oklch, oklch_to_hex
from .palette import PIGMENTS, dominant_pigments
from .seed import seed_for

_LOGO_ROWS = (
    "██╗  ██╗███████╗██████╗ ███╗   ███╗███████╗███████╗       █████╗  ██████╗ ███████╗███╗   ██╗████████╗",
    "██║  ██║██╔════╝██╔══██╗████╗ ████║██╔════╝██╔════╝      ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝",
    "███████║█████╗  ██████╔╝██╔████╔██║█████╗  ███████╗█████╗███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║",
    "██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██╔══╝  ╚════██║╚════╝██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║",
    "██║  ██║███████╗██║  ██║██║ ╚═╝ ██║███████╗███████║      ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║",
    "╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝╚══════╝      ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝",
)

def banner_logo(identity_hex: str, session_id: str = '') -> str:
    identity = hex_to_oklch(identity_hex)
    names = dominant_pigments(session_id or identity_hex)
    hues = [PIGMENTS[n] for n in names]
    # Identity remains in the mix, while each active cell gets a discrete pigment.
    colors = [oklch_to_hex(OKLCh(.62 + .05*(i%2), min(.20, max(.12, identity.C)), h if h is not None else identity.h)) for i,h in enumerate(hues)]
    seed = seed_for(session_id or identity_hex)
    lines=[]
    for y,row in enumerate(_LOGO_ROWS):
        out=[]
        for x,ch in enumerate(row):
            if ch == ' ':
                out.append(ch)
            else:
                color=colors[(seed + x*13 + y*7) % len(colors)]
                if (x + y) == 0:
                    # Keep same pigment layout while making session re-inking visible.
                    color = oklch_to_hex(OKLCh(.64, min(.20, max(.12, identity.C)), (PIGMENTS[names[0]] + seed % 29) % 360))
                out.append(f'[{color}]{ch}[/]')
        lines.append(''.join(out))
    return '\n'.join(lines)

__all__ = ['banner_logo']
