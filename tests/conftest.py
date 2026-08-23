"""Shared pytest fixtures + import-path setup for the azarch test suite.

`bash tests.sh` already puts libraries/ and scripts/libraries/ on PYTHONPATH, and
pyproject.toml's [tool.pytest.ini_options] pythonpath does the same for a bare
`pytest` run. This conftest belt-and-suspenders it so the flat compiler modules
(build, paths, ...), the packages.* packages, and the flat specification_* modules
resolve no matter how the tests are launched.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO / "libraries", REPO / "scripts" / "libraries"):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

# Also put THIS tests/ dir on the path so a test module can import a shared, test-only
# helper module that sits beside it (e.g. `from hypervisor_helpers import make_cfg`).
# Under pytest's importlib import mode the rootdir's tests/ dir is NOT added implicitly,
# so without this a sibling-helper import fails with ModuleNotFoundError. conftest is
# imported before any test module, so this runs early enough for every test.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
