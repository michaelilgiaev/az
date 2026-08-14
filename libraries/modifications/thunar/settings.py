"""Thunar preferences -- the view/location-bar/side-pane/sizing settings, as the ONE
source of truth rendered into BOTH forms Thunar reads.

WHY TWO FILES FROM ONE TABLE. Thunar 4.20 MIGRATED its settings to Xfconf: on a fresh
profile it reads ~/.config/Thunar/thunarrc, migrates it into the Xfconf "thunar" channel
(~/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml), and uses Xfconf thereafter
("Your Thunar settings have been migrated to Xfconf." -- verified in the 4.20 binary). So
the RUNTIME source of truth on the real desktop (where xfconfd runs) is the channel XML,
while thunarrc is what a fresh profile migrates FROM and what Thunar falls back to when
xfconfd is absent. To be correct in BOTH cases -- and never let the two drift -- this
module keeps the settings ONCE (SETTINGS below) and renders both thunarrc() and
xfconf_channel_xml() from it. (The same belt-and-braces the repo uses for the gtk2/3/4
settings.ini trio.)

WHAT WE SET (PROMPT task 2 + task 7), every value VERIFIED against the installed Thunar
4.20 (the thunarrc CamelCase keys from the binary's GParamSpec names; the Xfconf
kebab-case property names + canonical stored values captured by round-tripping through
xfconf-query):

  * last-location-bar = ThunarLocationEntry -- the TEXT-ENTRY (editable path) location bar,
    always visible, instead of the breadcrumb buttons (ThunarLocationButtons). PROMPT: "Always
    show the path as an editable text path".
  * last-side-pane = ThunarShortcutsPane -- the SHORTCUTS pane (our sidebar), not the tree
    pane (ThunarTreePane) and not hidden.
  * last-view = ThunarDetailsView -- open in the details (list) view by default.
  * misc-enable-expandable-folders = false -- NO inline +/- disclosure triangles to expand a
    directory in place. PROMPT: "disable that (Thunar's expandable behavior)".
  * misc-always-enable-split-view = false + last-splitview-separator-position pinned -- the
    split view stays OFF by default (the toggle/menu item is also dropped, see actions.py).
  * misc-volume-management = false -- do NOT auto-manage/auto-mount removable volumes, which
    keeps the "Devices" removable clutter out of the side pane. PROMPT: "not showing mounted
    volumes".
  * misc-single-click = false -- double-click to open (single-click selects), the expected
    desktop behaviour.
  * last-menubar-visible = true -- keep the menubar (Thunar's menu is lean; the user wants
    the path box + menu, not a chromeless window).
  * last-show-hidden = false -- hidden files off by default.
  * misc-folders-first = true -- list folders before files.

THE ZOOM BUMP (PROMPT task 7, scale-relative). last-icon-view-zoom-level is bumped one step
above stock to THUNAR_ZOOM_LEVEL_150_PERCENT (stock is _100_PERCENT = 48px icons; 150% =
72px). Thunar zoom levels are RELATIVE percentage steps of the theme icon size, NOT absolute
pixels, so they COMPOSE with the global desktop scale (a scale change rescales the base icon
size and the percentage rides on top) -- exactly the "must NOT be a hardcoded absolute pixel
size" requirement. The FONT half of the +20% is a Thunar-scoped gtk.css rule in em units
(gtk_css(), also here) -- em is relative to the inherited, globally-scaled GTK font, so it
too composes with the scale. Together they make Thunar ~20% larger than stock at any scale.

Pure standard library (returns strings). compiler._emit_apps writes both files as HOME files
(owner "home"), skel-mirrored, exactly like vlc's vlcrc.
"""

from __future__ import annotations

# The live user's home (matches openbox.HOME / the airootfs /home/main tree).
HOME = "/home/main"

# Where Thunar reads its two config forms. thunarrc is the classic GKeyFile; the Xfconf
# channel XML is the migrated runtime store (the real source of truth once xfconfd has run).
THUNARRC_PATH = f"{HOME}/.config/Thunar/thunarrc"
XFCONF_THUNAR_PATH = f"{HOME}/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml"
# The Thunar-scoped GTK CSS (font half of the +20% bump). ~/.config/gtk-3.0/gtk.css is the
# per-user CSS GTK3 loads; the rules here are SELECTOR-SCOPED to Thunar's window node so no
# other GTK app is affected.
GTK_CSS_PATH = f"{HOME}/.config/gtk-3.0/gtk.css"

# The ~20% font bump, in em (relative to the inherited/globally-scaled GTK font, so it
# composes with the desktop scale rather than pinning pixels). 1.2 == +20%.
THUNAR_FONT_SCALE = 1.2

# --- The single source of truth -------------------------------------------------
# Ordered so both rendered files list settings the same way. Each entry:
#   (thunarrc_key CamelCase, xfconf_property kebab-case, kind, value)
# kind is "string" or "bool"; value is the canonical value Thunar stores (VERIFIED against
# Thunar 4.20 -- the class-name strings like ThunarLocationEntry and the percentage zoom
# enums are exactly what xfconf-query round-trips). thunarrc renders bools as TRUE/FALSE and
# strings verbatim; the Xfconf XML renders type="bool" value="true|false" / type="string".
_TRUE = True
_FALSE = False
SETTINGS: tuple[tuple[str, str, str, object], ...] = (
    ("LastView", "last-view", "string", "ThunarDetailsView"),
    ("LastLocationBar", "last-location-bar", "string", "ThunarLocationEntry"),
    ("LastSidePane", "last-side-pane", "string", "ThunarShortcutsPane"),
    ("LastIconViewZoomLevel", "last-icon-view-zoom-level", "string",
     "THUNAR_ZOOM_LEVEL_150_PERCENT"),
    ("LastDetailsViewZoomLevel", "last-details-view-zoom-level", "string",
     "THUNAR_ZOOM_LEVEL_100_PERCENT"),
    ("LastMenubarVisible", "last-menubar-visible", "bool", _TRUE),
    ("LastShowHidden", "last-show-hidden", "bool", _FALSE),
    ("MiscEnableExpandableFolders", "misc-enable-expandable-folders", "bool", _FALSE),
    ("MiscAlwaysEnableSplitView", "misc-always-enable-split-view", "bool", _FALSE),
    ("MiscSingleClick", "misc-single-click", "bool", _FALSE),
    ("MiscVolumeManagement", "misc-volume-management", "bool", _FALSE),
    ("MiscFoldersFirst", "misc-folders-first", "bool", _TRUE),
)

# --- Hidden built-in side-pane shortcuts (PROMPT task 2: remove Devices/Network clutter) --
# Thunar's shortcuts pane shows built-in "Places" (Computer/Recent/Network/Trash) and
# "Devices" (File System, removable volumes) shortcuts ON TOP of our GTK bookmarks. There is
# no group-visibility boolean; instead Thunar hides individual built-ins via two STRING-ARRAY
# properties on the shortcuts model, keyed by the built-in's URI (verified against Thunar 4.20
# by hiding them through xfconf-query and reading back the canonical values). A group with all
# its built-ins hidden disappears, so hiding these empties the Devices/Network/Computer/Recent
# clutter. We deliberately do NOT hide trash:/// -- the sidebar keeps a Trash entry (the PROMPT
# wants Trash in the sidebar; it is also provided as a resolved-path bookmark). misc-volume-
# management=false (above) already keeps removable volumes from appearing. These are a Thunar-
# 4.20 XFCONF feature (arrays), so they are shipped ONLY in the channel XML, not thunarrc.
HIDDEN_BOOKMARKS: tuple[str, ...] = (
    "recent:///",     # the "Recent" place
    "computer:///",   # the "Computer" place
    "network:///",    # the "Network" place (Browse Network)
    "trash:///",      # the built-in Trash place -- we ship our OWN resolved-path Trash bookmark
                      # (file://.../Trash/files, PROMPT task 2), so hide the trash:/// built-in
                      # to avoid a duplicate. (Our bookmark's URI differs, so it survives.)
)
HIDDEN_DEVICES: tuple[str, ...] = (
    "computer:///",   # "Computer" under Devices
    "network:///",    # "Network" under Devices (Browse Network)
)
# NOTE on the "File System" (filesystem root) device: Thunar shows a permanent "File System"
# entry under Devices that CANNOT be hidden -- it has no hide/eject affordance and is not
# governed by hidden-devices (verified against Thunar 4.20: right-clicking it offers no Hide,
# and file:/// in hidden-devices does not remove it). This is by design (it is the user's
# filesystem-access anchor, not removable clutter), so it legitimately remains. Removable
# media is kept out via MiscVolumeManagement=false above (no auto-mount), and the
# Computer/Network/Recent built-ins are hidden above -- which is the "Devices/Network clutter"
# the PROMPT asks to remove.


def _bool_thunarrc(value: bool) -> str:
    """thunarrc stores booleans as the tokens TRUE/FALSE (verified: Thunar reads/writes
    these exact tokens in the [Configuration] group)."""
    return "TRUE" if value else "FALSE"


def _bool_xfconf(value: bool) -> str:
    """Xfconf stores booleans as lowercase true/false in the channel XML."""
    return "true" if value else "false"


def thunarrc() -> str:
    """Return ~/.config/Thunar/thunarrc -- the classic GKeyFile Thunar migrates FROM on a
    fresh profile and falls back to when xfconfd is absent. One `[Configuration]` group with
    the CamelCase keys; rendered from SETTINGS so it never drifts from the Xfconf XML."""
    lines = [
        "# Az'arch Thunar settings. Generated by modifications/thunar (edit the Python, not this",
        "# file). Thunar 4.20 migrates these into the Xfconf 'thunar' channel on first run and",
        "# uses Xfconf thereafter; this file is the fresh-profile seed + the no-xfconfd fallback.",
        "# The SAME values are shipped as xfce-perchannel-xml/thunar.xml (the runtime store).",
        "[Configuration]",
    ]
    for rc_key, _prop, kind, value in SETTINGS:
        rendered = _bool_thunarrc(value) if kind == "bool" else str(value)
        lines.append(f"{rc_key}={rendered}")
    return "\n".join(lines) + "\n"


def xfconf_channel_xml() -> str:
    """Return ~/.config/xfce4/xfconf/xfce-perchannel-xml/thunar.xml -- the Xfconf channel
    store Thunar 4.20 actually reads at runtime (once xfconfd has run). The format
    (declaration `<?xml version="1.1"?>`, `<channel name="thunar" version="1.0">`,
    `<property .../>`) and the canonical values are VERIFIED against the installed Thunar
    (captured by round-tripping the settings through xfconf-query). Rendered from the SAME
    SETTINGS table as thunarrc()."""
    lines = [
        '<?xml version="1.1" encoding="UTF-8"?>',
        "",
        "<!-- Az'arch Thunar settings (Xfconf channel). Generated by modifications/thunar",
        "     (edit the Python, not this file). The runtime store Thunar 4.20 reads;",
        "     rendered from the same settings table as thunarrc. -->",
        '<channel name="thunar" version="1.0">',
    ]
    for _rc_key, prop, kind, value in SETTINGS:
        rendered = _bool_xfconf(value) if kind == "bool" else str(value)
        lines.append(
            f'  <property name="{prop}" type="{kind}" value="{rendered}"/>'
        )
    # The two string-array properties that hide the built-in Places/Devices/Network clutter.
    for prop, uris in (("hidden-bookmarks", HIDDEN_BOOKMARKS),
                       ("hidden-devices", HIDDEN_DEVICES)):
        lines.append(f'  <property name="{prop}" type="array">')
        for uri in uris:
            lines.append(f'    <value type="string" value="{uri}"/>')
        lines.append("  </property>")
    lines.append("</channel>")
    return "\n".join(lines) + "\n"


def gtk_css() -> str:
    """Return ~/.config/gtk-3.0/gtk.css -- the FONT half of the Thunar +20% bump (PROMPT
    task 7), SELECTOR-SCOPED to Thunar's window so no other GTK app is touched.

    The selector `window.thunar-window` targets Thunar's top-level window (its CSS node name
    is `thunar-window`, verified in the 4.20 binary); the descendant selectors cover the file
    area (`.standard-view`) and the sidebar (`.sidebar`/`.shortcuts-pane`). The size is set in
    EM (THUNAR_FONT_SCALE = 1.2 -> +20%), which is RELATIVE to the inherited GTK font -- so
    when the global desktop scale changes the inherited size, this rides on top of it and
    Thunar stays ~20% larger at ANY scale (never an absolute pixel size). GTK3 loads this
    file for every app, but only Thunar windows match the selector."""
    pct = f"{THUNAR_FONT_SCALE:g}em"
    return f"""\
/* Az'arch Thunar font bump (~20 percent). Generated by modifications/thunar (edit the Python, not
   this file). SCOPED to Thunar's window node so no other GTK app is affected. The size is in
   em -- relative to the inherited, globally-scaled GTK font -- so it COMPOSES with the desktop
   scale instead of pinning pixels (PROMPT task 7). */
window.thunar-window,
window.thunar-window .standard-view,
window.thunar-window .standard-view .view,
window.thunar-window .sidebar,
window.thunar-window .shortcuts-pane {{
    font-size: {pct};
}}
"""
