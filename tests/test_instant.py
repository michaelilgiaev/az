"""Tests for the INSTANT (unattended auto-install) variants.

Covers the three moving parts: the instant autorun SCRIPT (installer.instant_install_sh)
that pre-seeds the AZ_INSTALL_* environment and execs the CLI installer; the systemd
SERVICE (system.INSTANT_INSTALL_SERVICE) that runs it live-only; and the per-variant
emission/enablement + password posture in compiler._apply_variant. Plus the locked/kept
password sentinels the identity fragments honour.
"""

from __future__ import annotations

import installer
import installer_identity
import system
import compiler
import variants
from variants import Variant


# --- the instant autorun script --------------------------------------------


def test_instant_script_preseeds_defaults_and_execs_cli_installer():
    s = installer.instant_install_sh("Asia/Jerusalem", ssh=False)
    assert "AZ_INSTALL_CHOICE=1" in s          # largest non-USB disk, no confirm
    assert "AZ_INSTALL_USERNAME=main" in s
    assert "AZ_INSTALL_HOSTNAME=azarch" in s
    assert "azarch-install-cli.sh" in s        # hands off to the shared CLI installer
    assert s.startswith("#!/bin/bash")


def test_instant_script_threads_the_timezone():
    s = installer.instant_install_sh("Europe/London", ssh=False)
    assert "AZ_INSTALL_TIMEZONE='Europe/London'" in s


def test_instant_non_ssh_locks_the_account():
    s = installer.instant_install_sh("Asia/Jerusalem", ssh=False)
    assert "AZ_INSTALL_LOCK=1" in s            # Ubuntu-style locked !* account
    assert "AZ_INSTALL_KEEP_PASSWORD" not in s


def test_instant_ssh_keeps_the_cloned_password():
    s = installer.instant_install_sh("Asia/Jerusalem", ssh=True)
    # ssh variant: keep the --ssh hash the rootfs clone carried; do NOT lock, do NOT prompt.
    assert "AZ_INSTALL_KEEP_PASSWORD=1" in s
    assert "AZ_INSTALL_LOCK" not in s


def test_instant_scripts_are_valid_bash():
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    bash = shutil.which("bash")
    if not bash:
        return
    for ssh in (False, True):
        s = installer.instant_install_sh("Asia/Jerusalem", ssh=ssh)
        p = Path(tempfile.mkstemp(suffix=".sh")[1])
        p.write_text(s)
        assert subprocess.run([bash, "-n", str(p)]).returncode == 0
        p.unlink()


# --- the systemd service ----------------------------------------------------


def test_instant_service_is_live_medium_only():
    svc = system.INSTANT_INSTALL_SERVICE
    # ConditionPathExists=/run/archiso guards it to the archiso live system; the installed
    # clone (no /run/archiso) is CONDITION-skipped, so it can never re-wipe the target disk.
    assert "ConditionPathExists=/run/archiso" in svc


def test_instant_service_runs_the_staged_script_on_console():
    svc = system.INSTANT_INSTALL_SERVICE
    assert "ExecStart=/root/azarch/azarch-instant-install.sh" in svc
    assert "Type=oneshot" in svc
    assert "TTYPath=/dev/tty1" in svc           # visible on the console (no X needed)
    assert "Conflicts=getty@tty1.service" in svc  # do not fight the autologin over tty1
    assert "WantedBy=multi-user.target" in svc


# --- per-variant emission in _apply_variant ---------------------------------


def _prep(tmp_path):
    W = tmp_path
    airootfs = W / "airootfs"
    (airootfs / "etc/systemd/system/multi-user.target.wants").mkdir(parents=True)
    (airootfs / "root/azarch").mkdir(parents=True)
    return W, airootfs


def test_apply_variant_instant_emits_and_enables_the_unit(tmp_path):
    W, airootfs = _prep(tmp_path)
    compiler._apply_variant(W, airootfs, Variant(line="desktop", instant=True),
                            ssh_password_hash=None, timezone="Asia/Jerusalem")
    svc = airootfs / "etc/systemd/system/azarch-instant-install.service"
    link = airootfs / "etc/systemd/system/multi-user.target.wants/azarch-instant-install.service"
    script = airootfs / "root/azarch/azarch-instant-install.sh"
    assert svc.is_file()
    assert link.is_symlink() or link.exists()
    assert script.is_file()
    # non-ssh instant -> the staged script locks the account
    assert "AZ_INSTALL_LOCK=1" in script.read_text()


def test_apply_variant_instant_ssh_keeps_password(tmp_path):
    W, airootfs = _prep(tmp_path)
    fake_hash = "$6$salt$" + "d" * 86
    compiler._apply_variant(W, airootfs, Variant(line="server", instant=True, ssh=True),
                            ssh_password_hash=fake_hash, timezone="Asia/Jerusalem")
    script = (airootfs / "root/azarch/azarch-instant-install.sh").read_text()
    assert "AZ_INSTALL_KEEP_PASSWORD=1" in script  # keep the cloned --ssh hash
    # and the ssh side still emits its shadow + sshd service
    assert fake_hash in (airootfs / "etc/shadow").read_text()
    assert (airootfs / "etc/systemd/system/sshd-hypervisor-setup.service").is_file()


def test_apply_variant_non_instant_removes_the_unit(tmp_path):
    W, airootfs = _prep(tmp_path)
    # First make it instant, then re-apply a NON-instant variant on the same tree: the
    # instant unit/link/script must be affirmatively removed so a prior instant pass never
    # bleeds onto a plain ISO built from the shared airootfs.
    compiler._apply_variant(W, airootfs, Variant(line="desktop", instant=True),
                            ssh_password_hash=None, timezone="Asia/Jerusalem")
    compiler._apply_variant(W, airootfs, Variant(line="desktop", instant=False),
                            ssh_password_hash=None, timezone="Asia/Jerusalem")
    assert not (airootfs / "etc/systemd/system/azarch-instant-install.service").exists()
    assert not (airootfs / "etc/systemd/system/multi-user.target.wants"
                / "azarch-instant-install.service").exists()
    assert not (airootfs / "root/azarch/azarch-instant-install.sh").exists()


# --- the identity lock/keep sentinels ---------------------------------------


def test_identity_collect_honours_lock_and_keep_sentinels():
    col = installer_identity.identity_collect_sh()
    assert 'AZ_INSTALL_LOCK" = "1"' in col          # lock branch
    assert 'AZ_INSTALL_KEEP_PASSWORD" = "1"' in col  # keep branch


def test_identity_chroot_locks_accounts_when_marked():
    ch = installer_identity.identity_chroot_sh()
    assert "lock_account" in ch
    assert 'passwd -l "$az_login"' in ch
    assert "passwd -l root" in ch


def test_identity_write_persists_lock_marker_only_when_locked():
    wr = installer_identity.identity_write_sh()
    assert "lock_account" in wr
    # keep-password writes NEITHER a password file nor a lock marker (the `:` no-op branch)
    assert "az_keep_password" in wr


def test_default_instant_timezone_matches_installer_default():
    # The compile-flag default and the installer's own DEFAULT_TIMEZONE agree, so a bare
    # --instant lands on Asia/Jerusalem exactly like the interactive default.
    assert compiler.DEFAULT_INSTANT_TIMEZONE == installer_identity.DEFAULT_TIMEZONE
