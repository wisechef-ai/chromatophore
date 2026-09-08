"""Make the repo importable as the `chromatophore` package during tests.

Hermes loads a plugin directory AS the package (the directory name is the module
name), so the package root is this repo root. Tests therefore need the PARENT
directory on sys.path to `import chromatophore`, which is what this adds.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
