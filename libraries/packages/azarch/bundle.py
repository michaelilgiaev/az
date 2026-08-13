"""Bundle the `azarch` guest-CLI package into ONE self-contained script.

The `azarch` CLI source is split across several small modules under this package
(libraries/packages/azarch/) for maintainability, but the artifact that ships to the guest
is a SINGLE file at /usr/local/bin/azarch: it must be one runnable Python script (a lone
executable at a path, not an importable package). This module reassembles the split source
into that single script.

HOW THE BUNDLE IS BUILT. Every source module has, right after its imports, a line:

    # BUNDLE_START

`bundle_source()` emits:
  * the HEADER of the first module (common.py) -- its shebang, module docstring, and all
    imports, i.e. everything UP TO AND INCLUDING its `# BUNDLE_START` line -- once; then
  * the BODY of each module in MODULE_ORDER -- everything AFTER that module's `# BUNDLE_START`
    line -- concatenated in order.

Because the result is one module namespace, the later modules reference the shared helpers
and the country table by bare name (no intra-package imports), which is exactly how they are
written. The order is chosen so every name is defined before it is used at IMPORT time
(definitions only; nothing runs until main() is called at the very end via cli.py).

modifications.openbox.azarch_cli() calls bundle_source() and then re-injects the country table
between the AZARCH_CC markers from the single source of truth (modifications/calamares/locale).
"""

from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent

# The bundle order. common.py FIRST (its header becomes the whole script's preamble), then
# the data + feature modules (definitions), then cli.py LAST (usage/main + the __main__
# guard that actually runs it). Every module must contain a `# BUNDLE_START` marker.
MODULE_ORDER = [
    "common.py",
    "country_table.py",
    "resolver.py",
    "theme.py",
    "wallpaper.py",
    "sshd.py",
    "cli.py",
]

_MARKER = "# BUNDLE_START"


def _split(src: str, name: str) -> tuple[str, str]:
    """Split a module's source at its `# BUNDLE_START` marker into (header, body).

    header = everything up to AND INCLUDING the marker line; body = everything after it.
    The marker MUST be present (each package module carries one) -- a missing marker is a
    packaging bug, so raise loudly rather than silently mis-bundling."""
    idx = src.find(_MARKER)
    if idx == -1:
        raise ValueError(f"azarch bundle: module {name} has no {_MARKER!r} marker")
    # Include the rest of the marker line in the header.
    line_end = src.find("\n", idx)
    if line_end == -1:
        return src, ""
    return src[: line_end + 1], src[line_end + 1:]


def bundle_source() -> str:
    """Return the single self-contained /usr/local/bin/azarch script text (with the
    on-disk country table; modifications.openbox.azarch_cli re-injects the canonical one)."""
    parts: list[str] = []
    for i, mod in enumerate(MODULE_ORDER):
        src = (_PKG_DIR / mod).read_text(encoding="utf-8")
        header, body = _split(src, mod)
        if i == 0:
            # First module's header (shebang + docstring + imports) is the script preamble.
            parts.append(header.rstrip("\n"))
            parts.append("")
            parts.append(f"# --- bundled from {mod} ---")
            parts.append(body.strip("\n"))
        else:
            parts.append("")
            parts.append(f"# --- bundled from {mod} ---")
            parts.append(body.strip("\n"))
    return "\n".join(parts).rstrip("\n") + "\n"
