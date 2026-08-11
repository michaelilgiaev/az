"""The `azarch-sshd` build variant: the second ISO a single build produces,
identical to the base one but named azarch-sshd-<ver>-x86_64.iso and auto-running
`azarch --sshd-hypervisor` at boot.

A single `compile.sh` run builds BOTH ISOs (there is no build-time flag to pick
one): every step up to mkarchiso is variant-independent, so the flow is
compile.sh -> compiler.py -> compiler.run(), which loops over compiler.VARIANTS
("base", "sshd") applying each variant's tiny differences via compiler._apply_variant
and running one mkarchiso pass each.

The two observable per-variant effects, both checked here as pure data/emit (no
mkarchiso):

  1. profiledef's iso_name flips azarch -> azarch-sshd, so mkarchiso writes the
     azarch-sshd-*.iso filename the prompt asked for.
  2. _apply_variant emits + enables sshd-hypervisor-setup.service (a systemd
     oneshot that runs `azarch --sshd-hypervisor`) ONLY for the sshd variant; the
     base ISO gets NEITHER the unit nor its enable link, so there it stays a manual
     `sudo azarch --sshd-hypervisor`.

A drift in any of these silently ships the wrong ISO name or an sshd ISO that does
NOT actually start sshd on boot (or a base ISO that unexpectedly does).
"""

from __future__ import annotations

import os
import re

import compiler
import profile
import system


# --- both ISOs, no flag ------------------------------------------------------

def test_variants_are_base_and_sshd():
    # A single build produces exactly these two ISOs, base first.
    assert compiler.VARIANTS == ("base", "sshd")


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


# --- always-on links: identical for both variants ---------------------------

def _link_dest(airootfs):
    return (airootfs / "etc/systemd/system/multi-user.target.wants"
            / "sshd-hypervisor-setup.service")


def test_link_services_never_creates_the_sshd_link(tmp_path):
    # _link_services now only enables the variant-INDEPENDENT daemons; the sshd
    # enable-link is applied per-variant by _apply_variant, never here.
    root = tmp_path / "root"
    compiler._link_services(root)
    assert not _link_dest(root).is_symlink()
    # The three always-on daemon links ARE created (sanity that the helper ran).
    always = root / "etc/systemd/system/multi-user.target.wants/NetworkManager.service"
    assert always.is_symlink()


# --- compiler._apply_variant: emit + enable only for the sshd variant ----------

def _svc_dest(airootfs):
    return airootfs / "etc/systemd/system/sshd-hypervisor-setup.service"


def test_apply_variant_sshd_emits_and_enables_service(tmp_path):
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    compiler._apply_variant(W, airootfs, "sshd")
    # The unit file is written...
    svc = _svc_dest(airootfs)
    assert svc.is_file()
    assert "azarch --sshd-hypervisor" in svc.read_text()
    # ...and enabled via a multi-user.target.wants symlink to it.
    link = _link_dest(airootfs)
    assert link.is_symlink()
    assert os.readlink(link) == "/etc/systemd/system/sshd-hypervisor-setup.service"
    # profiledef at the profile root carries the sshd iso_name.
    assert _iso_name((W / "profiledef.sh").read_text()) == "azarch-sshd"


def test_apply_variant_base_has_no_sshd_service_or_link(tmp_path):
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    compiler._apply_variant(W, airootfs, "base")
    assert not _svc_dest(airootfs).exists()
    assert not _link_dest(airootfs).is_symlink()
    assert _iso_name((W / "profiledef.sh").read_text()) == "azarch"


def test_apply_variant_base_after_sshd_removes_the_leftover(tmp_path):
    # The finalize loop reuses ONE shared airootfs across passes. If sshd were built
    # before base, base's pass MUST strip the sshd unit + enable link the sshd pass
    # left behind -- otherwise the base ISO would silently auto-start sshd too. Assert
    # _apply_variant("base") affirmatively removes both even when they pre-exist.
    W = tmp_path / "profile"
    airootfs = W / "airootfs"
    compiler._apply_variant(W, airootfs, "sshd")   # leave the sshd artifacts in place
    assert _svc_dest(airootfs).is_file()
    assert _link_dest(airootfs).is_symlink()
    compiler._apply_variant(W, airootfs, "base")   # base pass must clean them up
    assert not _svc_dest(airootfs).exists()
    assert not _link_dest(airootfs).is_symlink()


def test_run_signature_has_no_variant_param():
    # There is no build-time variant flag anymore: run() always builds both ISOs, so
    # it must NOT take a `variant` argument (a stray one would resurrect the old
    # one-ISO-per-run behaviour).
    import inspect
    params = inspect.signature(compiler.run).parameters
    assert "variant" not in params


def test_run_calls_mkarchiso_once_per_variant():
    # run() must invoke _run_mkarchiso once per variant (both ISOs in one build), and
    # append each returned ISO. Assert the finalize loop iterates VARIANTS and calls
    # _run_mkarchiso inside it.
    import inspect
    src = inspect.getsource(compiler.run)
    assert "for variant in VARIANTS" in src
    assert "_run_mkarchiso(" in src
    assert "_apply_variant(" in src


def test_mkarchiso_pass_resets_work_dir_before_running():
    # THE two-variant integration hazard: mkarchiso guards every build step with a
    # `_run_once` sentinel file under work/ (work/base.<fn>, work/iso.<fn>) and refuses
    # to delete a pre-existing work dir. If the second (sshd) pass reused the first
    # pass's work/, mkarchiso would skip airootfs/squashfs/ISO-write as "already done"
    # and NEVER write azarch-sshd-*.iso. So each pass MUST wipe work/ before invoking
    # mkarchiso. Assert the reset (rm -rf of the work dir) happens in _run_mkarchiso
    # BEFORE the mkarchiso subprocess is spawned.
    import inspect
    src = inspect.getsource(compiler._run_mkarchiso)
    # A work-dir wipe must be present...
    assert 'rm", "-rf"' in src and 'W / "work"' in src, \
        "_run_mkarchiso must rm -rf the work dir so each variant is a fresh mkarchiso pass"
    # ...and it must come BEFORE the mkarchiso invocation (else the sentinels from a
    # prior pass are still present when mkarchiso decides what to skip).
    reset_at = src.index('"work"')
    mkarchiso_at = src.index('"mkarchiso"')
    assert reset_at < mkarchiso_at, "work/ must be reset BEFORE mkarchiso runs"


def test_iso_selection_glob_distinguishes_base_from_sshd():
    # output/ can hold BOTH azarch-*.iso and azarch-sshd-*.iso. The base pass must
    # never pick up the sshd ISO. mkarchiso names artifacts <iso_name>-<YYYY.MM.DD>-
    # <arch>.iso, so anchoring the glob with a digit after "{iso_name}-" separates
    # them ("azarch-2026..." matches base; "azarch-sshd-..." does not, since 's' is
    # not a digit). Emulate the exact glob _run_mkarchiso uses and assert the split.
    import fnmatch
    both = ["azarch-2026.07.31-x86_64.iso", "azarch-sshd-2026.07.31-x86_64.iso"]
    base_hits = [f for f in both if fnmatch.fnmatch(f, "azarch-[0-9]*.iso")]
    sshd_hits = [f for f in both if fnmatch.fnmatch(f, "azarch-sshd-[0-9]*.iso")]
    assert base_hits == ["azarch-2026.07.31-x86_64.iso"]
    assert sshd_hits == ["azarch-sshd-2026.07.31-x86_64.iso"]
    # And the source really uses the digit-anchored glob (not a bare "-*.iso").
    import inspect
    src = inspect.getsource(compiler._run_mkarchiso)
    assert '{iso_name}-[0-9]*.iso' in src
