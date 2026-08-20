"""modification_discovery -- find the modifications the compiler should emit.

``modifications`` is a NAMESPACE package (PEP 420): it is just the directory
``libraries/modifications/`` with NO ``__init__.py`` of its own. Each modification is
its OWN sub-directory with an ``__init__.py`` (kitty/, openbox/, gedit/, thunar/,
librewolf/, ...), and it is those sub-packages that are importable as
``from modifications import kitty`` etc. A directory WITHOUT an ``__init__.py`` is not a
package, so it is simply skipped -- which is exactly the "add or remove a modification by
creating/deleting its directory, and a half-finished/data-only directory never breaks the
build" contract.

Because ``modifications`` has no ``__init__.py``, the discovery helpers cannot live inside
it; they live here, as a flat sibling module in ``libraries/`` (imported bare, like
``compiler``/``paths``/``emit``). They scan the ``modifications/`` directory ON DISK for
sub-directories that contain an ``__init__.py`` and import those:

  * ``names()``     -- the modification names present, WITHOUT importing any.
  * ``discover()``  -- import each and return {name: module}, optionally filtered.
  * ``with_emit_plan()`` -- just the ones exposing an ``emit_plan()`` (the builder/dest/mode
    contract ``compiler.py`` iterates in ``_emit_apps``).

The compiler uses these so dropping a new ``modifications/<app>/__init__.py`` with an
``emit_plan()`` ships it with no edit to the compiler's import list, and removing one does
not leave a dangling ``import`` that aborts the build.

Note: a modification may legitimately expose different surfaces -- most define
``emit_plan()`` (the openbox/kitty/... builder contract), a few are data-only
(home_directory) or hold a vendored script the build copies verbatim (ckbcomp). Discovery
therefore just IMPORTS the sub-package; callers pick the attribute they need (and can filter
with ``discover(predicate=...)``).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Callable

# The modifications directory lives right next to this module (both under libraries/). This is
# the single place modifications are scanned from -- the namespace package's one directory.
_MODIFICATIONS_DIR = Path(__file__).resolve().parent / "modifications"
# Sub-packages import as ``modifications.<name>`` (the namespace package's name), regardless of
# how this flat helper module itself is imported.
_PKG_NAME = "modifications"


def names() -> list[str]:
    """Every modification present, as a sorted list of directory names, WITHOUT importing any.

    A directory counts as a modification only if it contains an ``__init__.py`` (so it is a
    real package that can be imported). Directories without one -- and ``__pycache__`` and any
    stray dunder dirs -- are skipped. This is the "add/remove a directory freely" contract:
    the list simply reflects whatever directories-with-__init__.py are on disk right now."""
    found = []
    for child in _MODIFICATIONS_DIR.iterdir():
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
