"""Entry point so `python -m packages.hypervisor` runs the CLI (handy for tests and
local runs). The SHIPPED command is the /usr/local/bin/hypervisor launcher, which
execs cli.py directly (see packaging.py); this module makes the package runnable as a
module too. Uses a package-relative import (this file only runs when the dir IS loaded
as the `packages.hypervisor` package, so `.cli` resolves)."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
