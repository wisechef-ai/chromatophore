# tools/

Development instruments, not part of the plugin. They live here rather than in
the package root because Hermes imports the plugin DIRECTORY as the package, so
anything at the root is shipped and imported at session start.

| script | what it answers |
|---|---|
| `sample_photos.py` | What does a real cuttlefish actually measure? Samples OKLCh statistics from photographs of *Metasepia pfefferi* in display. Every colour constant in `palette.py` and `field.py` traces back to its output. |
| `render_chat.py` | Does the theme reach the whole UI? Renders a mock chat screen from the REAL resolved style dict, so an ignored key shows up as stock gold. |
| `render_preview.py` | Does the pixel field look like skin? Rasterises the field and the transition curves to PNG, using the same compositor as the terminal. |
| `record_demo_gif.py` | **The README GIF.** Records a real `hermes` session on a pty and replays the captured bytes through a small terminal emulator. If a colour is not on screen it cannot be in the GIF. |
| `render_demo_gif.py` | *(superseded)* Composed the GIF from a mock chat layout. It could look perfect while the real terminal painted stock gold — which is what happened for four releases. Kept only as the palette-story renderer. |

Run from the repo root:

```bash
python3 tools/sample_photos.py     # needs /tmp/cfphotos/*.jpg
python3 tools/render_chat.py       # needs the Hermes venv
python3 tools/render_preview.py
python3 tools/render_demo_gif.py  # -> /tmp/cuttlefish-demo.gif, copy to docs/demo.gif
```

Regenerate `docs/` after any palette change, or the README will advertise a theme
that no longer exists.
