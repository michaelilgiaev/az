"""Allow `python -m packages.azarch ...` to run the CLI in-place (dev/testing).

The SHIPPED artifact is always the single bundled script (bundle.bundle_source(), installed
to /usr/local/bin/azarch). This entry point just wires the split package's cli.main() so the
CLI is runnable from the source tree without bundling first.
"""

from __future__ import annotations

import sys

# The split source modules assume ONE namespace (they call helpers by bare name, matching
# how they are bundled). To honour that when running from the package, execute the bundle
# text in a single namespace rather than importing each module separately.
from .bundle import bundle_source

if __name__ == "__main__":
    ns: dict = {"__name__": "__azarch_main__"}
    exec(compile(bundle_source(), "azarch-bundle", "exec"), ns)
    sys.exit(ns["main"]())
