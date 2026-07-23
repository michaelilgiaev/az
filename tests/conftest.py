"""Shared pytest fixtures + import-path setup for the azarch test suite.

`bash tests.sh` already puts libraries/ and scripts/libraries/ on PYTHONPATH, and
pyproject.toml's [tool.pytest.ini_options] pythonpath does the same for a bare
`pytest` run. This conftest belt-and-suspenders it so `import azarch.*` and the
flat `spec_*` modules resolve no matter how the tests are launched.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO / "libraries", REPO / "scripts" / "libraries"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)
