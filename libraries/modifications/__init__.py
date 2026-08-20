"""modifications - upstream software Az'arch modifies/configures, as a discoverable package.

Every modification is its OWN DIRECTORY with an ``__init__.py`` (kitty/, openbox/, gedit/,
thunar/, librewolf/, ...). The package is deliberately built so the set of modifications is
DISCOVERED at runtime rather than hard-coded: you can add or remove a modification by simply
adding or deleting its directory, and

  * a directory that HAS an ``__init__.py`` is loaded as a modification, and
  * a directory that does NOT have an ``__init__.py`` is SKIPPED (so a half-finished or
    data-only directory never breaks the import / the build).

``discover()`` returns the loaded modification modules keyed by name; ``names()`` lists what
is present without importing. The compiler uses these so dropping a new ``modifications/foo/``
with an ``__init__.py`` is picked up with no edit to the compiler's import list, and removing
one does not leave a dangling ``import`` that aborts the build.

Note: a modification may legitimately expose different surfaces -- most define ``emit_plan()``
(the openbox/kitty/... builder contract), a few are data-only (home_directory) or hold a
vendored script the build copies verbatim (ckbcomp). Discovery therefore just IMPORTS the
package; callers pick the attribute they need (and can filter with ``discover(predicate=...)``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Callable

# The directory this package lives in -- the single place modifications are scanned from.
_PKG_DIR = Path(__file__).resolve().parent
_PKG_NAME = __name__  # "modifications"


def names() -> list[str]:
    """Every modification present, as a sorted list of directory names, WITHOUT importing any.

    A directory counts as a modification only if it contains an ``__init__.py`` (so it is a
    real package that can be imported). Directories without one -- and ``__pycache__`` and any
    stray dunder dirs -- are skipped. This is the "add/remove a directory freely" contract:
    the list simply reflects whatever directories-with-__init__.py are on disk right now."""
    found = []
    for child in _PKG_DIR.iterdir():
        if not child.is_dir():
            continue
        if child.name.startswith("__"):        # __pycache__ and the like
            continue
        if not (child / "__init__.py").is_file():
            continue                            # no __init__.py -> skip (not a package)
        found.append(child.name)
    return sorted(found)


def discover(predicate: Callable[[ModuleType], bool] | None = None) -> dict[str, ModuleType]:
    """Import every modification package and return {name: module}, skipping any directory
    without an ``__init__.py``.

    A directory that lacks ``__init__.py`` is silently skipped (see the module docstring):
    this is what lets a modification be added or removed just by creating/deleting its
    directory, with the compiler never tripping over a missing or extra one.

    predicate: optional filter run on each imported module; only modules for which it returns
    True are included (e.g. ``lambda m: hasattr(m, "emit_plan")`` to get just the builders)."""
    modules: dict[str, ModuleType] = {}
    for name in names():
        module = importlib.import_module(f"{_PKG_NAME}.{name}")
        if predicate is None or predicate(module):
            modules[name] = module
    return modules


def with_emit_plan() -> dict[str, ModuleType]:
    """The modifications that expose an ``emit_plan()`` (the builder/dest/mode contract the
    compiler iterates to write configuration files). A convenience wrapper over discover()."""
    return discover(lambda m: callable(getattr(m, "emit_plan", None)))
