"""The Az'arch application menu -- baked into the live/installed system.

This is OUR application menu: a Python (Tkinter) program shown to the RIGHT of
KDE's Kickoff -- a borderless, Breeze-styled launcher (search, launch-frequency
ordering, pin, power actions) that is the seed of a custom menu meant to replace
Kickoff entirely.

It is a multi-module package: menu.py orchestrates and imports the siblings
(widgets/theme/apps/icons/usage/actions) as flat modules, so the whole set MUST be
emitted together (see MENU_MODULES) or menu.py fails to import at launch.

Layers:
  * SOURCE tree -- libraries/packages/application_menu/ (paths.APPLICATION_MENU_DIR):
      libraries/menu.py                    the Tkinter menu orchestrator
      libraries/{widgets,theme,apps,icons,usage,actions}.py  its sibling modules
      libraries/test_menu.py               the menu's own test suite (rides along)
      libraries/azarch-application-menu.sh  the launcher the panel icon runs
      libraries/azarch-application-menu.desktop  what the icon points at
      libraries/panel_icon.py              add/remove the panel applet (for the
                                           standalone install.sh; NOT needed at
                                           build time -- the applet is baked into
                                           configuration/desktop.plasma_appletsrc)
      install.sh / uninstall.sh            standalone (post-install) (un)installer
  * BUILD wiring -- this module copies ALL the menu modules plus the launcher and
    its .desktop to fixed system paths in the airootfs, and configuration/desktop.py
    bakes an org.kde.plasma.icon applet (pointing at MENU_DESKTOP_SYSTEM_PATH) into
    the panel between Kickoff and the task manager.

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
# The resident daemon the launcher signals (menu built once, kept hidden, so the
# panel icon opens INSTANTLY). daemon.py imports menu.py; the launcher execs this.
MENU_DAEMON_PY_SYSTEM_PATH = f"{MENU_LIB_DIR}/daemon.py"
MENU_LAUNCHER_SYSTEM_PATH = "/usr/local/bin/azarch-application-menu"
MENU_DESKTOP_SYSTEM_PATH = (
    "/usr/local/share/applications/azarch-application-menu.desktop"
)
# Per-user autostart entry that starts the resident daemon at login, so even the
# FIRST panel-icon click is instant. Emitted by configuration/desktop.py (which
# owns the per-user files + /etc/skel mirroring); content lives here.
MENU_DAEMON_AUTOSTART_SYSTEM_PATH = (
    "/home/main/.config/autostart/azarch-application-menu-daemon.desktop"
)

# The panel icon glyph: the SAME "application-menu" hamburger Plasma's Kickoff
# uses, so our icon is visually identical to it. Single source of truth;
# configuration/desktop.py imports it.
MENU_ICON_NAME = "application-menu"


# --- Source files (in the repo) ---------------------------------------------
# The menu is a multi-module package: menu.py (the orchestrator) imports the other
# modules as flat siblings (widgets/theme/apps/icons/usage/actions/editing), and
# daemon.py imports menu.py to keep it resident for instant open; test_menu rides
# along with them. ALL of these must land in MENU_LIB_DIR together or menu.py (or
# the daemon) crashes on launch with an ImportError. This list is the single source
# of truth for what the build emits; keep it in lock-step with the standalone
# install.sh.
MENU_MODULES = [
    "menu.py",
    "widgets.py",
    "theme.py",
    "apps.py",
    "winwatch.py",
    "icons.py",
    "usage.py",
    "actions.py",
    "editing.py",
    "daemon.py",
    "test_menu.py",
]

# Relative paths under paths.APPLICATION_MENU_DIR for the non-module runtime files.
_SRC_LAUNCHER = Path("libraries") / "azarch-application-menu.sh"
_SRC_DESKTOP = Path("libraries") / "azarch-application-menu.desktop"
_SRC_DAEMON_DESKTOP = Path("libraries") / "azarch-application-menu-daemon.desktop"


def _read_source(rel: Path) -> str:
    """Read a source file from the application-menu tree as text."""
    return (paths.APPLICATION_MENU_DIR / rel).read_text(encoding="utf-8")


def _module_src(name: str) -> str:
    """Read one menu module (e.g. "widgets.py") verbatim from the source tree."""
    return _read_source(Path("libraries") / name)


def menu_py() -> str:
    """The Tkinter menu orchestrator (verbatim from the source tree)."""
    return _module_src("menu.py")


def daemon_py() -> str:
    """The resident daemon that keeps the menu built + hidden for instant open
    (verbatim from the source tree). It imports menu.py and drives its window."""
    return _module_src("daemon.py")


def menu_package_source() -> str:
    """Every menu module concatenated, for whole-package assertions.

    menu.py was split into sibling modules (theme/widgets/...), so a symbol such as
    the HighlightBar or the #3daee9 accent may live in widgets.py or theme.py rather
    than menu.py. Tests that pin a property of the MENU (not of one file) read this.
    """
    return "\n".join(_module_src(name) for name in MENU_MODULES)


def launcher_sh() -> str:
    """The launcher script the panel icon runs (verbatim from the source tree)."""
    return _read_source(_SRC_LAUNCHER)


def menu_desktop() -> str:
    """The .desktop the panel icon points at (verbatim from the source tree)."""
    return _read_source(_SRC_DESKTOP)


def daemon_autostart_desktop() -> str:
    """The per-user autostart .desktop that starts the resident daemon at login
    (verbatim from the source tree). Emitted by configuration/desktop.py into
    ~/.config/autostart so the daemon is up before the first panel-icon click."""
    return _read_source(_SRC_DAEMON_DESKTOP)


# --- Emit plan --------------------------------------------------------------
# Declarative map (builder -> dest -> mode) so steps.py can iterate, mirroring
# configuration/desktop.PLAN. All are absolute SYSTEM paths (root-owned): the
# OFFLINE Calamares install rsyncs the live rootfs, so these carry onto the
# installed system with no separate installer step.
_EXEC = 0o755
_CONF = 0o644


def _module_builder(name: str):
    """A no-arg builder that reads menu module `name` (bound now, not late)."""
    return lambda: _module_src(name)


# One emit entry per menu module (all mode 0644 in MENU_LIB_DIR), then the launcher
# (0755, run by the panel icon) and the .desktop it points at. Building the module
# entries from MENU_MODULES means the build can never again ship menu.py without its
# siblings. menu.py stays first so MENU_PY_SYSTEM_PATH keeps a stable builder.
PLAN = [
    {
        "builder": _module_builder(name),
        "dest": f"{MENU_LIB_DIR}/{name}",
        "mode": _CONF,
    }
    for name in MENU_MODULES
] + [
    {"builder": launcher_sh, "dest": MENU_LAUNCHER_SYSTEM_PATH, "mode": _EXEC},
    {"builder": menu_desktop, "dest": MENU_DESKTOP_SYSTEM_PATH, "mode": _CONF},
]


def emit_plan() -> list[dict]:
    """Return the PLAN list (builder/dest/mode) for steps.py to emit into the
    airootfs. Kept as a function to mirror configuration/desktop.emit_plan()."""
    return PLAN
