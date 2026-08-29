"""Make `python -m unittest discover -s tests -t .` work on a fresh clone.

This is a src-layout package, so `tervatrix_rtl` is not importable from the
repository root until the package is installed. Rather than make the documented
test command depend on an install, put `src/` on the path here. An installed
copy still wins, because it is already in `sys.modules` by the time this runs in
that case - so this never shadows a real install.
"""

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
