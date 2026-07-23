"""azarch.config.pacman -- the pacman.conf variants.

These are pure string generators/transforms. The offline/online repo switching
(switch_to_local_repo, append_local_repo) is exactly the brittle string surgery
where a dropped line or a missed section silently produces a config that either
contacts the network when it must not, or fails to find the local repo.
"""

from __future__ import annotations

from azarch.config import pacman


# --- download_conf: host-independent fetch config --------------------------

def test_download_conf_never_includes_host_mirrorlist():
    # The whole point: fetch identically on Manjaro/Arch/Docker. Including the host
    # mirrorlist would point at the wrong distro's repos.
    conf = pacman.download_conf()
    assert "Include = /etc/pacman.d/mirrorlist" not in conf


def test_download_conf_trust_and_repos():
    conf = pacman.download_conf()
    assert "SigLevel          = Never" in conf
    assert "[core]" in conf and "[extra]" in conf and "[multilib]" in conf
    # Hard-coded Arch mirrors, not a host mirrorlist.
    assert "geo.mirror.pkgbuild.com" in conf


def test_download_conf_has_no_active_download_user():
    # pacman runs as root into root-owned scratch here; the privilege-dropped alpm
    # helper would fail, so no ACTIVE DownloadUser directive may be set. (The conf
    # DOES carry a comment explaining the omission, so match only non-comment lines.)
    for line in pacman.download_conf().splitlines():
        code = line.split("#", 1)[0].strip()
        assert not code.startswith("DownloadUser"), line


# --- build_profile_conf: mkarchiso's internal pacstrap ---------------------

def test_build_profile_conf_injects_cachedir():
    conf = pacman.build_profile_conf(cachedir="/build/cache/pacman-pkg")
    assert "CacheDir     = /build/cache/pacman-pkg" in conf


def test_build_profile_conf_without_cachedir_leaves_it_commented():
    conf = pacman.build_profile_conf(cachedir=None)
    assert "#CacheDir     = /var/cache/pacman/pkg/" in conf
    assert "CacheDir     = /build" not in conf


def test_build_profile_conf_noextracts_os_release():
    # os-release must be NoExtract'd so the Az'arch branding wins over `filesystem`.
    conf = pacman.build_profile_conf()
    assert "NoExtract   = usr/lib/os-release" in conf


def test_build_profile_conf_multilib_off():
    conf = pacman.build_profile_conf()
    assert "\n[multilib]\n" not in conf
    assert "#[multilib]" in conf


# --- installer_base_conf: the installed system's /etc/pacman.conf -----------

def test_installer_base_conf_enables_multilib():
    conf = pacman.installer_base_conf()
    assert "\n[multilib]\n" in conf
    # No build-only tweaks leak into the installed config.
    assert "NoExtract   = usr/lib/os-release" not in conf


# --- append_local_repo: online build, keep network repos + add local -------

def test_append_local_repo_adds_section():
    out = pacman.append_local_repo("[options]\n[core]\n", "/mnt/repo")
    assert "[pacstrap-azarch-repo]" in out
    assert "Server = file:///mnt/repo" in out
    assert "SigLevel = Never" in out
    # Network repo is kept.
    assert "[core]" in out


def test_append_local_repo_is_idempotent():
    once = pacman.append_local_repo("[core]\n", "/mnt/repo")
    twice = pacman.append_local_repo(once, "/mnt/repo")
    assert once == twice
    assert once.count("[pacstrap-azarch-repo]") == 1


# --- switch_to_local_repo: fully-offline rebuild ---------------------------

def test_switch_to_local_repo_drops_network_repos():
    conf = pacman.build_profile_conf()
    out = pacman.switch_to_local_repo(conf, "/mnt/repo")
    # Every active network repo section header is gone.
    assert "\n[core]\n" not in out
    assert "\n[extra]\n" not in out
    assert "\n[multilib]\n" not in out


def test_switch_to_local_repo_appends_single_local_repo():
    conf = pacman.build_profile_conf()
    out = pacman.switch_to_local_repo(conf, "/srv/azrepo")
    assert out.count("[pacstrap-azarch-repo]") == 1
    assert "Server = file:///srv/azrepo" in out
    assert out.rstrip().endswith("Server = file:///srv/azrepo")


def test_switch_to_local_repo_keeps_options_block():
    conf = pacman.build_profile_conf()
    out = pacman.switch_to_local_repo(conf, "/srv/azrepo")
    # The [options] section and its directives survive the surgery.
    assert "[options]" in out
    assert "HoldPkg     = pacman glibc" in out


# --- installer_pacstrap_conf: transient offline-install config -------------

def test_installer_pacstrap_conf_only_local_repo_active():
    conf = pacman.installer_pacstrap_conf()
    # Network repos all commented, local file:// repo active.
    assert "#[core]" in conf and "#[extra]" in conf
    assert "[pacstrap-azarch-repo]" in conf
    assert "Server = file:///mnt/pacstrap-azarch-repo/" in conf


# --- _options_block: the [options] header with the two toggled directives ---

def test_options_block_falsy_cachedir_leaves_commented():
    # cachedir is truthy-tested (`if cachedir`); an empty string is falsy, so the
    # default commented CacheDir line must survive and no active line be injected.
    ob = pacman._options_block(cachedir="")
    assert "#CacheDir     = /var/cache/pacman/pkg/" in ob
    # No uncommented CacheDir directive leaked in.
    for line in ob.splitlines():
        assert not line.startswith("CacheDir")


def test_options_block_truthy_cachedir_injected():
    ob = pacman._options_block(cachedir="/build/cache/pacman-pkg")
    assert "CacheDir     = /build/cache/pacman-pkg" in ob
    assert "#CacheDir     = /var/cache/pacman/pkg/" not in ob


def test_options_block_empty_noextract_leaves_commented():
    # noextract is truthy-tested too; an empty list is falsy -> the commented
    # placeholder "#NoExtract   =" is emitted, never an active empty NoExtract.
    ob = pacman._options_block(cachedir=None, noextract=[])
    assert "#NoExtract   =" in ob
    for line in ob.splitlines():
        assert not line.startswith("NoExtract")


def test_options_block_noextract_paths_injected():
    ob = pacman._options_block(cachedir=None, noextract=["usr/lib/os-release"])
    assert "NoExtract   = usr/lib/os-release" in ob


# --- _net_repos: multilib active vs commented -------------------------------

def test_net_repos_multilib_true_active():
    block = pacman._net_repos(multilib=True)
    assert "\n[core]\n" in block and "\n[extra]\n" in block
    # Multilib section header is uncommented (active).
    assert "\n[multilib]\n" in block
    assert "#[multilib]" not in block


def test_net_repos_multilib_false_commented():
    block = pacman._net_repos(multilib=False)
    assert "\n[core]\n" in block and "\n[extra]\n" in block
    # Multilib header is commented out, not active.
    assert "\n[multilib]\n" not in block
    assert "#[multilib]" in block
    assert "#Include = /etc/pacman.d/mirrorlist" in block
