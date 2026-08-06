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

Usage:
    panel_icon.py add    <appletsrc> <panel_id> <desktop_path> <icon_name>
    panel_icon.py remove <appletsrc> <panel_id>

`add` is idempotent: if our icon applet (identified by the desktop_path in its
url=) already exists, it is left as-is. `remove` deletes the applet stanza(s)
and drops it from AppletOrder. Both rewrite the file in place.
"""

from __future__ import annotations

import re
import sys


PANEL_APPLET_ICON = "org.kde.plasma.icon"


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


def add(path: str, panel_id: str, desktop_path: str, icon_name: str) -> None:
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
    stanza = [
        "",
        _applet_header(panel_id, new_id),
        "immutability=1",
        f"plugin={PANEL_APPLET_ICON}",
        "",
        _applet_header(panel_id, new_id) + "[Configuration][General]",
        f"url={desktop_path}",
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
    if action == "add" and len(argv) == 6:
        add(argv[2], argv[3], argv[4], argv[5])
        return 0
    if action == "remove" and len(argv) == 4:
        remove(argv[2], argv[3])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
