"""Cross-cutting invariants -- the "whack-a-mole ends here" guards that span
whole families of modules rather than one function.

Each single-module test file pins one generator's exact bytes. These tests
instead assert the properties that must hold ACROSS every member of a family,
so an edit that adds a new emitter / category / subsystem entry and forgets the
shared contract fails here even if its own dedicated test was never written:

  * every config emitter returns a non-empty ``str`` -- an f-string that raises
    at call time, or a helper that silently returns ``None``, is caught for the
    whole config package at once (an empty file makes archiso/calamares/pacman
    abort at build or install time, nothing in Python notices otherwise);
  * every YAML config Calamares reads actually parses -- a stray tab or an
    unbalanced brace turns into a runtime abort inside the installer, never a
    Python error;
  * the shipped package manifest tokenizes to clean names with no accidental
    in-block duplicate (pacman/mkarchiso dedup across blocks, so only a repeat
    WITHIN the hand-edited additions block is the real hazard);
  * the ``STOCK_PACKAGES`` reference tuple stays sorted, unique and clean so it
    keeps diffing against upstream releng;
  * the category legend is closed: order-list, color-map and every category any
    classification rule can emit are the SAME set (a new rule pointing at a
    typo'd category would silently drop that package's color/legend slot);
  * the deliberate ``_sudo`` asymmetry holds -- teardown-path modules pass
    ``-n`` (fail fast, never block on a password prompt), build-path modules do
    not -- and both collapse to ``[]`` when already root;
  * ``SUBSYSTEMS`` keeps its 4-tuple arity, unique keys and ``' / '`` label
    convention the renderer splits on.

All pure: no network, no subprocess, no docker, no sudo. The one seam touched is
``paths.is_root`` (monkeypatched, never the real euid) for the ``_sudo`` checks.
"""

from __future__ import annotations

import re

import pytest
import yaml

from azarch import build, makepkg, packages, paths, steps
from azarch.config import (
    calamares,
    desktop,
    installer,
    locale,
    pacman,
    pkgbuild,
    profile,
)
import spec_classify
import spec_content
import spec_stock_baseline


# ---------------------------------------------------------------------------
# 1. Every config emitter returns non-empty content.
# ---------------------------------------------------------------------------
#
# Collected as (label, callable) pairs so a failure names the offending emitter.
# These are exactly the no-argument (or all-defaulted) content generators the
# build iterates to write the config tree; recipe_dirs contents are checked
# separately below because they are nested dicts, not top-level generators.

_EMITTERS = [
    *[(f"calamares:{rel}", (lambda v=content: v))
      for rel, content in calamares.emit_map().items()],
    *[(f"desktop:{e['dest']}", e["builder"]) for e in desktop.emit_plan()],
    ("installer.installer_sh", installer.installer_sh),
    ("installer.chroot_setup_sh", installer.chroot_setup_sh),
    ("installer.setup_pkgs_sh", installer.setup_pkgs_sh),
    ("installer.first_boot_conf", installer.first_boot_conf),
    ("installer.first_boot_service", installer.first_boot_service),
    ("installer.first_boot_sh", installer.first_boot_sh),
    ("locale.setup_locale_sh", locale.setup_locale_sh),
    ("profile.profiledef_sh", profile.profiledef_sh),
    ("pacman.download_conf", pacman.download_conf),
    ("pacman.build_profile_conf", pacman.build_profile_conf),
    ("pacman.installer_base_conf", pacman.installer_base_conf),
    ("pacman.installer_pacstrap_conf", pacman.installer_pacstrap_conf),
    ("pkgbuild.pkgbuild_calamares", pkgbuild.pkgbuild_calamares),
    ("pkgbuild.librewolf_desktop", pkgbuild.librewolf_desktop),
    ("pkgbuild.librewolf_overrides_cfg", pkgbuild.librewolf_overrides_cfg),
    ("pkgbuild.pkgbuild_librewolf", pkgbuild.pkgbuild_librewolf),
    ("pkgbuild.pkgbuild_librewolf_src", pkgbuild.pkgbuild_librewolf_src),
]


@pytest.mark.parametrize("label,fn", _EMITTERS, ids=[e[0] for e in _EMITTERS])
def test_every_config_emitter_returns_nonempty_str(label, fn):
    out = fn()
    assert isinstance(out, str), f"{label} returned {type(out).__name__}, not str"
    assert out.strip(), f"{label} returned empty/whitespace-only content"


def test_emitter_family_covers_all_config_modules():
    # Sanity check that the parametrized family did not silently shrink to a
    # handful of entries -- the whole point is breadth. 14 calamares files + 7
    # desktop builders + 6 installer + locale + profile + 4 pacman + 5 pkgbuild.
    assert len(_EMITTERS) == 14 + 7 + 6 + 1 + 1 + 4 + 5


def test_recipe_dir_contents_are_nonempty_str_both_tiers():
    # recipe_dirs(full_compile) returns [(dirname, {filename: content})]; every
    # emitted file (PKGBUILD, .desktop, overrides) must be real content or
    # makepkg builds an empty package.
    for full in (False, True):
        for name, files in pkgbuild.recipe_dirs(full):
            assert files, f"recipe dir {name!r} (full={full}) has no files"
            for fn, content in files.items():
                assert isinstance(content, str), f"{name}/{fn} is not str"
                assert content.strip(), f"{name}/{fn} is empty"


# ---------------------------------------------------------------------------
# 2. Every YAML config Calamares reads parses.
# ---------------------------------------------------------------------------

def test_every_calamares_yaml_value_parses():
    # Calamares reads these with libyaml at install time; a parse error there is
    # a runtime abort with no Python stack. The .qml file is Qt markup, not YAML.
    for rel, content in calamares.emit_map().items():
        if rel.endswith(".qml"):
            continue
        try:
            yaml.safe_load(content)
        except yaml.YAMLError as e:  # pragma: no cover - failure path
            pytest.fail(f"{rel} is not valid YAML: {e}")


def test_exactly_one_calamares_file_is_non_yaml():
    # Guards the assumption above: only the branding show.qml is exempt from the
    # YAML-parse contract. A second non-YAML file would slip past the loop.
    non_yaml = [rel for rel in calamares.emit_map() if rel.endswith(".qml")]
    assert non_yaml == ["branding/azarch/show.qml"]


# ---------------------------------------------------------------------------
# 3. The shipped package manifest tokenizes clean, no in-block duplicate.
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    # The exact strip mkarchiso/packages._sync_and_download applies: everything
    # from the first '#' is a comment, remainder stripped, empties dropped.
    return [tok for line in text.splitlines()
            if (tok := line.split("#", 1)[0].strip())]


def test_packages_manifest_tokens_are_clean():
    text = paths.PACKAGES_FILE.read_text()
    toks = _tokenize(text)
    assert toks, "packages.x86_64 tokenized to nothing"
    for t in toks:
        assert "#" not in t, f"token still carries a comment: {t!r}"
        assert t == t.strip(), f"token has surrounding whitespace: {t!r}"
        assert " " not in t, f"token has internal whitespace: {t!r}"


def test_packages_manifest_no_duplicate_within_additions_block():
    # A package in BOTH the STOCK and ADDITIONS blocks is intentional and benign
    # (releng ships e.g. grub/lvm2 and the installer re-declares them; pacman and
    # mkarchiso dedup the manifest). The real editing hazard is the same name
    # typed twice WITHIN the hand-edited additions block, which is what we guard.
    lines = paths.PACKAGES_FILE.read_text().splitlines()
    banner = max(i for i, l in enumerate(lines) if "AZ'ARCH ADDITIONS" in l)
    close = next(i for i in range(banner + 1, len(lines))
                 if set(lines[i].strip()) <= set("#= "))
    additions = _tokenize("\n".join(lines[close + 1:]))
    dupes = sorted({t for t in additions if additions.count(t) > 1})
    assert not dupes, f"duplicate packages within Az'arch-additions block: {dupes}"


# ---------------------------------------------------------------------------
# 4. STOCK_PACKAGES reference tuple invariants.
# ---------------------------------------------------------------------------

def test_stock_packages_is_a_frozen_sorted_unique_tuple():
    pkgs = spec_stock_baseline.STOCK_PACKAGES
    assert isinstance(pkgs, tuple), "STOCK_PACKAGES must be a tuple (frozen ref data)"
    assert pkgs, "STOCK_PACKAGES is empty"
    assert len(set(pkgs)) == len(pkgs), "STOCK_PACKAGES has duplicates"
    assert list(pkgs) == sorted(pkgs), "STOCK_PACKAGES is not C-locale sorted"


def test_stock_packages_entries_are_clean_tokens():
    for p in spec_stock_baseline.STOCK_PACKAGES:
        assert isinstance(p, str) and p, f"bad STOCK entry: {p!r}"
        assert p == p.strip(), f"STOCK entry has surrounding whitespace: {p!r}"
        assert " " not in p, f"STOCK entry has internal whitespace: {p!r}"
        assert not p.startswith("#"), f"STOCK entry is a comment: {p!r}"


# ---------------------------------------------------------------------------
# 7. Category legend closure: order == colors == rule-emitted set.
# ---------------------------------------------------------------------------

_HEX6 = re.compile(r"#[0-9a-fA-F]{6}$")


def test_category_order_and_colors_are_the_same_set():
    # The SVG/legend iterates CATEGORY_ORDER and looks up CATEGORY_COLORS[cat];
    # a category present in one but not the other is either a legend slot with no
    # color or a color no legend ever shows.
    assert set(spec_classify.CATEGORY_ORDER) == set(spec_classify.CATEGORY_COLORS)
    assert len(spec_classify.CATEGORY_ORDER) == len(set(spec_classify.CATEGORY_ORDER))


def test_every_category_color_is_six_hex_digits():
    for cat, color in spec_classify.CATEGORY_COLORS.items():
        assert _HEX6.match(color), f"{cat!r} color {color!r} is not #RRGGBB"


def test_every_rule_emitted_category_is_in_the_order():
    # Enumerate every category any of the five classification stages can return
    # (curated map, group map, name-prefix/substr rules, dev-tool constant, desc
    # keyword rules, and the two fallbacks). Every one must have a legend slot.
    order = set(spec_classify.CATEGORY_ORDER)
    emitted = set(spec_classify.CURATED.values())
    emitted |= set(spec_classify.GROUP_ROLE.values())
    emitted |= {cat for _, cat in spec_classify.NAME_PREFIX_RULES}
    emitted |= {cat for _, cat in spec_classify.NAME_SUBSTR_RULES}
    emitted |= {cat for _, cat in spec_classify.DESC_RULES}
    emitted |= {"Developer tools", "Shared library", "System"}
    assert emitted <= order, f"rule categories missing from legend: {emitted - order}"


def test_azarch_configured_keys_and_removed_are_stable():
    # The per-package "Az'arch configured" notes cross-reference real package
    # names; every value must be a real note, and the removed set is empty (no
    # package is dropped from the stock baseline in this build).
    conf = spec_classify.AZARCH_CONFIGURED
    assert set(conf) == {
        "fastfetch", "filesystem", "grub", "pacman",
        "sudo", "syslinux", "systemd", "ufw",
    }
    for k, v in conf.items():
        assert isinstance(v, str) and v.strip(), f"empty note for {k!r}"
    assert spec_classify.AZARCH_REMOVED == set()


# ---------------------------------------------------------------------------
# 8. The deliberate _sudo asymmetry, parametrized across modules.
# ---------------------------------------------------------------------------
#
# build/steps run cleanup on the Ctrl-C teardown path, so they pass `-n`
# (non-interactive: a chown/unmount after the sudo timestamp expired fails fast
# instead of hanging on a password prompt with no TTY). makepkg/packages run in
# the normal build flow where an interactive prompt is acceptable, so no `-n`.
# All four collapse to [] when already root (no sudo binary needed).

_SUDO_MODULES = [
    ("build", build, ["sudo", "-n"]),
    ("steps", steps, ["sudo", "-n"]),
    ("makepkg", makepkg, ["sudo"]),
    ("packages", packages, ["sudo"]),
]


@pytest.mark.parametrize("name,mod,expected_nonroot", _SUDO_MODULES,
                         ids=[m[0] for m in _SUDO_MODULES])
def test_sudo_prefix_nonroot(name, mod, expected_nonroot, monkeypatch):
    # paths is the single shared azarch.paths module object all four import by
    # name, so patching is_root here reaches every _sudo() at once.
    monkeypatch.setattr(paths, "is_root", lambda: False)
    assert mod._sudo() == expected_nonroot


@pytest.mark.parametrize("name,mod,expected_nonroot", _SUDO_MODULES,
                         ids=[m[0] for m in _SUDO_MODULES])
def test_sudo_prefix_root_is_empty(name, mod, expected_nonroot, monkeypatch):
    monkeypatch.setattr(paths, "is_root", lambda: True)
    assert mod._sudo() == []


def test_teardown_modules_use_dash_n_build_modules_do_not(monkeypatch):
    # Locks the asymmetry as a single assertion so removing the `-n` from a
    # teardown module (re-introducing the password-prompt hang) fails loudly.
    monkeypatch.setattr(paths, "is_root", lambda: False)
    assert "-n" in build._sudo()
    assert "-n" in steps._sudo()
    assert "-n" not in makepkg._sudo()
    assert "-n" not in packages._sudo()


# ---------------------------------------------------------------------------
# 9. SUBSYSTEMS arity, key uniqueness, and slash convention.
# ---------------------------------------------------------------------------

def test_subsystems_every_entry_is_a_4_tuple():
    # The renderer unpacks `for key, title, prose, pkgs in SUBSYSTEMS`; any entry
    # with the wrong arity is a ValueError at spec-render time.
    for entry in spec_content.SUBSYSTEMS:
        assert isinstance(entry, tuple) and len(entry) == 4, f"bad arity: {entry!r}"


def test_subsystems_keys_are_unique_and_clean():
    keys = [key for key, _t, _p, _pkgs in spec_content.SUBSYSTEMS]
    assert len(keys) == len(set(keys)), f"duplicate subsystem keys: {keys}"
    for k in keys:
        assert isinstance(k, str) and k == k.strip() and k, f"bad key: {k!r}"


def test_subsystems_multi_package_labels_use_space_slash_space():
    # Multi-package rows use `a / b` (space-slash-space); the renderer splits on
    # ' / '. A bare `a/b` would not split and would be treated as one bogus name.
    saw_multi = False
    for _key, _title, _prose, pkgs in spec_content.SUBSYSTEMS:
        for label, _cap in pkgs:
            assert label.count("/") == label.count(" / "), f"unspaced slash: {label!r}"
            if " / " in label:
                saw_multi = True
                for tok in label.split(" / "):
                    assert tok == tok.strip() and tok, f"bad split token in {label!r}"
    assert saw_multi, "no multi-package label present -- the ' / ' rule is untested"
