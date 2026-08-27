"""The `azarch network ssh` server front-end + the first-run security notice.

Two closely-related surfaces, both pinned against the BUNDLED shipped script
(packages.azarch.bundle.bundle_source -- the exact /usr/local/bin/azarch artifact):

  * `azarch network ssh <start|stop|status>` -- start opens :22/tcp and enables sshd
    (via the `--sshd-hypervisor` bring-up), stop disables sshd AND closes :22, status
    reports both. This is the CLI behind the TUI's Network > SSH Server screen.
  * `azarch security-notice` -- the one-time base-desktop warning (password login + ssh
    OFF by default, enabling either exposes the box). It self-gates on the ssh variant /
    a real password and self-silences after the first show.

Nothing touches the host: `_sudo` and the reads are stubbed.
"""

from __future__ import annotations

import types

import pytest

from packages.azarch.bundle import bundle_source
from packages import openbox as desktop


def _cli():
    mod = types.ModuleType("azarch_cli_ssh_test")
    exec(compile(bundle_source(), "azarch_cli", "exec"), mod.__dict__)
    return mod


def _capture_sudo(cli, monkeypatch, rc=0):
    calls: list[tuple] = []
    monkeypatch.setattr(cli, "_sudo", lambda *a, **k: (calls.append(a) or rc))
    return calls


# --- ssh is a network noun --------------------------------------------------

def test_ssh_is_a_network_noun():
    src = desktop.azarch_command_line_interface()
    assert 'noun == "ssh"' in src
    assert "return cmd_ssh(rest)" in src
    # advertised in the network usage
    assert "ssh <start|stop|status>" in src


def test_network_ssh_help_exits_zero(capsys):
    cli = _cli()
    assert cli.main(["network", "ssh", "--help"]) == 0
    out = capsys.readouterr().out
    assert "start" in out and "stop" in out and "status" in out
    assert "22" in out  # mentions the port


def test_network_ssh_unknown_verb_is_rc_two(capsys):
    cli = _cli()
    assert cli.main(["network", "ssh", "frob"]) == 2


# --- start = the --sshd-hypervisor bring-up ---------------------------------

def test_ssh_start_delegates_to_sshd_hypervisor(monkeypatch):
    cli = _cli()
    called = {}

    def _fake():
        called["hit"] = True
        return 0

    monkeypatch.setattr(cli, "sshd_hypervisor", _fake)
    assert cli.cmd_ssh(["start"]) == 0
    assert called.get("hit")


# --- stop disables sshd AND closes port 22 ----------------------------------

def test_ssh_stop_disables_sshd_and_closes_port(monkeypatch, capsys):
    cli = _cli()
    calls = _capture_sudo(cli, monkeypatch, rc=0)
    # sshd_stop reads _power_pending? no -- it reads nothing; just runs _sudo steps.
    assert cli.cmd_ssh(["stop"]) == 0
    # It must disable+stop sshd...
    assert ("systemctl", "disable", "--now", "sshd") in calls
    # ...and delete the allow rule for 22/tcp (do not leave :22 open with no service).
    assert ("ufw", "delete", "allow", "22/tcp") in calls


def test_ssh_stop_reports_failure_when_systemctl_fails(monkeypatch, capsys):
    cli = _cli()
    # systemctl disable fails -> non-zero rc, error surfaced.
    monkeypatch.setattr(cli, "_sudo", lambda *a, **k: 1 if a[:1] == ("systemctl",) else 0)
    assert cli.cmd_ssh(["stop"]) == 1


# --- the sshd bring-up opens 22/tcp explicitly (user's "port 22 allow tcp") ---

def test_ssh_bringup_hardens_permit_empty_passwords_no():
    # DECISION 2 hardening: the ssh bring-up drops a sshd_config.d snippet with
    # `PermitEmptyPasswords no`, so a blank shadow field can never be logged into even if
    # one ever slipped through. Assert the shipped source writes it before enabling sshd.
    src = desktop.azarch_command_line_interface()
    assert "PermitEmptyPasswords no" in src
    assert "sshd_config.d/10-azarch-hardening.conf" in src


def test_ssh_bringup_writes_hardening_before_enabling_sshd(monkeypatch):
    cli = _cli()
    # The hardening config must be written BEFORE `systemctl enable --now sshd`, so sshd
    # reads it on first start. Record the order of the privileged calls.
    calls: list = []
    monkeypatch.setattr(cli, "_sudo", lambda *a, **k: calls.append(("sudo",) + a) or 0)
    monkeypatch.setattr(cli, "_sudo_write", lambda p, c: calls.append(("write", p)))
    monkeypatch.setattr(cli, "_is_mountpoint", lambda p: False)  # no share (bare metal)
    monkeypatch.setenv("SUDO_USER", "main")
    import pwd
    import types
    import tempfile
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(pwd, "getpwnam", lambda u: types.SimpleNamespace(pw_dir=tmp))
    assert cli.sshd_hypervisor() == 0
    write_idx = next(i for i, c in enumerate(calls) if c[0] == "write")
    enable_idx = next(i for i, c in enumerate(calls)
                      if c[:1] == ("sudo",) and "enable" in c)
    assert write_idx < enable_idx, calls


def test_sshd_hypervisor_opens_22_tcp_not_ssh_alias():
    # The bring-up must open 22/tcp explicitly (the user's firewall spec), so the port is
    # unambiguously tcp/22. Assert the shipped source uses `ufw allow 22/tcp`.
    src = desktop.azarch_command_line_interface()
    assert '"ufw", "allow", "22/tcp"' in src
    # And it must NOT still use the old `ufw allow ssh` alias.
    assert '"ufw", "allow", "ssh"' not in src


# --- security-notice: wording + self-gating ---------------------------------

def test_security_notice_is_a_dispatch_branch():
    src = desktop.azarch_command_line_interface()
    assert 'cmd == "security-notice"' in src
    assert "return cmd_security_notice(argv[1:])" in src


def test_security_notice_text_covers_the_required_points():
    cli = _cli()
    text = cli.SECURITY_NOTICE_TEXT
    low = text.lower()
    # The user asked for: password not configured, ssh exposure is a risk, and a
    # "stay safe / follow security practices" closing.
    assert "password" in low
    assert "ssh" in low
    assert "network" in low or "internet" in low
    assert "security practices" in low
    assert "stay safe" in low
    # Prose rules: no colons/semicolons/dashes in the notice sentences (paths/URLs exempt,
    # and there are none here). The apostrophe in "Az'arch" is allowed.
    assert ":" not in text and ";" not in text
    assert " - " not in text and "--" not in text


def test_security_notice_force_prints_text(monkeypatch, capsys):
    cli = _cli()
    # --force bypasses the gates and the stamp, always printing (used to preview wording).
    # Stub the desktop notifier + stamp writer so nothing touches the real home/display.
    monkeypatch.setattr(cli, "_notify_desktop", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_write_stamp", lambda *a, **k: None)
    assert cli.cmd_security_notice(["--force"]) == 0
    assert "security notice" in capsys.readouterr().out.lower()


def test_security_notice_quiet_on_ssh_variant(monkeypatch, tmp_path, capsys):
    cli = _cli()
    # On the ssh variant (enable-link present) the notice stays quiet and just stamps.
    monkeypatch.setattr(cli, "_ssh_variant_configured", lambda: True)
    monkeypatch.setattr(cli, "_main_has_login_password", lambda: False)
    stamp = tmp_path / "stamp"
    monkeypatch.setattr(cli, "_security_notice_stamp_path", lambda: str(stamp))
    written = {}
    monkeypatch.setattr(cli, "_write_stamp", lambda p: written.setdefault("p", p))
    rc = cli.cmd_security_notice([])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""  # nothing printed
    assert written.get("p") == str(stamp)  # decision recorded so it does not re-check


def test_security_notice_quiet_when_password_set(monkeypatch, tmp_path, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_ssh_variant_configured", lambda: False)
    monkeypatch.setattr(cli, "_main_has_login_password", lambda: True)
    stamp = tmp_path / "stamp"
    monkeypatch.setattr(cli, "_security_notice_stamp_path", lambda: str(stamp))
    monkeypatch.setattr(cli, "_write_stamp", lambda p: None)
    assert cli.cmd_security_notice([]) == 0
    assert capsys.readouterr().out.strip() == ""


def test_security_notice_shows_once_then_silent(monkeypatch, tmp_path, capsys):
    cli = _cli()
    # Base desktop, no password, not ssh variant -> shows ONCE, writes the stamp, then a
    # second call (stamp present) stays silent.
    monkeypatch.setattr(cli, "_ssh_variant_configured", lambda: False)
    monkeypatch.setattr(cli, "_main_has_login_password", lambda: False)
    monkeypatch.setattr(cli, "_notify_desktop", lambda *a, **k: None)
    stamp = tmp_path / "stamp"
    monkeypatch.setattr(cli, "_security_notice_stamp_path", lambda: str(stamp))
    # First call: prints and stamps (real _write_stamp so the file appears).
    assert cli.cmd_security_notice([]) == 0
    assert "security notice" in capsys.readouterr().out.lower()
    assert stamp.exists()
    # Second call: stamp present -> silent.
    assert cli.cmd_security_notice([]) == 0
    assert capsys.readouterr().out.strip() == ""


# --- the TUI sudo fix: non-interactive sudo when driven from the UI -----------

def test_sudo_is_noninteractive_under_the_tui(monkeypatch):
    cli = _cli()
    # The TUI sets AZARCH_SUDO_NONINTERACTIVE so privileged applies fail FAST instead of
    # hanging on a dead /dev/null prompt. With it set (and not root), _sudo must prefix
    # `sudo -n`. Without it, plain `sudo` (interactive) is kept for normal CLI use.
    seen = {}
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda argv, **k: seen.update(argv=argv) or type("R", (), {"returncode": 0})())
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)  # not root

    monkeypatch.setenv("AZARCH_SUDO_NONINTERACTIVE", "1")
    cli._sudo("ufw", "status", check=False)
    assert seen["argv"][:3] == ["sudo", "-n", "ufw"], seen["argv"]

    monkeypatch.delenv("AZARCH_SUDO_NONINTERACTIVE", raising=False)
    cli._sudo("ufw", "status", check=False)
    assert seen["argv"][:2] == ["sudo", "ufw"], seen["argv"]  # interactive kept


def test_sudo_is_direct_when_root(monkeypatch):
    cli = _cli()
    # As root, no sudo prefix at all (even with the env var set).
    seen = {}
    monkeypatch.setattr(cli.subprocess, "run",
                        lambda argv, **k: seen.update(argv=argv) or type("R", (), {"returncode": 0})())
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    monkeypatch.setenv("AZARCH_SUDO_NONINTERACTIVE", "1")
    cli._sudo("ufw", "status", check=False)
    assert seen["argv"][0] == "ufw", seen["argv"]


def test_tui_sets_noninteractive_sudo_env():
    # The C TUI must set AZARCH_SUDO_NONINTERACTIVE at startup so the applies it spawns run
    # sudo non-interactively (the fix for the UI wedging when a privileged action needs
    # sudo). Assert the shipped main.c does it.
    import pathlib
    main_c = pathlib.Path("libraries/packages/azarch/main.c").read_text()
    assert 'setenv("AZARCH_SUDO_NONINTERACTIVE", "1", 1)' in main_c


def test_security_notice_gate_reads_shadow_field(monkeypatch):
    cli = _cli()
    # _main_has_login_password treats a '$'-hash as "has password" and '!'/'*'/'' as not.
    def fake_run(argv, **k):
        class R:
            returncode = 0
            stdout = "main:$6$salt$digest:19000:0:99999:7:::\n"
        return R()
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._main_has_login_password() is True

    def fake_run_locked(argv, **k):
        class R:
            returncode = 0
            stdout = "main:!:19000:0:99999:7:::\n"
        return R()
    monkeypatch.setattr(cli.subprocess, "run", fake_run_locked)
    assert cli._main_has_login_password() is False
