"""Lock in the libraries/ classification the reclassification established.

The three buckets have a precise, load-bearing meaning that a future edit could
silently violate:

  libraries/            the COMPILER's own modules (flat) + the entry point
  libraries/packages/   Az'arch's OWN packages (things WE build/ship)
  libraries/modifications/    ONLY upstream software we modify/configure

Two of these are also a genuine IMPORT hazard: the compiler's package-cache module
is `downloader` (was `packages.py`) precisely so the payload `packages/` directory
can be a real import package (`packages.pkgbuild`, `packages.application_menu`)
without the module shadowing the directory (or vice versa). If someone renames
`downloader.py` back to `packages.py`, both imports below break. These tests catch
that, and the "modifications holds only upstream" invariant, at unit-test time.

`packages/` carries no top-level `__init__.py` -- it is an implicit namespace package,
resolved off PYTHONPATH (= libraries/). The flat module `packages/pkgbuild.py` imports
as `packages.pkgbuild`. Every SUB-directory of packages/, however, is now a REGULAR
package with its own `__init__.py` (application_menu/, azarch/, calamares/, passwords/,
timedate/) -- they resolve under the namespace `packages`. `modifications/` DOES carry a
top-level `__init__.py` (its discovery machinery), and every modification is likewise a
regular package directory with an `__init__.py`.
"""

from __future__ import annotations

import paths


def test_downloader_and_packages_dir_coexist():
    # The package-cache module is `downloader` (a flat compiler module) so the
    # `packages/` payload dir can be a real import package. Both must resolve.
    import downloader  # the renamed package-cache module (was packages.py)
    from packages import pkgbuild  # noqa: F401  (payload package, not the module)

    assert downloader.__file__.endswith("libraries/downloader.py")
    # `packages` here is the payload directory-package, NOT downloader. It carries
    # no __init__.py (implicit namespace package), so `__file__` is None and its
    # search path points at libraries/packages/.
    import packages as payload_pkg
    assert payload_pkg.__file__ is None
    assert any(p.endswith("libraries/packages") for p in payload_pkg.__path__)


def test_our_packages_import_from_packages_bucket():
    # pkgbuild recipes and the application-menu build wiring are OUR packages, so
    # they import from packages.* (not modifications.*). pkgbuild is now a flat module
    # (packages/pkgbuild.py); application_menu stays a multi-module subpackage.
    from packages import pkgbuild
    from packages.application_menu import application_menu

    assert pkgbuild.__file__.endswith("libraries/packages/pkgbuild.py")
    assert callable(pkgbuild.recipe_dirs)
    assert callable(application_menu.emit_plan)


def test_every_packages_subdirectory_is_a_regular_package():
    # Every SUB-directory of libraries/packages/ must carry an __init__.py so it is a real,
    # importable package (application_menu, azarch, calamares, passwords, timedate, ...). This
    # is the packages-side counterpart of the modifications "each dir is a package" rule.
    packages_dir = paths.PACKAGESDIR
    for child in packages_dir.iterdir():
        if not child.is_dir() or child.name.startswith("__"):
            continue
        assert (child / "__init__.py").is_file(), (
            f"packages/{child.name}/ must have an __init__.py (every packages subdirectory "
            "is a regular package)"
        )
    # The critically-modified calamares install config is one of OUR packages now.
    assert (packages_dir / "calamares" / "__init__.py").is_file()


def test_modifications_bucket_holds_only_upstream():
    # After the reclassification, libraries/modifications/ contains ONLY upstream software
    # we modify/configure. Anything WE author outright must have left it.
    #
    # Each modification is now a DIRECTORY MODULE with an __init__.py: the modifications tree
    # is a discoverable package where a dir with an __init__.py loads and a dir without one is
    # skipped, so modifications can be added/removed freely. calamares is NOT here anymore --
    # it is a critically-modified package we compile from source and ship, so it lives under
    # packages/ (packages/calamares/), not modifications/.
    modifications_dir = paths.MODIFICATIONSDIR
    names = {p.name for p in modifications_dir.iterdir()}
    dirs = {p.name for p in modifications_dir.iterdir() if p.is_dir()}
    # calamares moved OUT of modifications/ into packages/.
    assert "calamares" not in names, "calamares is now a package (packages/calamares/), not a modification"
    # The per-app modifications are directory modules (each with an __init__.py):
    for mod in ("ckbcomp", "fastfetch", "librewolf", "openbox", "kitty", "gedit", "thunar"):
        assert mod in dirs, f"{mod} should be a modification directory module"
        assert (paths.MODIFICATIONSDIR / mod / "__init__.py").is_file(), (
            f"{mod}/__init__.py must exist so the modification loads"
        )
    # No stray flat modification .py modules at the top of modifications/ -- every modification
    # is a directory now. The package's own __init__.py (the discovery machinery) is the only
    # .py allowed directly here.
    stray = {n for n in names if n.endswith(".py") and n != "__init__.py"}
    assert not stray, f"modifications/ should hold only directory modules, found flat files: {stray}"
    # our-own things that must NOT be under modifications/ anymore:
    for ours in ("application_menu", "pkgbuild", "profile", "pacman", "installer",
                 "system", "desktop", "locale", "calamares"):
        assert ours not in names, f"{ours} is OURS -- it must not be a modification package"


def test_locale_lives_with_the_calamares_package():
    # locale.py is Calamares install-time config, so it lives with the calamares package
    # (which moved out of modifications/ into packages/ -- calamares is a critically-modified
    # package we compile from source and ship, not a plain upstream modification).
    from packages.calamares import locale

    assert locale.__file__.endswith("libraries/packages/calamares/locale.py")
    assert callable(locale.resolver_country_table_py)


def test_openbox_replaced_desktop():
    # desktop.py was renamed openbox.py (it configures the upstream openbox WM) and stays under
    # modifications/. Every modification is a DIRECTORY MODULE now, so openbox lives at
    # modifications/openbox/__init__.py and still imports as `from modifications import openbox`.
    # The old modifications.desktop must be gone.
    from modifications import openbox

    assert openbox.__file__.endswith("libraries/modifications/openbox/__init__.py")
    assert callable(openbox.emit_plan)


def test_compiler_is_the_entry_point():
    # build.py was cannibalized into compiler.py, so `python3 -m compiler` is the
    # entry point: compiler must own BOTH the step sequencer and the driver's main().
    import compiler

    assert compiler.__file__.endswith("libraries/compiler.py")
    assert callable(compiler.main)          # the folded-in driver
    assert callable(compiler.run)           # the step sequencer
    assert callable(compiler.cache_is_complete)
