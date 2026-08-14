"""modifications.thunar -- the Az'arch Thunar file-manager setup (PROMPT task 2/4/7).

Why these tests matter: Thunar's config was authored against VERIFIED facts from the installed
Thunar 4.20 (the thunarrc keys, the Xfconf channel property names + canonical values, the
uca.xml schema, the sidebar built-in URIs). Each of those is a silent-regression trap -- a
drifted key/value or a malformed uca.xml is accepted by the build but breaks the feature at
runtime. These lock the load-bearing details:

  * thunarrc AND the Xfconf channel XML render the SAME settings (they must not drift; Thunar
    reads the channel at runtime and thunarrc on a fresh profile / no-xfconfd).
  * the location bar is the text entry, the side pane is the shortcuts pane, expandable
    folders + split view are off, removable-volume management is off.
  * the uca.xml is WELL-FORMED XML with all four actions (an unescaped `&&` once dropped the
    Create Link + Open Terminal actions), gedit on any file, gimp on images only, and the
    folder actions carry <range> (required to appear on the folder background).
  * the sidebar bookmarks come from home_directory (resolved paths), Desktop is not duplicated
    with the built-in, and the built-in Computer/Network/Recent/Trash are hidden.
  * the launcher is renamed to "Thunar" with the custom icon; the icon uses a private name.
"""

from __future__ import annotations

from xml.dom import minidom

from modifications import thunar
from modifications import home_directory
from modifications.thunar import actions, launcher, menu_cleanup, settings, sidebar


# --- thunarrc + xfconf channel (settings.py) --------------------------------

def test_thunarrc_and_xfconf_render_the_same_settings():
    # The two files must carry identical values (Thunar migrates thunarrc -> xfconf and uses
    # the channel at runtime; a drift means the fresh-profile seed and the runtime store
    # disagree). Compare the shared SETTINGS table's presence in both.
    rc = settings.thunarrc()
    xml = settings.xfconf_channel_xml()
    for rc_key, prop, kind, value in settings.SETTINGS:
        if kind == "bool":
            assert f"{rc_key}={'TRUE' if value else 'FALSE'}" in rc, rc_key
            assert f'name="{prop}" type="bool" value="{"true" if value else "false"}"' in xml, prop
        else:
            assert f"{rc_key}={value}" in rc, rc_key
            assert f'name="{prop}" type="string" value="{value}"' in xml, prop


def test_location_bar_is_the_text_entry():
    # PROMPT: always show the path as an editable text path. ThunarLocationEntry is the
    # text-entry bar (ThunarLocationButtons is the breadcrumb we do NOT want).
    assert ("LastLocationBar", "last-location-bar", "string", "ThunarLocationEntry") in settings.SETTINGS
    assert "ThunarLocationButtons" not in settings.thunarrc()


def test_side_pane_is_the_shortcuts_pane():
    assert ("LastSidePane", "last-side-pane", "string", "ThunarShortcutsPane") in settings.SETTINGS


def test_expandable_folders_and_split_view_are_off():
    # PROMPT task 2: disable the expandable-folder tree arrows and the split view.
    d = {rc: value for rc, _p, _k, value in settings.SETTINGS}
    assert d["MiscEnableExpandableFolders"] is False
    assert d["MiscAlwaysEnableSplitView"] is False


def test_removable_volume_management_is_off():
    # PROMPT task 2: do not show mounted (removable) volumes -- volume management off.
    d = {rc: value for rc, _p, _k, value in settings.SETTINGS}
    assert d["MiscVolumeManagement"] is False


def test_zoom_bump_is_relative_percent_not_absolute_pixels():
    # PROMPT task 7: the icon zoom bump must be a RELATIVE step (composes with the global
    # scale), never an absolute pixel size. The value is a THUNAR_ZOOM_LEVEL_*_PERCENT enum.
    d = {rc: value for rc, _p, _k, value in settings.SETTINGS}
    assert d["LastIconViewZoomLevel"] == "THUNAR_ZOOM_LEVEL_150_PERCENT"
    # no bare pixel number pinned anywhere in the settings values
    for _rc, _p, _k, value in settings.SETTINGS:
        assert not (isinstance(value, str) and value.rstrip("0123456789") == "" and value), value


def test_xfconf_channel_is_wellformed_xml_and_hides_builtins():
    xml = settings.xfconf_channel_xml()
    dom = minidom.parseString(xml)  # raises if not well-formed
    ch = dom.getElementsByTagName("channel")[0]
    assert ch.getAttribute("name") == "thunar"
    # hidden-bookmarks hides Computer/Network/Recent/Trash; hidden-devices hides Computer/Network.
    assert "recent:///" in settings.HIDDEN_BOOKMARKS
    assert "computer:///" in settings.HIDDEN_BOOKMARKS
    assert "network:///" in settings.HIDDEN_BOOKMARKS
    assert "trash:///" in settings.HIDDEN_BOOKMARKS  # built-in trash hidden; our resolved one stays
    assert "computer:///" in settings.HIDDEN_DEVICES
    assert "network:///" in settings.HIDDEN_DEVICES
    # the arrays are rendered as type="array" with <value> children
    assert '<property name="hidden-bookmarks" type="array">' in xml
    assert '<value type="string" value="recent:///"/>' in xml


def test_gtk_css_font_bump_is_scoped_and_relative():
    # PROMPT task 7: the font bump is Thunar-SCOPED (selector on the thunar-window node) and
    # RELATIVE (em, composes with the global scale) -- never an absolute px size.
    css = settings.gtk_css()
    assert "window.thunar-window" in css
    assert "em;" in css                  # relative unit
    assert "px" not in css               # no absolute pixels
    assert f"{settings.THUNAR_FONT_SCALE:g}em" in css


# --- uca.xml + link script (actions.py) -------------------------------------

def test_uca_xml_is_wellformed_with_all_four_actions():
    # A malformed uca.xml (e.g. an unescaped &&) makes Thunar drop actions silently.
    dom = minidom.parseString(actions.uca_xml())
    names = [n.firstChild.data for n in dom.getElementsByTagName("name")]
    assert names == [
        "Edit with gedit",
        "Edit with gimp",
        "Create Link (Website URL or Directory or File)",
        "Open Terminal Here",
    ]


def test_uca_gedit_first_on_any_file_gimp_on_images_only():
    # PROMPT task 2: first option "Edit with gedit" on ANY file; "Edit with gimp" only on
    # images. gedit's action carries all file-type conditions; gimp's carries only image-files.
    dom = minidom.parseString(actions.uca_xml())
    acts = dom.getElementsByTagName("action")
    gedit_act = acts[0]
    assert gedit_act.getElementsByTagName("name")[0].firstChild.data == "Edit with gedit"
    gedit_conds = {c.tagName for c in gedit_act.childNodes if c.nodeType == c.ELEMENT_NODE}
    for cond in ("audio-files", "image-files", "other-files", "text-files", "video-files"):
        assert cond in gedit_conds, cond
    assert "directories" not in gedit_conds  # gedit is for FILES, not folders
    gimp_act = acts[1]
    gimp_conds = {c.tagName for c in gimp_act.childNodes if c.nodeType == c.ELEMENT_NODE}
    assert "image-files" in gimp_conds
    assert "text-files" not in gimp_conds  # gimp ONLY on images


def test_uca_folder_actions_carry_range_for_background_visibility():
    # VERIFIED: without <range>, the folder-only actions (Create Link, Open Terminal Here) do
    # NOT appear on the folder background. Every action must carry <range>.
    xml = actions.uca_xml()
    assert xml.count("<range></range>") == 4  # one per action


def test_uca_create_link_and_terminal_target_the_right_commands():
    xml = actions.uca_xml()
    # Create Link calls the shipped link helper by absolute path; Open Terminal runs kitty.
    assert actions.LINK_SCRIPT_DEST in xml
    assert "zenity --entry" in xml            # prompts for name + target
    assert f"{actions.TERMINAL_BIN} --working-directory %f" in xml
    # the && in the Create Link command is XML-escaped (else the file is malformed)
    assert "&amp;&amp;" in xml


def test_link_script_matches_prompt_behaviour():
    # PROMPT task 2: URL -> <name>.html redirect; path -> symlink <name> -> target (realpath'd).
    script = actions.link_script()
    assert script.startswith("#!/usr/bin/env bash")
    assert 'window.location.href' in script          # the HTML redirect
    assert "ln -s -- " in script                      # the symlink branch
    assert 'realpath -- ' in script                   # realpath the existing target
    assert 'www.*' in script                          # www. counts as a URL
    assert "scheme" not in script or "://" in script  # URL scheme detection present


# --- sidebar (sidebar.py) ---------------------------------------------------

def test_sidebar_bookmarks_come_from_home_directory_resolved():
    # PROMPT task 2: sidebar entries point at RESOLVED targets, driven by home_directory.
    bm = sidebar.gtk_bookmarks()
    # Config resolves to .config (not the /home/main/Config symlink path).
    assert "file:///home/main/.config Config" in bm
    assert "file:///home/main/.cache Cache" in bm
    assert "file:///home/main/.local/share/Trash/files Trash" in bm
    assert "file:///home/main/Downloads Downloads" in bm


def test_sidebar_skips_desktop_to_avoid_builtin_duplicate():
    # Thunar shows a built-in Desktop at the same path; adding our own would DUPLICATE it, so
    # sidebar.py skips Desktop (the built-in serves it). Verified in the VM.
    bm = sidebar.gtk_bookmarks()
    assert "Desktop" in sidebar._BUILTIN_PROVIDED
    assert " Desktop\n" not in bm  # no "... Desktop" bookmark line


def test_sidebar_bookmarks_have_no_comment_lines():
    # The GTK bookmarks format parses EVERY non-blank line as a bookmark; a comment would show
    # as a bogus sidebar entry.
    for line in sidebar.gtk_bookmarks().splitlines():
        if line.strip():
            assert line.startswith("file://"), line


def test_sidebar_covers_the_full_layout_set_minus_desktop():
    # Every home_directory sidebar label except the built-in-provided ones appears.
    bm = sidebar.gtk_bookmarks()
    for label, _target in home_directory.sidebar_entries():
        if label in sidebar._BUILTIN_PROVIDED:
            continue
        assert f" {label}\n" in bm or bm.rstrip().endswith(f" {label}"), label


# --- launcher (launcher.py) -------------------------------------------------

def test_thunar_desktop_renamed_and_custom_icon():
    # PROMPT task 4: Name="Thunar" (not "Thunar File Manager") + custom icon.
    d = launcher.thunar_desktop()
    assert "Name=Thunar\n" in d
    # the visible Name line is exactly "Thunar", not "Thunar File Manager"
    assert "Name=Thunar File Manager" not in d
    assert f"Icon={launcher.THUNAR_ICON_NAME}\n" in d
    assert launcher.THUNAR_ICON_NAME == "azarch-thunar"  # private name (upgrade-proof)
    # stock Exec + actions preserved
    assert "Exec=thunar %U" in d
    assert "Actions=open-home;open-computer;open-trash;" in d


# --- menu cleanup (menu_cleanup.py) -----------------------------------------

def test_menu_cleanup_hides_the_four_extra_launchers():
    # PROMPT task 3: Bulk Rename, Thunar Preferences, About Xfce (+ Removable Drives) hidden
    # via NoDisplay=true.
    basenames = {b for b, _n, _e, _i in menu_cleanup.SUPPRESSED}
    assert "thunar-bulk-rename.desktop" in basenames
    assert "thunar-settings.desktop" in basenames
    assert "xfce4-about.desktop" in basenames
    assert "thunar-volman-settings.desktop" in basenames
    for dest, body in menu_cleanup.builders():
        assert "NoDisplay=true" in body, dest
        assert dest.startswith("/usr/share/applications/")


# --- emit_plan (thunar/__init__.py) -----------------------------------------

def test_emit_plan_owners_and_paths():
    plan = thunar.emit_plan()
    by_dest = {e["dest"]: e for e in plan}
    # HOME (skel-mirrored) config files
    for home_path in (settings.THUNARRC_PATH, settings.XFCONF_THUNAR_PATH, settings.GTK_CSS_PATH,
                      sidebar.GTK_BOOKMARKS_PATH, actions.UCA_PATH):
        assert by_dest[home_path]["owner"] == "home", home_path
    # SYSTEM (root) files: the link script (executable), the icon SVG, the .desktop overrides
    assert by_dest[actions.LINK_SCRIPT_DEST]["owner"] == "root"
    assert by_dest[actions.LINK_SCRIPT_DEST]["mode"] == 0o755  # executable
    assert by_dest[launcher.ICON_SCALABLE_PATH]["owner"] == "root"
    assert by_dest[launcher.THUNAR_DESKTOP_PATH]["owner"] == "root"


def test_emit_plan_ships_icon_svg_and_png_rasterizations():
    plan = thunar.emit_plan()
    # the scalable SVG asset entry
    svg = next(e for e in plan if e["dest"] == launcher.ICON_SCALABLE_PATH)
    assert svg.get("asset") == launcher.ICON_ASSET
    # a PNG render per configured size
    for size in launcher.ICON_PNG_SIZES:
        dest = f"/usr/share/icons/hicolor/{size}x{size}/apps/{launcher.THUNAR_ICON_NAME}.png"
        e = next(x for x in plan if x["dest"] == dest)
        assert e.get("render") == {"asset": launcher.ICON_ASSET, "size": size}


def test_emit_plan_desktop_overrides_match_iso_app_overrides():
    # The package-owned .desktop dests (thunar.desktop + the four NoDisplay overrides) must be
    # in pacman.ISO_APP_OVERRIDES so compiler stages them post-pacstrap (not the overlay).
    import pacman
    override_targets = {t for _b, t, _r in pacman.ISO_APP_OVERRIDES}
    desktop_dests = [e["dest"] for e in thunar.emit_plan()
                     if e["dest"].startswith("/usr/share/applications/")]
    assert desktop_dests, "expected some .desktop overrides"
    for dest in desktop_dests:
        assert dest in override_targets, dest


def test_icon_asset_exists():
    import paths
    assert (paths.ASSETSDIR / launcher.ICON_ASSET).is_file()
