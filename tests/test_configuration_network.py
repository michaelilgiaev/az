"""The `azarch network` command -- one front-end over nmcli / rfkill / bluetoothctl / ufw.

Az'arch wraps the confusing raw networking tools in a plain noun/verb command matching
`azarch theme` / `azarch wallpaper`. These tests pin, against the BUNDLED shipped script
(packages.azarch.bundle.bundle_source -- the exact /usr/local/bin/azarch artifact):

  * that `network` is a real top-level dispatch branch advertised in usage();
  * the noun surface (status/wifi/wired/bluetooth/airplane/firewall/ip) and that each
    noun dispatches to the right function and prints help;
  * that the ACTIONS build the correct backend argv (nmcli/ufw/rfkill/bluetoothctl)
    WITHOUT touching the host -- `_sudo` and the read helpers are stubbed;
  * the guard rails: unknown noun/verb -> rc 2, bad port token -> rc 2, a missing
    backend degrades to rc 1 with a clear message;
  * that Bluetooth is OFF by default (build-time) and airplane kills every radio.

The CLI is exercised via its bundle executed in one namespace, so tests drive the real
functions exactly as shipped.
"""

from __future__ import annotations

import types

import pytest

from packages.azarch.bundle import bundle_source
from modifications import openbox as desktop


def _cli():
    """Exec the bundled azarch CLI in a fresh module namespace (as shipped)."""
    mod = types.ModuleType("azarch_cli_network_test")
    exec(compile(bundle_source(), "azarch_cli", "exec"), mod.__dict__)
    return mod


def _capture_sudo(cli, monkeypatch, rc=0):
    """Replace _sudo with a recorder; return the list that receives each argv tuple."""
    calls: list[tuple] = []
    monkeypatch.setattr(cli, "_sudo", lambda *a, **k: (calls.append(a) or rc))
    return calls


def _stub_reads(cli, monkeypatch, have=True, run=(0, "")):
    """Stub the read side so nothing shells out: _have -> `have`, _run -> `run`."""
    monkeypatch.setattr(cli, "_have", lambda prog: have)
    monkeypatch.setattr(cli, "_run", lambda *a: run)


# --- dispatch wiring --------------------------------------------------------

def test_network_is_a_dispatch_branch_in_main():
    src = desktop.azarch_cli()
    assert 'cmd == "network"' in src
    assert "return cmd_network(argv[1:])" in src
    # advertised in the top-level usage()
    assert "network <wifi|wired|bluetooth|airplane|firewall|ip|status>" in src


def test_network_help_prints_usage_and_exits_zero(capsys):
    cli = _cli()
    rc = cli.main(["network", "--help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Usage: azarch network" in out
    for noun in ("wifi", "wired", "bluetooth", "airplane", "firewall", "ip"):
        assert noun in out
    # The firewall line advertises the full port verb set, including delete.
    assert "port list|open|close|delete" in out


def test_bare_network_prints_overview(monkeypatch, capsys):
    cli = _cli()
    # No backends present -> status still returns 0 and prints the sections.
    _stub_reads(cli, monkeypatch, have=False)
    rc = cli.main(["network"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Airplane mode:" in out
    assert "Bluetooth:" in out
    assert "Firewall:" in out


def test_unknown_noun_is_rc_two(capsys):
    cli = _cli()
    rc = cli.main(["network", "bogus"])
    assert rc == 2
    assert "unknown command" in capsys.readouterr().err


@pytest.mark.parametrize("noun", ["wifi", "wired", "bluetooth", "airplane", "firewall", "ip"])
def test_each_noun_help_exits_zero(noun, capsys):
    cli = _cli()
    assert cli.main(["network", noun, "--help"]) == 0
    assert "Usage:" in capsys.readouterr().out


# --- wifi -------------------------------------------------------------------

def test_wifi_connect_builds_nmcli_argv(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    rc = cli.main(["network", "wifi", "connect", "MyNet", "hunter2"])
    assert rc == 0
    assert ("nmcli", "device", "wifi", "connect", "MyNet", "password", "hunter2") in calls
    assert "Connected to MyNet." in capsys.readouterr().out


def test_wifi_connect_without_ssid_is_rc_two(capsys):
    cli = _cli()
    assert cli.main(["network", "wifi", "connect"]) == 2
    assert "need an SSID" in capsys.readouterr().err


def test_wifi_on_off_toggles_radio(monkeypatch):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "wifi", "on"]) == 0
    assert cli.main(["network", "wifi", "off"]) == 0
    assert ("nmcli", "radio", "wifi", "on") in calls
    assert ("nmcli", "radio", "wifi", "off") in calls


def test_wifi_without_nmcli_degrades(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: False)
    rc = cli.main(["network", "wifi", "on"])
    assert rc == 1
    assert "nmcli not found" in capsys.readouterr().err


# --- bluetooth (off by default) --------------------------------------------

def test_bluetooth_on_unblocks_and_enables(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    rc = cli.main(["network", "bluetooth", "on"])
    assert rc == 0
    assert ("rfkill", "unblock", "bluetooth") in calls
    assert ("systemctl", "enable", "--now", "bluetooth") in calls
    assert "Bluetooth enabled." in capsys.readouterr().out


def test_bluetooth_off_blocks_and_disables(monkeypatch):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "bluetooth", "off"]) == 0
    assert ("rfkill", "block", "bluetooth") in calls
    assert ("systemctl", "disable", "--now", "bluetooth") in calls


def test_bluetooth_connect_needs_mac(capsys):
    cli = _cli()
    assert cli.main(["network", "bluetooth", "connect"]) == 2
    assert "need a device MAC" in capsys.readouterr().err


# --- airplane ---------------------------------------------------------------

def test_airplane_on_kills_all_radios(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    rc = cli.main(["network", "airplane", "on"])
    assert rc == 0
    assert ("nmcli", "radio", "all", "off") in calls
    assert ("rfkill", "block", "all") in calls
    assert "Airplane mode ON" in capsys.readouterr().out


def test_airplane_off_restores_all_radios(monkeypatch):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "airplane", "off"]) == 0
    assert ("nmcli", "radio", "all", "on") in calls
    assert ("rfkill", "unblock", "all") in calls


def test_airplane_status_reads_nmcli(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: True)
    # nmcli radio all -> disabled  => airplane ON
    monkeypatch.setattr(cli, "_run",
                        lambda *a: (0, "disabled\n") if a[:3] == ("nmcli", "radio", "all")
                        else (0, ""))
    assert cli.main(["network", "airplane", "status"]) == 0
    assert "Airplane mode: on" in capsys.readouterr().out


# --- firewall + ports -------------------------------------------------------

def test_firewall_default_builds_ufw_argv(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    rc = cli.main(["network", "firewall", "default", "deny", "allow"])
    assert rc == 0
    assert ("ufw", "default", "deny", "incoming") in calls
    assert ("ufw", "default", "allow", "outgoing") in calls
    assert "incoming deny, outgoing allow" in capsys.readouterr().out


def test_firewall_default_rejects_bad_policy(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "firewall", "default", "open", "allow"]) == 2
    assert "allow|deny|reject" in capsys.readouterr().err


def test_firewall_enable_uses_force(monkeypatch):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "firewall", "enable"]) == 0
    assert ("ufw", "--force", "enable") in calls
    assert cli.main(["network", "firewall", "disable"]) == 0
    assert ("ufw", "disable") in calls


def test_firewall_port_open_and_close(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "firewall", "port", "open", "8080/tcp"]) == 0
    assert ("ufw", "allow", "8080/tcp") in calls
    assert cli.main(["network", "firewall", "port", "close", "53/udp"]) == 0
    assert ("ufw", "deny", "53/udp") in calls
    out = capsys.readouterr().out
    assert "Port 8080/tcp opened." in out
    assert "Port 53/udp closed." in out


def test_firewall_port_rejects_bad_token(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "firewall", "port", "open", "99999"]) == 2
    assert cli.main(["network", "firewall", "port", "open", "80/sctp"]) == 2
    assert cli.main(["network", "firewall", "port", "open", "abc"]) == 2
    assert "invalid port" in capsys.readouterr().err


# --- firewall port: Title column + delete (the PROMPT.md additions) ---------

def test_firewall_port_49154_has_timedate_title():
    """The port-title map ships 49154 -> 'timedate' (the Az'arch timedate home page)."""
    cli = _cli()
    assert cli.PORT_TITLES.get(49154) == "timedate"
    # The title is matched by base port, regardless of protocol suffix.
    assert cli._title_for_to("49154") == "timedate"
    assert cli._title_for_to("49154/tcp") == "timedate"
    # An untitled / non-numeric 'To' value yields an empty Title cell (never raises).
    assert cli._title_for_to("22/tcp") == ""
    assert cli._title_for_to("Anywhere") == ""


def test_firewall_port_list_renders_title_column():
    """`firewall port list` re-renders ufw's numbered rules with a leading Title column,
    and port 49154 shows the 'timedate' title in that column."""
    cli = _cli()
    sample = (
        "Status: active\n"
        "\n"
        "     To                         Action      From\n"
        "     --                         ------      ----\n"
        "[ 1] 49154                      DENY IN     Anywhere\n"
        "[ 2] 22/tcp                     ALLOW IN    Anywhere\n"
    )
    table = cli._render_port_table(sample)
    header = table.splitlines()
    # The Title column header is present...
    assert any(line.strip().startswith("#") and "Title" in line and "To" in line
               for line in header)
    # ...and 49154's row carries 'timedate' while the 22/tcp row's Title stays empty.
    row_49154 = next(l for l in header if "49154" in l)
    assert "timedate" in row_49154
    row_22 = next(l for l in header if "22/tcp" in l)
    assert "timedate" not in row_22


def test_firewall_port_list_dispatches_to_ufw_status_numbered(monkeypatch, capsys):
    """The list verb reads ufw status numbered (via a sudo -n probe) and prints the table."""
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: True)
    monkeypatch.setattr(cli, "_run",
                        lambda *a: (0, "Status: active\n[ 1] 49154   DENY IN   Anywhere\n"))
    _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "firewall", "port", "list"]) == 0
    out = capsys.readouterr().out
    assert "Title" in out
    assert "timedate" in out


def test_firewall_port_delete_removes_rule(monkeypatch, capsys):
    """`firewall port delete <n>` issues `ufw delete` for BOTH the allow and deny forms so
    the rule is removed whether it was opened or closed, and reports it deleted."""
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    calls = _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "firewall", "port", "delete", "8080/tcp"]) == 0
    assert ("ufw", "delete", "allow", "8080/tcp") in calls
    assert ("ufw", "delete", "deny", "8080/tcp") in calls
    assert "Port 8080/tcp deleted." in capsys.readouterr().out


def test_firewall_port_delete_rejects_bad_token(monkeypatch, capsys):
    cli = _cli()
    _stub_reads(cli, monkeypatch, have=True)
    _capture_sudo(cli, monkeypatch)
    assert cli.main(["network", "firewall", "port", "delete", "99999"]) == 2
    assert "invalid port" in capsys.readouterr().err


def test_firewall_port_help_lists_delete(capsys):
    cli = _cli()
    assert cli.main(["network", "firewall", "port", "--help"]) == 0
    assert "delete" in capsys.readouterr().out


def test_firewall_help_documents_title_and_delete(capsys):
    cli = _cli()
    assert cli.main(["network", "firewall", "--help"]) == 0
    out = capsys.readouterr().out
    assert "Title column" in out
    assert "port delete" in out


# --- ip (static / dynamic IPv4) --------------------------------------------

def test_ip_static_builds_nmcli_argv(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: True)
    # _conn_for_iface reads nmcli device rows; return a connection named 'Wired-1' for eth0.
    monkeypatch.setattr(cli, "_conn_for_iface", lambda iface: "Wired-1")
    calls = _capture_sudo(cli, monkeypatch)
    rc = cli.main(["network", "ip", "static", "eth0",
                   "192.168.1.50/24", "192.168.1.1", "1.1.1.1", "8.8.8.8"])
    assert rc == 0
    assert ("nmcli", "connection", "modify", "Wired-1",
            "ipv4.method", "manual",
            "ipv4.addresses", "192.168.1.50/24",
            "ipv4.gateway", "192.168.1.1") in calls
    assert ("nmcli", "connection", "modify", "Wired-1", "ipv4.dns", "1.1.1.1,8.8.8.8") in calls
    assert ("nmcli", "connection", "up", "Wired-1") in calls
    assert "Static IPv4 192.168.1.50/24" in capsys.readouterr().out


def test_ip_static_requires_cidr(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: True)
    monkeypatch.setattr(cli, "_conn_for_iface", lambda iface: "Wired-1")
    _capture_sudo(cli, monkeypatch)
    # address without /prefix is rejected before any sudo call
    assert cli.main(["network", "ip", "static", "eth0", "192.168.1.50", "192.168.1.1"]) == 2
    assert "must be CIDR" in capsys.readouterr().err


def test_ip_dynamic_switches_to_auto(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: True)
    monkeypatch.setattr(cli, "_conn_for_iface", lambda iface: "Wired-1")
    calls = _capture_sudo(cli, monkeypatch)
    rc = cli.main(["network", "ip", "dynamic", "eth0"])
    assert rc == 0
    assert ("nmcli", "connection", "modify", "Wired-1",
            "ipv4.method", "auto",
            "ipv4.addresses", "",
            "ipv4.gateway", "",
            "ipv4.dns", "") in calls
    assert "Dynamic IPv4 (DHCP) set on eth0." in capsys.readouterr().out


def test_ip_static_without_connection_is_rc_one(monkeypatch, capsys):
    cli = _cli()
    monkeypatch.setattr(cli, "_have", lambda prog: True)
    monkeypatch.setattr(cli, "_conn_for_iface", lambda iface: "")
    _capture_sudo(cli, monkeypatch)
    rc = cli.main(["network", "ip", "static", "eth9", "10.0.0.2/24", "10.0.0.1"])
    assert rc == 1
    assert "no NetworkManager connection" in capsys.readouterr().err


# --- port token validator (unit) -------------------------------------------

def test_port_spec_validator():
    cli = _cli()
    assert cli._port_spec("80") == "80"
    assert cli._port_spec("8080/tcp") == "8080/tcp"
    assert cli._port_spec("53/udp") == "53/udp"
    assert cli._port_spec("0") is None
    assert cli._port_spec("70000") is None
    assert cli._port_spec("80/sctp") is None
    assert cli._port_spec("abc") is None
