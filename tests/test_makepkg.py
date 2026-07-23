"""azarch.makepkg -- the own-package build stage.

The heavy lifting (makepkg, sudo, gpg) is io-heavy and not unit-tested here. The
one pure, load-bearing branch is produced_names(): it decides which packages are
EXCLUDED from the Arch `pacman -Sw` download. Get it wrong and the build tries to
download a package that is on no mirror (Arch dropped calamares from extra/, so a
missing exclusion makes `pacman -Sw calamares` fail with "target not found" and
aborts the whole download). Both tiers now build calamares + librewolf.
_repo_has_all is pure given a dir.

The OFFLINE-RERUN branch is also covered here (with the real makepkg monkeypatched
away): the DEFAULT tier must SKIP makepkg when the cached packages are present,
while a --full-compile rerun must RE-COMPILE from the cached source tree WITHOUT
wiping it and WITHOUT any network. _scratch_has_sources is pure given a dir.
"""

from __future__ import annotations

import pytest

from azarch import makepkg
from azarch.config import pkgbuild as pkgbuild_cfg


def test_produced_names_default_tier_builds_calamares_and_librewolf():
    # Arch dropped calamares from extra/, so the default tier must build it too
    # (it can no longer be pacman-downloaded). Both own packages are built here.
    assert makepkg.produced_names(full_compile=False) == ("calamares", "librewolf")


def test_produced_names_is_tier_independent():
    # --full-compile only changes the RECIPE, not the set of names built.
    assert makepkg.produced_names(full_compile=True) == makepkg.produced_names(full_compile=False)


def test_produced_constant_matches_produced_names():
    assert makepkg.PRODUCED == makepkg.produced_names(full_compile=False)


def test_repo_has_all_true_when_every_name_present(tmp_path):
    (tmp_path / "librewolf-1.0-1-x86_64.pkg.tar.zst").write_text("")
    assert makepkg._repo_has_all(tmp_path, ("librewolf",)) is True


def test_repo_has_all_false_when_a_name_missing(tmp_path):
    (tmp_path / "librewolf-1.0-1-x86_64.pkg.tar.zst").write_text("")
    # calamares file absent -> not all present.
    assert makepkg._repo_has_all(tmp_path, ("calamares", "librewolf")) is False


def test_repo_has_all_matches_by_name_prefix(tmp_path):
    # A different package that merely starts similarly must not satisfy the glob.
    (tmp_path / "librewolf-common-1.0-1-x86_64.pkg.tar.zst").write_text("")
    # glob is "librewolf-*", which DOES match librewolf-common; the point of this
    # test is to document that behavior so a future tightening is a conscious change.
    assert makepkg._repo_has_all(tmp_path, ("librewolf",)) is True


def test_repo_has_all_false_for_wrong_extension(tmp_path):
    # The glob is "<name>-*.pkg.tar.zst". A package compressed as .xz (the older
    # default) is NOT a zst and must not satisfy the presence check, otherwise an
    # offline build would skip makepkg while pacstrap later can't find the .zst.
    (tmp_path / "librewolf-1.0-1-x86_64.pkg.tar.xz").write_text("")
    assert makepkg._repo_has_all(tmp_path, ("librewolf",)) is False


def test_sudo_root_vs_nonroot(monkeypatch):
    # _sudo() prepends nothing when already root (already privileged), and a bare
    # "sudo" (no -n, unlike steps/build) when not -- so an interactive password
    # prompt is allowed for the makepkg host-dep installs.
    monkeypatch.setattr(makepkg.paths, "is_root", lambda: True)
    assert makepkg._sudo() == []
    monkeypatch.setattr(makepkg.paths, "is_root", lambda: False)
    assert makepkg._sudo() == ["sudo"]


# --- _scratch_has_sources: the "can an offline recompile succeed?" check -----
def _populate_scratch(scratch, *, with_build_content):
    """Create the expected recipe dirs under scratch, each with a PKGBUILD and a
    .build dir. with_build_content controls whether .build has any files (the real
    "sources were fetched" signal)."""
    for dirname, _files in pkgbuild_cfg.recipe_dirs(full_compile=True):
        d = scratch / dirname
        (d / ".build").mkdir(parents=True)
        (d / "PKGBUILD").write_text("x")
        if with_build_content:
            (d / ".build" / "tree").write_text("x")


def test_scratch_has_sources_true(tmp_path):
    _populate_scratch(tmp_path, with_build_content=True)
    assert makepkg._scratch_has_sources(tmp_path, full_compile=True) is True


def test_scratch_has_sources_false_empty_build(tmp_path):
    # PKGBUILD present but .build empty -> no fetched source -> False.
    _populate_scratch(tmp_path, with_build_content=False)
    assert makepkg._scratch_has_sources(tmp_path, full_compile=True) is False


def test_scratch_has_sources_false_missing_pkgbuild(tmp_path):
    assert makepkg._scratch_has_sources(tmp_path, full_compile=True) is False


# --- build_own_packages offline branch, per tier ----------------------------
def test_offline_default_skips_makepkg(monkeypatch, tmp_path):
    # DEFAULT tier + complete cache -> skip makepkg entirely (the fast rerun).
    monkeypatch.setattr(makepkg.paths, "PKG_REPO", tmp_path)
    monkeypatch.setattr(makepkg.paths, "is_root", lambda: False)
    (tmp_path / "calamares-1-1-x86_64.pkg.tar.zst").write_text("")
    (tmp_path / "librewolf-1-1-x86_64.pkg.tar.zst").write_text("")

    def must_not_build(*a, **k):
        raise AssertionError("default offline rerun must not run makepkg")
    monkeypatch.setattr(makepkg, "_makepkg_one", must_not_build)

    makepkg.build_own_packages(offline=True, full_compile=False, progress=lambda _p: None)


def test_offline_full_missing_source_raises(monkeypatch, tmp_path):
    # FULL tier offline but the cached source tree is gone -> fail loudly, never
    # silently go online.
    monkeypatch.setattr(makepkg.paths, "CACHEDIR", tmp_path)
    monkeypatch.setattr(makepkg.paths, "PKG_REPO", tmp_path / "repo")
    monkeypatch.setattr(makepkg.paths, "is_root", lambda: False)
    monkeypatch.setattr(makepkg, "_makepkg_one",
                        lambda *a, **k: pytest.fail("must not build when source missing"))
    with pytest.raises(makepkg.MakepkgError):
        makepkg.build_own_packages(offline=True, full_compile=True, progress=lambda _p: None)


def test_offline_full_recompiles_and_preserves_scratch(monkeypatch, tmp_path):
    # FULL tier offline with a populated scratch -> RE-COMPILE (offline=True on every
    # makepkg call) AND leave the fetched source tree intact (the offline path must
    # never wipe the scratch, or the next rerun loses the Firefox source).
    scratch = tmp_path / "makepkg"
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(makepkg.paths, "CACHEDIR", tmp_path)
    monkeypatch.setattr(makepkg.paths, "PKG_REPO", repo)
    monkeypatch.setattr(makepkg.paths, "is_root", lambda: False)
    monkeypatch.setattr(makepkg, "_ensure_builder_user", lambda: "me")

    for dirname, _files in pkgbuild_cfg.recipe_dirs(full_compile=True):
        d = scratch / dirname
        (d / ".build").mkdir(parents=True)
        (d / "PKGBUILD").write_text("x")
        (d / ".build" / "sentinel").write_text("keep")

    calls = []

    def fake_one(builder, d, offline=False):
        calls.append((d.name, offline))
        (d / f"{d.name}-1-1-x86_64.pkg.tar.zst").write_text("")
    monkeypatch.setattr(makepkg, "_makepkg_one", fake_one)

    makepkg.build_own_packages(offline=True, full_compile=True, progress=lambda _p: None)

    assert calls, "offline full recompile did not invoke makepkg"
    assert all(off is True for _name, off in calls), "recompile must pass offline=True"
    # scratch (and its fetched source tree) must survive the recompile.
    assert (scratch / "librewolf" / ".build" / "sentinel").exists()
