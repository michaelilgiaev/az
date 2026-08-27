"""The `azarch power` command -- shutdown / restart / sleep / lock, with timers.

These pin, against the BUNDLED shipped script (packages.azarch.bundle.bundle_source -- the
exact /usr/local/bin/azarch artifact):

  * that `power` (and the top-level `shutdown`/`restart`/`sleep`/`lock` convenience verbs)
    are real dispatch branches in main();
  * the duration parser (30m/1h/90s/N-minutes) and HH:MM validation;
  * that immediate actions call `systemctl poweroff|reboot|suspend`, scheduling builds a
    `systemd-run --unit=azarch-<action> --on-active=/--on-calendar=` timer, --status reads
    `systemctl list-timers`, and --cancel stops the transient unit -- all WITHOUT touching
    the host (`_sudo` and the reads are stubbed);
  * lock tries `loginctl lock-session` first;
  * the guard rails: unknown verb -> rc 2, bad duration/time -> rc 2, scheduling with no
    --in/--at -> rc 2.

The command line interface is exercised via its bundle executed in one namespace, so tests
drive the real functions exactly as shipped.
"""

from __future__ import annotations

import types

import pytest

from packages.azarch.bundle import bundle_source
from packages import openbox as desktop


def _cli():
    """Exec the bundled azarch CLI in a fresh module namespace (as shipped)."""
    mod = types.ModuleType("azarch_cli_power_test")
    exec(compile(bundle_source(), "azarch_cli", "exec"), mod.__dict__)
    return mod


def _capture_sudo(cli, monkeypatch, rc=0):
    calls: list[tuple] = []
    monkeypatch.setattr(cli, "_sudo", lambda *a, **k: (calls.append(a) or rc))
    return calls


def _have(cli, monkeypatch, have=True):
    monkeypatch.setattr(cli, "_have", lambda prog: have)


# --- dispatch wiring --------------------------------------------------------

def test_power_is_a_dispatch_branch_in_main():
    # Assert against the SHIPPED bundle source (as the network test does) -- the exec'd
    # namespace has no source file for inspect.getsource.
    src = desktop.azarch_command_line_interface()
    assert 'cmd == "power"' in src
    assert "return cmd_power(argv[1:])" in src
    # The convenience top-level verbs exist too.
    for verb in ("shutdown", "restart", "sleep", "lock"):
        assert f'cmd == "{verb}"' in src


def test_power_help_exits_zero(capsys):
    cli = _cli()
    assert cli.cmd_power(["--help"]) == 0
    out = capsys.readouterr().out
    assert "shutdown" in out and "restart" in out and "sleep" in out and "lock" in out


def test_power_unknown_verb_is_rc_two(capsys):
    cli = _cli()
    assert cli.cmd_power(["frobnicate"]) == 2


# --- duration parsing -------------------------------------------------------

@pytest.mark.parametrize("token,secs", [
    ("90s", 90), ("30m", 1800), ("2h", 7200), ("1d", 86400),
    ("1h30m", 5400), ("5", 300),  # bare number = minutes
])
def test_parse_duration_valid(token, secs):
    cli = _cli()
    assert cli.parse_duration(token) == secs


@pytest.mark.parametrize("token", ["", "0", "-5", "x", "10x", "1h30", "h", "1.5h"])
def test_parse_duration_invalid(token):
    cli = _cli()
    assert cli.parse_duration(token) is None


@pytest.mark.parametrize("token", ["²", "①", "²h", "②③"])
def test_parse_duration_non_ascii_digits_dont_crash(token):
    # str.isdigit() accepts non-ASCII "digit" chars (superscript "²", circled "①")
    # that int() then rejects with ValueError. parse_duration must treat them as INVALID
    # (return None), never raise an uncaught exception that surfaces as a traceback.
    cli = _cli()
    assert cli.parse_duration(token) is None


def test_schedule_non_ascii_time_is_rc_two_not_crash(monkeypatch):
    # Same guard on the --at HH:MM validator: a non-ASCII "digit" must be rejected cleanly
    # (rc 2), not crash mid-schedule.
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: True)
    assert cli.cmd_power(["shutdown", "--at", "²:²"]) == 2


# --- immediate actions call systemctl ---------------------------------------

@pytest.mark.parametrize("verb,systemctl_verb", [
    ("shutdown", "poweroff"), ("restart", "reboot"), ("sleep", "suspend"),
])
def test_power_now_calls_systemctl(verb, systemctl_verb, monkeypatch):
    cli = _cli()
    _have(cli, monkeypatch, True)
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.cmd_power([verb]) == 0
    assert (calls[-1] == ("systemctl", systemctl_verb)), calls


# --- scheduling builds a systemd-run timer ----------------------------------

def test_schedule_in_builds_on_active_timer(monkeypatch):
    cli = _cli()
    _have(cli, monkeypatch, True)
    # _cancel_power runs first (idempotent replace); we only care the systemd-run call is
    # correct, so let reads report "no pending" and record every _sudo argv.
    monkeypatch.setattr(cli, "_power_pending", lambda action: "")
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.cmd_power(["shutdown", "--in", "30m"]) == 0
    run = [c for c in calls if c and c[0] == "systemd-run"]
    assert run, f"expected a systemd-run call, got {calls}"
    argv = run[0]
    assert "--unit=azarch-shutdown" in argv
    assert "--on-active=1800s" in argv
    assert argv[-2:] == ("systemctl", "poweroff")


def test_schedule_at_builds_on_calendar_timer(monkeypatch):
    cli = _cli()
    _have(cli, monkeypatch, True)
    monkeypatch.setattr(cli, "_power_pending", lambda action: "")
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.cmd_power(["restart", "--at", "3:07"]) == 0
    run = [c for c in calls if c and c[0] == "systemd-run"]
    assert run
    argv = run[0]
    assert "--unit=azarch-restart" in argv
    # HH:MM is zero-padded and expanded to a full OnCalendar spec.
    assert any(a == "--on-calendar=*-*-* 03:07:00" for a in argv), argv
    assert argv[-2:] == ("systemctl", "reboot")


def test_schedule_requires_in_or_at(capsys):
    cli = _cli()
    # A stray option that is neither --in/--at/--status/--cancel is rejected.
    assert cli.cmd_power(["shutdown", "--soon"]) == 2


def test_schedule_bad_duration_is_rc_two(monkeypatch, capsys):
    cli = _cli()
    _have(cli, monkeypatch, True)
    assert cli.cmd_power(["shutdown", "--in", "banana"]) == 2


def test_schedule_bad_time_is_rc_two(monkeypatch, capsys):
    cli = _cli()
    _have(cli, monkeypatch, True)
    assert cli.cmd_power(["sleep", "--at", "25:99"]) == 2


# --- status + cancel --------------------------------------------------------

def test_status_reads_list_timers(monkeypatch, capsys):
    cli = _cli()
    seen = {}

    def fake_run(argv, **k):
        seen["argv"] = argv
        class R:  # noqa: N801 -- tiny stand-in for CompletedProcess
            returncode = 0
            stdout = ("Mon 2026-08-27 03:07:00 UTC 1h left n/a n/a "
                      "azarch-shutdown.timer azarch-shutdown.service\n")
        return R()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli.cmd_power(["shutdown", "--status"])
    assert rc == 0
    assert "list-timers" in seen["argv"]
    assert "scheduled" in capsys.readouterr().out


def test_status_reports_none_when_no_timer(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_power_pending", lambda action: "")
    rc = cli.cmd_power(["restart", "--status"])
    assert rc == 1
    assert "no timer" in capsys.readouterr().out.lower()


def test_cancel_stops_the_transient_unit(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_power_pending", lambda action: "something pending")
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.cmd_power(["shutdown", "--cancel"]) == 0
    stops = [c for c in calls if c[:2] == ("systemctl", "stop")]
    assert any("azarch-shutdown.timer" in c for c in stops), calls


# --- lock -------------------------------------------------------------------

def test_lock_prefers_loginctl(monkeypatch, capsys):
    cli = _cli()
    _have(cli, monkeypatch, True)
    seen = {}

    def fake_run(argv, **k):
        seen.setdefault("first", argv)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.cmd_lock([]) == 0
    assert seen["first"][:2] == ["loginctl", "lock-session"]


def test_lock_no_locker_is_rc_one(monkeypatch, capsys):
    cli = _cli()
    _have(cli, monkeypatch, False)  # nothing available
    assert cli.cmd_lock([]) == 1
