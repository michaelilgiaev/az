#!/usr/bin/env python3
"""Az'arch application menu -- application discovery + category typing.

Scans the freedesktop ``.desktop`` files that make up the system's application
menu and turns each visible one into a small :class:`AppEntry` the menu can
render: its display Name, the command to Exec, the Icon name, and -- the part
the design cares about -- a short human "type" label derived from the entry's
``Categories=`` field (Kitty -> "Terminal", LibreWolf -> "Web Browser").

Only the standard library is used (backed by nothing but Python itself); the Tk
UI lives in ``menu.py`` and the icon rasterising in ``icons.py``.

Category typing
---------------
freedesktop's Desktop Menu Specification splits ``Categories`` into a handful of
"Main" categories (AudioVideo, Development, Game, Graphics, Network, Office,
Science, Settings, System, Utility) plus many finer "Additional" categories
(WebBrowser, TerminalEmulator, FileManager, TextEditor, ...). The Additional
category is the more specific and human-meaningful one, so we prefer it for the
subtitle and fall back to the Main category, then to a generic label.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass


# --- Where application .desktop files live --------------------------------
# Standard XDG application dirs, most-specific last. /usr/local is where Az'arch
# drops its own launchers; the per-user dir lets a user's own entries show too.
def _app_dirs() -> list[str]:
    dirs = [
        os.path.join(
            os.environ.get(
                "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
            ),
            "applications",
        ),
    ]
    xdg_data = os.environ.get(
        "XDG_DATA_DIRS", "/usr/local/share:/usr/share"
    )
    for base in xdg_data.split(":"):
        base = base.strip()
        if base:
            dirs.append(os.path.join(base, "applications"))
    # De-dupe while preserving order (last-writer-wins is handled by the caller
    # keying on the .desktop basename).
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


# --- Category -> human "type" label ---------------------------------------
# The subtitle under each app name. Keys are freedesktop category tokens; we map
# the most specific token present to a friendly noun. Ordered most-specific
# first when scanning so e.g. WebBrowser wins over the generic Network.
#
# "Additional" (specific) categories -- the good subtitles.
ADDITIONAL_CATEGORY_LABELS: dict[str, str] = {
    "WebBrowser": "Web Browser",
    "TerminalEmulator": "Terminal",
    "FileManager": "File Manager",
    "FileTransfer": "File Transfer",
    "TextEditor": "Text Editor",
    "IDE": "Development Environment",
    "Debugger": "Debugger",
    "GUIDesigner": "GUI Designer",
    "WebDevelopment": "Web Development",
    "Documentation": "Documentation",
    "Email": "Email Client",
    "InstantMessaging": "Instant Messaging",
    "IRCClient": "IRC Client",
    "Chat": "Chat",
    "VideoConference": "Video Conference",
    "News": "News Reader",
    "Feed": "Feed Reader",
    "RemoteAccess": "Remote Access",
    "P2P": "File Sharing",
    "Dialup": "Dialup",
    "WordProcessor": "Word Processor",
    "Spreadsheet": "Spreadsheet",
    "Presentation": "Presentation",
    "Database": "Database",
    "Calendar": "Calendar",
    "ContactManagement": "Contacts",
    "Publishing": "Publishing",
    "Finance": "Finance",
    "Photography": "Photography",
    "Viewer": "Viewer",
    "Scanning": "Scanning",
    "OCR": "OCR",
    "2DGraphics": "Graphics",
    "3DGraphics": "3D Graphics",
    "VectorGraphics": "Vector Graphics",
    "RasterGraphics": "Image Editor",
    "ImageProcessing": "Image Processing",
    "Player": "Media Player",
    "Recorder": "Recorder",
    "AudioVideoEditing": "Media Editor",
    "Audio": "Audio",
    "Video": "Video",
    "Mixer": "Mixer",
    "Sequencer": "Sequencer",
    "Tuner": "Tuner",
    "TV": "TV",
    "DiscBurning": "Disc Burning",
    "Music": "Music",
    "Midi": "MIDI",
    "TerminalEmulatorConsole": "Console",
    "PackageManager": "Package Manager",
    "Monitor": "System Monitor",
    "Security": "Security",
    "Accessibility": "Accessibility",
    "Printing": "Printing",
    "Filesystem": "Filesystem",
    "HardwareSettings": "Hardware Settings",
    "DesktopSettings": "Desktop Settings",
    "PackageSettings": "Package Settings",
    "Screensaver": "Screensaver",
    "Calculator": "Calculator",
    "Clock": "Clock",
    "TextTools": "Text Tools",
    "Archiving": "Archive Tool",
    "Compression": "Compression",
    "Telephony": "Telephony",
    "Dictionary": "Dictionary",
    "FileTools": "File Tool",
    "Emulator": "Emulator",
    "Engineering": "Engineering",
    "Astronomy": "Astronomy",
    "Biology": "Biology",
    "Chemistry": "Chemistry",
    "Geoscience": "Geoscience",
    "Physics": "Physics",
    "Math": "Mathematics",
    "Electronics": "Electronics",
    "Robotics": "Robotics",
    "MedicalSoftware": "Medical",
    "ArtificialIntelligence": "AI",
    "ComputerScience": "Computer Science",
    "DataVisualization": "Data Visualization",
    "NumericalAnalysis": "Numerical Analysis",
    "History": "History",
    "Languages": "Languages",
    "Literature": "Literature",
    "Geography": "Geography",
    "ActionGame": "Action Game",
    "AdventureGame": "Adventure Game",
    "ArcadeGame": "Arcade Game",
    "BoardGame": "Board Game",
    "BlocksGame": "Puzzle Game",
    "CardGame": "Card Game",
    "KidsGame": "Kids Game",
    "LogicGame": "Logic Game",
    "RolePlaying": "Role-Playing Game",
    "Shooter": "Shooter",
    "Simulation": "Simulation",
    "SportsGame": "Sports Game",
    "StrategyGame": "Strategy Game",
    "Emulator2": "Emulator",
}

# "Main" categories -- the fallback subtitles when nothing more specific exists.
MAIN_CATEGORY_LABELS: dict[str, str] = {
    "AudioVideo": "Multimedia",
    "Audio": "Audio",
    "Video": "Video",
    "Development": "Development",
    "Education": "Education",
    "Game": "Game",
    "Graphics": "Graphics",
    "Network": "Internet",
    "Office": "Office",
    "Science": "Science",
    "Settings": "Settings",
    "System": "System",
    "Utility": "Utility",
}

# Tokens that carry no user-facing meaning (toolkit / vendor / packaging tags);
# never used as a subtitle.
_NOISE_CATEGORIES: frozenset[str] = frozenset(
    {
        "Qt",
        "GTK",
        "KDE",
        "GNOME",
        "Motif",
        "Java",
        "Application",
        "ConsoleOnly",
        "Core",
        "Documentation",  # too generic as a *main* label; kept above as additional
    }
)

GENERIC_TYPE = "Application"

# When several recognised Additional categories are present on one entry, the
# .desktop token order is NOT reliable (Dolphin lists FileTools before
# FileManager). This priority list picks the strongest user-facing signal:
# tokens earlier here win. Anything recognised but unlisted ranks after these
# but still above the Main-category fallback.
_ADDITIONAL_PRIORITY: tuple[str, ...] = (
    "WebBrowser",
    "TerminalEmulator",
    "FileManager",
    "Email",
    "InstantMessaging",
    "IRCClient",
    "IDE",
    "TextEditor",
    "WordProcessor",
    "Spreadsheet",
    "Presentation",
    "Database",
    "Player",
    "RasterGraphics",
    "VectorGraphics",
    "PackageManager",
    "Monitor",
    "FileTransfer",
    "RemoteAccess",
    "Calculator",
    "Archiving",
    "Printing",
)
_ADDITIONAL_RANK: dict[str, int] = {
    tok: i for i, tok in enumerate(_ADDITIONAL_PRIORITY)
}


def category_type(categories: list[str]) -> str:
    """Return a friendly one-word-ish "type" for an app given its Categories.

    Prefers the most specific (Additional) category, then a Main category, then
    a generic fallback. ``categories`` is the already-split list of tokens.
    """
    # 1. Most specific: among the recognised Additional categories present, pick
    #    the highest-priority one (so FileManager beats FileTools regardless of
    #    the order they appear in the .desktop file).
    recognised = [tok for tok in categories if tok in ADDITIONAL_CATEGORY_LABELS]
    if recognised:
        best = min(
            recognised,
            key=lambda t: _ADDITIONAL_RANK.get(t, len(_ADDITIONAL_PRIORITY)),
        )
        return ADDITIONAL_CATEGORY_LABELS[best]
    # 2. Fall back to a recognised Main category.
    for tok in categories:
        label = MAIN_CATEGORY_LABELS.get(tok)
        if label:
            return label
    # 3. Last resort: the first non-noise token, prettified, else generic.
    for tok in categories:
        if tok and tok not in _NOISE_CATEGORIES and not tok.startswith("X-"):
            return tok
    return GENERIC_TYPE


# --- One application entry -------------------------------------------------
@dataclass(frozen=True)
class AppEntry:
    """A single launchable application distilled from a .desktop file."""

    name: str
    type_label: str          # the small subtitle, e.g. "Web Browser"
    exec_argv: list[str]     # command already split, field codes stripped
    icon: str                # Icon= value (name or path), may be ""
    comment: str             # Comment= (kept, though the design uses type_label)
    desktop_id: str          # basename, used to de-dupe across dirs

    def sort_key(self) -> str:
        return self.name.casefold()


# --- .desktop parsing ------------------------------------------------------
# Field codes (%f %u %U ...) the spec says to strip when we run the app without
# passing files/URLs. We launch with no argument, so drop them all.
def _strip_field_codes(exec_str: str) -> list[str]:
    try:
        parts = shlex.split(exec_str)
    except ValueError:
        parts = exec_str.split()
    out: list[str] = []
    for p in parts:
        if len(p) == 2 and p[0] == "%":
            continue  # %f %u %U %i %c %k etc -- drop standalone field codes
        out.append(p)
    return out


def _parse_desktop_file(path: str) -> AppEntry | None:
    """Parse a single .desktop file into an AppEntry, or None if it should not
    appear in the menu (NoDisplay/Hidden, not an Application, no Exec)."""
    data: dict[str, str] = {}
    in_entry = False
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    # Only read the main [Desktop Entry] group; ignore the
                    # "Desktop Action" groups (New Window, etc).
                    in_entry = stripped == "[Desktop Entry]"
                    continue
                if not in_entry:
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                # Keep the first occurrence; ignore locale-suffixed keys
                # (Name[de]=...) so we always take the unlocalised value.
                if "[" in key:
                    continue
                key = key.strip()
                if key not in data:
                    data[key] = val.strip()
    except OSError:
        return None

    if data.get("Type", "Application") != "Application":
        return None
    if data.get("NoDisplay", "").lower() == "true":
        return None
    if data.get("Hidden", "").lower() == "true":
        return None
    name = data.get("Name", "").strip()
    exec_str = data.get("Exec", "").strip()
    if not name or not exec_str:
        return None
    argv = _strip_field_codes(exec_str)
    if not argv:
        return None

    cats = [c for c in data.get("Categories", "").split(";") if c]
    return AppEntry(
        name=name,
        type_label=category_type(cats),
        exec_argv=argv,
        icon=data.get("Icon", "").strip(),
        comment=data.get("Comment", "").strip(),
        desktop_id=os.path.basename(path),
    )


# --- Apps hidden from OUR menu (not uninstalled) --------------------------
# These applications stay installed and keep working; they are simply not shown
# in the Az'arch menu (clutter / not useful here). Keyed on the .desktop
# basename because that is stable across locales, unlike the display Name. The
# Menu Editor (org.kde.kmenuedit) is deleted outright by the install path rather
# than hidden here, but keeping it in the set is harmless belt-and-suspenders.
HIDDEN_DESKTOP_IDS: frozenset[str] = frozenset(
    {
        "bssh.desktop",              # Avahi SSH Server Browser
        "bvnc.desktop",              # Avahi VNC Server Browser
        "avahi-discover.desktop",    # Avahi Zeroconf Browser
        "azarch-install.desktop",    # Az'arch Linux Installer
        "lstopo.desktop",            # Hardware Locality lstopo
        "htop.desktop",              # Htop
        "lftp.desktop",              # lftp
        "cups.desktop",              # Manage Printing
        "org.kde.kmenuedit.desktop", # Menu Editor (also deleted outright)
        "assistant.desktop",         # Qt Assistant
        "qdbusviewer.desktop",       # Qt D-Bus Viewer
        "linguist.desktop",          # Qt Linguist
        "qv4l2.desktop",             # Qt V4L2 test Utility
        "qvidcap.desktop",           # Qt V4L2 video capture utility
        "designer.desktop",          # Qt Widgets Designer
        "stoken-gui.desktop",        # Software Token
        "stoken-gui-small.desktop",  # Software Token (small)
        "vim.desktop",               # Vim
    }
)


def scan_applications(dirs: list[str] | None = None) -> list[AppEntry]:
    """Return all visible applications, de-duplicated by .desktop id and sorted
    alphabetically by display name.

    Later directories in the search path override earlier ones for the same
    .desktop id (per XDG precedence: XDG_DATA_HOME wins). We therefore walk in
    REVERSE precedence and keep the FIRST id we see.

    Entries in HIDDEN_DESKTOP_IDS are skipped: they stay installed but are kept
    out of our menu.
    """
    if dirs is None:
        dirs = _app_dirs()

    by_id: dict[str, AppEntry] = {}
    # dirs is ordered most-specific FIRST (_app_dirs puts XDG_DATA_HOME first),
    # so keep the first occurrence of each id.
    for d in dirs:
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for fn in names:
            if not fn.endswith(".desktop"):
                continue
            if fn in by_id:
                continue  # higher-precedence dir already provided this id
            if fn in HIDDEN_DESKTOP_IDS:
                continue  # hidden from our menu (still installed)
            entry = _parse_desktop_file(os.path.join(d, fn))
            if entry is not None:
                by_id[fn] = entry

    return sorted(by_id.values(), key=AppEntry.sort_key)


if __name__ == "__main__":
    # Tiny CLI for eyeballing what the menu will show.
    for app in scan_applications():
        print(f"{app.name}  --  {app.type_label}  [{app.icon}]")
