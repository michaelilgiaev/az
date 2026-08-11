"""packages.pkgbuild -- the Az'arch-authored package recipes.

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
import tarfile
from pathlib import Path

import pytest

from packages import pkgbuild


_HEX = re.compile(r"\A[0-9a-fA-F]+\Z")

# Repo root (tests/ is one level down). Used to locate the vendored, pinned
# calamares tarball the defaults patch is authored against.
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _find_calamares_tarball() -> Path | None:
    """Locate the pinned calamares-<ver>.tar.gz under cache/ (the makepkg source
    cache), or None if it isn't present in this checkout.

    The patch is authored against PRISTINE upstream source, so the integration
    guard must read from the tarball -- NOT the extracted build scratch under
    .build/. makepkg runs the patch in-place during prepare(), so any local
    build leaves that scratch tree already-patched; dry-running the patch against
    it then trips "Reversed (or previously applied) patch detected!" and the test
    false-fails. The .src/ tarball is exactly what makepkg downloads and is the
    only trustworthy pristine copy on disk."""
    base = _REPO_ROOT / "cache" / "makepkg" / "calamares"
    if not base.is_dir():
        return None
    # makepkg stores the fetched tarball under .src/; fall back to a wider glob
    # in case the cache layout differs, but never match extracted trees.
    name = f"calamares-{pkgbuild.CALAMARES_VERSION}.tar.gz"
    for cand in (base / ".src" / name, *base.glob(f"**/{name}")):
        if cand.is_file():
            return cand
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


def test_librewolf_src_make_build_caps_jobs():
    # `make build` alone lets Firefox's build spawn one job per core and pin the
    # whole machine. It must carry the -j cap fed via AZARCH_JOBS (exported by
    # makepkg), defaulting to 1 when the var is unset.
    s = pkgbuild.pkgbuild_librewolf_src()
    assert 'make build -j"${AZARCH_JOBS:-1}"' in s


def test_librewolf_src_shares_pkgver_and_lwver():
    # The from-source recipe uses the SAME version split as the repackage one.
    s = pkgbuild.pkgbuild_librewolf_src()
    assert "pkgver=153.0.1.1" in s
    assert "_lwver=153.0.1-1" in s


# --- pkgbuild_calamares -----------------------------------------------------

def test_calamares_pkgver_and_sha():
    s = pkgbuild.pkgbuild_calamares()
    assert "pkgver=3.4.2" in s
    # The tarball hash is pinned; the TWO shipped-in-repo patches (defaults +
    # region-keyboard) are each SKIP (local files, matched by position to the
    # second and third source() entries).
    assert ("sha256sums=('%s' 'SKIP' 'SKIP')" % pkgbuild.CALAMARES_SHA256) in s


def test_calamares_pkgver_var_survives_brace_collapse():
    # 'calamares-${{pkgver}}.tar.gz' in the f-string must collapse to a single
    # '${pkgver}' shell expansion, not leak double braces.
    s = pkgbuild.pkgbuild_calamares()
    assert "${pkgver}" in s
    assert "calamares-${pkgver}.tar.gz" in s


def test_calamares_cmake_build_caps_jobs():
    # `cmake --build build` auto-detects every core and pins the machine. It must
    # carry the -j cap fed via AZARCH_JOBS (exported by makepkg), defaulting
    # to 1 when unset. The brace pair in the recipe f-string must also have
    # collapsed to a single ${...} shell expansion.
    s = pkgbuild.pkgbuild_calamares()
    assert 'cmake --build build -j"${AZARCH_JOBS:-1}"' in s


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
    # for each local patch file. Exactly two SKIPs (the defaults + region patches).
    s = pkgbuild.pkgbuild_calamares()
    assert ("sha256sums=('%s' 'SKIP' 'SKIP')" % pkgbuild.CALAMARES_SHA256) in s
    assert s.count("'SKIP'") == 2


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
    #
    # Source the two files from the PRISTINE tarball, not the .build/ scratch:
    # makepkg patches the scratch in place during prepare(), so reading it back
    # would test the patch against already-patched source (see
    # _find_calamares_tarball for the full rationale).
    tarball = _find_calamares_tarball()
    if tarball is None:
        pytest.skip("pinned calamares tarball not present under cache/ (CI checkout)")
    if shutil.which("patch") is None:
        pytest.skip("`patch` not available on this host")

    import tempfile

    # The two files the patch touches, as stored inside the tarball (prefixed by
    # the calamares-<ver>/ top-level directory the archive unpacks into).
    rels = (
        "src/modules/keyboard/KeyboardLayoutModel.cpp",
        "src/modules/users/Config.cpp",
    )
    top = f"calamares-{pkgbuild.CALAMARES_VERSION}"

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        # Extract only the two files pristine, dropping the top-level dir so the
        # -p1 a/src/... paths line up when patch runs from `work`.
        with tarfile.open(tarball, "r:gz") as tf:
            for rel in rels:
                member = tf.getmember(f"{top}/{rel}")
                fobj = tf.extractfile(member)
                assert fobj is not None, f"missing {rel} in tarball"
                dst = work / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(fobj.read())

        # Guard against silently testing already-patched source: the pristine
        # files must NOT yet contain the additions the patch introduces.
        pristine_kbd = (work / rels[0]).read_text()
        pristine_users = (work / rels[1]).read_text()
        assert "alt_shift_toggle" not in pristine_kbd
        assert "seededHostname" not in pristine_users

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


# --- calamares source patch (region-driven keyboard) -----------------------

def test_calamares_region_patch_name_is_a_patch_file():
    assert pkgbuild.CALAMARES_REGION_KEYBOARD_PATCH_NAME.endswith(".patch")
    # Distinct from the defaults patch (two separate files applied in sequence).
    assert (
        pkgbuild.CALAMARES_REGION_KEYBOARD_PATCH_NAME
        != pkgbuild.CALAMARES_DEFAULTS_PATCH_NAME
    )


def test_calamares_pkgbuild_references_region_patch_in_source_and_prepare():
    # The region patch must be BOTH a source() entry and applied in prepare(); the
    # defaults patch must still be too (both are applied, in order).
    s = pkgbuild.pkgbuild_calamares()
    name = pkgbuild.CALAMARES_REGION_KEYBOARD_PATCH_NAME
    assert ("'%s'" % name) in s
    assert ("patch -p1 < \"$srcdir/%s\"" % name) in s
    # Both patches present in source() -> now TWO local files -> two SKIPs.
    assert ("sha256sums=('%s' 'SKIP' 'SKIP')" % pkgbuild.CALAMARES_SHA256) in s
    assert s.count("'SKIP'") == 2


def test_calamares_region_patch_touches_keyboard_and_locale_modules():
    # The feature spans three files: the keyboard module header + impl (the
    # region->layout logic) and the locale module (publishing locationCountry to GS).
    p = pkgbuild.calamares_region_keyboard_patch()
    for f in (
        "src/modules/keyboard/Config.h",
        "src/modules/keyboard/Config.cpp",
        "src/modules/locale/Config.cpp",
    ):
        assert ("--- a/%s" % f) in p
        assert ("+++ b/%s" % f) in p


def test_calamares_region_patch_locale_publishes_country_to_gs():
    # The locale module must insert the selected zone's ISO-3166 country code into
    # GlobalStorage under "locationCountry" -- the only clean country signal the
    # keyboard module can key its layout table on.
    p = pkgbuild.calamares_region_keyboard_patch()
    added = [ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    body = "\n".join(added)
    assert "locationCountry" in body
    assert "location->country()" in body


def test_calamares_region_patch_keeps_english_first_and_alt_shift():
    # The added logic must (a) read regionSecondLayout, (b) force "us" as the
    # additional layout (English first/active in "us,<region>"), and (c) use
    # grp:alt_shift_toggle as the switcher. Non-English scripts and Latin ones
    # (Hebrew "il", Arabic "ara", Spanish "latam") must be in the country table.
    p = pkgbuild.calamares_region_keyboard_patch()
    added = [ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    body = "\n".join(added)
    assert "regionSecondLayout" in body
    assert 'additionalLayout = QStringLiteral( "us" )' in body
    assert "grp:alt_shift_toggle" in body
    assert "guessRegionKeyboardLayout" in body
    # Layout codes are the real base.lst identifiers (Hebrew is "il", not "he").
    assert '"IL", "il"' in body
    assert '"ara"' in body
    assert '"latam"' in body
    # And it must NOT map Hebrew to a bogus "he" layout code.
    assert '"IL", "he"' not in body


def test_calamares_region_patch_reguesses_on_every_activate():
    # BUG (installer keyboard does not follow the region): the stock keyboard guess
    # early-returns unless m_state==State::Initial, so after the first Keyboard visit
    # (state becomes UserSelected) changing the region on the Location page and
    # returning never re-derives the layout. The patch must relax that gate for the
    # region path so it re-runs on every activation. The gate condition must gain the
    # `&& !m_regionSecondLayout` clause (region path bypasses the Initial-only gate).
    p = pkgbuild.calamares_region_keyboard_patch()
    added = [ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    body = "\n".join(added)
    assert "( m_state != State::Initial && !m_regionSecondLayout ) || !m_guessLayout" in body
    # And the ORIGINAL Initial-only gate must be REMOVED (a "-" line), not left behind
    # (else the region path would still early-return on the second visit).
    removed = [ln[1:] for ln in p.splitlines() if ln.startswith("-") and not ln.startswith("---")]
    assert "    if ( m_state != State::Initial || !m_guessLayout )" in removed


def test_calamares_region_patch_preserves_hand_picked_layout_on_revisit():
    # Re-running the region guess on every Keyboard activation (the BUG 2 gate fix) must
    # NOT clobber a layout the user hand-picked when they revisit the page WITHOUT
    # changing the region. The patch must capture whether the user had already selected
    # (m_state==UserSelected) before the scoped assignment resets it, thread it into
    # guessRegionKeyboardLayout(bool), and short-circuit when the region is unchanged
    # (country == m_regionGuessedCountry). Without this, revisiting Keyboard overwrites
    # a hand-picked primary layout back to the region layout every time.
    p = pkgbuild.calamares_region_keyboard_patch()
    added = [ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    body = "\n".join(added)
    # Entry-state captured before the scoped assignment resets m_state.
    assert "const bool azUserHadSelected = ( m_state == State::UserSelected )" in body
    # Threaded into the region guess.
    assert "guessRegionKeyboardLayout( azUserHadSelected )" in body
    assert "void guessRegionKeyboardLayout( bool userHadSelected )" in body \
        or "Config::guessRegionKeyboardLayout( bool userHadSelected )" in body
    # The preserve guard: user hand-picked AND region unchanged -> return without reselecting.
    assert "userHadSelected && !m_regionGuessedCountry.isEmpty() && country == m_regionGuessedCountry" in body
    # And it must record the guessed country so a later same-region revisit is detected.
    assert "m_regionGuessedCountry = country;" in body


def test_calamares_region_patch_falls_back_to_zone_for_default_region():
    # BUG corollary: on the FIRST Keyboard activation GlobalStorage "locationCountry"
    # may not be populated yet (the locale module writes it on location-change /
    # finalize), which would make the default Asia/Jerusalem resolve to English-only
    # instead of us,il. The patch must fall back to the published "locationZone" via a
    # countryForZone() table, and the default Jerusalem MUST map to IL.
    p = pkgbuild.calamares_region_keyboard_patch()
    added = [ln[1:] for ln in p.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    body = "\n".join(added)
    assert "countryForZone" in body
    assert "locationZone" in body
    # Default region -> IL so out-of-the-box stays us,il.
    assert '{ "Jerusalem", "IL" }' in body
    # A couple of representative non-default zones the PROMPT calls out.
    assert '{ "El_Salvador", "SV" }' in body
    assert '{ "Riyadh", "SA" }' in body
    # The read must be a MUTABLE QString (so the empty-country fallback can reassign it),
    # not the old `const QString country`.
    assert "const QString country = gs->value" not in body
    assert 'QString country = gs->value( QStringLiteral( "locationCountry" ) )' in body


def test_calamares_region_patch_context_lines_have_leading_space():
    # Same unified-diff hygiene as the defaults patch: every body line begins with
    # exactly one of " ", "+", "-"; blank context lines survived as " ".
    p = pkgbuild.calamares_region_keyboard_patch()
    for ln in p.splitlines():
        if ln.startswith(("--- ", "+++ ", "@@ ")):
            continue
        assert ln[:1] in (" ", "+", "-"), repr(ln)
    assert " " in p.splitlines()


def test_calamares_region_patch_emitted_with_recipe():
    # recipe_dirs must emit the region patch under its filename in BOTH tiers.
    for tier in (False, True):
        files = dict(pkgbuild.recipe_dirs(tier))["calamares"]
        assert files[pkgbuild.CALAMARES_REGION_KEYBOARD_PATCH_NAME] == (
            pkgbuild.calamares_region_keyboard_patch()
        )


def test_both_calamares_patches_apply_in_sequence_to_pinned_source():
    # THE integration guard for the region feature: BOTH patches must apply cleanly,
    # IN THE ORDER prepare() runs them (defaults first, then region), to the real
    # pinned source. They touch disjoint files/regions, so this also proves they do
    # not conflict. Catches context drift on a version bump for either patch.
    tarball = _find_calamares_tarball()
    if tarball is None:
        pytest.skip("pinned calamares tarball not present under cache/ (CI checkout)")
    if shutil.which("patch") is None:
        pytest.skip("`patch` not available on this host")

    import tempfile

    # Union of every file the two patches touch, extracted pristine.
    rels = (
        "src/modules/keyboard/KeyboardLayoutModel.cpp",
        "src/modules/users/Config.cpp",
        "src/modules/keyboard/Config.h",
        "src/modules/keyboard/Config.cpp",
        "src/modules/locale/Config.cpp",
    )
    top = f"calamares-{pkgbuild.CALAMARES_VERSION}"

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        with tarfile.open(tarball, "r:gz") as tf:
            for rel in rels:
                member = tf.getmember(f"{top}/{rel}")
                fobj = tf.extractfile(member)
                assert fobj is not None, f"missing {rel} in tarball"
                dst = work / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(fobj.read())

        # Pristine guard: the region additions must not already be present.
        assert "guessRegionKeyboardLayout" not in (work / "src/modules/keyboard/Config.cpp").read_text()
        assert "locationCountry" not in (work / "src/modules/locale/Config.cpp").read_text()

        # Apply defaults THEN region, exactly as prepare() does. Dry-run each first.
        for patch_text in (
            pkgbuild.calamares_defaults_patch(),
            pkgbuild.calamares_region_keyboard_patch(),
        ):
            dry = subprocess.run(
                ["patch", "-p1", "--dry-run"],
                input=patch_text, text=True, cwd=work, capture_output=True, timeout=30,
            )
            assert dry.returncode == 0, f"dry-run failed:\n{dry.stdout}\n{dry.stderr}"
            real = subprocess.run(
                ["patch", "-p1"],
                input=patch_text, text=True, cwd=work, capture_output=True, timeout=30,
            )
            assert real.returncode == 0, f"apply failed:\n{real.stdout}\n{real.stderr}"

        # The region feature actually landed in the patched source.
        kbd_cpp = (work / "src/modules/keyboard/Config.cpp").read_text()
        assert "guessRegionKeyboardLayout" in kbd_cpp
        assert "regionLayoutForCountry" in kbd_cpp
        kbd_h = (work / "src/modules/keyboard/Config.h").read_text()
        assert "m_regionSecondLayout" in kbd_h
        loc = (work / "src/modules/locale/Config.cpp").read_text()
        assert 'gs->insert( countryKey, location->country() )' in loc


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
        pkgbuild.CALAMARES_REGION_KEYBOARD_PATCH_NAME,
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
        pkgbuild.CALAMARES_REGION_KEYBOARD_PATCH_NAME,
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
