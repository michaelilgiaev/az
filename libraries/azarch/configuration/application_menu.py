"""The Az'arch application menu -- baked into the live/installed system.

This is OUR application menu: a small Python (Tkinter) program shown to the RIGHT
of KDE's Kickoff. For now it is a "Hello World" window; it exists as the seed of a
custom menu that will eventually replace Kickoff entirely.

Layers:
  * SOURCE tree -- libraries/packages/application_menu/ (paths.APPLICATION_MENU_DIR):
      libraries/menu.py                    the Tkinter menu (single window)
      libraries/azarch-application-menu.sh  the launcher the panel icon runs
      libraries/azarch-application-menu.desktop  what the icon points at
      libraries/panel_icon.py              add/remove the panel applet (for the
                                           standalone install.sh; NOT needed at
                                           build time -- the applet is baked into
                                           configuration/desktop.plasma_appletsrc)
      install.sh / uninstall.sh            standalone (post-install) (un)installer
  * BUILD wiring -- this module copies the three RUNTIME files to fixed system
    paths in the airootfs, and configuration/desktop.py bakes an
    org.kde.plasma.icon applet (pointing at MENU_DESKTOP_SYSTEM_PATH) into the
    panel between Kickoff and the task manager.

The panel icon therefore appears by DEFAULT on a fresh profile (no post-install
step needed); the standalone install.sh/uninstall.sh remain for adding/removing
the menu on an already-running system.

No pip dependencies: Tkinter is in the Python standard library (backed by the
`tk` package, which is in the manifest). See requirements.txt in the source tree.
"""

from __future__ import annotations

from pathlib import Path

from .. import paths


# --- Installed system paths (root-owned) ------------------------------------
# Where the menu program lands in the live/installed rootfs. These MUST match the
# standalone install.sh so both the baked-in build and a manual install agree.
MENU_LIB_DIR = "/usr/local/lib/azarch-application-menu"
MENU_PY_SYSTEM_PATH = f"{MENU_LIB_DIR}/menu.py"
MENU_LAUNCHER_SYSTEM_PATH = "/usr/local/bin/azarch-application-menu"
MENU_DESKTOP_SYSTEM_PATH = (
    "/usr/local/share/applications/azarch-application-menu.desktop"
)

# The panel icon glyph: the SAME "application-menu" hamburger Plasma's Kickoff
# uses, so our icon is visually identical to it. Single source of truth;
# configuration/desktop.py imports it.
MENU_ICON_NAME = "application-menu"


# --- Source files (in the repo) ---------------------------------------------
# Relative paths under paths.APPLICATION_MENU_DIR for the three runtime files.
_SRC_MENU_PY = Path("libraries") / "menu.py"
_SRC_LAUNCHER = Path("libraries") / "azarch-application-menu.sh"
_SRC_DESKTOP = Path("libraries") / "azarch-application-menu.desktop"


def _read_source(rel: Path) -> str:
    """Read a source file from the application-menu tree as text."""
    return (paths.APPLICATION_MENU_DIR / rel).read_text(encoding="utf-8")


def menu_py() -> str:
    """The Tkinter menu program (verbatim from the source tree)."""
    return _read_source(_SRC_MENU_PY)


def launcher_sh() -> str:
    """The launcher script the panel icon runs (verbatim from the source tree)."""
    return _read_source(_SRC_LAUNCHER)


def menu_desktop() -> str:
    """The .desktop the panel icon points at (verbatim from the source tree)."""
    return _read_source(_SRC_DESKTOP)


# --- Emit plan --------------------------------------------------------------
# Declarative map (builder -> dest -> mode) so steps.py can iterate, mirroring
# configuration/desktop.PLAN. All are absolute SYSTEM paths (root-owned): the
# OFFLINE Calamares install rsyncs the live rootfs, so these carry onto the
# installed system with no separate installer step.
_EXEC = 0o755
_CONF = 0o644

PLAN = [
    {"builder": menu_py, "dest": MENU_PY_SYSTEM_PATH, "mode": _CONF},
    {"builder": launcher_sh, "dest": MENU_LAUNCHER_SYSTEM_PATH, "mode": _EXEC},
    {"builder": menu_desktop, "dest": MENU_DESKTOP_SYSTEM_PATH, "mode": _CONF},
]


def emit_plan() -> list[dict]:
    """Return the PLAN list (builder/dest/mode) for steps.py to emit into the
    airootfs. Kept as a function to mirror configuration/desktop.emit_plan()."""
    return PLAN
