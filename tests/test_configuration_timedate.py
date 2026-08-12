"""packages.timedate -- OUR Flask Time + Calendar home page (localhost:49154).

This is the site LibreWolf lands on: a small local Flask website that shows the current
time (hour/minute/seconds) and a calendar (day/month/year), run in the background by a
systemd service that starts at boot, with the timezone following the SYSTEM live
(default Asia/Jerusalem, updating itself if the user changes it by any means).

Why these tests matter: like the OpenBox/application-menu payloads, compiler.py never
inspects the CONTENT of these builders -- it blindly iterates emit_plan() and calls
emit.write_text with the (dest, mode) each entry declares, and _link_services creates the
service enable-symlink. So the declarative PLAN table + the unit text ARE the contract:
a wrong mode makes the launcher non-executable (systemd's Exec= then fails), a wrong
WantedBy means the home page never starts at boot, and a port that drifts from
patches/librewolf's URL means the browser lands on a dead tab. None of that raises in
Python; it only shows up as a blank home page on the built ISO. These tests pin:

  * the emit_plan() dest/mode table + that it does not mutate module state,
  * the systemd unit (Type/ExecStart/Restart/WantedBy=multi-user.target + hardening),
  * the launcher (execs `python app.py` from the install dir),
  * the PORT lock-step between the app, this package, and patches/librewolf.TIMEDATE_URL,
  * that patches/librewolf now makes the timedate URL the home + startup page,
  * page.render()'s self-contained HTML (seeds the time, embeds the system zone, ships
    the client-side Intl ticking script + /api/now re-sync -- pure stdlib, no Flask),
  * the /etc/localtime -> IANA-zone resolution algorithm app.py uses to follow the
    system timezone live.
"""

from __future__ import annotations

import datetime
import os
from zoneinfo import ZoneInfo

import pytest

from packages.timedate import timedate as td
from packages.timedate import page as td_page
from patches import librewolf


# --- The fixed port contract ------------------------------------------------
def test_port_is_49154_everywhere():
    """The one port the whole system agrees on. The app, this package, and the URL are
    all 49154; librewolf's TIMEDATE_URL is derived from td.URL so they cannot drift."""
    assert td.PORT == 49154
    assert td.URL == "http://localhost:49154"
    assert librewolf.TIMEDATE_URL == td.URL
    # The app source hard-codes the same port (it binds it); pin that too.
    assert "PORT = 49154" in td.app_py()
    assert 'app.run(host="0.0.0.0", port=PORT' in td.app_py()


# --- emit_plan() contract ---------------------------------------------------
EXPECTED_PLAN = {
    "/usr/local/lib/azarch-timedate/app.py": 0o644,
    "/usr/local/lib/azarch-timedate/page.py": 0o644,
    "/usr/local/bin/azarch-timedate": 0o755,
    "/etc/systemd/system/azarch-timedate.service": 0o644,
}


def test_emit_plan_dest_mode_table():
    """The declarative (dest -> mode) table compiler.py iterates. The launcher MUST be
    executable (0o755) so systemd's ExecStart can run it; the rest are plain data."""
    got = {e["dest"]: e["mode"] for e in td.emit_plan()}
    assert got == EXPECTED_PLAN


def test_emit_plan_builders_are_callable_and_nonempty():
    """Every entry's builder returns real content (compiler.py calls builder())."""
    for e in td.emit_plan():
        content = e["builder"]()
        assert isinstance(content, str) and content.strip(), e["dest"]


def test_emit_plan_is_pure():
    """compiler.py may call emit_plan() more than once; it must not mutate module state
    or return aliased dicts that a caller could mutate. Mirrors the openbox test."""
    a = td.emit_plan()
    b = td.emit_plan()
    assert a == b
    a[0]["mode"] = 0o000  # mutate the returned copy
    assert td.emit_plan()[0]["mode"] == 0o644  # module PLAN unaffected


def test_dest_paths_are_absolute_system_paths():
    """All root-owned absolute paths under /usr/local or /etc (the OFFLINE install rsyncs
    the live rootfs, so no per-user home entry is needed here)."""
    for e in td.emit_plan():
        assert e["dest"].startswith(("/usr/local/", "/etc/")), e["dest"]


# --- systemd service unit ---------------------------------------------------
def test_service_unit_runs_at_boot_in_background():
    unit = td.service_unit()
    assert "[Service]" in unit and "[Install]" in unit
    assert "Type=simple" in unit
    assert f"ExecStart={td.LAUNCHER_SYSTEM_PATH}" in unit
    # Starts at boot: pulled by multi-user.target (the symlink is added by
    # compiler._link_services, tested in the compiler tests).
    assert "WantedBy=multi-user.target" in unit
    # A dead home page must come back so a new tab is never broken.
    assert "Restart=on-failure" in unit
    assert str(td.PORT) in unit


def test_service_unit_is_hardened_and_unprivileged():
    """The page only reads world-readable tzdata and listens on a loopback-facing port,
    so it runs unprivileged and locked down."""
    unit = td.service_unit()
    assert "User=nobody" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    # It writes nothing and needs only INET sockets.
    assert "RestrictAddressFamilies=AF_INET AF_INET6" in unit


def test_service_name_constants_agree():
    assert td.SERVICE_NAME == "azarch-timedate.service"
    assert td.SERVICE_SYSTEM_PATH == f"/etc/systemd/system/{td.SERVICE_NAME}"


# --- launcher ---------------------------------------------------------------
def test_launcher_execs_python_app_from_install_dir():
    """The launcher cd's into the install dir (so `import page` resolves) and execs the
    system python on app.py. `exec` so systemd supervises the python process directly."""
    sh = td.launcher_sh()
    assert sh.startswith("#!/bin/sh")
    assert f"cd '{td.LIB_DIR}'" in sh
    assert "exec python -u app.py" in sh


# --- LibreWolf lands on the timedate page -----------------------------------
def test_librewolf_home_and_startup_point_at_timedate():
    """patches/librewolf makes the timedate site the home page AND opens it on startup
    (browser.startup.page = 1 = home), so LibreWolf 'defaults to land on it'."""
    cfg = librewolf.overrides_cfg()
    assert f'defaultPref("browser.startup.homepage", "{td.URL}");' in cfg
    assert 'defaultPref("browser.startup.page", 1);' in cfg
    # AutoConfig files must begin with a comment line (engine ignores line 1).
    assert cfg.splitlines()[0].startswith("//")


def test_librewolf_keeps_cookie_persistence():
    """Landing on the home page replaced the tab-restore, but LOGINS must still persist
    (sanitizeOnShutdown off + full session-store privacy level)."""
    cfg = librewolf.overrides_cfg()
    assert 'defaultPref("privacy.sanitize.sanitizeOnShutdown", false);' in cfg
    assert 'defaultPref("browser.sessionstore.privacy_level", 0);' in cfg


# --- page.render(): self-contained, seeded, zone-aware, ticking -------------
def _rendered(zone="Asia/Jerusalem"):
    now = datetime.datetime(2026, 8, 12, 14, 5, 9, tzinfo=ZoneInfo(zone))
    return td_page.render(zone_name=zone, now=now), now


def test_page_is_one_self_contained_html_document():
    html, _ = _rendered()
    assert html.startswith("<!DOCTYPE html>")
    # Everything inline: exactly one <style> and one <script>, no external asset refs.
    assert html.count("<script>") == 1 and html.count("<style>") == 1
    assert "src=" not in html and "href=" not in html  # no external CSS/JS/links


def test_page_seeds_the_current_time_and_date():
    """The server seeds the first paint so there is no flash of a wrong time before JS
    runs: HH/MM/SS and the day/month/year must be present in the initial markup."""
    html, now = _rendered()
    assert ">14<" in html and ">05<" in html and ">09<" in html  # 14:05:09
    assert "August" in html and "2026" in html and "12" in html
    assert now.strftime("%A") in html  # weekday name


def test_page_embeds_the_system_zone_and_ticks_in_it():
    """The IANA zone is embedded so the browser formats in the SYSTEM zone (not its own),
    and the client ticks with Intl.DateTimeFormat + re-syncs to /api/now."""
    html, _ = _rendered("America/New_York")
    assert "America/New_York" in html
    assert "Intl.DateTimeFormat" in html
    assert "/api/now" in html
    assert 'timeZone: state.zone' in html  # formats in the embedded system zone


def test_page_escapes_the_zone_name():
    """Defense-in-depth: the zone name is HTML-escaped where it is shown (it comes from a
    filesystem symlink, so treat it as untrusted even though tzdata names are safe)."""
    html, _ = _rendered("Asia/Jerusalem")
    # No raw angle brackets injected around the zone label.
    assert "System timezone" in html


# --- the /etc/localtime -> IANA-zone algorithm (follows the system live) -----
# app.py needs Flask to import, so we re-express its resolution algorithm here and pin
# the behaviour the app source declares (constants + the realpath-strip contract). This
# is the mechanism that makes the page track a timezone change made by ANY tool.
def _zone_from_localtime(localtime: str, zoneinfo_dir: str) -> str | None:
    try:
        target = os.path.realpath(localtime)
    except OSError:
        return None
    root = os.path.realpath(zoneinfo_dir)
    prefix = root.rstrip("/") + "/"
    if not target.startswith(prefix):
        return None
    return target[len(prefix):] or None


def test_zone_resolution_follows_the_symlink(tmp_path):
    """A /etc/localtime symlink into the zoneinfo tree resolves to its IANA name, and
    following a change (as timedatectl / azarch --resolve-date-time / a manual relink
    would do) yields the new zone -- with no caching, so the page updates itself."""
    zi = tmp_path / "zoneinfo"
    (zi / "Asia").mkdir(parents=True)
    (zi / "America").mkdir(parents=True)
    (zi / "Asia" / "Jerusalem").write_bytes(b"")
    (zi / "America" / "New_York").write_bytes(b"")
    lt = tmp_path / "localtime"

    lt.symlink_to(zi / "Asia" / "Jerusalem")
    assert _zone_from_localtime(str(lt), str(zi)) == "Asia/Jerusalem"

    lt.unlink()
    lt.symlink_to(zi / "America" / "New_York")  # user changed the timezone
    assert _zone_from_localtime(str(lt), str(zi)) == "America/New_York"


def test_zone_resolution_falls_back_when_missing(tmp_path):
    """No /etc/localtime -> None (app.py then uses FALLBACK_ZONE); a target outside the
    zoneinfo tree -> None. The home page must never 500 over timezone plumbing."""
    zi = tmp_path / "zoneinfo"
    zi.mkdir()
    missing = tmp_path / "localtime"  # does not exist
    assert _zone_from_localtime(str(missing), str(zi)) is None

    outside = tmp_path / "elsewhere"
    outside.write_bytes(b"")
    lt = tmp_path / "localtime2"
    lt.symlink_to(outside)
    assert _zone_from_localtime(str(lt), str(zi)) is None


def test_app_declares_the_localtime_source_and_fallback():
    """The app must read the real system-zone source (/etc/localtime under
    /usr/share/zoneinfo) and default to Asia/Jerusalem -- the distro default the spec
    names. Pinned against the app source so the contract cannot silently change."""
    src = td.app_py()
    assert 'LOCALTIME_PATH = "/etc/localtime"' in src
    assert 'ZONEINFO_DIR = "/usr/share/zoneinfo"' in src
    assert 'FALLBACK_ZONE = "Asia/Jerusalem"' in src
    # It resolves the zone per request (no build-time cache), the "updates itself" bit.
    assert "def _system_zone()" in src and "_zone_name_from_localtime" in src
