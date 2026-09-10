"""Render the v6 six-session × three-signal frame preview."""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFont
import conftest  # noqa: F401
from cuttlefish_theme.color.identity import allocate
from cuttlefish_theme.mantle import mantle_rows
from cuttlefish_theme.linework import separator
from cuttlefish_theme.pattern import render
from cuttlefish_theme.session import Signal
ANSI = re.compile(r'\x1b\[38;2;(\d+);(\d+);(\d+)m\x1b\[48;2;(\d+);(\d+);(\d+)m\u2580')
SIDS = ['alpha','bravo','charlie','delta','echo','foxtrot']
SIGS = [Signal.RESTING, Signal.NEEDS_ME, Signal.FAULT]
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf', 12)
cell = 5; panel_w, panel_h = 30*cell, 15*cell+32
img = Image.new('RGB', (len(SIGS)*panel_w+40, len(SIDS)*panel_h+30), (8,8,14)); d=ImageDraw.Draw(img)
for r, sid in enumerate(SIDS):
  for c, sig in enumerate(SIGS):
    p=render(allocate(sid),sig); ansi=mantle_rows(sid,p.identity_hex,p.sheen_hex,p.ground_hex,acute_hex=p.acute_hex,markup=False)
    x0=20+c*panel_w; y0=20+r*panel_h
    for yy,line in enumerate(ansi.splitlines()):
      for xx,m in enumerate(ANSI.finditer(line)):
        vals=tuple(map(int,m.groups())); d.rectangle((x0+xx*cell,y0+yy*cell,x0+(xx+1)*cell-1,y0+(yy+1)*cell-1),fill=vals[:3])
    d.text((x0,y0+15*cell+2),f'{sid} / {sig.value[:4]}',font=font,fill=(225,225,232))
img.save('docs/preview-v6.png')
print('wrote docs/preview-v6.png')
