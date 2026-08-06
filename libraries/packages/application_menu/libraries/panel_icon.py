#!/usr/bin/env python3
"""Insert (or remove) the Az'arch menu ICON applet in the Plasma panel config.

The panel layout lives in plasma-org.kde.plasma.desktop-appletsrc as an INI-ish
file with NESTED bracket groups, e.g.:

    [Containments][2][General]
    AppletOrder=12;2;3;4;5;6;7;8;9

    [Containments][2][Applets][12]
    plugin=org.kde.plasma.kickoff
    ...

We add one applet -- an org.kde.plasma.icon that launches our menu .desktop --
positioned immediately AFTER Kickoff and BEFORE the task manager (so it sits to
the right of the Application Launcher and left of LibreWolf).

This is done in Python (not kwriteconfig6) because kwriteconfig6 escapes the
nested `][` group syntax into a broken flat `[Foo\x5d\x5b..]` group (seen live);
plain text surgery on the exact group headers is reliable and reversible.

THE "PAPER ICON THAT LAUNCHES NOTHING" BUG: org.kde.plasma.icon does NOT read the
configured .desktop directly. On first paint it derives its OWN backing copy under
~/.local/share/plasma_icons/ and reads THAT (stored as the applet's
[Configuration] localPath). It only copies the target verbatim (keeping
Type=Application + Exec=) when it recognises the configured url as a LOCAL .desktop
file; given a BARE path (…/foo.desktop, no file:// scheme) it takes the generic
branch and writes a Type=Link / URL= / Icon=unknown wrapper -- which on click opens
the file's location instead of Exec'ing (nothing launches) and shows the generic
"piece of paper" glyph. So `add` PRE-CREATES that backing file itself as a real
launcher and points localPath at it, writes url= as a file:// URI (belt), and
leaves the applet immutability=0 so Plasma can refresh it.

Usage:
    panel_icon.py add    <appletsrc> <panel_id> <desktop_path> <icon_name> \\
                         <backing_path> [<exec_path>]
    panel_icon.py remove <appletsrc> <panel_id>

`add` is idempotent: if our icon applet (identified by the desktop_path in its
url=) already exists, it is left as-is. `remove` deletes the applet stanza(s)
and drops it from AppletOrder. Both rewrite the file in place. `add` also writes
<backing_path> (the plasma_icons localPath) as a Type=Application launcher whose
Exec is <exec_path> (default: the installed azarch-application-menu launcher).
"""

from __future__ import annotations

import os
import re
import sys


PANEL_APPLET_ICON = "org.kde.plasma.icon"

# Default Exec for the backing .desktop: the installed menu launcher (matches
# configuration/application_menu.MENU_LAUNCHER_SYSTEM_PATH and install.sh's BIN_DEST).
DEFAULT_MENU_LAUNCHER = "/usr/local/bin/azarch-application-menu"


def _write_backing_desktop(backing_path: str, name: str, icon_name: str,
                           exec_path: str) -> None:
    """Create the org.kde.plasma.icon backing .desktop the applet reads via its
    localPath. It MUST be a real launcher (Type=Application + Exec=), NOT the
    Type=Link/Icon=unknown wrapper the applet would otherwise generate from a bare
    url= (that wrapper is the paper-icon-launches-nothing bug). Parent dir is
    created.

    It MUST also be EXECUTABLE (0o755): KDE's isAuthorizedDesktopFile() treats a
    NON-executable Type=Application file as UNTRUSTED, so the applet's KIO click path
    pops a modal "this desktop entry is not trusted, execute?" dialog (a noisy error)
    and launches nothing until confirmed. The exec bit is KDE's trust signal."""
    parent = os.path.dirname(backing_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Comment={name}\n"
        f"Exec={exec_path}\n"
        f"Icon={icon_name}\n"
        "Terminal=false\n"
        "Categories=System;Utility;\n"
    )
    with open(backing_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    # Executable = trusted to KDE (no "untrusted desktop entry" dialog on click).
    os.chmod(backing_path, 0o755)


def _general_header(panel_id: str) -> str:
    return f"[Containments][{panel_id}][General]"


def _applet_header(panel_id: str, applet_id: int) -> str:
    return f"[Containments][{panel_id}][Applets][{applet_id}]"


def _read(path: str) -> list[str]:
    with open(path, encoding="utf-8") as fh:
        return fh.read().splitlines()


def _write(path: str, lines: list[str]) -> None:
    # Trim trailing blank lines so add/remove round-trips are byte-clean (Plasma
    # ignores trailing whitespace, but a clean diff makes changes auditable).
    while lines and lines[-1] == "":
        lines.pop()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def _find_applet_order(lines: list[str], panel_id: str) -> tuple[int, list[int]]:
    """Return (line_index_of_AppletOrder, current_id_list). Searches within the
    panel's [General] group."""
    gen = _general_header(panel_id)
    in_general = False
    for i, ln in enumerate(lines):
        if ln.startswith("[") and ln == gen:
            in_general = True
            continue
        if in_general and ln.startswith("["):
            in_general = False
        if in_general and ln.startswith("AppletOrder="):
            ids = [int(x) for x in ln.split("=", 1)[1].split(";") if x.strip()]
            return i, ids
    raise SystemExit(f"panel_icon: AppletOrder not found in {gen}")


def _existing_applet_ids(lines: list[str], panel_id: str) -> set[int]:
    ids = set()
    pat = re.compile(
        r"^\[Containments\]\[" + re.escape(panel_id) + r"\]\[Applets\]\[(\d+)\]$"
    )
    for ln in lines:
        m = pat.match(ln)
        if m:
            ids.add(int(m.group(1)))
    return ids


def _kickoff_id(lines: list[str], panel_id: str) -> int | None:
    """Find the applet id whose plugin is Kickoff, so we can place our icon
    right after it."""
    pat = re.compile(
        r"^\[Containments\]\[" + re.escape(panel_id) + r"\]\[Applets\]\[(\d+)\]$"
    )
    current = None
    for ln in lines:
        m = pat.match(ln)
        if m:
            current = int(m.group(1))
        elif ln == "plugin=org.kde.plasma.kickoff" and current is not None:
            return current
    return None


def _our_icon_id(lines: list[str], panel_id: str, desktop_path: str) -> int | None:
    """Return the applet id of an already-installed Az'arch icon applet (one
    whose url= references our desktop_path), or None."""
    pat = re.compile(
        r"^\[Containments\]\[" + re.escape(panel_id)
        + r"\]\[Applets\]\[(\d+)\]\[Configuration\]\[General\]$"
    )
    current = None
    for ln in lines:
        m = pat.match(ln)
        if m:
            current = int(m.group(1))
        elif current is not None and ln.startswith("url=") and desktop_path in ln:
            return current
    return None


def add(path: str, panel_id: str, desktop_path: str, icon_name: str,
        backing_path: str, exec_path: str = DEFAULT_MENU_LAUNCHER) -> None:
    # Create the backing .desktop the applet reads (localPath) FIRST, as a real
    # Type=Application launcher -- so the applet never bakes the Type=Link/Icon=
    # unknown wrapper (the paper-icon-launches-nothing bug). Name/Comment come from
    # the .desktop basename; Exec runs the installed launcher.
    name = os.path.splitext(os.path.basename(desktop_path))[0]
    _write_backing_desktop(backing_path, name, icon_name, exec_path)

    lines = _read(path)

    # Idempotent: already installed?
    if _our_icon_id(lines, panel_id, desktop_path) is not None:
        return

    order_idx, order = _find_applet_order(lines, panel_id)
    used = _existing_applet_ids(lines, panel_id) | set(order)
    new_id = max(used) + 1  # a fresh, unused applet id

    # Position: immediately after Kickoff in AppletOrder; if Kickoff not found,
    # put it first.
    kick = _kickoff_id(lines, panel_id)
    new_order = []
    inserted = False
    for aid in order:
        new_order.append(aid)
        if kick is not None and aid == kick and not inserted:
            new_order.append(new_id)
            inserted = True
    if not inserted:  # Kickoff absent -> lead with our icon
        new_order = [new_id] + order
    lines[order_idx] = "AppletOrder=" + ";".join(str(x) for x in new_order)

    # Append the applet stanzas at end of file (group order does not matter to
    # Plasma; AppletOrder controls on-screen position).
    #   * immutability=0 so Plasma can refresh the applet's backing file.
    #   * [Configuration] localPath -> the backing .desktop we just wrote, so the
    #     applet reads our real launcher instead of generating a broken wrapper.
    #   * url= is a file:// URI (NOT a bare path): a bare path triggers the
    #     Type=Link/Icon=unknown branch -- the paper-icon bug.
    stanza = [
        "",
        _applet_header(panel_id, new_id),
        "immutability=0",
        f"plugin={PANEL_APPLET_ICON}",
        "",
        _applet_header(panel_id, new_id) + "[Configuration]",
        f"localPath={backing_path}",
        "",
        _applet_header(panel_id, new_id) + "[Configuration][General]",
        f"url=file://{desktop_path}",
        f"iconName={icon_name}",
    ]
    lines.extend(stanza)
    _write(path, lines)


def remove(path: str, panel_id: str) -> None:
    lines = _read(path)
    # Find our applet id(s): any icon applet whose config references our binary
    # path OR desktop -- we match by the plugin being org.kde.plasma.icon AND a
    # url mentioning azarch-application-menu.
    ids_to_remove = set()
    pat_applet = re.compile(
        r"^\[Containments\]\[" + re.escape(panel_id) + r"\]\[Applets\]\[(\d+)\]$"
    )
    pat_cfg = re.compile(
        r"^\[Containments\]\[" + re.escape(panel_id)
        + r"\]\[Applets\]\[(\d+)\]\[Configuration\]\[General\]$"
    )
    # First pass: which ids are icon applets, which reference our menu.
    is_icon = {}
    refs_us = {}
    current = None
    for ln in lines:
        m = pat_applet.match(ln)
        mc = pat_cfg.match(ln)
        if m:
            current = int(m.group(1))
        elif mc:
            current = int(mc.group(1))
        elif current is not None:
            if ln == f"plugin={PANEL_APPLET_ICON}":
                is_icon[current] = True
            if ln.startswith("url=") and "azarch-application-menu" in ln:
                refs_us[current] = True
    for aid in refs_us:
        if is_icon.get(aid):
            ids_to_remove.add(aid)

    if not ids_to_remove:
        return

    # Drop from AppletOrder.
    order_idx, order = _find_applet_order(lines, panel_id)
    new_order = [a for a in order if a not in ids_to_remove]
    lines[order_idx] = "AppletOrder=" + ";".join(str(x) for x in new_order)

    # Remove every group block whose header is one of our applet ids (the applet
    # stanza AND its [Configuration][...] subgroups). A block runs from its
    # header line until the next top-level "[" line.
    out = []
    skip = False
    hdr_re = re.compile(
        r"^\[Containments\]\[" + re.escape(panel_id) + r"\]\[Applets\]\[(\d+)\]"
    )
    for ln in lines:
        m = hdr_re.match(ln)
        if ln.startswith("[") and m and int(m.group(1)) in ids_to_remove:
            skip = True
            continue
        if ln.startswith("[") and (not m or int(m.group(1)) not in ids_to_remove):
            skip = False
        if skip:
            continue
        out.append(ln)

    # Collapse any doubled blank lines left behind.
    collapsed = []
    for ln in out:
        if ln == "" and collapsed and collapsed[-1] == "":
            continue
        collapsed.append(ln)
    _write(path, collapsed)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    action = argv[1]
    # add <appletsrc> <panel_id> <desktop_path> <icon_name> <backing_path> [<exec_path>]
    if action == "add" and len(argv) in (7, 8):
        add(*argv[2:])
        return 0
    if action == "remove" and len(argv) == 4:
        remove(argv[2], argv[3])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
