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

_harden_dlagents is the other pure, load-bearing piece: a real build aborted on a
transient `curl: (92) HTTP/2 stream reset (0x8 CANCEL)` fetching the calamares
tarball despite the stock DLAGENT's --retry 3, because plain --retry recovers from
neither a mid-stream reset nor a slow-crawl stall. It rewrites the system
makepkg.conf's network curl agents to add --retry-all-errors + --speed-time/-limit
(and makepkg is pointed at the result via --config). These tests pin exactly which
agents are hardened, that nothing else in the config is disturbed, that there are no
duplicate flags, and that it is idempotent. _write_hardened_conf is its IO wrapper.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from azarch import makepkg
from azarch.configuration import pkgbuild as pkgbuild_cfg


# A faithful slice of Arch's stock /etc/makepkg.conf DLAGENTS block: the local
# file:: copy, the three network curl agents (each already carrying the stock
# --retry 3 --retry-delay 3), and the non-curl rsync/scp agents. Used by the
# DLAGENTS-hardening tests so they don't depend on the host's real config.
_STOCK_DLAGENTS = """\
# some preamble
CFLAGS="-march=native -O2"
DLAGENTS=('file::/usr/bin/curl -qgC - -o %o %u'
          'ftp::/usr/bin/curl -qgfC - --ftp-pasv --retry 3 --retry-delay 3 -o %o %u'
          'http::/usr/bin/curl -qgb "" -fLC - --retry 3 --retry-delay 3 -o %o %u'
          'https::/usr/bin/curl -qgb "" -fLC - --retry 3 --retry-delay 3 -o %o %u'
          'rsync::/usr/bin/rsync --no-motd -z %u %o'
          'scp::/usr/bin/scp -C %u %o')
PKGEXT='.pkg.tar.zst'
"""


def _agent_line(conf: str, proto: str) -> str:
    """The single DLAGENTS line defining `proto::` in a rendered makepkg.conf."""
    return next(l for l in conf.splitlines() if f"{proto}::" in l)


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


# --- _harden_dlagents: retry/stall-recovery flags on network curl agents -----
# A real build died fetching the calamares tarball with `curl: (92) HTTP/2 stream
# reset (0x8 CANCEL)` even though the stock https DLAGENT already had --retry 3.
# These tests pin the fix: network curl agents gain --retry-all-errors (retry a
# mid-stream reset, which plain --retry won't) and --speed-time/--speed-limit
# (abort a slow-crawl stall so a retry can happen), without disturbing anything
# else in the config, without duplicate --retry flags, and idempotently.
def test_harden_adds_recovery_flags_to_https_agent():
    out = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    https = _agent_line(out, "https")
    # The two flags the stock agent lacked -- the actual fix for the observed failure.
    assert "--retry-all-errors" in https
    assert "--speed-time" in https and "--speed-limit" in https


def test_harden_hardens_all_network_curl_agents():
    out = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    for proto in ("http", "https", "ftp"):
        assert "--retry-all-errors" in _agent_line(out, proto), proto


def test_harden_leaves_local_file_agent_untouched():
    # file:: is a local copy; retry/speed flags are meaningless there. It shares the
    # physical `DLAGENTS=(...` line, so this also guards the parser from hardening an
    # agent just because the line starts with DLAGENTS.
    out = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    assert _agent_line(out, "file") == _agent_line(_STOCK_DLAGENTS, "file")


def test_harden_leaves_non_curl_agents_untouched():
    out = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    assert _agent_line(out, "rsync") == _agent_line(_STOCK_DLAGENTS, "rsync")
    assert _agent_line(out, "scp") == _agent_line(_STOCK_DLAGENTS, "scp")


def test_harden_no_duplicate_retry_flags():
    # The stock line already had `--retry 3`; ours must REPLACE it, not append a
    # second one (curl would take the last value, silently overriding our count).
    out = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    https = _agent_line(out, "https")
    assert https.count("--retry ") == 1
    assert https.count("--retry-delay") == 1
    assert https.count("--speed-limit") == 1


def test_harden_preserves_curl_url_placeholders_and_flags():
    # makepkg substitutes %o (output) and %u (url); losing either breaks every
    # download. The stock functional flags must also survive.
    out = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    https = _agent_line(out, "https")
    assert https.rstrip().endswith("-o %o %u'")
    assert '-qgb ""' in https and "-fLC -" in https


def test_harden_preserves_unrelated_config_lines():
    out = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    assert 'CFLAGS="-march=native -O2"' in out
    assert "PKGEXT='.pkg.tar.zst'" in out
    assert "# some preamble" in out


def test_harden_is_idempotent():
    once = makepkg._harden_dlagents(_STOCK_DLAGENTS)
    twice = makepkg._harden_dlagents(once)
    assert once == twice


def test_harden_handles_config_without_dlagents():
    # A config that never defines DLAGENTS (makepkg would use its built-in default)
    # must pass through unchanged rather than error.
    conf = 'CFLAGS="-O2"\nPKGEXT=".pkg.tar.zst"\n'
    assert makepkg._harden_dlagents(conf) == conf


# --- _write_hardened_conf: the thin IO wrapper around _harden_dlagents -------
def test_write_hardened_conf_writes_hardened_file(tmp_path):
    recipe = tmp_path / "calamares"
    recipe.mkdir()
    sysconf = tmp_path / "makepkg.conf"
    sysconf.write_text(_STOCK_DLAGENTS)

    dest = makepkg._write_hardened_conf(recipe, system_conf=sysconf)

    assert dest is not None and dest.exists()
    assert dest.parent == recipe
    text = dest.read_text()
    assert "--retry-all-errors" in _agent_line(text, "https")
    # It is a standalone config (no `source`/include) so makepkg needs nothing else.
    assert "source " not in text


def test_write_hardened_conf_returns_none_when_system_conf_missing(tmp_path):
    # Missing system config -> None (makepkg falls back to its own default; we lose
    # only the extra resilience, never the build).
    recipe = tmp_path / "calamares"
    recipe.mkdir()
    missing = tmp_path / "does-not-exist.conf"
    assert makepkg._write_hardened_conf(recipe, system_conf=missing) is None
