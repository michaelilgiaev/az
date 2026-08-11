"""The Az'arch application menu -- baked into the live/installed system.

This is OUR application menu, and it is the WHOLE shell: KDE Plasma was removed and
the desktop is OpenBox with no panel, so this menu -- a borderless, Breeze-styled
Tkinter launcher CENTERED on the screen (search, launch-frequency ordering, power
actions) -- is the only launcher surface. It is opened by the Super key (via xcape +
the OpenBox rc.xml keybind); see patches/openbox/openbox.py.

It is a multi-module package: menu.py orchestrates and imports the siblings
(widgets/theme/apps/icons/usage/actions/...) as flat modules, so the whole set MUST be
emitted together (see MENU_MODULES) or menu.py fails to import at launch.

The package is ALL Python -- no shell scripts, no .desktop payload files. The old
install.sh/uninstall.sh, the POSIX-sh launcher, the checked-in .desktop entries, and
the legacy Plasma panel_icon.py were removed: the launcher is now launcher.py, and the
.desktop entry is generated here as a Python string (menu_desktop()).

Layers:
  * SOURCE tree -- libraries/packages/application_menu/ (paths.APPLICATION_MENU_DIR).
    All the menu modules live DIRECTLY in this dir, next to this build-wiring module:
      menu.py                    the Tkinter menu orchestrator
      {widgets,theme,apps,icons,usage,actions}.py  its sibling modules
      daemon.py                  the resident daemon (built once, instant open)
      launcher.py                the launcher (signals the daemon), pure Python
      test_menu.py / conftest.py the menu's own test suite (rides along)
  * BUILD wiring -- THIS module (application_menu.py, alongside the source) copies ALL
    the menu modules (launcher.py included) to fixed system paths in the airootfs,
    installs launcher.py to /usr/local/bin, and writes a generated .desktop entry. The
    OpenBox session (patches/openbox/openbox.py) starts the daemon from its autostart and
    binds the Super key to the launcher; there is no panel applet to bake.

No pip dependencies: Tkinter is in the Python standard library (backed by the `tk`
package, which is in the manifest), so this package needs no requirements.txt.
"""

from __future__ import annotations

from pathlib import Path

import paths


# --- Installed system paths (root-owned) ------------------------------------
# Where the menu program lands in the live/installed rootfs.
MENU_LIB_DIR = "/usr/local/lib/azarch-application-menu"
MENU_PY_SYSTEM_PATH = f"{MENU_LIB_DIR}/menu.py"
# The resident daemon the launcher signals (menu built once, kept hidden, so the
# menu opens INSTANTLY). daemon.py imports menu.py; the launcher starts this.
MENU_DAEMON_PY_SYSTEM_PATH = f"{MENU_LIB_DIR}/daemon.py"
# The launcher (launcher.py) is installed here as the bin entry point the Super key /
# .desktop run; it finds daemon.py at its default MENU_DIR (= MENU_LIB_DIR).
MENU_LAUNCHER_SYSTEM_PATH = "/usr/local/bin/azarch-application-menu"
MENU_DESKTOP_SYSTEM_PATH = (
    "/usr/local/share/applications/azarch-application-menu.desktop"
)

# --- Super/Meta key -> menu (handled by OpenBox, not KDE) --------------------
# Pressing the Super key alone OPENS THIS MENU. Under OpenBox that is wired WITHOUT any
# KDE machinery: xcape turns a lone Super_L tap into the chord Super_L+Menu and the
# OpenBox rc.xml binds W-Menu to MENU_LAUNCHER_SYSTEM_PATH (see patches/openbox/openbox.py
# openbox_rc_xml + openbox_autostart). There is therefore NO X-KDE-Shortcuts .desktop
# and NO kglobalaccel anymore -- the old KDE global-shortcut file was removed.
#
# The daemon that keeps the menu resident (instant open) is likewise started from the
# OpenBox autostart (patches/openbox.openbox_autostart), not from a KDE autostart
# .desktop.

# Per-user seed for the launch-frequency store (usage.py's UsageStore file). The menu
# orders apps most-launched first; on a FRESH profile there is no history, so without
# this everything would sort alphabetically. Seeding a few counts fixes the STARTING top
# of the list to EXACTLY the first three apps a new user wants -- LibreWolf, kitty,
# Dolphin (descending) -- while leaving it fully dynamic: as the user opens apps the
# WindowWatcher bumps these counts and the order re-sorts, so the seed only decides the
# initial arrangement. Keyed by .desktop id (usage.py's key); counts are spaced so the
# intended order is unambiguous. Emitted by patches/openbox/openbox.py as a home-owned
# file (mirrored into /etc/skel).
MENU_USAGE_SEED_SYSTEM_PATH = (
    "/home/main/.local/share/azarch-application-menu/usage.json"
)

# desktop_id -> starting launch count. Descending so order_key (-count, name) puts them
# in exactly this order at the top of a fresh menu; the tail (everything else, count 0)
# stays alphabetical. EXACTLY three are seeded per the user's request ("make it those
# three when it's first installed"): LibreWolf, kitty, Dolphin. Everything else (GIMP
# included) starts in the count-0 alphabetical tail and floats up only as it is used.
MENU_USAGE_SEED: dict[str, int] = {
    "librewolf.desktop": 3,          # LibreWolf (browser)
    "kitty.desktop": 2,              # kitty (terminal)
    "org.kde.dolphin.desktop": 1,   # Dolphin (file manager)
}

# The menu launcher's icon glyph: the standard "application-menu" hamburger, so the
# .desktop entry and any launcher show a recognizable menu icon. Single source of truth.
MENU_ICON_NAME = "application-menu"


# --- Source files (in the repo) ---------------------------------------------
# The menu is a multi-module package: menu.py (the orchestrator) imports the other
# modules as flat siblings (applist/widgets/theme/apps/icons/usage/actions/editing/
# xfocus), and daemon.py imports menu.py to keep it resident for instant open;
# launcher.py (the bin entry point) and test_menu ride along. ALL of these must land
# in MENU_LIB_DIR together or menu.py (or the daemon) crashes on launch with an
# ImportError. This list is the single source of truth for what the build emits.
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
    "launcher.py",
    "test_menu.py",
]

# The launcher module in the source tree, installed (also) as the bin entry point.
# The menu source lives DIRECTLY in APPLICATION_MENU_DIR (no nested libraries/ dir).
_SRC_LAUNCHER = Path("launcher.py")


def _read_source(rel: Path) -> str:
    """Read a source file from the application-menu tree as text."""
    return (paths.APPLICATION_MENU_DIR / rel).read_text(encoding="utf-8")


def _module_src(name: str) -> str:
    """Read one menu module (e.g. "widgets.py") verbatim from the source tree."""
    return _read_source(Path(name))


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


def launcher_py() -> str:
    """The launcher the Super key / .desktop runs (verbatim from the source tree). Pure
    Python (launcher.py); it signals the resident daemon (SIGUSR1 toggle / SIGUSR2 show)
    and finds daemon.py at its default MENU_DIR. Installed to MENU_LAUNCHER_SYSTEM_PATH
    with the exec bit (see PLAN)."""
    return _read_source(_SRC_LAUNCHER)


def menu_desktop() -> str:
    """A standard application-launcher .desktop for the menu, landing in
    /usr/local/share/applications so the menu can be launched by name and appears in app
    scans. GENERATED here (the package ships no .desktop files) -- Exec points at the
    launcher and Icon at MENU_ICON_NAME. (The Super key is bound by OpenBox's rc.xml, not
    by this file -- see patches/openbox/openbox.py.)"""
    return f"""\
[Desktop Entry]
Type=Application
Name=Az'arch Menu
GenericName=Application Menu
Comment=The Az'arch application menu
Exec={MENU_LAUNCHER_SYSTEM_PATH}
Icon={MENU_ICON_NAME}
Terminal=false
Categories=System;Utility;
Keywords=menu;launcher;azarch;
"""


def usage_seed_json() -> str:
    """The seed launch-frequency store (usage.json) that fixes the STARTING top three of
    the menu to LibreWolf, kitty, Dolphin on a fresh profile.

    Rendered in the SAME compact form usage.py's UsageStore._save writes (json.dump with
    separators=(",", ":")) so the store reads it straight back (the emitter adds a
    trailing newline, which json.load ignores). It stays fully dynamic afterwards: the
    daemon's WindowWatcher bumps these counts on every real app-open and re-sorts."""
    import json

    return json.dumps(MENU_USAGE_SEED, separators=(",", ":"))


# --- Emit plan --------------------------------------------------------------
# Declarative map (builder -> dest -> mode) so compiler.py can iterate, mirroring
# patches/openbox.PLAN. All are absolute SYSTEM paths (root-owned): the
# OFFLINE Calamares install rsyncs the live rootfs, so these carry onto the
# installed system with no separate installer step.
_EXEC = 0o755
_CONF = 0o644


def _module_builder(name: str):
    """A no-arg builder that reads menu module `name` (bound now, not late)."""
    return lambda: _module_src(name)


# One emit entry per menu module (all mode 0644 in MENU_LIB_DIR), then the launcher
# INSTALLED AS THE BIN (0755, run by the Super key) and a generated app-launcher
# .desktop. launcher.py is in MENU_MODULES too, so it also lands in MENU_LIB_DIR as a
# sibling (harmless; the bin copy is the one on PATH). Building the module entries from
# MENU_MODULES means the build can never again ship menu.py without its siblings.
# menu.py stays first so MENU_PY_SYSTEM_PATH keeps a stable builder.
PLAN = [
    {
        "builder": _module_builder(name),
        "dest": f"{MENU_LIB_DIR}/{name}",
        "mode": _CONF,
    }
    for name in MENU_MODULES
] + [
    {"builder": launcher_py, "dest": MENU_LAUNCHER_SYSTEM_PATH, "mode": _EXEC},
    {"builder": menu_desktop, "dest": MENU_DESKTOP_SYSTEM_PATH, "mode": _CONF},
]


def emit_plan() -> list[dict]:
    """Return the PLAN list (builder/dest/mode) for compiler.py to emit into the
    airootfs. Kept as a function to mirror patches/openbox.emit_plan()."""
    return PLAN
