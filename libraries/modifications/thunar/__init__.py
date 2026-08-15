"""Thunar file-manager configuration (PROMPT task 2/4/7) -- the Az'arch Thunar setup.

Thunar (Xfce's GTK file manager) replaced Dolphin. This package configures it to Az'arch's
taste and is consumed by compiler._emit_apps exactly like the other modification modules
(emit_plan() in the builder/dest/mode/owner shape, plus the asset/render extras kitty uses).
It is a DIRECTORY module (like modifications/gedit's source tree) because it is large; the
pieces are split into focused submodules and re-exported here:

  * settings.py -- the preferences (view, TEXT-ENTRY location bar, shortcuts side pane, no
    expandable-folder arrows, split view off, removable-volume management off, the ~20% zoom
    bump) rendered into BOTH thunarrc AND the Xfconf channel XML from one table, plus the
    Thunar-scoped gtk.css that carries the font half of the +20% bump in scale-relative em.
    Also the hidden-bookmarks/hidden-devices arrays that remove the Devices/Network/Computer/
    Recent side-pane clutter.
  * sidebar.py  -- ~/.config/gtk-3.0/bookmarks, the shortcuts pane, built from
    modifications/home_directory (the SAME set as the on-disk home layout, resolved paths).
  * actions.py  -- ~/.config/Thunar/uca.xml (Edit with gedit on any file, Edit with gimp on
    images, Create Link via zenity, Open Terminal Here via kitty) + the `link` helper script.
  * launcher.py -- the thunar.desktop override (Name="Thunar", custom Az'arch icon) + the
    custom icon files.

WHAT LANDS WHERE:
  HOME files (owner "home", chowned 1000:998 and mirrored into /etc/skel):
    ~/.config/Thunar/thunarrc, ~/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml,
    ~/.config/gtk-3.0/gtk.css, ~/.config/gtk-3.0/bookmarks, ~/.config/Thunar/uca.xml
  SYSTEM files (owner "root"):
    the `link` helper (/usr/local/bin/azarch-link, executable), the custom icon (scalable SVG
    + PNG rasterizations), and the thunar.desktop override (a package-owned path -> staged for
    the post-pacstrap install hook via pacman.ISO_APP_OVERRIDES, not the overlay).

The suppression of the extra Thunar/Xfce app-menu launchers (Bulk Rename, Thunar Preferences,
About Xfce, Removable Drives) is done in pacman.ISO_APP_OVERRIDES via NoDisplay overrides (see
pacman.py), not here -- those are separate package-owned .desktop files.
"""

from __future__ import annotations

from modifications.thunar import actions
from modifications.thunar import launcher
from modifications.thunar import live_sidebar
from modifications.thunar import locale
from modifications.thunar import menu_cleanup
from modifications.thunar import settings
from modifications.thunar import sidebar

# Re-export the public constants callers/tests reach for (paths + the icon name), so
# `from modifications import thunar; thunar.THUNARRC_PATH` works like the flat modules.
THUNARRC_PATH = settings.THUNARRC_PATH
XFCONF_THUNAR_PATH = settings.XFCONF_THUNAR_PATH
GTK_CSS_PATH = settings.GTK_CSS_PATH
GTK_BOOKMARKS_PATH = sidebar.GTK_BOOKMARKS_PATH
UCA_PATH = actions.UCA_PATH
LINK_SCRIPT_DEST = actions.LINK_SCRIPT_DEST
THUNAR_DESKTOP_PATH = launcher.THUNAR_DESKTOP_PATH
THUNAR_ICON_NAME = launcher.THUNAR_ICON_NAME
ICON_ASSET = launcher.ICON_ASSET
ICON_SCALABLE_PATH = launcher.ICON_SCALABLE_PATH
ICON_PNG_SIZES = launcher.ICON_PNG_SIZES
LIVE_SIDEBAR_SYNC_DEST = live_sidebar.SYNC_SCRIPT_DEST

_CONF = 0o644
_EXEC = 0o755


def emit_plan() -> list[dict]:
    """Return the emit plan for the whole Thunar setup, in the builder/dest/mode/owner shape
    compiler._emit_apps consumes (with the "asset"/"render" extras for the icon). HOME files
    are skel-mirrored; the `link` script and icon are root-owned system files; the
    thunar.desktop entry's dest matches an ISO_APP_OVERRIDES target so it is staged for the
    post-pacstrap install hook. Returns FRESH dicts so a caller cannot mutate module state."""
    plan: list[dict] = [
        # --- HOME config files (skel-mirrored) ---
        {   # thunarrc: the classic GKeyFile (fresh-profile seed + no-xfconfd fallback).
            "builder": settings.thunarrc,
            "dest": settings.THUNARRC_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        {   # the Xfconf channel XML: the runtime store Thunar 4.20 actually reads.
            "builder": settings.xfconf_channel_xml,
            "dest": settings.XFCONF_THUNAR_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        {   # the Thunar-scoped gtk.css (font half of the +20% bump).
            "builder": settings.gtk_css,
            "dest": settings.GTK_CSS_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        {   # the sidebar shortcuts (GTK bookmarks) built from home_directory.
            "builder": sidebar.gtk_bookmarks,
            "dest": sidebar.GTK_BOOKMARKS_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        {   # the custom actions (Edit with gedit/gimp, Create Link, Open Terminal Here).
            "builder": actions.uca_xml,
            "dest": actions.UCA_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        # --- SYSTEM files (root-owned) ---
        {   # the `link` helper the Create Link action calls (executable).
            "builder": actions.link_script,
            "dest": actions.LINK_SCRIPT_DEST,
            "mode": _EXEC,
            "owner": "root",
        },
        {   # the custom icon: scalable SVG master (our asset, our icon name).
            "builder": None,
            "asset": launcher.ICON_ASSET,
            "dest": launcher.ICON_SCALABLE_PATH,
            "mode": _CONF,
            "owner": "root",
        },
        {   # the thunar.desktop override (package-owned dest -> staged post-pacstrap).
            "builder": launcher.thunar_desktop,
            "dest": launcher.THUNAR_DESKTOP_PATH,
            "mode": _CONF,
            "owner": "root",
        },
    ]
    # The NoDisplay overrides that hide the extra Thunar/Xfce launchers (Bulk Rename, Thunar
    # Preferences, Removable Drives, About Xfce) from the application menu (PROMPT task 3).
    # Each is a package-owned .desktop, so its dest matches an ISO_APP_OVERRIDES target and
    # compiler._emit_apps stages the body for the post-pacstrap install hook. The body is a
    # fixed string per launcher, so a default-arg lambda captures it as the builder.
    for dest, body in menu_cleanup.builders():
        plan.append({
            "builder": (lambda b=body: b),
            "dest": dest,
            "mode": _CONF,
            "owner": "root",
        })
    # PNG rasterizations of the icon at the standard sizes (so the loader has a source at
    # every size without a theme-cache rebuild). Each renders the SAME asset SVG.
    for size in launcher.ICON_PNG_SIZES:
        png_dir = launcher.ICON_PNG_DIR.format(size=size)
        plan.append({
            "builder": None,
            "render": {"asset": launcher.ICON_ASSET, "size": size},
            "dest": f"{png_dir}/{launcher.THUNAR_ICON_NAME}.png",
            "mode": _CONF,
            "owner": "root",
        })
    # The gettext .mo override catalog (relabels "Places" -> "Home Directory", the built-in
    # default-opener to "Edit with %s", and the Create Folder/Document labels -- PROMPT batch
    # items 3/7/8). A BINARY blob (bytes_builder), shipped ROOT-owned at the standard system
    # locale path for EACH locale the ISO generates, so it takes effect with the session LANG.
    # Both dests are in pacman.ISO_APP_OVERRIDES: the en_GB path is package-owned (thunar ships
    # it), so it is NoExtract'd + planted post-pacstrap -- planting it in the overlay aborts
    # pacstrap ("thunar.mo exists in filesystem"). compiler._emit_apps redirects the bytes to
    # the post-pacstrap staging dir when the dest matches an override target.
    for loc in locale.LOCALES:
        plan.append({
            "builder": None,
            "bytes_builder": locale.mo_bytes,
            "dest": locale.mo_path(loc),
            "mode": _CONF,
            "owner": "root",
        })
    # The live-sidebar sync helper (regenerates the GTK bookmarks from the ACTUAL home contents
    # at runtime, so additions show up in the sidebar -- PROMPT). Root-owned executable; wired
    # into session startup by modifications/openbox's autostart.
    plan += live_sidebar.emit_plan()
    return plan
