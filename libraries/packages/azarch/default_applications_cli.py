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
    ("web",          "Web",          "Internet",   ("x-scheme-handler/http", "x-scheme-handler/https"), ("librewolf.desktop",)),
    ("mail",         "Mail",         "Internet",   (),                                          ()),
    ("html",         "HTML",         "Internet",   ("text/html", "application/xhtml+xml"),      ("librewolf.desktop", "org.gnome.gedit.desktop")),
    ("music",        "Music",        "Multimedia", ("audio/mpeg", "audio/flac", "audio/ogg", "audio/x-wav", "audio/x-vorbis+ogg", "audio/mp4", "audio/aac", "audio/x-m4a"), ("vlc.desktop",)),
    ("video",        "Video",        "Multimedia", ("video/mp4", "video/x-matroska", "video/webm", "video/x-msvideo", "video/quicktime", "video/mpeg", "video/x-flv"), ("vlc.desktop",)),
    ("photos",       "Photos",       "Multimedia", ("image/jpeg", "image/png", "image/gif", "image/bmp", "image/tiff", "image/webp", "image/x-xpixmap", "image/svg+xml"), ("xviewer.desktop", "gimp.desktop")),
    ("word",         "Word",         "Office",     ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword", "application/vnd.oasis.opendocument.text", "application/rtf"), ("libreoffice-writer.desktop",)),
    ("spreadsheet",  "Spreadsheet",  "Office",     ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel", "application/vnd.oasis.opendocument.spreadsheet", "text/csv"), ("libreoffice-calc.desktop",)),
    ("pdf",          "PDF",          "Office",     ("application/pdf",),                        ("librewolf.desktop",)),
    ("source-code",  "Source Code",  "Office",     ("text/x-csrc", "text/x-chdr", "text/x-python", "text/x-shellscript", "application/javascript", "text/x-c++src", "application/json", "text/markdown", "text/xml"), ("org.gnome.gedit.desktop",)),
    ("file-manager", "File Manager", "System",     ("inode/directory",),                        ("thunar.desktop",)),
    ("plain-text",   "Plain Text",   "System",     ("text/plain",),                             ("org.gnome.gedit.desktop",)),
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


def _da_current_handler(key: str) -> str:
    """The .desktop id currently handling a category, or "(none)". For a MIME category ask
    `xdg-mime query default <mime>`; Terminal reads helpers.rc; Mail/Calculator have no query."""
    row = _da_row(key)
    if row is None:
        return "(unknown)"
    _k, _label, _group, mimes, _cands = row
    if key == "terminal":
        return _da_current_terminal() or "(none)"
    if not mimes:
        return "(none)"
    if not _have("xdg-mime"):
        return "(xdg-mime missing)"
    r = subprocess.run(["xdg-mime", "query", "default", mimes[0]],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    val = r.stdout.decode("utf-8", "replace").strip()
    return val or "(none)"


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


def _da_set(key: str, desktop_id: str) -> int:
    """Set a category's default handler to <desktop_id>. MIME categories go through
    `xdg-mime default`; Terminal through the exo helper. Rejects an unknown category or a
    candidate not offered for it (so a typo can't set a nonexistent handler)."""
    row = _da_row(key)
    if row is None:
        _err(f"azarch default-applications: unknown category: {key}")
        return 2
    _k, label, _group, mimes, cands = row
    if desktop_id not in cands:
        _err(f"azarch default-applications: {desktop_id!r} is not a candidate for {label!r} "
             f"(choices: {', '.join(cands) or 'none'})")
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
        "  candidates <key>        Print the handlers you can pick for one category.\n"
        "  set <key> <id.desktop>  Set the category's default handler.\n"
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
    if verb == "set":
        if len(args) < 3:
            _err("azarch default-applications set: need <category> <id.desktop>")
            return 2
        return _da_set(args[1], args[2])
    _err(f"azarch default-applications: unknown subcommand: {verb}")
    default_applications_usage()
    return 2
