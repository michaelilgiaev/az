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

`packages/` carries no `__init__.py` -- it (like `modifications/`) is an implicit
namespace package, resolved off PYTHONPATH (= libraries/). The flat module
`packages/pkgbuild.py` imports as `packages.pkgbuild`; the `azarch` guest CLI grew a
`theme` subcommand and became a REGULAR sub-package (`packages/azarch/` with its own
__init__.py), importing as `packages.azarch` -- both resolve under the namespace
`packages` (which itself still has no top-level __init__.py).
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


def test_modifications_bucket_holds_only_upstream():
    # After the reclassification, libraries/modifications/ contains ONLY upstream software
    # we modify/configure. Anything WE author outright must have left it.
    #
    # The single-file modifications (ckbcomp/fastfetch/librewolf/openbox) were FLATTENED from a
    # one-file dir (modifications/openbox/openbox.py) to a flat module (modifications/openbox.py),
    # mirroring the earlier azarch/pkgbuild flattening. calamares stays a dir (genuinely
    # multi-module: calamares.py + locale.py + calamares_shellprocess.py); librewolf is a
    # single file (just librewolf.py), so it is a flat module too -- it must NOT be left
    # as a one-file dir (that inconsistency was a regression).
    modifications_dir = paths.MODIFICATIONSDIR
    names = {p.name for p in modifications_dir.iterdir()}
    dirs = {p.name for p in modifications_dir.iterdir() if p.is_dir()}
    # ONLY genuinely multi-module upstream modifications stay as directories:
    assert "calamares" in dirs
    assert "librewolf" not in dirs, (
        "librewolf is a single-file modification -- it must be a flat module "
        "(modifications/librewolf.py), not a one-file dir"
    )
    # flattened single-file upstream modifications are now flat modules (files), not dirs:
    for flat in ("ckbcomp.py", "fastfetch.py", "librewolf.py", "openbox.py"):
        assert flat in names, f"{flat} should be a flat modification module"
        assert (paths.MODIFICATIONSDIR / flat).is_file()
        assert flat[:-3] not in dirs, f"{flat[:-3]}/ dir should be gone after flattening"
    # our-own things that must NOT be under modifications/ anymore:
    for ours in ("application_menu", "pkgbuild", "profile", "pacman", "installer",
                 "system", "desktop", "locale"):
        assert ours not in names, f"{ours} is OURS -- it must not be a modification package"


def test_locale_moved_into_calamares_modification():
    # locale.py is Calamares install-time config, so it lives with the calamares modification.
    from modifications.calamares import locale

    assert locale.__file__.endswith("libraries/modifications/calamares/locale.py")
    assert callable(locale.resolver_country_table_py)


def test_openbox_replaced_desktop():
    # desktop.py was renamed openbox.py (it configures the upstream openbox WM) and
    # stays under modifications/. It was then FLATTENED from modifications/openbox/openbox.py to a
    # flat module modifications/openbox.py, so it imports as `from modifications import openbox`.
    # The old modifications.desktop AND the nested modifications.openbox.openbox must be gone.
    from modifications import openbox

    assert openbox.__file__.endswith("libraries/modifications/openbox.py")
    assert callable(openbox.emit_plan)


def test_compiler_is_the_entry_point():
    # build.py was cannibalized into compiler.py, so `python3 -m compiler` is the
    # entry point: compiler must own BOTH the step sequencer and the driver's main().
    import compiler

    assert compiler.__file__.endswith("libraries/compiler.py")
    assert callable(compiler.main)          # the folded-in driver
    assert callable(compiler.run)           # the step sequencer
    assert callable(compiler.cache_is_complete)
