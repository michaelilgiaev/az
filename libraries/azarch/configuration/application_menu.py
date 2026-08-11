"""The Az'arch application menu -- baked into the live/installed system.

This is OUR application menu, and it is the WHOLE shell: KDE Plasma was removed and
the desktop is OpenBox with no panel, so this menu -- a borderless, Breeze-styled
Tkinter launcher CENTERED on the screen (search, launch-frequency ordering, power
actions) -- is the only launcher surface. It is opened by the Super key (via xcape +
the OpenBox rc.xml keybind); see configuration/desktop.py.

It is a multi-module package: menu.py orchestrates and imports the siblings
(widgets/theme/apps/icons/usage/actions/...) as flat modules, so the whole set MUST be
emitted together (see MENU_MODULES) or menu.py fails to import at launch.

Layers:
  * SOURCE tree -- libraries/packages/application_menu/ (paths.APPLICATION_MENU_DIR):
      libraries/menu.py                    the Tkinter menu orchestrator
      libraries/{widgets,theme,apps,icons,usage,actions}.py  its sibling modules
      libraries/daemon.py                  the resident daemon (built once, instant open)
      libraries/test_menu.py               the menu's own test suite (rides along)
      libraries/azarch-application-menu.sh  the launcher (signals the daemon)
      libraries/azarch-application-menu.desktop  a standard app-launcher entry
      libraries/panel_icon.py              LEGACY Plasma-applet (un)installer, kept for
                                           the standalone install.sh only -- NOT used by
                                           the OpenBox build (there is no panel)
      install.sh / uninstall.sh            standalone (post-install) (un)installer
  * BUILD wiring -- this module copies ALL the menu modules plus the launcher and its
    .desktop to fixed system paths in the airootfs. The OpenBox session (configuration/
    desktop.py) starts the daemon from its autostart and binds the Super key to the
    launcher; there is no panel applet to bake anymore.

No pip dependencies: Tkinter is in the Python standard library (backed by the `tk`
package, which is in the manifest). See requirements.txt in the source tree.
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

# --- Super/Meta key -> menu (handled by OpenBox, not KDE) --------------------
# Pressing the Super key alone OPENS THIS MENU. Under OpenBox that is wired WITHOUT any
# KDE machinery: xcape turns a lone Super_L tap into the chord Super_L+Menu and the
# OpenBox rc.xml binds W-Menu to MENU_LAUNCHER_SYSTEM_PATH (see configuration/desktop.py
# openbox_rc_xml + openbox_autostart). There is therefore NO X-KDE-Shortcuts .desktop
# and NO kglobalaccel anymore -- the old KDE global-shortcut file was removed.
#
# The daemon that keeps the menu resident (instant open) is likewise started from the
# OpenBox autostart (configuration/desktop.openbox_autostart), not from a KDE autostart
# .desktop.

# Per-user seed for the launch-frequency store (usage.py's UsageStore file). The menu
# orders apps most-launched first; on a FRESH profile there is no history, so without
# this everything would sort alphabetically. Seeding a few counts fixes the STARTING top
# of the list to the apps a new user wants first -- LibreWolf, kitty, Dolphin, GIMP
# (descending) -- while leaving it fully dynamic: as the user opens apps the
# WindowWatcher bumps these counts and the order re-sorts, so the seed only decides the
# initial arrangement. Keyed by .desktop id (usage.py's key); counts are spaced so the
# intended order is unambiguous. Emitted by configuration/desktop.py as a home-owned
# file (mirrored into /etc/skel).
MENU_USAGE_SEED_SYSTEM_PATH = (
    "/home/main/.local/share/azarch-application-menu/usage.json"
)

# desktop_id -> starting launch count. Descending so order_key (-count, name) puts them
# in exactly this order at the top of a fresh menu; the tail (everything else, count 0)
# stays alphabetical. KDE's "System Settings" (systemsettings.desktop) is gone with
# Plasma, so the seed now leads with the shipped apps a new user actually reaches for.
MENU_USAGE_SEED: dict[str, int] = {
    "librewolf.desktop": 4,          # LibreWolf (browser)
    "kitty.desktop": 3,              # kitty (terminal)
    "org.kde.dolphin.desktop": 2,   # Dolphin (file manager)
    "gimp.desktop": 1,               # GIMP
}

# The menu launcher's icon glyph: the standard "application-menu" hamburger, so the
# .desktop entry and any launcher show a recognizable menu icon. Single source of truth.
MENU_ICON_NAME = "application-menu"


# --- Source files (in the repo) ---------------------------------------------
# The menu is a multi-module package: menu.py (the orchestrator) imports the other
# modules as flat siblings (applist/widgets/theme/apps/icons/usage/actions/editing/
# xfocus), and daemon.py imports menu.py to keep it resident for instant open;
# test_menu rides along with them. ALL of these must land in MENU_LIB_DIR together
# or menu.py (or the daemon) crashes on launch with an ImportError. This list is the
# single source of truth for what the build emits; keep it in lock-step with the
# standalone install.sh.
MENU_MODULES = [
    "menu.py",
    "applist.py",
    "widgets.py",
    "theme.py",
    "apps.py",
    "winwatch.py",
    "icons.py",
    "usage.py",
    "actions.py",
    "editing.py",
    "xfocus.py",
    "daemon.py",
    "test_menu.py",
]

# Relative paths under paths.APPLICATION_MENU_DIR for the non-module runtime files.
_SRC_LAUNCHER = Path("libraries") / "azarch-application-menu.sh"
_SRC_DESKTOP = Path("libraries") / "azarch-application-menu.desktop"


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

    menu.py was split into sibling modules (theme/widgets/...), so a symbol such as the
    #3daee9 accent may live in widgets.py or theme.py rather than menu.py. Tests that
    pin a property of the MENU (not of one file) read this.
    """
    return "\n".join(_module_src(name) for name in MENU_MODULES)


def launcher_sh() -> str:
    """The launcher script the Super key / root menu runs (verbatim from the source
    tree). It signals the resident daemon (SIGUSR1 toggle / SIGUSR2 show)."""
    return _read_source(_SRC_LAUNCHER)


def menu_desktop() -> str:
    """A standard application-launcher .desktop for the menu (verbatim from the source
    tree), landing in /usr/local/share/applications so the menu can be launched by name
    and appears in app scans. (The Super key is bound by OpenBox's rc.xml, not by this
    file -- see configuration/desktop.py.)"""
    return _read_source(_SRC_DESKTOP)


def usage_seed_json() -> str:
    """The seed launch-frequency store (usage.json) that fixes the STARTING top of the
    menu to LibreWolf, kitty, Dolphin, GIMP on a fresh profile.

    Rendered in the SAME compact form usage.py's UsageStore._save writes (json.dump with
    separators=(",", ":")) so the store reads it straight back (the emitter adds a
    trailing newline, which json.load ignores). It stays fully dynamic afterwards: the
    daemon's WindowWatcher bumps these counts on every real app-open and re-sorts."""
    import json

    return json.dumps(MENU_USAGE_SEED, separators=(",", ":"))


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
# (0755, run by the Super key) and a standard app-launcher .desktop.
# Building the module entries from MENU_MODULES means the build can never again ship
# menu.py without its siblings. menu.py stays first so MENU_PY_SYSTEM_PATH keeps a
# stable builder.
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
