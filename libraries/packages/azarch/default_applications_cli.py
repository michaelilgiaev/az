#!/usr/bin/env python3
"""azarch guest command line interface -- `azarch default-applications` (list / get / set the
XDG default apps), the command surface behind the TUI's "Default Applications" screen.

WHAT IT DOES. The build-time emitter packages/azarch/default_applications.py ships the initial
~/.config/mimeapps.list (and the exo TerminalEmulator helper). This module makes those defaults
LIVE and REACHABLE: `azarch default-applications` lists every category and the handler it
currently resolves to, and lets the user CHANGE a category's default -- which the TUI drives
(the same apply-and-capture flow as the network/theme screens).

  azarch default-applications list            print every category + its current handler
  azarch default-applications categories      print the category keys (one per line; used by the
                                              TUI to enumerate the sub-screens)
  azarch default-applications get <key>       print the current handler for one category
  azarch default-applications candidates <key>  print the pickable handlers for one category
  azarch default-applications set <key> <id>  set the category's default handler to <id>.desktop

HOW A SET APPLIES (immediately, no re-login):
  * MIME-backed categories (Web/HTML/Music/Video/Photos/Word/Spreadsheet/PDF/Source Code/File
    Manager/Plain Text): `xdg-mime default <id> <mime>...` rewrites the [Default Applications]
    group of ~/.config/mimeapps.list -- the same file the emitter seeds and every GTK/XDG app
    reads, so the change is effective at once.
  * Terminal (no MIME of its own): rewrites the exo TerminalEmulator preferred-app
    (~/.config/xfce4/helpers.rc), which is what Thunar's "Open Terminal Here" uses.
  * Calculator / Mail: Calculator has no MIME (qalculate-gtk is recorded but there is no
    xdg-mime key to flip); Mail is intentionally empty. `get` still reports them.

SINGLE SOURCE OF TRUTH. The category -> label -> key -> MIME -> candidate table lives in
default_applications.py; this bundled module carries a mirror (the bundle is a standalone script
and cannot import the build-time package at runtime) that a test pins BYTE-FOR-BYTE against that
source, so the two cannot drift -- exactly the wallpaper.py <-> model.c lock-step pattern.

Standard library only (this module is bundled into /usr/local/bin/azarch; see common.py). No
sudo -- it writes the user's own config.
"""

from __future__ import annotations

# BUNDLE_START

# The category table, MIRRORED from packages/azarch/default_applications.py (a test pins them
# equal). Each entry: key -> (label, group, representative-mime-tuple, candidate .desktop ids).
# `mimes` is the MIME types xdg-mime sets for that category (empty for the non-MIME ones); the
# first candidate is the Az'arch shipped default. Order matters: it is the TUI's row order.
DA_CATEGORIES: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    # key,            label,          group,        mimes,                                       candidates
    ("web",          "Web",          "Internet",   ("x-scheme-handler/http", "x-scheme-handler/https"), ("librewolf.desktop", "firefox.desktop")),
    ("mail",         "Mail",         "Internet",   (),                                          ()),
    ("html",         "HTML",         "Internet",   ("text/html", "application/xhtml+xml"),      ("librewolf.desktop", "firefox.desktop", "org.gnome.gedit.desktop")),
    ("music",        "Music",        "Multimedia", ("audio/mpeg", "audio/flac", "audio/ogg", "audio/x-wav", "audio/x-vorbis+ogg", "audio/mp4", "audio/aac", "audio/x-m4a"), ("vlc.desktop",)),
    ("video",        "Video",        "Multimedia", ("video/mp4", "video/x-matroska", "video/webm", "video/x-msvideo", "video/quicktime", "video/mpeg", "video/x-flv"), ("vlc.desktop",)),
    ("photos",       "Photos",       "Multimedia", ("image/jpeg", "image/png", "image/gif", "image/bmp", "image/tiff", "image/webp", "image/x-xpixmap", "image/svg+xml"), ("xviewer.desktop", "gimp.desktop", "feh.desktop")),
    ("word",         "Word",         "Office",     ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword", "application/vnd.oasis.opendocument.text", "application/rtf"), ("libreoffice-writer.desktop",)),
    ("spreadsheet",  "Spreadsheet",  "Office",     ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel", "application/vnd.oasis.opendocument.spreadsheet", "text/csv"), ("libreoffice-calc.desktop",)),
    ("pdf",          "PDF",          "Office",     ("application/pdf",),                        ("librewolf.desktop", "firefox.desktop")),
    ("source-code",  "Source Code",  "Office",     ("text/x-csrc", "text/x-chdr", "text/x-python", "text/x-shellscript", "application/javascript", "text/x-c++src", "application/json", "text/markdown", "text/xml"), ("org.gnome.gedit.desktop", "vim.desktop")),
    ("file-manager", "File Manager", "System",     ("inode/directory",),                        ("thunar.desktop",)),
    ("plain-text",   "Plain Text",   "System",     ("text/plain",),                             ("org.gnome.gedit.desktop", "vim.desktop")),
    ("calculator",   "Calculator",   "System",     (),                                          ("qalculate-gtk.desktop",)),
    ("terminal",     "Terminal",     "System",     (),                                          ("kitty.desktop",)),
)

# The exo TerminalEmulator preferred-app selection Thunar's "Open Terminal Here" uses. Kept in
# lock-step with default_applications.HELPERS_RC_PATH / TERMINAL_BIN (a test pins them).
DA_HELPERS_RC = "xfce4/helpers.rc"           # under ~/.config
_DA_TERMINAL_KEY = "TerminalEmulator"


def _da_row(key: str):
    for row in DA_CATEGORIES:
        if row[0] == key:
            return row
    return None


def _da_config_home() -> str:
    """~/.config (honouring XDG_CONFIG_HOME), where mimeapps.list + helpers.rc live."""
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")


def _da_current_terminal() -> str:
    """The exo TerminalEmulator .desktop-ish handler, read from helpers.rc. Returns the raw
    value (e.g. "kitty") mapped to "<value>.desktop" for a uniform display, or "" if unset."""
    path = os.path.join(_da_config_home(), DA_HELPERS_RC)
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith(_DA_TERMINAL_KEY + "="):
                val = line.split("=", 1)[1].strip()
                return f"{val}.desktop" if val and not val.endswith(".desktop") else val
    except OSError:
        pass
    return ""


def _da_mimeapps_default(mime: str) -> str:
    """The .desktop id mapped to <mime> under [Default Applications] in ~/.config/mimeapps.list,
    or "". Read DIRECTLY from the file (no `xdg-mime query` fork) -- this is the same value
    xdg-mime returns, but instant, which is what keeps the TUI's Default Applications screen
    snappy (the C model reads the same file the same way). Only the [Default Applications] group
    is consulted (associations groups are ignored, matching xdg-mime's "default" query)."""
    path = os.path.join(_da_config_home(), "mimeapps.list")
    try:
        in_defaults = False
        for line in open(path, encoding="utf-8"):
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                in_defaults = (s == "[Default Applications]")
                continue
            if in_defaults and "=" in s:
                k, v = s.split("=", 1)
                if k.strip() == mime:
                    # a mimeapps value may be a ';'-separated list; the first is the default.
                    return v.strip().split(";", 1)[0].strip()
    except OSError:
        pass
    return ""


def _da_current_handler(key: str) -> str:
    """The .desktop id currently handling a category, or "(none)". MIME categories read
    ~/.config/mimeapps.list directly (no fork -- snappy); Terminal reads helpers.rc;
    Mail/Calculator have no query."""
    row = _da_row(key)
    if row is None:
        return "(unknown)"
    _k, _label, _group, mimes, _cands = row
    if key == "terminal":
        return _da_current_terminal() or "(none)"
    if not mimes:
        return "(none)"
    return _da_mimeapps_default(mimes[0]) or "(none)"


def _da_set_terminal(desktop_id: str) -> int:
    """Point the exo TerminalEmulator at the app in <desktop_id> (strip ".desktop" -> the bin
    name exo expects in helpers.rc). Rewrites the TerminalEmulator= line (creating the file)."""
    bin_name = desktop_id[:-len(".desktop")] if desktop_id.endswith(".desktop") else desktop_id
    path = os.path.join(_da_config_home(), DA_HELPERS_RC)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines: list[str] = []
    found = False
    try:
        for line in open(path, encoding="utf-8"):
            if line.strip().startswith(_DA_TERMINAL_KEY + "="):
                lines.append(f"{_DA_TERMINAL_KEY}={bin_name}\n")
                found = True
            else:
                lines.append(line)
    except OSError:
        pass
    if not found:
        lines.append(f"{_DA_TERMINAL_KEY}={bin_name}\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    print(f"Terminal default set to {desktop_id}.")
    return 0


# The freedesktop application directories, in the order xdg-mime/GIO consult them (user dir
# first so a user override wins). This is WHERE THE .DESKTOP FILES LIVE -- the `desktops`
# subcommand prints these so a developer knows where to drop or edit their own.
def _da_desktop_dirs() -> list[str]:
    home = os.path.expanduser("~")
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    dirs = [os.path.join(data_home, "applications")]
    dirs += [os.path.join(d, "applications") for d in data_dirs.split(":") if d]
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _da_installed_desktops() -> list[str]:
    """Every installed .desktop id (basename), across the application dirs, sorted & de-duped.
    This is the FULL set of apps the user can set as a handler -- not just the shipped quick-picks
    -- so whatever the user installs (e.g. firefox) shows up here."""
    found: set[str] = set()
    for d in _da_desktop_dirs():
        try:
            for name in os.listdir(d):
                if name.endswith(".desktop"):
                    found.add(name)
        except OSError:
            continue
    return sorted(found)


def _da_desktop_exists(desktop_id: str) -> bool:
    """True if <desktop_id> is an installed .desktop in any application dir."""
    for d in _da_desktop_dirs():
        if os.path.isfile(os.path.join(d, desktop_id)):
            return True
    return False


def _da_set(key: str, desktop_id: str) -> int:
    """Set a category's default handler to <desktop_id>. MIME categories go through
    `xdg-mime default`; Terminal through the exo helper.

    The handler may be ANY installed .desktop -- not only the shipped quick-picks. So a developer
    can set e.g. firefox even though it is not in the curated candidate list ("HOW DO I MANUALLY
    PUT MY OWN STUFF"). The only guard is that the .desktop must actually be installed (an unknown
    quick-pick shorthand or a typo is rejected), so a set always resolves to a real app. Pass an
    absolute path or a bare id; a bare id is looked up in the application dirs (see `desktops`)."""
    row = _da_row(key)
    if row is None:
        _err(f"azarch default-applications: unknown category: {key}")
        return 2
    _k, label, _group, mimes, cands = row
    # Accept any INSTALLED .desktop (candidates are just the quick-picks). Reject only if it is
    # neither a listed candidate nor an installed .desktop -- that is a typo/nonexistent app.
    if desktop_id not in cands and not _da_desktop_exists(desktop_id):
        _err(f"azarch default-applications: {desktop_id!r} is not installed "
             f"(quick-picks for {label!r}: {', '.join(cands) or 'none'}; "
             f"see `azarch default-applications desktops {key}` for all installed apps)")
        return 2
    if key == "terminal":
        return _da_set_terminal(desktop_id)
    if not mimes:
        _err(f"azarch default-applications: {label!r} has no MIME default to set")
        return 2
    if not _have("xdg-mime"):
        _err("azarch default-applications: xdg-mime not found")
        return 1
    # xdg-mime default <id> <mime>...: rewrites ~/.config/mimeapps.list's [Default Applications].
    rc = subprocess.run(["xdg-mime", "default", desktop_id, *mimes]).returncode
    if rc != 0:
        _err(f"azarch default-applications: xdg-mime failed (rc {rc})")
        return rc
    print(f"{label} default set to {desktop_id}.")
    return 0


def _da_desktops(key: str | None) -> int:
    """Print WHERE the .desktop files live and WHICH apps are installed -- the discovery surface
    a developer asked for ("WHERE IS THE .DESKTOP, HOW DO I MANUALLY PUT MY OWN STUFF"). With a
    category key, also shows that category's quick-picks + current handler and the exact
    `xdg-mime default` / `azarch default-applications set` commands to change it by hand."""
    print("Application (.desktop) directories, in priority order (a file in an earlier dir wins):")
    for d in _da_desktop_dirs():
        exists = "" if os.path.isdir(d) else "   (absent)"
        print(f"  {d}{exists}")
    print("\nTo add or override an app: drop a <name>.desktop into the FIRST dir above (create it")
    print("if needed), then set it as a default with either command below.")
    if key is not None:
        row = _da_row(key)
        if row is None:
            _err(f"\nazarch default-applications: unknown category: {key}")
            return 2
        _k, label, _group, mimes, cands = row
        print(f"\n[{label}]  current: {_da_current_handler(key)}")
        print(f"  quick-picks: {', '.join(cands) or '(none)'}")
        if mimes:
            print(f"  MIME types : {' '.join(mimes)}")
            print(f"  set by hand : xdg-mime default <id>.desktop {' '.join(mimes)}")
        print(f"  set (azarch): azarch default-applications set {key} <id>.desktop")
    print("\nAll installed .desktop apps you can set as a handler:")
    for name in _da_installed_desktops():
        print(f"  {name}")
    return 0


def _da_list() -> int:
    """Print every category (grouped) and the handler it currently resolves to."""
    last_group = None
    for key, label, group, _mimes, _cands in DA_CATEGORIES:
        if group != last_group:
            print(f"[{group}]")
            last_group = group
        print(f"  {label} ({key}): {_da_current_handler(key)}")
    return 0


def default_applications_usage() -> None:
    print(
        "Usage: azarch default-applications <list|categories|get|candidates|set> [args]\n"
        "\n"
        "List and change the XDG default applications (which app opens which file type).\n"
        "\n"
        "  list                    Print every category and its current handler.\n"
        "  categories              Print the category keys (one per line).\n"
        "  get <key>               Print the current handler for one category.\n"
        "  candidates <key>        Print the quick-pick handlers for one category.\n"
        "  desktops [key]          Show WHERE .desktop files live + ALL installed apps (and, with\n"
        "                          a category, how to set it by hand). Use this to find/add apps.\n"
        "  set <key> <id.desktop>  Set the category's default handler (ANY installed .desktop,\n"
        "                          not only the quick-picks).\n"
        "\n"
        "Categories: " + ", ".join(k for k, *_ in DA_CATEGORIES) + "\n"
    )


def cmd_default_applications(args: list[str]) -> int:
    """Dispatch `azarch default-applications ...`."""
    if not args or args[0] in ("-h", "--help", "help"):
        default_applications_usage()
        return 0
    verb = args[0]
    if verb == "list":
        return _da_list()
    if verb == "categories":
        for key, *_ in DA_CATEGORIES:
            print(key)
        return 0
    if verb == "get":
        if len(args) < 2:
            _err("azarch default-applications get: need a category key")
            return 2
        print(_da_current_handler(args[1]))
        return 0
    if verb == "candidates":
        if len(args) < 2:
            _err("azarch default-applications candidates: need a category key")
            return 2
        row = _da_row(args[1])
        if row is None:
            _err(f"azarch default-applications: unknown category: {args[1]}")
            return 2
        for c in row[4]:
            print(c)
        return 0
    if verb == "desktops":
        # optional category key; without one, just the dirs + full installed list.
        return _da_desktops(args[1] if len(args) >= 2 else None)
    if verb == "set":
        if len(args) < 3:
            _err("azarch default-applications set: need <category> <id.desktop>")
            return 2
        return _da_set(args[1], args[2])
    _err(f"azarch default-applications: unknown subcommand: {verb}")
    default_applications_usage()
    return 2
