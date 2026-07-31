"""The `azarch-sshd` build variant: a second ISO identical to the base one but
named azarch-sshd-<ver>-x86_64.iso and auto-running `azarch --sshd-hypervisor` at
boot.

The variant is threaded compile.sh(--sshd) -> build.py -> steps.run(variant="sshd").
Its two observable effects, both checked here as pure data/emit (no mkarchiso):

  1. profiledef's iso_name flips azarch -> azarch-sshd, so mkarchiso writes the
     azarch-sshd-*.iso filename the prompt asked for.
  2. steps emits + enables sshd-hypervisor-setup.service (a systemd oneshot that
     runs `azarch --sshd-hypervisor`) ONLY for the sshd variant; the base ISO never
     gets it, so there it stays a manual `sudo azarch --sshd-hypervisor`.

A drift in any of these silently ships the wrong ISO name or an sshd ISO that does
NOT actually start sshd on boot (or a base ISO that unexpectedly does).
"""

from __future__ import annotations

import re

from azarch import steps
from azarch.config import profile, system


# --- profiledef iso_name per variant ----------------------------------------

def _iso_name(pd: str) -> str:
    m = re.search(r'iso_name="([^"]+)"', pd)
    assert m, "profiledef has no iso_name"
    return m.group(1)


def test_iso_name_for_maps_variants():
    assert profile.iso_name_for("base") == "azarch"
    assert profile.iso_name_for("sshd") == "azarch-sshd"
    # An unknown variant must fall back to the base name, never crash the build.
    assert profile.iso_name_for("nonsense") == "azarch"
    assert profile.iso_name_for() == "azarch"


def test_profiledef_base_is_azarch():
    assert _iso_name(profile.profiledef_sh("base")) == "azarch"
    # Default (no arg) is the base ISO.
    assert _iso_name(profile.profiledef_sh()) == "azarch"


def test_profiledef_sshd_is_azarch_sshd():
    # This is what makes mkarchiso name the artifact azarch-sshd-<ver>-x86_64.iso.
    assert _iso_name(profile.profiledef_sh("sshd")) == "azarch-sshd"


def test_only_iso_name_differs_between_variants():
    # The variants must be otherwise byte-identical: same bootmodes, permissions,
    # squashfs options, everything. Normalizing the one iso_name line makes the rest
    # comparable, proving the variant changes ONLY the name (packages/behaviour
    # parity is what "basically like the normal one" requires).
    base = profile.profiledef_sh("base")
    sshd = profile.profiledef_sh("sshd")
    norm = lambda s: s.replace('iso_name="azarch-sshd"', 'iso_name="azarch"')
    assert norm(sshd) == base


# --- the auto-setup systemd unit --------------------------------------------

def test_sshd_service_runs_the_cli_subcommand():
    svc = system.SSHD_HYPERVISOR_SETUP_SERVICE
    # It must invoke exactly the documented subcommand -- this IS "on by default".
    assert "ExecStart=/usr/local/bin/azarch --sshd-hypervisor" in svc


def test_sshd_service_targets_main_via_sudo_user():
    # Run as root with SUDO_USER=main: the azarch CLI keys off ${SUDO_USER:-...} and
    # refuses a bare-root target, so this is what makes the pubkey land in
    # /home/main/.ssh (the account sshd accepts) without needing a PAM session.
    svc = system.SSHD_HYPERVISOR_SETUP_SERVICE
    assert "Environment=SUDO_USER=main" in svc
    assert "Type=oneshot" in svc


def test_sshd_service_ordering_is_sane():
    svc = system.SSHD_HYPERVISOR_SETUP_SERVICE
    # After pkgs-setup (whose `ufw enable` default-rejects incoming) so our
    # `ufw allow ssh` wins and :22 is reachable.
    assert "After=pkgs-setup.service" in svc
    assert "WantedBy=multi-user.target" in svc
    # MUST NOT order after the target that pulls it in (anti-pattern / cycle risk).
    assert "After=multi-user.target" not in svc


def test_sshd_service_guarded_on_cli_presence():
    # ConditionPathExists keeps it from failing loudly if the azarch CLI is absent.
    assert "ConditionPathExists=/usr/local/bin/azarch" in system.SSHD_HYPERVISOR_SETUP_SERVICE


# --- steps wiring: emit + enable only for the sshd variant ------------------

def _link_dest(airootfs):
    return (airootfs / "etc/systemd/system/multi-user.target.wants"
            / "sshd-hypervisor-setup.service")


def test_link_services_enables_sshd_only_for_sshd_variant(tmp_path):
    # Base variant: the enable symlink must NOT be created.
    base_root = tmp_path / "base"
    steps._link_services(base_root, "base")
    assert not _link_dest(base_root).is_symlink()
    # The three always-on daemon links ARE created (sanity that the helper ran).
    always = base_root / "etc/systemd/system/multi-user.target.wants/NetworkManager.service"
    assert always.is_symlink()

    # sshd variant: the enable symlink IS created, pointing at the unit file.
    sshd_root = tmp_path / "sshd"
    steps._link_services(sshd_root, "sshd")
    link = _link_dest(sshd_root)
    assert link.is_symlink()
    import os
    assert os.readlink(link) == "/etc/systemd/system/sshd-hypervisor-setup.service"


def test_link_services_default_variant_is_base(tmp_path):
    # Called with no variant (default) must behave like base: no sshd link.
    root = tmp_path / "default"
    steps._link_services(root)
    assert not _link_dest(root).is_symlink()
