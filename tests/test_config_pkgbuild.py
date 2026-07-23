"""azarch.config.pkgbuild -- the Az'arch-authored package recipes.

These PKGBUILDs are Python f-strings emitted to disk and then fed verbatim to
makepkg. Two failure modes here are silent and expensive:

  1. A wrong version literal. LibreWolf has TWO version strings that look almost
     identical -- the upstream tag "153.0-1" (used to build the download URL and
     the source filename) and the pacman-legal pkgver "153.0.1" (the '-' is a
     pkgrel separator, illegal in pkgver). Swap them and makepkg either 404s the
     download or rejects the version; nothing in Python catches it because both
     are valid strings.

  2. A broken sha256sums / SKIP alignment. makepkg matches each checksum to the
     corresponding source() entry by position. The repackage tier has one real
     hash + three 'SKIP's (tarball hashed, .sig GPG-checked, two local files);
     the from-source tier has three 'SKIP's and no pinned hash at all. An
     off-by-one in that tuple makes makepkg verify the wrong file.

  3. f-string brace-doubling. Every literal shell brace in these recipes is
     written '{{'/'}}' so the f-string collapses it to a single '{'/'}'. A
     missed doubling leaks a stray brace (or an f-string ValueError at import).
     These tests assert no '{{'/'}}' survives into the emitted text.

  4. Tier dispatch. recipe_dirs(full_compile) decides which recipes are emitted:
     BOTH tiers build calamares (from source -- Arch dropped extra/calamares) and
     librewolf. The DEFAULT tier repackages librewolf; --full-compile swaps in the
     from-source librewolf recipe. The set of packages is the same in both tiers.

Pure string logic -- no filesystem, no network, no makepkg invoked.
"""

from __future__ import annotations

import re

from azarch.config import pkgbuild


_HEX = re.compile(r"\A[0-9a-fA-F]+\Z")


# --- pinned upstream constants ---------------------------------------------

def test_version_constants_distinct():
    # The two LibreWolf version strings must never be equal: the '-1' tag form
    # and the '.1' pkgver form are used in different, non-interchangeable places.
    assert pkgbuild.LIBREWOLF_VERSION == "153.0-1"
    assert pkgbuild.LIBREWOLF_PKGVER == "153.0.1"
    assert pkgbuild.LIBREWOLF_VERSION != pkgbuild.LIBREWOLF_PKGVER


def test_pgp_key_is_40_hex_chars():
    # makepkg's validpgpkeys=() needs a full 40-char primary key fingerprint.
    key = pkgbuild.LIBREWOLF_PGP_KEY
    assert len(key) == 40
    assert _HEX.match(key)


def test_sha256_constants_are_64_hex():
    # A sha256 is exactly 32 bytes = 64 hex chars; a wrong length would be a
    # truncated/pasted-over hash that makepkg would reject on every build.
    for h in (pkgbuild.LIBREWOLF_SHA256, pkgbuild.CALAMARES_SHA256):
        assert len(h) == 64
        assert _HEX.match(h)


def test_calamares_version_literal():
    assert pkgbuild.CALAMARES_VERSION == "3.4.2"


# --- pkgbuild_librewolf (DEFAULT / repackage tier) -------------------------

def test_librewolf_pkgver_field_correct():
    # The pkgver= field must carry the pacman-legal "153.0.1", NOT the tag form.
    # _lwver= carries the tag form "153.0-1" for URL/filename construction.
    s = pkgbuild.pkgbuild_librewolf()
    assert "pkgver=153.0.1" in s
    assert "pkgver=153.0-1" not in s
    assert "_lwver=153.0-1" in s


def test_librewolf_sha256sums_shape():
    # One real hash then three 'SKIP's: tarball hashed, .sig GPG-checked (SKIP),
    # two shipped-in-repo local files (SKIP each).
    s = pkgbuild.pkgbuild_librewolf()
    assert (
        "sha256sums=('%s' 'SKIP' 'SKIP' 'SKIP')" % pkgbuild.LIBREWOLF_SHA256
    ) in s
    assert s.count("'SKIP'") == 3


def test_librewolf_validpgpkeys_present():
    # The repackage tier GPG-verifies the tarball, so the primary key must be
    # pinned in validpgpkeys=().
    s = pkgbuild.pkgbuild_librewolf()
    assert ("validpgpkeys=('%s')" % pkgbuild.LIBREWOLF_PGP_KEY) in s


def test_librewolf_repackage_has_no_make_fetch():
    # The repackage tier just unpacks the prebuilt tarball; it never runs the
    # bsys6 make targets. Their presence would mean the from-source recipe leaked.
    s = pkgbuild.pkgbuild_librewolf()
    assert "make fetch" not in s
    assert "make build" not in s


def test_librewolf_download_url_uses_tag_version():
    # The download host path and source filename are built from the tag form.
    s = pkgbuild.pkgbuild_librewolf()
    assert "https://dl.librewolf.net/librewolf/153.0-1" in s
    assert "librewolf-153.0-1-linux-x86_64-package.tar.xz" in s


# --- pkgbuild_librewolf_src (FULL / from-source tier) ----------------------

def test_librewolf_src_three_skips_no_hash():
    # From-source tier pins nothing by sha (bsys6 verifies Firefox itself): all
    # three source() entries are 'SKIP', the LibreWolf tarball hash never appears,
    # and there is no validpgpkeys line (no .sig download in this path).
    s = pkgbuild.pkgbuild_librewolf_src()
    assert "sha256sums=('SKIP' 'SKIP' 'SKIP')" in s
    assert s.count("'SKIP'") == 3
    assert pkgbuild.LIBREWOLF_SHA256 not in s
    assert "validpgpkeys" not in s


def test_librewolf_src_runs_bsys6_make_targets():
    s = pkgbuild.pkgbuild_librewolf_src()
    assert "make fetch" in s
    assert "make build" in s
    assert "make package" in s


def test_librewolf_src_shares_pkgver_and_lwver():
    # The from-source recipe uses the SAME version split as the repackage one.
    s = pkgbuild.pkgbuild_librewolf_src()
    assert "pkgver=153.0.1" in s
    assert "_lwver=153.0-1" in s


# --- pkgbuild_calamares -----------------------------------------------------

def test_calamares_pkgver_and_sha():
    s = pkgbuild.pkgbuild_calamares()
    assert "pkgver=3.4.2" in s
    assert ("sha256sums=('%s')" % pkgbuild.CALAMARES_SHA256) in s


def test_calamares_pkgver_var_survives_brace_collapse():
    # 'calamares-${{pkgver}}.tar.gz' in the f-string must collapse to a single
    # '${pkgver}' shell expansion, not leak double braces.
    s = pkgbuild.pkgbuild_calamares()
    assert "${pkgver}" in s
    assert "calamares-${pkgver}.tar.gz" in s


# --- brace-doubling invariant across every generator -----------------------

def test_no_leftover_double_braces():
    # Any surviving '{{' or '}}' means an f-string brace was not properly doubled
    # -- the shell would then see a literal double brace and misbehave. Also
    # confirm a real shell expansion ('${...}') survived, proving the collapse
    # actually happened rather than the string being brace-free by accident.
    for gen in (
        pkgbuild.pkgbuild_calamares,
        pkgbuild.pkgbuild_librewolf,
        pkgbuild.pkgbuild_librewolf_src,
    ):
        out = gen()
        assert "{{" not in out, gen.__name__
        assert "}}" not in out, gen.__name__
        assert "${" in out, gen.__name__


# --- companion files --------------------------------------------------------

def test_desktop_exec_path_matches_install():
    # The .desktop Exec= and the package()'d binary must point at the SAME path,
    # or the menu entry launches nothing.
    desktop = pkgbuild.librewolf_desktop()
    assert "Exec=/opt/librewolf/librewolf %u" in desktop
    # Cross-check: the repackage PKGBUILD installs the tree at /opt/librewolf and
    # symlinks the same binary.
    pb = pkgbuild.pkgbuild_librewolf()
    assert "/opt/librewolf" in pb
    assert "/opt/librewolf/librewolf" in pb


def test_overrides_first_line_is_comment():
    # AutoConfig files: the engine ignores line 1, so it MUST be a comment.
    first = pkgbuild.librewolf_overrides_cfg().splitlines()[0]
    assert first.startswith("//")


def test_overrides_disables_sanitize_on_shutdown():
    cfg = pkgbuild.librewolf_overrides_cfg()
    assert (
        'defaultPref("privacy.sanitize.sanitizeOnShutdown", false);' in cfg
    )


# --- recipe_dirs tier dispatch ---------------------------------------------

def test_recipe_dirs_default_tier():
    # DEFAULT tier: calamares first (Arch dropped extra/calamares, so it must be
    # built here now), then librewolf. calamares carries only its PKGBUILD; the
    # librewolf dir carries PKGBUILD + two companion files, and its PKGBUILD is the
    # repackage recipe (no bsys6 make targets).
    dirs = pkgbuild.recipe_dirs(False)
    names = [name for name, _ in dirs]
    assert names == ["calamares", "librewolf"]
    assert set(dict(dirs)["calamares"]) == {"PKGBUILD"}
    files = dict(dirs)["librewolf"]
    assert set(files) == {"PKGBUILD", "librewolf.desktop", "librewolf.overrides.cfg"}
    assert "make fetch" not in files["PKGBUILD"]


def test_recipe_dirs_full_tier():
    # FULL tier: calamares first (index 0), then librewolf; librewolf's PKGBUILD
    # is now the from-source recipe (has the bsys6 make targets).
    dirs = pkgbuild.recipe_dirs(True)
    names = [name for name, _ in dirs]
    assert names == ["calamares", "librewolf"]
    assert dirs[0][0] == "calamares"
    assert set(dict(dirs)["calamares"]) == {"PKGBUILD"}
    assert "make fetch" in dict(dirs)["librewolf"]["PKGBUILD"]


def test_recipe_dirs_companion_files_shared_across_tiers():
    # The two companion files are identical content regardless of tier -- both
    # tiers embed the same .desktop and overrides.cfg.
    default_lw = dict(pkgbuild.recipe_dirs(False))["librewolf"]
    full_lw = dict(pkgbuild.recipe_dirs(True))["librewolf"]
    assert default_lw["librewolf.desktop"] == full_lw["librewolf.desktop"]
    assert (
        default_lw["librewolf.overrides.cfg"] == full_lw["librewolf.overrides.cfg"]
    )
    assert default_lw["librewolf.desktop"] == pkgbuild.librewolf_desktop()
