"""libraries/packages/application_menu/libraries/panel_icon.py -- the standalone
installer's Plasma panel-icon surgeon.

THE BUG THIS PINS ("piece of paper icon that launches nothing"): org.kde.plasma.icon
does not read its configured .desktop directly -- on first paint it derives its OWN
backing copy under ~/.local/share/plasma_icons and reads THAT. Given only a bare
`url=<path>` it takes the generic branch and bakes Type=Link / Icon=unknown (a paper
glyph that opens a file location instead of Exec'ing). So `add` must instead:
  * pre-create the backing .desktop itself (Type=Application + Exec= + Icon=),
  * point the applet's [Configuration] localPath at it,
  * write url= as a file:// URI (belt), and
  * leave the applet immutability=0 so Plasma can refresh it.

panel_icon.py is a source-tree helper (not part of the importable `azarch` package),
so it is loaded here directly from its file path.
"""

from __future__ import annotations

import configparser
import importlib.util
from pathlib import Path

import pytest

_PANEL_ICON_SRC = (
    Path(__file__).resolve().parents[1]
    / "libraries" / "packages" / "application_menu" / "libraries" / "panel_icon.py"
)


def _load_panel_icon():
    spec = importlib.util.spec_from_file_location("azarch_panel_icon", _PANEL_ICON_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


panel_icon = _load_panel_icon()


# A minimal appletsrc with a bottom panel (id 2) carrying Kickoff (id 12) + a task
# manager (id 3), matching the nested [Group][Sub] header shape Plasma uses.
_MINIMAL_APPLETSRC = """\
[Containments][2][General]
AppletOrder=12;3

[Containments][2][Applets][12]
plugin=org.kde.plasma.kickoff

[Containments][2][Applets][3]
plugin=org.kde.plasma.icontasks
"""

_DESKTOP_PATH = "/usr/local/share/applications/azarch-application-menu.desktop"
_ICON_NAME = "application-menu"


def _parse(text: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(text)
    return cp


@pytest.fixture()
def appletsrc(tmp_path: Path) -> Path:
    p = tmp_path / "plasma-org.kde.plasma.desktop-appletsrc"
    p.write_text(_MINIMAL_APPLETSRC, encoding="utf-8")
    return p


def test_add_places_icon_after_kickoff(appletsrc: Path, tmp_path: Path):
    backing = tmp_path / "plasma_icons" / "azarch-application-menu.desktop"
    panel_icon.add(str(appletsrc), "2", _DESKTOP_PATH, _ICON_NAME, str(backing))
    cp = _parse(appletsrc.read_text())
    order = cp["Containments][2][General"]["AppletOrder"].split(";")
    # Kickoff (12) first, our new icon immediately after it, tasks (3) still present.
    assert order[0] == "12"
    assert order[1] not in ("12", "3")          # a fresh applet id
    assert "3" in order


def test_add_writes_localpath_and_file_uri_url_not_bare_path(appletsrc: Path, tmp_path: Path):
    # THE FIX: the applet config must carry a localPath to a backing file WE create,
    # and url= must be a file:// URI (not a bare path that triggers the Type=Link
    # wrapper). iconName is preserved for the applet's own icon hint.
    backing = tmp_path / "plasma_icons" / "azarch-application-menu.desktop"
    panel_icon.add(str(appletsrc), "2", _DESKTOP_PATH, _ICON_NAME, str(backing))
    body = appletsrc.read_text()
    assert f"localPath={backing}" in body
    assert f"url=file://{_DESKTOP_PATH}" in body
    # No BARE url= path (the bug). Every url= line must be the file:// form.
    url_lines = [ln for ln in body.splitlines() if ln.startswith("url=")]
    assert url_lines, "no url= written"
    for ln in url_lines:
        assert ln == f"url=file://{_DESKTOP_PATH}"
    assert f"iconName={_ICON_NAME}" in body


def test_add_applet_is_not_immutable(appletsrc: Path, tmp_path: Path):
    # A locked (immutability=1) applet froze the broken backing file so Plasma could
    # never refresh it. The applet must be immutability=0.
    backing = tmp_path / "plasma_icons" / "azarch-application-menu.desktop"
    panel_icon.add(str(appletsrc), "2", _DESKTOP_PATH, _ICON_NAME, str(backing))
    cp = _parse(appletsrc.read_text())
    # Find our applet id (the one whose plugin is org.kde.plasma.icon).
    icon_id = None
    for sect in cp.sections():
        if cp[sect].get("plugin") == "org.kde.plasma.icon":
            icon_id = sect
    assert icon_id is not None, "icon applet not written"
    assert cp[icon_id].get("immutability", "0") == "0"


def test_add_creates_backing_desktop_as_application_launcher(appletsrc: Path, tmp_path: Path):
    # The backing file the applet reads MUST be a real launcher, not the generic
    # Type=Link/Icon=unknown wrapper: Type=Application, Exec runs the installed
    # launcher path, Icon is the passed icon name (NOT "unknown").
    backing = tmp_path / "plasma_icons" / "azarch-application-menu.desktop"
    launcher = "/usr/local/bin/azarch-application-menu"
    panel_icon.add(str(appletsrc), "2", _DESKTOP_PATH, _ICON_NAME, str(backing),
                   exec_path=launcher)
    assert backing.exists(), "backing .desktop not created"
    cp = _parse(backing.read_text())
    entry = cp["Desktop Entry"]
    assert entry["Type"] == "Application"
    assert entry["Exec"] == launcher
    assert entry["Icon"] == _ICON_NAME
    assert entry["Icon"] != "unknown"
    assert "Type=Link" not in backing.read_text()
    # The backing file MUST be executable: KDE treats a non-executable
    # Type=Application desktop file as untrusted, so the applet's KIO click path pops
    # a modal "not trusted, execute?" dialog and launches nothing. Exec bit = trusted.
    import os
    import stat
    mode = stat.S_IMODE(os.stat(backing).st_mode)
    assert mode & 0o111, f"backing .desktop not executable (mode {oct(mode)})"


def test_add_is_idempotent(appletsrc: Path, tmp_path: Path):
    # Running add twice must not add a second icon applet (idempotent installer).
    backing = tmp_path / "plasma_icons" / "azarch-application-menu.desktop"
    panel_icon.add(str(appletsrc), "2", _DESKTOP_PATH, _ICON_NAME, str(backing))
    once = appletsrc.read_text()
    panel_icon.add(str(appletsrc), "2", _DESKTOP_PATH, _ICON_NAME, str(backing))
    twice = appletsrc.read_text()
    assert once == twice
    # Exactly one org.kde.plasma.icon applet (exact line, so it does not also match
    # the icontasks task manager, whose plugin STARTS WITH org.kde.plasma.icon).
    icon_lines = [ln for ln in twice.splitlines() if ln == "plugin=org.kde.plasma.icon"]
    assert len(icon_lines) == 1


def test_remove_reverses_add(appletsrc: Path, tmp_path: Path):
    # remove must drop our applet from AppletOrder and delete its stanzas, returning
    # the file to (semantically) its pre-add state.
    backing = tmp_path / "plasma_icons" / "azarch-application-menu.desktop"
    panel_icon.add(str(appletsrc), "2", _DESKTOP_PATH, _ICON_NAME, str(backing))
    panel_icon.remove(str(appletsrc), "2")
    body = appletsrc.read_text()
    # Exact-line check: our org.kde.plasma.icon applet is gone (icontasks, whose
    # plugin STARTS WITH org.kde.plasma.icon, must survive -- see order check below).
    assert "plugin=org.kde.plasma.icon\n" not in body
    assert "plugin=org.kde.plasma.icontasks" in body   # untouched
    cp = _parse(body)
    order = cp["Containments][2][General"]["AppletOrder"].split(";")
    assert order == ["12", "3"]
