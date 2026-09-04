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

import pytest

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

# The tests/ dir is now on the path, so the test-mode helper (which lives beside this file)
# imports cleanly.
import _testmodes  # noqa: E402  (import after the sys.path setup above, by design)


def pytest_collection_modifyitems(config, items):
    """Skip the privileged test tiers unless their mode is enabled in tests/test_modes.conf.

    Two independent booleans gate two tiers; both default OFF so a plain `bash tests.sh` is green
    with no connectivity and no sudo. We SKIP (not deselect) so the logs still SHOW the gated tests
    as `s` -- visibly not-run, not silently vanished. Modes come from tests/test_modes.conf (env
    vars override); flip them with `tests.sh --online/--offline` (network) and `tests.sh
    --user/--root` (root). See tests/_testmodes.py for the parser and precedence.

    - `network`: OFFLINE (default) skips it -- those tests reach a real host and a plain run must
      stay green with no connectivity and NEVER hang on a DNS lookup. ONLINE runs them. (The
      network tests ALSO keep their own inline reachability probe as a second layer of defence.)
    - `root`: USER (default) skips it. ROOT selects it -- the two calamares btrfs loop-mount tests
      then run IF the process is actually UID 0, else self-skip via their own `os.geteuid()` guard.
    """
    marks = []
    if _testmodes.is_offline():
        marks.append(("network",
                      pytest.mark.skip(reason="offline mode (tests.sh --offline); run with tests.sh --online")))
    if _testmodes.is_user():
        marks.append(("root",
                      pytest.mark.skip(reason="user mode (tests.sh --user); run with tests.sh --root")))
    if not marks:
        return
    for item in items:
        for keyword, skip in marks:
            if keyword in item.keywords:
                item.add_marker(skip)
