#!/usr/bin/env python3
"""azarch guest CLI -- `azarch network` (one friendly front-end for ALL networking).

WHY THIS EXISTS. The raw tools -- nmcli (NetworkManager), rfkill, bluetoothctl, ufw --
are powerful but hard to remember. `azarch network` wraps them in the same plain
noun/verb shape as `azarch theme` and `azarch wallpaper`, so wifi, wired, bluetooth,
firewall, ports, static/dynamic IPv4 and an airplane toggle are all one command.

SHAPE. `azarch network <noun> <verb...>`. The nouns:

  status                     one-screen overview (bare `azarch network` does this too)
  wifi                       list/scan, connect <ssid> [pass], disconnect, on/off, status
  wired                      on/off, status (NetworkManager management of ethernet)
  bluetooth                  on/off (OFF by default), status, list/scan,
                             pair/connect/disconnect <mac>
  airplane                   on/off/toggle/status -- kill/restore ALL radios at once
  firewall                   status, enable/disable, default <in> <out>,
                             port list (with a Title column) |open <n[/proto]>
                             |close <n[/proto]>|delete <n[/proto]>
  ip                         show, static <iface> <cidr> <gw> [dns...], dynamic <iface>

BACKENDS + DEGRADATION. Each backend is probed with _have(); a missing tool prints a
clear one-line reason and returns 1 rather than a confusing traceback. nmcli drives
wifi/wired/ip and the radio side of airplane; rfkill is the hard radio kill (airplane
+ bluetooth block); bluetoothctl + systemctl drive bluetooth; ufw drives the firewall.

PRIVILEGE. Queries run as the user; changes go through _sudo() (nmcli connection edits,
ufw, systemctl, rfkill). Output is result-only on stdout, errors on stderr, exit codes
0 (ok) / 1 (error) / 2 (usage) -- identical to the rest of the CLI.

DEFAULTS ARE SET AT BUILD TIME, NOT HERE. The ISO ships firewall ENABLED (deny incoming,
allow outgoing, :49154 timedate closed) and bluetooth DISABLED; the sshd variant also
allows ssh. This module is the live control surface on top of those defaults.
"""

from __future__ import annotations

# BUNDLE_START


# ---------------------------------------------------------------------------
# tiny shared helpers for this module (query backends without sudo)
# ---------------------------------------------------------------------------
def _run(*args: str) -> tuple[int, str]:
    """Run a read-only command as the current user; return (returncode, stdout).

    stderr is swallowed (these are status queries; a non-zero rc is reported by the
    caller). Used for the nmcli/rfkill/bluetoothctl/ufw *reads*; the *writes* go through
    _sudo() from common.py."""
    try:
        r = subprocess.run(list(args), stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, check=False)
    except OSError:
        return 1, ""
    return r.returncode, r.stdout.decode("utf-8", "replace")


def _need(prog: str, hint: str) -> bool:
    """True if `prog` is on PATH; else print a clear one-line reason and return False.

    `hint` names the package/feature so the message is actionable, e.g.
    _need("nmcli", "NetworkManager") -> "azarch network: nmcli not found (NetworkManager)."."""
    if _have(prog):
        return True
    _err(f"azarch network: {prog} not found ({hint} is required).")
    return False


# ---------------------------------------------------------------------------
# NetworkManager helpers (wifi / wired / ip all sit on nmcli)
# ---------------------------------------------------------------------------
def _nm_field(fields: str, *args: str) -> list[list[str]]:
    """Run `nmcli -t -f <fields> <args...>` and return rows split on ':'. The terse (-t)
    output is colon-separated and stable, so this is the machine-readable nmcli read."""
    rc, out = _run("nmcli", "-t", "-f", fields, *args)
    if rc != 0:
        return []
    rows: list[list[str]] = []
    for line in out.splitlines():
        if line:
            # nmcli escapes literal ':' in values as '\:' -- unescape after splitting.
            rows.append([c.replace("\\:", ":") for c in _split_terse(line)])
    return rows


def _split_terse(line: str) -> list[str]:
    """Split one nmcli -t line on unescaped ':' (nmcli backslash-escapes ':' inside a
    field). Kept tiny; nmcli never escapes anything else in -t output we read."""
    out: list[str] = []
    cur = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            cur += line[i:i + 2]
            i += 2
            continue
        if ch == ":":
            out.append(cur)
            cur = ""
        else:
            cur += ch
        i += 1
    out.append(cur)
    return out


def _nm_radio(kind: str) -> str:
    """Current nmcli radio state for a SINGLE radio ('wifi' | 'wwan') -> 'enabled'/'disabled'
    (or '' if unavailable). Only call this for a single radio: `nmcli radio all` prints a
    two-line table (header + values), so its .strip() is not a single word -- use
    _airplane_is_on() for the all-radios verdict instead."""
    rc, out = _run("nmcli", "radio", kind)
    return out.strip() if rc == 0 else ""


def _conn_for_iface(iface: str) -> str:
    """The NetworkManager connection NAME bound to a device, or "" if none. Used by the
    ip static/dynamic commands, which edit the device's connection profile."""
    for dev, _typ, _state, conn in _nm_field("DEVICE,TYPE,STATE,CONNECTION", "device"):
        if dev == iface:
            return conn
    return ""


# ---------------------------------------------------------------------------
# status (the bare `azarch network`)
# ---------------------------------------------------------------------------
def _internet_state() -> str:
    """The plain headline the TUI shows too: 'Online - Connected to Internet' when
    NetworkManager reports FULL connectivity, else 'Offline - No Internet'. This is the one
    thing a developer actually cares about, so it leads the overview."""
    if _have("nmcli"):
        rc, out = _run("nmcli", "networking", "connectivity")
        if rc == 0 and out.strip() == "full":
            return "Online - Connected to Internet"
    return "Offline - No Internet"


def network_status() -> int:
    """One-screen overview across every backend (the bare `azarch network`)."""
    print(_internet_state())
    if _have("nmcli"):
        rc, out = _run("nmcli", "-t", "-f", "STATE", "general")
        print(f"NetworkManager: {out.strip() or 'unknown'}" if rc == 0
              else "NetworkManager: unavailable")
        actives = [r for r in _nm_field("NAME,TYPE,DEVICE", "connection", "show", "--active")]
        if actives:
            for name, typ, dev in actives:
                print(f"  active: {name} ({typ}) on {dev}")
        else:
            print("  active: none")
        print(f"  wifi radio: {_nm_radio('wifi') or 'unknown'}")
    else:
        print("NetworkManager: nmcli not found")
    print(f"Airplane mode: {'on' if _airplane_is_on() else 'off'}")
    print(f"Bluetooth: {_bt_state()}")
    _firewall_print_status(indent="")
    return 0


# ---------------------------------------------------------------------------
# wifi
# ---------------------------------------------------------------------------
def _wifi_list() -> int:
    if not _need("nmcli", "NetworkManager"):
        return 1
    _sudo("nmcli", "device", "wifi", "rescan", check=False)
    rc, out = _run("nmcli", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list")
    if rc != 0:
        _err("azarch network wifi: could not list networks (is wifi enabled?).")
        return 1
    print(out.rstrip("\n"))
    return 0


def _wifi_connect(args: list[str]) -> int:
    if not args:
        _err("azarch network wifi connect: need an SSID.")
        return 2
    if not _need("nmcli", "NetworkManager"):
        return 1
    ssid = args[0]
    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if len(args) > 1:
        cmd += ["password", args[1]]
    rc = _sudo(*cmd, check=False)
    if rc != 0:
        _err(f"azarch network wifi: failed to connect to {ssid}.")
        return 1
    print(f"Connected to {ssid}.")
    return 0


def _wifi_radio(on: bool) -> int:
    if not _need("nmcli", "NetworkManager"):
        return 1
    rc = _sudo("nmcli", "radio", "wifi", "on" if on else "off", check=False)
    if rc != 0:
        _err("azarch network wifi: could not toggle the wifi radio.")
        return 1
    print(f"Wifi radio {'enabled' if on else 'disabled'}.")
    return 0


def _wifi_disconnect() -> int:
    if not _need("nmcli", "NetworkManager"):
        return 1
    # Disconnect every wifi device (there is usually one).
    devs = [d for d, t, *_ in _nm_field("DEVICE,TYPE", "device") if t == "wifi"]
    if not devs:
        print("No wifi device to disconnect.")
        return 0
    rc = 0
    for d in devs:
        rc |= _sudo("nmcli", "device", "disconnect", d, check=False)
    print("Wifi disconnected." if rc == 0 else "Wifi disconnect reported an error.")
    return 0 if rc == 0 else 1


def _wifi_status() -> int:
    print(f"Wifi radio: {_nm_radio('wifi') or 'unknown'}")
    for name, typ, dev in _nm_field("NAME,TYPE,DEVICE", "connection", "show", "--active"):
        if "wireless" in typ:
            print(f"  connected: {name} on {dev}")
    return 0


def cmd_wifi(args: list[str]) -> int:
    """`azarch network wifi ...`"""
    verb = args[0] if args else "status"
    rest = args[1:]
    if verb in ("list", "scan"):
        return _wifi_list()
    if verb == "connect":
        return _wifi_connect(rest)
    if verb == "disconnect":
        return _wifi_disconnect()
    if verb == "on":
        return _wifi_radio(True)
    if verb == "off":
        return _wifi_radio(False)
    if verb == "status":
        return _wifi_status()
    if verb in ("--help", "-h", "help"):
        print("Usage: azarch network wifi [list|connect <ssid> [pass]|disconnect|on|off|status]")
        return 0
    _err(f"azarch network wifi: unknown verb: {verb}")
    return 2


# ---------------------------------------------------------------------------
# wired (ethernet: toggle NetworkManager management of the device)
# ---------------------------------------------------------------------------
def _wired_devices() -> list[str]:
    return [d for d, t, *_ in _nm_field("DEVICE,TYPE", "device") if t == "ethernet"]


def _wired_toggle(on: bool) -> int:
    if not _need("nmcli", "NetworkManager"):
        return 1
    devs = _wired_devices()
    if not devs:
        print("No wired (ethernet) device found.")
        return 0
    rc = 0
    for d in devs:
        rc |= _sudo("nmcli", "device", "connect" if on else "disconnect", d, check=False)
    if rc != 0:
        _err("azarch network wired: could not toggle the wired device.")
        return 1
    print(f"Wired {'connected' if on else 'disconnected'}.")
    return 0


def _wired_status() -> int:
    devs = _wired_devices()
    if not devs:
        print("Wired: no ethernet device.")
        return 0
    for d, t, state, conn in _nm_field("DEVICE,TYPE,STATE,CONNECTION", "device"):
        if t == "ethernet":
            print(f"Wired {d}: {state}" + (f" ({conn})" if conn else ""))
    return 0


def cmd_wired(args: list[str]) -> int:
    """`azarch network wired ...`"""
    verb = args[0] if args else "status"
    if verb == "on":
        return _wired_toggle(True)
    if verb == "off":
        return _wired_toggle(False)
    if verb == "status":
        return _wired_status()
    if verb in ("--help", "-h", "help"):
        print("Usage: azarch network wired [on|off|status]")
        return 0
    _err(f"azarch network wired: unknown verb: {verb}")
    return 2


# ---------------------------------------------------------------------------
# bluetooth (OFF by default; on/off flips the service AND unblocks rfkill)
# ---------------------------------------------------------------------------
def _bt_state() -> str:
    """'on' if the bluetooth service is active and not rfkill-blocked, else 'off'
    (or 'unavailable' if neither bluetoothctl nor the service exists)."""
    if not (_have("bluetoothctl") or _have("systemctl")):
        return "unavailable"
    rc, out = _run("systemctl", "is-active", "bluetooth")
    active = out.strip() == "active"
    if _have("rfkill"):
        _rc, ro = _run("rfkill", "list", "bluetooth")
        if "Soft blocked: yes" in ro or "Hard blocked: yes" in ro:
            return "off"
    return "on" if active else "off"


def _bt_toggle(on: bool) -> int:
    ok = False
    if _have("rfkill"):
        _sudo("rfkill", "unblock" if on else "block", "bluetooth", check=False)
        ok = True
    if _have("systemctl"):
        action = ("enable", "--now") if on else ("disable", "--now")
        _sudo("systemctl", *action, "bluetooth", check=False)
        ok = True
    if not ok:
        _err("azarch network bluetooth: neither rfkill nor systemctl available.")
        return 1
    if on and _have("bluetoothctl"):
        _sudo("bluetoothctl", "power", "on", check=False)
    print(f"Bluetooth {'enabled' if on else 'disabled'}.")
    return 0


def _bt_scan() -> int:
    if not _need("bluetoothctl", "bluez-utils"):
        return 1
    # A short, bounded discovery: turn scanning on, wait, list, off. Timeout keeps it from
    # hanging the CLI (per the project's "always bound a program" rule).
    _sudo("bluetoothctl", "--timeout", "6", "scan", "on", check=False)
    rc, out = _run("bluetoothctl", "devices")
    if rc != 0:
        _err("azarch network bluetooth: could not list devices.")
        return 1
    print(out.rstrip("\n") or "No devices found.")
    return 0


def _bt_dev(verb: str, mac: str) -> int:
    if not mac:
        _err(f"azarch network bluetooth {verb}: need a device MAC address.")
        return 2
    if not _need("bluetoothctl", "bluez-utils"):
        return 1
    rc = _sudo("bluetoothctl", verb, mac, check=False)
    if rc != 0:
        _err(f"azarch network bluetooth: {verb} {mac} failed.")
        return 1
    print(f"Bluetooth {verb} {mac} ok.")
    return 0


def cmd_bluetooth(args: list[str]) -> int:
    """`azarch network bluetooth ...` (disabled by default)."""
    verb = args[0] if args else "status"
    rest = args[1:]
    if verb == "on":
        return _bt_toggle(True)
    if verb == "off":
        return _bt_toggle(False)
    if verb == "status":
        print(f"Bluetooth: {_bt_state()}")
        return 0
    if verb in ("list", "scan"):
        return _bt_scan()
    if verb in ("pair", "connect", "disconnect", "remove", "trust"):
        return _bt_dev(verb, rest[0] if rest else "")
    if verb in ("--help", "-h", "help"):
        print("Usage: azarch network bluetooth "
              "[on|off|status|list|pair <mac>|connect <mac>|disconnect <mac>]")
        return 0
    _err(f"azarch network bluetooth: unknown verb: {verb}")
    return 2


# ---------------------------------------------------------------------------
# airplane (kill/restore every radio at once: nmcli radio all + rfkill)
# ---------------------------------------------------------------------------
def _airplane_is_on() -> bool:
    """True when airplane mode is ON = the controllable radios are all down. Default OFF.

    `nmcli -t radio all` prints ONE terse line 'WIFI-HW:WIFI:WWAN-HW:WWAN' (e.g.
    'enabled:disabled:missing:enabled'); the SOFTWARE radios are WIFI and WWAN -- fields at
    indices 1 and 3 (the '-HW' fields 0 and 2 are hardware kill switches). Airplane is ON iff
    neither software radio is 'enabled'. (The old code used `nmcli radio all` and
    compared the whole two-line table to 'disabled', which was never equal.) Falls back to
    rfkill (ON == every listed radio soft/hard blocked)."""
    rc, out = _run("nmcli", "-t", "radio", "all")
    if rc == 0 and out.strip():
        fields = out.strip().splitlines()[0].split(":")
        software = [fields[i] for i in (1, 3) if i < len(fields)]
        if software:
            return not any(s == "enabled" for s in software)
    if _have("rfkill"):
        _rc, out = _run("rfkill", "list")
        blocks = [ln for ln in out.splitlines() if "blocked" in ln.lower()]
        # ON only if there is at least one radio and none is unblocked.
        return bool(blocks) and all("yes" in ln.lower() for ln in blocks)
    return False


def _airplane_set(on: bool) -> int:
    """on=True -> all radios OFF (airplane engaged). Uses nmcli radio all when present and
    rfkill as the hard kill so non-NM radios go down too."""
    did = False
    if _have("nmcli"):
        _sudo("nmcli", "radio", "all", "off" if on else "on", check=False)
        did = True
    if _have("rfkill"):
        _sudo("rfkill", "block" if on else "unblock", "all", check=False)
        did = True
    if not did:
        _err("azarch network airplane: neither nmcli nor rfkill available.")
        return 1
    print(f"Airplane mode {'ON -- all radios off' if on else 'OFF -- radios restored'}.")
    return 0


def cmd_airplane(args: list[str]) -> int:
    """`azarch network airplane ...` -- the all-radios toggle."""
    verb = args[0] if args else "status"
    if verb == "on":
        return _airplane_set(True)
    if verb == "off":
        return _airplane_set(False)
    if verb == "toggle":
        return _airplane_set(not _airplane_is_on())
    if verb == "status":
        print(f"Airplane mode: {'on' if _airplane_is_on() else 'off'}")
        return 0
    if verb in ("--help", "-h", "help"):
        print("Usage: azarch network airplane [on|off|toggle|status]")
        return 0
    _err(f"azarch network airplane: unknown verb: {verb}")
    return 2


# ---------------------------------------------------------------------------
# firewall (ufw) + ports
# ---------------------------------------------------------------------------
# The firewall noun (ufw enable/disable/default, the port open/close/delete verbs, the
# Title-column listing, and PORT_TITLES) lives in its OWN module, firewall.py -- network.py
# was outgrowing the per-file size budget. It is bundled ahead of this module, so
# cmd_firewall / _firewall_print_status resolve by bare name here (see bundle.MODULE_ORDER).


# ---------------------------------------------------------------------------
# ip (static / dynamic IPv4 on a device's NetworkManager connection)
# ---------------------------------------------------------------------------
def _ip_show() -> int:
    if not _need("nmcli", "NetworkManager"):
        return 1
    rc, out = _run("nmcli", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status")
    if rc == 0:
        print(out.rstrip("\n"))
    for dev, _t, state, _c in _nm_field("DEVICE,TYPE,STATE,CONNECTION", "device"):
        if state == "connected":
            rc2, addr = _run("nmcli", "-g", "IP4.ADDRESS", "device", "show", dev)
            if rc2 == 0 and addr.strip():
                print(f"  {dev}: {addr.strip()}")
    return 0


def _ip_static(args: list[str]) -> int:
    """`ip static <iface> <cidr> <gateway> [dns...]` -- pin a manual IPv4 on the device's
    connection and bring it back up."""
    if len(args) < 3:
        _err("azarch network ip static: need <iface> <address/prefix> <gateway> [dns...].")
        return 2
    if not _need("nmcli", "NetworkManager"):
        return 1
    iface, cidr, gateway = args[0], args[1], args[2]
    dns = ",".join(args[3:]) if len(args) > 3 else ""
    if "/" not in cidr:
        _err("azarch network ip static: address must be CIDR, e.g. 192.168.1.50/24.")
        return 2
    conn = _conn_for_iface(iface)
    if not conn:
        _err(f"azarch network ip static: no NetworkManager connection on {iface}.")
        return 1
    rc = _sudo("nmcli", "connection", "modify", conn,
               "ipv4.method", "manual",
               "ipv4.addresses", cidr,
               "ipv4.gateway", gateway, check=False)
    if dns:
        rc |= _sudo("nmcli", "connection", "modify", conn, "ipv4.dns", dns, check=False)
    rc |= _sudo("nmcli", "connection", "up", conn, check=False)
    if rc != 0:
        _err(f"azarch network ip static: could not apply the static address on {iface}.")
        return 1
    print(f"Static IPv4 {cidr} (gw {gateway}) set on {iface}.")
    return 0


def _ip_dynamic(args: list[str]) -> int:
    """`ip dynamic <iface>` -- switch the device's connection back to DHCP."""
    if not args:
        _err("azarch network ip dynamic: need <iface>.")
        return 2
    if not _need("nmcli", "NetworkManager"):
        return 1
    iface = args[0]
    conn = _conn_for_iface(iface)
    if not conn:
        _err(f"azarch network ip dynamic: no NetworkManager connection on {iface}.")
        return 1
    rc = _sudo("nmcli", "connection", "modify", conn,
               "ipv4.method", "auto",
               "ipv4.addresses", "",
               "ipv4.gateway", "",
               "ipv4.dns", "", check=False)
    rc |= _sudo("nmcli", "connection", "up", conn, check=False)
    if rc != 0:
        _err(f"azarch network ip dynamic: could not switch {iface} to DHCP.")
        return 1
    print(f"Dynamic IPv4 (DHCP) set on {iface}.")
    return 0


def cmd_ip(args: list[str]) -> int:
    """`azarch network ip ...`"""
    verb = args[0] if args else "show"
    rest = args[1:]
    if verb == "show":
        return _ip_show()
    if verb == "static":
        return _ip_static(rest)
    if verb == "dynamic":
        return _ip_dynamic(rest)
    if verb in ("--help", "-h", "help"):
        print("Usage: azarch network ip "
              "[show|static <iface> <addr/prefix> <gw> [dns...]|dynamic <iface>]")
        return 0
    _err(f"azarch network ip: unknown verb: {verb}")
    return 2


# ---------------------------------------------------------------------------
# top-level dispatch + usage
# ---------------------------------------------------------------------------
def network_usage() -> None:
    print(
        "Usage: azarch network <command>\n"
        "\n"
        "One friendly front-end over nmcli / rfkill / bluetoothctl / ufw.\n"
        "\n"
        "  status                          Overview of every network subsystem.\n"
        "  wifi ...                        list, connect <ssid> [pass], disconnect, "
        "on/off, status.\n"
        "  wired ...                       on, off, status (ethernet).\n"
        "  bluetooth ...                   on/off (off by default), status, list, "
        "pair/connect/disconnect <mac>.\n"
        "  airplane [on|off|toggle|status] Kill or restore ALL radios at once.\n"
        "  firewall ...                    status, enable/disable, default <in> <out>, "
        "port list|open|close|delete.\n"
        "  ip ...                          show, static <iface> <addr/prefix> <gw> "
        "[dns...], dynamic <iface>.\n"
        "  --help                          Show this help.\n"
        "  (no command)                    Print the overview (same as status).\n"
    )


def cmd_network(args: list[str]) -> int:
    """Dispatch `azarch network ...`. No noun -> overview; each noun has its own verbs;
    --help/-h prints usage. Mirrors cmd_theme/cmd_wallpaper (plain string dispatch)."""
    if not args:
        return network_status()
    noun = args[0]
    rest = args[1:]
    if noun == "status":
        return network_status()
    if noun == "wifi":
        return cmd_wifi(rest)
    if noun == "wired":
        return cmd_wired(rest)
    if noun == "bluetooth":
        return cmd_bluetooth(rest)
    if noun == "airplane":
        return cmd_airplane(rest)
    if noun == "firewall":
        return cmd_firewall(rest)
    if noun == "ip":
        return cmd_ip(rest)
    if noun in ("--help", "-h", "help"):
        network_usage()
        return 0
    _err(f"azarch network: unknown command: {noun}")
    network_usage()
    return 2
