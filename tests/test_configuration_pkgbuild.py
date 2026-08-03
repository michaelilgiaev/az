"""azarch.configuration.pkgbuild -- the Az'arch-authored package recipes.

These PKGBUILDs are Python f-strings emitted to disk and then fed verbatim to
makepkg. Two failure modes here are silent and expensive:

  1. A wrong version literal. LibreWolf has TWO version strings that look almost
     identical -- the upstream tag "153.0.1-1" (used to build the download URL and
     the source filename) and the pacman-legal pkgver "153.0.1.1" (the '-' is a
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
import shutil
import subprocess
from pathlib import Path

import pytest

from azarch.configuration import pkgbuild


_HEX = re.compile(r"\A[0-9a-fA-F]+\Z")

# Repo root (tests/ is one level down). Used to locate the vendored, extracted
# calamares source the defaults patch is authored against.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _find_calamares_src() -> Path | None:
    """Locate an extracted calamares-<ver> source tree under cache/ (the makepkg
    build scratch), or None if it isn't present in this checkout."""
    base = _REPO_ROOT / "cache" / "makepkg" / "calamares"
    if not base.is_dir():
        return None
    hits = list(base.glob(f"**/calamares-{pkgbuild.CALAMARES_VERSION}"))
    # Want the directory that actually contains src/modules (the source root).
    for h in hits:
        if (h / "src" / "modules").is_dir():
            return h
    return None


# --- pinned upstream constants ---------------------------------------------

def test_version_constants_distinct():
    # The two LibreWolf version strings must never be equal: the '-1' tag form
    # and the '.1' pkgver form are used in different, non-interchangeable places.
    assert pkgbuild.LIBREWOLF_VERSION == "153.0.1-1"
    assert pkgbuild.LIBREWOLF_PKGVER == "153.0.1.1"
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
    # The pkgver= field must carry the pacman-legal "153.0.1.1", NOT the tag form.
    # _lwver= carries the tag form "153.0.1-1" for URL/filename construction.
    s = pkgbuild.pkgbuild_librewolf()
    assert "pkgver=153.0.1.1" in s
    assert "pkgver=153.0.1-1" not in s
    assert "_lwver=153.0.1-1" in s


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
    # Binaries are served from Codeberg's package API (dl.librewolf.net is down).
    s = pkgbuild.pkgbuild_librewolf()
    assert "https://codeberg.org/api/packages/librewolf/generic/librewolf/153.0.1-1" in s
    assert "librewolf-153.0.1-1-linux-x86_64-package.tar.xz" in s


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
    assert "pkgver=153.0.1.1" in s
    assert "_lwver=153.0.1-1" in s


# --- pkgbuild_calamares -----------------------------------------------------

def test_calamares_pkgver_and_sha():
    s = pkgbuild.pkgbuild_calamares()
    assert "pkgver=3.4.2" in s
    # The tarball hash is pinned; the shipped-in-repo patch is SKIP (a local file,
    # matched by position to the second source() entry).
    assert ("sha256sums=('%s' 'SKIP')" % pkgbuild.CALAMARES_SHA256) in s


def test_calamares_pkgver_var_survives_brace_collapse():
    # 'calamares-${{pkgver}}.tar.gz' in the f-string must collapse to a single
    # '${pkgver}' shell expansion, not leak double braces.
    s = pkgbuild.pkgbuild_calamares()
    assert "${pkgver}" in s
    assert "calamares-${pkgver}.tar.gz" in s


# --- calamares source patch (installer UI defaults) ------------------------

def test_calamares_pkgbuild_references_patch_in_source_and_prepare():
    # The patch must be a source() entry (so makepkg stages it) AND actually applied
    # in prepare(); a patch present but never applied would silently do nothing.
    s = pkgbuild.pkgbuild_calamares()
    name = pkgbuild.CALAMARES_DEFAULTS_PATCH_NAME
    assert ("'%s'" % name) in s                       # listed in source=()
    assert "prepare() {" in s
    assert ("patch -p1 < \"$srcdir/%s\"" % name) in s  # applied, -p1, from srcdir


def test_calamares_patch_skip_aligned_after_tarball_hash():
    # sha256sums matches source() by POSITION: real tarball hash first, then SKIP
    # for the local patch file. Exactly one SKIP (only the patch is a local file).
    s = pkgbuild.pkgbuild_calamares()
    assert ("sha256sums=('%s' 'SKIP')" % pkgbuild.CALAMARES_SHA256) in s
    assert s.count("'SKIP'") == 1


def test_calamares_patch_name_is_a_patch_file():
    assert pkgbuild.CALAMARES_DEFAULTS_PATCH_NAME.endswith(".patch")


def test_calamares_patch_is_unified_diff_touching_both_files():
    # The patch must be a -p1 unified diff (a/ b/ prefixes) that edits BOTH the
    # keyboard group-switcher model (Alt+Shift default) and the users hostname
    # config (fixed default hostname). Missing either file means one of the two
    # requested defaults was dropped.
    p = pkgbuild.calamares_defaults_patch()
    assert "--- a/src/modules/keyboard/KeyboardLayoutModel.cpp" in p
    assert "+++ b/src/modules/keyboard/KeyboardLayoutModel.cpp" in p
    assert "--- a/src/modules/users/Config.cpp" in p
    assert "+++ b/src/modules/users/Config.cpp" in p
    # Hunk headers present (so `patch` has something to locate).
    assert p.count("@@") >= 4  # two hunks => two "@@ ... @@" markers (2 "@@" each)


def test_calamares_patch_keyboard_selects_alt_shift_toggle():
    # THE Alt+Shift default: the added code must select the group-switcher entry
    # whose xkb id is alt_shift_toggle. Only added ('+') lines are the change.
    p = pkgbuild.calamares_defaults_patch()
    added = [ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    body = "\n".join(added)
    assert "alt_shift_toggle" in body
    assert "setCurrentIndex(" in body


def test_calamares_patch_hostname_seeds_and_marks_custom():
    # THE fixed-hostname default: the added code seeds the hostname from the
    # template once and routes it through setHostName (which sets m_customHostName,
    # taking the field off the name-derived auto-update path).
    p = pkgbuild.calamares_defaults_patch()
    added = [ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    body = "\n".join(added)
    assert "makeHostnameSuggestion(" in body
    assert "setHostName(" in body


def test_calamares_patch_emitted_with_recipe():
    # recipe_dirs must actually emit the patch content under the recipe's filename,
    # in BOTH tiers (calamares is built the same way in each).
    for tier in (False, True):
        files = dict(pkgbuild.recipe_dirs(tier))["calamares"]
        assert files[pkgbuild.CALAMARES_DEFAULTS_PATCH_NAME] == (
            pkgbuild.calamares_defaults_patch()
        )


def test_calamares_patch_context_lines_have_leading_space():
    # A unified-diff context line MUST start with a single space (blank context
    # lines are exactly " "). If an editor stripped those, `patch` would choke.
    # Assert every non-header line is a valid diff body line.
    p = pkgbuild.calamares_defaults_patch()
    for ln in p.splitlines():
        if ln.startswith(("--- ", "+++ ", "@@ ")):
            continue
        assert ln[:1] in (" ", "+", "-"), repr(ln)
    # And there is at least one space-only context line (the blank source lines),
    # proving they survived as " " and not "".
    assert " " in p.splitlines()


def test_calamares_defaults_patch_applies_to_pinned_source():
    # THE integration guard: the patch must apply cleanly to the real, pinned
    # calamares source with the exact command the PKGBUILD runs (`patch -p1`).
    # This catches context drift on a version bump -- the failure mode where the
    # customization silently vanishes because the hunks no longer match.
    src = _find_calamares_src()
    if src is None:
        pytest.skip("extracted calamares source not present under cache/ (CI checkout)")
    if shutil.which("patch") is None:
        pytest.skip("`patch` not available on this host")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        # Copy only the two files the patch touches, preserving their paths.
        for rel in (
            "src/modules/keyboard/KeyboardLayoutModel.cpp",
            "src/modules/users/Config.cpp",
        ):
            dst = work / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / rel, dst)

        patch_text = pkgbuild.calamares_defaults_patch()
        # Dry-run first (pure check), then a real apply (proves the result is
        # writable and the offsets are exact, not fuzz-matched).
        dry = subprocess.run(
            ["patch", "-p1", "--dry-run"],
            input=patch_text,
            text=True,
            cwd=work,
            capture_output=True,
            timeout=30,
        )
        assert dry.returncode == 0, f"dry-run failed:\n{dry.stdout}\n{dry.stderr}"

        real = subprocess.run(
            ["patch", "-p1"],
            input=patch_text,
            text=True,
            cwd=work,
            capture_output=True,
            timeout=30,
        )
        assert real.returncode == 0, f"apply failed:\n{real.stdout}\n{real.stderr}"

        # The two behaviours actually landed in the patched source.
        kbd = (work / "src/modules/keyboard/KeyboardLayoutModel.cpp").read_text()
        assert "alt_shift_toggle" in kbd
        assert "setCurrentIndex(" in kbd
        users = (work / "src/modules/users/Config.cpp").read_text()
        assert "makeHostnameSuggestion(" in users
        assert "setHostName( seededHostname )" in users


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
    # built here now), then librewolf. calamares carries its PKGBUILD + the source
    # patch that sets the installer UI defaults; the librewolf dir carries PKGBUILD +
    # two companion files, and its PKGBUILD is the repackage recipe (no bsys6 make
    # targets).
    dirs = pkgbuild.recipe_dirs(False)
    names = [name for name, _ in dirs]
    assert names == ["calamares", "librewolf"]
    assert set(dict(dirs)["calamares"]) == {
        "PKGBUILD",
        pkgbuild.CALAMARES_DEFAULTS_PATCH_NAME,
    }
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
    assert set(dict(dirs)["calamares"]) == {
        "PKGBUILD",
        pkgbuild.CALAMARES_DEFAULTS_PATCH_NAME,
    }
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
