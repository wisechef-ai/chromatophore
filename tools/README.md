# tools/

Development instruments, not part of the plugin. They live here rather than in
the package root because Hermes imports the plugin DIRECTORY as the package, so
anything at the root is shipped and imported at session start.

| script | what it answers |
|---|---|
| `sample_photos.py` | What does a real cuttlefish actually measure? Samples OKLCh statistics from photographs of *Metasepia pfefferi* in display. Every colour constant in `palette.py` and `field.py` traces back to its output. |
| `render_chat.py` | Does the theme reach the whole UI? Renders a mock chat screen from the REAL resolved style dict, so an ignored key shows up as stock gold. |
| `render_preview.py` | Does the pixel field look like skin? Rasterises the field and the transition curves to PNG, using the same compositor as the terminal. |

Run from the repo root:

```bash
python3 tools/sample_photos.py     # needs /tmp/cfphotos/*.jpg
python3 tools/render_chat.py       # needs the Hermes venv
python3 tools/render_preview.py
```
