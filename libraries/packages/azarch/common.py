#!/usr/bin/env python3
"""azarch guest command line interface -- shared imports + tiny privileged/host helpers.

This is the FIRST module of the `azarch` guest-CLI package (libraries/packages/azarch/).
The package is split across several small modules for maintainability (common, resolver,
theme, sshd, command_line_interface), but the thing that actually ships to the guest is a SINGLE
self-contained script at /usr/local/bin/azarch: packages.openbox.azarch_command_line_interface() BUNDLES these
modules -- in the order packages.azarch.bundle.MODULE_ORDER -- into one file (this module's
imports/header first, then each later module's body after its `# BUNDLE_START` sentinel).
So everything below lands in ONE module namespace at runtime; that is why the later modules
call these helpers by bare name with no intra-package import.

Only the standard library is used (urllib + json for the geolocation query; subprocess for
the privileged steps). No curl/jq, no pip packages. NOTE: urllib.request and random are
imported LAZILY where they are used (resolver.py), NOT here in the shared header -- so the
bare `azarch` fast path (which execs the C terminal user interface) never pays their import cost at startup.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# BUNDLE_START -- everything ABOVE this line is the bundle header (shebang + docstring +
# imports), emitted once from THIS module; the bundler drops each later module's own
# header and keeps only what follows its `# BUNDLE_START`.


def _err(msg: str) -> None:
    """Print to stderr (stdout stays result-only, matching the old command line interface)."""
    print(msg, file=sys.stderr)


def _sudo(*args: str, check: bool = True) -> int:
    """Run a command under sudo (or directly if already root). Returns the exit
    code; raises subprocess.CalledProcessError when check and the command fails."""
    prefix: list[str] = [] if os.geteuid() == 0 else ["sudo"]
    return subprocess.run([*prefix, *args], check=check).returncode


def _have(prog: str) -> bool:
    return any(os.access(os.path.join(d, prog), os.X_OK)
               for d in os.environ.get("PATH", "").split(os.pathsep) if d)


def _sudo_write(path: str, content: str) -> None:
    """Write `content` to a root-owned file via `sudo tee` (works unprivileged)."""
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    subprocess.run([*prefix, "tee", path], input=content.encode(),
                   stdout=subprocess.DEVNULL, check=False)


def _sudo_write_append(path: str, content: str) -> None:
    """Append `content` to a root-owned file via `sudo tee -a`."""
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    subprocess.run([*prefix, "tee", "-a", path], input=content.encode(),
                   stdout=subprocess.DEVNULL, check=False)


def _current_user() -> str:
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return os.environ.get("USER", "")


def _is_mountpoint(path: str) -> bool:
    return subprocess.run(["mountpoint", "-q", path],
                          stderr=subprocess.DEVNULL).returncode == 0
