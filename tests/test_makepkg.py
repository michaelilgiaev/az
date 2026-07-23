"""azarch.makepkg -- the own-package build stage.

The heavy lifting (makepkg, sudo, gpg) is io-heavy and not unit-tested here. The
one pure, load-bearing branch is produced_names(): it decides which packages are
EXCLUDED from the Arch `pacman -Sw` download. Get it wrong and the build tries to
download a package that is on no mirror (Arch dropped calamares from extra/, so a
missing exclusion makes `pacman -Sw calamares` fail with "target not found" and
aborts the whole download). Both tiers now build calamares + librewolf.
_repo_has_all is pure given a dir.
"""

from __future__ import annotations

from azarch import makepkg


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
