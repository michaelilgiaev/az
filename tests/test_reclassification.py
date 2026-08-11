"""Lock in the libraries/ classification the reclassification established.

The three buckets have a precise, load-bearing meaning that a future edit could
silently violate:

  libraries/            the COMPILER's own modules (flat) + the entry point
  libraries/packages/   Az'arch's OWN packages (things WE build/ship)
  libraries/patches/    ONLY upstream software we modify/configure

Two of these are also a genuine IMPORT hazard: the compiler's package-cache module
is `downloader` (was `packages.py`) precisely so the payload `packages/` directory
can be a real import package (`packages.pkgbuild`, `packages.application_menu`)
without the module shadowing the directory (or vice versa). If someone renames
`downloader.py` back to `packages.py`, both imports below break. These tests catch
that, and the "patches holds only upstream" invariant, at unit-test time.
"""

from __future__ import annotations

import paths


def test_downloader_and_packages_dir_coexist():
    # The package-cache module is `downloader` (a flat compiler module) so the
    # `packages/` payload dir can be a real import package. Both must resolve.
    import downloader  # the renamed package-cache module (was packages.py)
    from packages import pkgbuild  # noqa: F401  (payload package, not the module)

    assert downloader.__file__.endswith("libraries/downloader.py")
    # `packages` here is the payload directory-package, NOT downloader.
    import packages as payload_pkg
    assert payload_pkg.__file__.endswith("libraries/packages/__init__.py")


def test_our_packages_import_from_packages_bucket():
    # pkgbuild recipes and the application-menu build wiring are OUR packages, so
    # they import from packages.* (not patches.*).
    from packages.pkgbuild import pkgbuild
    from packages.application_menu import application_menu

    assert callable(pkgbuild.recipe_dirs)
    assert callable(application_menu.emit_plan)


def test_patches_bucket_holds_only_upstream():
    # After the reclassification, libraries/patches/ contains ONLY upstream software
    # we modify/configure. Anything WE author outright must have left it.
    patches = paths.PATCHESDIR
    present = {p.name for p in patches.iterdir() if p.is_dir()}
    # genuine upstream we tailor:
    assert {"calamares", "ckbcomp", "fastfetch", "openbox"} <= present
    # our-own things that must NOT be under patches/ anymore:
    for ours in ("application_menu", "pkgbuild", "profile", "pacman", "installer",
                 "system", "desktop", "locale"):
        assert ours not in present, f"{ours} is OURS -- it must not be a patch package"


def test_locale_moved_into_calamares_patch():
    # locale.py is Calamares install-time config, so it lives with the calamares patch.
    from patches.calamares import locale

    assert locale.__file__.endswith("libraries/patches/calamares/locale.py")
    assert callable(locale.resolver_country_table_py)


def test_openbox_replaced_desktop():
    # desktop.py was renamed openbox.py (it configures the upstream openbox WM) and
    # stays under patches/. The old patches.desktop must be gone.
    from patches.openbox import openbox

    assert openbox.__file__.endswith("libraries/patches/openbox/openbox.py")
    assert callable(openbox.emit_plan)


def test_compiler_is_the_entry_point():
    # build.py was cannibalized into compiler.py, so `python3 -m compiler` is the
    # entry point: compiler must own BOTH the step sequencer and the driver's main().
    import compiler

    assert compiler.__file__.endswith("libraries/compiler.py")
    assert callable(compiler.main)          # the folded-in driver
    assert callable(compiler.run)           # the step sequencer
    assert callable(compiler.cache_is_complete)
