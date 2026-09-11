"""packages.file_manager -- the Azzio File Manager (file-manager-based) setup (PROMPT task 2/4/7).

Why these tests matter: the file manager's config was authored against VERIFIED facts from the
installed file manager 4.20 (the thunarrc keys, the Xfconf channel property names + canonical
values, the uca.xml schema, the sidebar built-in URIs). Each of those is a silent-regression
trap -- a drifted key/value or a malformed uca.xml is accepted by the build but breaks the
feature at runtime. These lock the load-bearing details:

  * thunarrc AND the Xfconf channel XML render the SAME settings (they must not drift; the file
    manager reads the channel at runtime and thunarrc on a fresh profile / no-xfconfd).
  * the location bar is the text entry, the side pane is the shortcuts pane, expandable
    folders + split view are off, removable-volume management is off.
  * the uca.xml is WELL-FORMED XML with all four actions (an unescaped `&&` once dropped the
    Create Link + Open Terminal actions), gedit on any file, gimp on images only, and the
    folder actions carry <range> (required to appear on the folder background).
  * the sidebar bookmarks come from home_directory (resolved paths), Desktop is not duplicated
    with the built-in, and the built-in Computer/Network/Recent/Trash are hidden.
  * the launcher is renamed to "Azzio File Manager" with the custom icon; the icon uses a
    private name (the .desktop id and the binary stay `thunar`).
"""

from __future__ import annotations

from xml.dom import minidom

from packages import file_manager as fm
from packages.file_manager import home_directory
from packages.file_manager import actions, launcher, locale, menu_cleanup, settings, sidebar


# --- thunarrc + xfconf channel (settings.py) --------------------------------

def test_thunarrc_and_xfconf_render_the_same_settings():
    # The two files must carry identical values (the file manager migrates thunarrc -> xfconf
    # and uses the channel at runtime; a drift means the fresh-profile seed and the runtime
    # store disagree). Compare the shared SETTINGS table's presence in both.
    rc = settings.file_manager_rc()
    xml = settings.xfconf_channel_xml()
    for rc_key, prop, kind, value in settings.SETTINGS:
        if kind == "bool":
            assert f"{rc_key}={'TRUE' if value else 'FALSE'}" in rc, rc_key
            assert f'name="{prop}" type="bool" value="{"true" if value else "false"}"' in xml, prop
        else:
            # string OR uint (misc-max-number-of-templates): thunarrc renders the value
            # verbatim; the xfconf XML carries the kind as the type= attribute.
            assert f"{rc_key}={value}" in rc, rc_key
            assert f'name="{prop}" type="{kind}" value="{value}"' in xml, prop


def test_location_bar_is_the_text_entry():
    # PROMPT: always show the path as an editable text path. ThunarLocationEntry is the
    # text-entry bar (ThunarLocationButtons is the breadcrumb we do NOT want).
    assert ("LastLocationBar", "last-location-bar", "string", "ThunarLocationEntry") in settings.SETTINGS
    assert "ThunarLocationButtons" not in settings.file_manager_rc()


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
    # PROMPT task 7: the font bump is file-manager-SCOPED (selector on the thunar-window node)
    # and RELATIVE (em, composes with the global scale) -- never an absolute px size.
    css = settings.gtk_css()
    assert "window.thunar-window" in css
    assert "em;" in css                  # relative unit
    assert "px" not in css               # no absolute pixels
    assert f"{settings.FILE_MANAGER_FONT_SCALE:g}em" in css


# --- File manager refinements batch (settings.py) ---------------------------

def test_default_view_is_icon_view():
    # PROMPT batch item 2: default view = Icon view (was ThunarDetailsView/list).
    d = {rc: value for rc, _p, _k, value in settings.SETTINGS}
    assert d["LastView"] == "ThunarIconView"
    assert "ThunarDetailsView" != d["LastView"]
    # thunarrc carries it (not the list view as the default).
    assert "LastView=ThunarIconView" in settings.file_manager_rc()


def test_devices_and_file_system_removed_via_hidden_bookmarks():
    # PROMPT batch item 1: remove the "Devices" section entirely, INCLUDING the permanent
    # "File System" row. VERIFIED against thunar-shortcuts-model.c: File System has the URI
    # "file:///" and is hidden via hidden-bookmarks (NOT hidden-devices); with it hidden and no
    # removable volumes, the whole Devices heading auto-hides.
    assert "file:///" in settings.HIDDEN_BOOKMARKS
    xml = settings.xfconf_channel_xml()
    assert '<value type="string" value="file:///"/>' in xml


def test_main_user_home_row_is_shown_at_the_top_not_hidden():
    # PROMPT: "add the user to the top of the sidebar ... simply name it 'main'." The user row is
    # the file manager's BUILT-IN Home place (group PLACES_DEFAULT, sort_id 0, displayed as the
    # home basename "main"), which already sits at the very top of Places. So its URI
    # (file:///home/main) must NOT be hidden -- un-hiding it IS how "main" appears at the top.
    assert f"file://{settings.HOME}" not in settings.HIDDEN_BOOKMARKS
    assert settings.HOME.rsplit("/", 1)[-1] == "main"     # the built-in Home displays as "main"
    # It is the built-in place, NOT a GTK bookmark: no "main"/"Home Directory" bookmark line, and
    # no leftover ".home-directory" URI anywhere.
    bm = sidebar.gtk_bookmarks()
    assert not any(ln.endswith(" main") for ln in bm.splitlines())
    assert not any(ln.endswith(" Home Directory") for ln in bm.splitlines())
    assert ".home-directory" not in bm
    # the old replacement-bookmark constants/label are gone from the sidebar module.
    assert not hasattr(sidebar, "HOME_BOOKMARK_LABEL")
    assert not hasattr(sidebar, "HOME_BOOKMARK_URI")


def test_bookmarks_menu_and_ctrl_d_removed_from_vendored_source():
    # PROMPT: remove "Bookmarks" (also "CTRL+D"). The side pane is driven SOLELY by the Azzio-
    # generated ~/.config/gtk-3.0/bookmarks (the hardcoded home scan), so the user-facing Bookmarks
    # feature is excised from the vendored fork:
    #   * the "_Bookmarks" top-level menu is no longer created (neither in the menubar nor the
    #     toolbar "hamburger" menu) -- both create_menu(... BOOKMARKS_MENU ...) calls are gone,
    #   * CTRL+D ("<Primary>D") is unbound from the "Add Bookmark" (sendto-shortcuts) action,
    #   * the "Send To -> Side Pane (Add Bookmark)" entry is dropped from the Send To submenu.
    win_c = (fm.SOURCE_DIR / "thunar" / "thunar-window.c").read_text()
    am_c = (fm.SOURCE_DIR / "thunar" / "thunar-action-manager.c").read_text()
    # The _Bookmarks menu is never built (the only two create-menu call sites are removed; the
    # bare action-entry row and internal loader may remain, but nothing surfaces them).
    assert "G_CALLBACK (thunar_window_update_bookmarks_menu), window->menubar)" not in win_c
    assert "G_CALLBACK (thunar_window_update_bookmarks_menu), menu)" not in win_c
    # CTRL+D is unbound from Add Bookmark: the sendto-shortcuts row no longer carries "<Primary>D".
    add_bookmark_line = next(
        ln for ln in am_c.splitlines() if "ThunarShortcutsPane/sendto-shortcuts" in ln
    )
    assert "<Primary>D" not in add_bookmark_line
    # The "Send To -> Side Pane (Add Bookmark)" menu item is gone from the Send To submenu.
    assert "Side Pane (Add Bookmark)" not in am_c


def test_go_menu_removed_from_topbar_and_its_accelerators_disabled():
    # PROMPT: remove the "Go" option from the TOPBAR, and within it disable Alt+Up, Alt+Home and
    # Ctrl+L -- while KEEPING "/" (opens the location entry) and Ctrl+F (search). The Go menu and
    # its accelerators are baked into the vendored fork's thunar-window.c:
    #   * the Go menu is dropped from the MENUBAR only -- the create_menu(... GO_MENU ...,
    #     window->menubar) call is gone; the window/hamburger-menu Go submenu stays, so the
    #     actions remain reachable without a keyboard shortcut,
    #   * open-parent (<Alt>Up), open-home (<Alt>Home) and open-location (<Primary>l) have their
    #     accelerator strings blanked in the action-entry table,
    #   * <Alt>d (open-location-alt) and <Primary>f (search) are deliberately LEFT intact, and
    #     "/" opens the location entry via a separate GTK type-ahead path (thunar-standard-view.c),
    #     not via any accelerator, so it is unaffected.
    win_c = (fm.SOURCE_DIR / "thunar" / "thunar-window.c").read_text()
    sv_c = (fm.SOURCE_DIR / "thunar" / "thunar-standard-view.c").read_text()

    # (1) The Go menu is no longer added to the TOPBAR menubar...
    assert "G_CALLBACK (thunar_window_update_go_menu), window->menubar)" not in win_c
    # ...but the window/hamburger-menu Go submenu is KEPT (still created into that popup `menu`),
    # so the navigation actions stay available from the menu even without their shortcuts.
    assert "G_CALLBACK (thunar_window_update_go_menu), menu)" in win_c

    # (2) The three named accelerators are blanked (accel string ""). Assert per action row so a
    # future re-add of the key is caught precisely.
    def _entry_line(action_path: str) -> str:
        # The action-entry row is the one defining this "<Actions>/..." path (registered with a
        # trailing quote+comma so a longer sibling path like "open-location-alt" is not matched).
        return next(ln for ln in win_c.splitlines() if f'"{action_path}",' in ln)

    for action_path, dead_accel in (
        ("<Actions>/ThunarWindow/open-parent", "<Alt>Up"),
        ("<Actions>/ThunarWindow/open-home", "<Alt>Home"),
        ("<Actions>/ThunarWindow/open-location", "<Primary>l"),
    ):
        line = _entry_line(action_path)
        assert dead_accel not in line, f"{action_path} still binds {dead_accel}"

    # (3) The KEPT bindings are still present: <Alt>d (alt location opener) and <Primary>f (search).
    assert '"<Actions>/ThunarWindow/open-location-alt",' in win_c
    assert "<Alt>d" in _entry_line("<Actions>/ThunarWindow/open-location-alt")
    assert "<Primary>f" in _entry_line("<Actions>/ThunarWindow/search")

    # (4) "/" still opens the location entry -- it is handled directly in the standard view
    # (GDK_KEY_slash -> start-open-location), NOT by the removed <Primary>l accelerator.
    assert "GDK_KEY_slash" in sv_c
    assert "start-open-location" in sv_c


def test_view_menu_removed_from_topbar_and_its_accelerators_disabled():
    # PROMPT: same treatment as "Go" -- remove the "View" option from the TOPBAR, and disable
    # Ctrl+R, F3, Ctrl+B, Ctrl+E, Ctrl+M while keeping their menu items/defaults permanent. Keep
    # Ctrl+H, Ctrl++, Ctrl+-, Ctrl+0, Ctrl+1, Ctrl+2, Ctrl+3. All baked into thunar-window.c:
    #   * the View menu is dropped from the MENUBAR only -- the create_menu(... VIEW_MENU ...,
    #     window->menubar) call is gone; the window/hamburger-menu View submenu stays (created into
    #     the popup `menu`), so the actions + their menu items remain reachable without a shortcut,
    #   * reload (<Primary>r), toggle-split-view (F3), view-side-pane-shortcuts (<Primary>b),
    #     view-side-pane-tree (<Primary>e) and view-menubar (<Primary>m) have their accelerator
    #     strings blanked in the action-entry table (the callbacks/menu items are untouched, so the
    #     defaults still work by click; F5 still reloads via the reload-alt row),
    #   * the KEPT keys -- <Primary>h (show hidden), <Primary>plus/minus/0 (zoom) and
    #     <Primary>1/2/3 (view-as) -- are asserted still bound so a future edit can't drop them.
    win_c = (fm.SOURCE_DIR / "thunar" / "thunar-window.c").read_text()

    # (1) The View menu is no longer added to the TOPBAR menubar...
    assert "G_CALLBACK (thunar_window_update_view_menu), window->menubar)" not in win_c
    # ...but the window/hamburger-menu View submenu is KEPT (still created into that popup `menu`).
    assert "G_CALLBACK (thunar_window_update_view_menu), menu)" in win_c

    def _entry_line(action_path: str) -> str:
        # The action-entry row is the one defining this "<Actions>/..." path (registered with a
        # trailing quote+comma so a longer sibling path is not matched).
        return next(ln for ln in win_c.splitlines() if f'"{action_path}",' in ln)

    # (2) The five named accelerators are blanked (accel string ""). Assert per action row so a
    # future re-add of the key is caught precisely.
    for action_path, dead_accel in (
        ("<Actions>/ThunarWindow/reload", "<Primary>r"),
        ("<Actions>/ThunarWindow/toggle-split-view", "F3"),
        ("<Actions>/ThunarWindow/view-side-pane-shortcuts", "<Primary>b"),
        ("<Actions>/ThunarWindow/view-side-pane-tree", "<Primary>e"),
        ("<Actions>/ThunarWindow/view-menubar", "<Primary>m"),
    ):
        line = _entry_line(action_path)
        assert dead_accel not in line, f"{action_path} still binds {dead_accel}"

    # (3) The KEPT bindings are still present on their own rows.
    for action_path, live_accel in (
        ("<Actions>/ThunarWindow/show-hidden", "<Primary>h"),
        ("<Actions>/ThunarWindow/zoom-in", "<Primary>plus"),
        ("<Actions>/ThunarWindow/zoom-out", "<Primary>minus"),
        ("<Actions>/ThunarWindow/zoom-reset", "<Primary>0"),
        ("<Actions>/ThunarWindow/view-as-icons", "<Primary>1"),
        ("<Actions>/ThunarWindow/view-as-detailed-list", "<Primary>2"),
        ("<Actions>/ThunarWindow/view-as-compact-list", "<Primary>3"),
    ):
        assert live_accel in _entry_line(action_path), f"{action_path} lost {live_accel}"

    # (4) F5 still reloads even though Ctrl+R is gone (the reload-alt-1 row keeps "F5").
    assert "F5" in _entry_line("<Actions>/ThunarWindow/reload-alt-1")


def test_edit_menu_removed_from_topbar_and_its_accelerators_disabled():
    # PROMPT: same treatment as "Go"/"View" -- remove the "Edit" option from the TOPBAR, and
    # disable Ctrl+S ("Select by Pattern...") and Shift+Ctrl+I ("Invert Selection"); the rest of
    # the Edit shortcuts are fine. Baked into the vendored fork:
    #   * the Edit menu is dropped from the MENUBAR only -- the create_menu(... EDIT_MENU ...,
    #     window->menubar) call is gone; the window/hamburger-menu Edit submenu stays (created into
    #     the popup `menu`), so the actions + their menu items remain reachable without the topbar,
    #   * select-by-pattern (<Primary>s) and invert-selection (<Primary><shift>I) have their
    #     accelerator strings blanked in thunar-standard-view.c's action-entry table (the callbacks/
    #     menu items are untouched, so both still work by click from the Edit submenu),
    #   * the KEPT Edit keys -- undo/redo (<Primary>z / <Primary><shift>z), select-all (<Primary>a),
    #     cut/copy/paste (<Primary>x/c/v) and rename (F2) -- are asserted still bound so a future
    #     edit can't silently drop them.
    win_c = (fm.SOURCE_DIR / "thunar" / "thunar-window.c").read_text()
    sv_c = (fm.SOURCE_DIR / "thunar" / "thunar-standard-view.c").read_text()
    am_c = (fm.SOURCE_DIR / "thunar" / "thunar-action-manager.c").read_text()

    # (1) The Edit menu is no longer added to the TOPBAR menubar...
    assert "G_CALLBACK (thunar_window_update_edit_menu), window->menubar)" not in win_c
    # ...but the window/hamburger-menu Edit submenu is KEPT (still created into that popup `menu`),
    # so undo/redo/cut/copy/paste/select-all stay available from the menu even without the topbar.
    assert "G_CALLBACK (thunar_window_update_edit_menu), menu)" in win_c

    def _sv_entry_line(action_path: str) -> str:
        # The standard-view action-entry row defining this "<Actions>/..." path (trailing
        # quote+comma so a longer sibling path is not matched).
        return next(ln for ln in sv_c.splitlines() if f'"{action_path}",' in ln)

    def _win_entry_line(action_path: str) -> str:
        return next(ln for ln in win_c.splitlines() if f'"{action_path}",' in ln)

    def _am_entry_line(action_path: str) -> str:
        return next(ln for ln in am_c.splitlines() if f'"{action_path}",' in ln)

    # (2) The two named accelerators are blanked (accel string ""). Assert per action row so a
    # future re-add of the key is caught precisely.
    for action_path, dead_accel in (
        ("<Actions>/ThunarStandardView/select-by-pattern", "<Primary>s"),
        ("<Actions>/ThunarStandardView/invert-selection", "<Primary><shift>I"),
    ):
        line = _sv_entry_line(action_path)
        assert dead_accel not in line, f"{action_path} still binds {dead_accel}"

    # (3) The KEPT Edit bindings are still present on their own rows. Undo/Redo/Preferences and
    # the Edit-menu label live on the window entries; Select All on the standard-view entries;
    # Cut/Copy/Paste and Rename on the action-manager entries.
    assert "<Primary>Z" in _win_entry_line("<Actions>/ThunarActionManager/undo")
    assert "<Primary><shift>Z" in _win_entry_line("<Actions>/ThunarActionManager/redo")
    assert "<Primary>a" in _sv_entry_line("<Actions>/ThunarStandardView/select-all-files")
    assert "<Primary>X" in _am_entry_line("<Actions>/ThunarActionManager/cut")
    assert "<Primary>C" in _am_entry_line("<Actions>/ThunarActionManager/copy")
    assert "<Primary>V" in _am_entry_line("<Actions>/ThunarActionManager/paste")
    assert "F2" in _am_entry_line("<Actions>/ThunarStandardView/rename")


def test_show_hidden_files_added_to_right_click_menu():
    # PROMPT: add "Show Hidden Files" to the menu that opens with the right mouse click. The
    # empty-space context menu is built in thunar_standard_view_context_menu (thunar-standard-view.c);
    # it now appends the window's SHOW_HIDDEN toggle (reflecting the current per-view state) after
    # the sort/arrange items. Only on the empty-space branch -- the file-selection menu is for file
    # operations, not global view toggles.
    sv_c = (fm.SOURCE_DIR / "thunar" / "thunar-standard-view.c").read_text()
    # The toggle is appended using the window's SHOW_HIDDEN action entry + the view's current state.
    assert "THUNAR_WINDOW_ACTION_SHOW_HIDDEN" in sv_c
    assert "thunar_window_get_action_entry (THUNAR_WINDOW (window), THUNAR_WINDOW_ACTION_SHOW_HIDDEN)" in sv_c
    assert "thunar_view_get_show_hidden (THUNAR_VIEW (standard_view))" in sv_c


def test_drag_drop_cannot_add_a_persisted_sidebar_shortcut():
    # PROMPT: the home scan (~/.config/gtk-3.0/bookmarks, regenerated from /home/main) must be the
    # ONLY way a row appears on the side pane. Dropping a folder BETWEEN shortcut rows used to add
    # AND persist a user bookmark: thunar_shortcuts_view_drag_data_received (the DROP_BEFORE/AFTER
    # branch) called thunar_shortcuts_view_drop_uri_list(view, drop_file_list, path) -> ...model_add
    # -> ...save_bookmarks, writing to gtk-3.0/bookmarks. That external-add branch is neutralized in
    # the vendored fork so no drop can create a sidebar row.
    view_c = (fm.SOURCE_DIR / "thunar" / "thunar-shortcuts-view.c").read_text()
    # The add-a-shortcut CALL SITE is gone (the drop_uri_list() function may remain defined/dead;
    # what must not exist is the invocation that feeds it the dropped file list).
    assert "thunar_shortcuts_view_drop_uri_list (view, view->drop_file_list, path)" not in view_c
    # And nothing else invokes model_add from the view (the only persisting add-to-sidebar path).
    assert "thunar_shortcuts_model_add (" not in view_c
    # The drop-INTO-an-existing-folder path (copy/move/link -> thunar_dnd_perform) is UNTOUCHED --
    # that is normal file management, not adding a sidebar row.
    assert "thunar_dnd_perform (widget, file, view->drop_file_list" in view_c


def test_templates_prefs_hide_about_and_cap():
    # PROMPT batch item 8: hide the modal "About Templates" dialog + cap the submenu.
    d = {rc: value for rc, _p, _k, value in settings.SETTINGS}
    assert d["MiscShowAboutTemplates"] is False
    assert d["MiscMaxNumberOfTemplates"] == 100
    # the uint pref renders as type="uint" in the xfconf XML.
    assert '<property name="misc-max-number-of-templates" type="uint" value="100"/>' \
        in settings.xfconf_channel_xml()


def test_resolve_links_pref_present_but_documented_as_4_21_only():
    # PROMPT batch item 5: ship misc-resolve-links=true (resolves the symlink path in the
    # location bar). It is a 4.21.6+ pref (ignored by 4.20), documented honestly in the module.
    d = {rc: value for rc, _p, _k, value in settings.SETTINGS}
    assert d["MiscResolveLinks"] is True
    # the honesty note is present in the module docstring/comments (no silent faking).
    assert "4.21.6" in settings.__doc__ or "4.21.6" in open(settings.__file__).read()


# --- gettext .mo override (locale.py) ---------------------------------------

def test_mo_overrides_relabel_the_hardcoded_strings():
    # The .mo catalog relabels the hardcoded file-manager strings. The shortcuts sidebar section
    # header "Places" is renamed to "Home" (user request, step SEVEN) -- it is a hardcoded
    # gettext msgid in the thunar binary (verified via `strings /usr/bin/thunar`), so the
    # catalog is the supported lever. Assert that override plus the others.
    o = locale.OVERRIDES
    assert o["Places"] == "Home"                                 # sidebar header rename (step 7)
    assert o['_Open With "%s"'] == "_Edit with %s"               # item 7 (built-in -> "Edit with gedit")
    assert o["Create _Folder..."] == "Create New _Folder..."     # item 8 wording
    assert o["Create _Document"] == "Create New _Document..."     # item 8 wording
    # App identity: the product name "Thunar" -> "Azzio File Manager" in every gettext-wrapped
    # display string (application name, Preferences title, About blurb).
    assert o["Thunar"] == "Azzio File Manager"
    assert o["Thunar Preferences"] == "Azzio File Manager Preferences"
    assert o[
        "Thunar is a fast and easy to use file manager\n"
        "for the Xfce Desktop Environment."
    ].startswith("Azzio File Manager is a fast")


def test_window_title_is_fixed_file_manager_in_vendored_source():
    # PROMPT: the Openbox title bar must show ONLY "File Manager" -- not the folder name and not
    # the product-name suffix. The title is a BARE C literal (gettext .mo overrides cannot reach
    # it), so thunar_window_update_title in the vendored fork's thunar-window.c is patched to set a
    # fixed "File Manager" and the upstream folder-name/"%s - %s"-suffix logic is dropped.
    win_c = (fm.SOURCE_DIR / "thunar" / "thunar-window.c").read_text()
    assert 'gtk_window_set_title (GTK_WINDOW (window), "File Manager");' in win_c
    # The old folder+suffix builders are gone (either the "Azzio File Manager" relabel or the
    # original "Thunar" literal would put the folder name / product name back in the title bar).
    assert 'g_strdup_printf ("%s - %s", name, "Azzio File Manager")' not in win_c
    assert 'g_strdup_printf ("%s - %s", name, "Thunar")' not in win_c


def test_help_menu_removed_from_vendored_source():
    # PROMPT: remove the file-manager Help menu's About and Contents items, and the Help menu
    # itself. The whole Help menu lives in thunar-window.c (built programmatically, no .ui file):
    # a top-level _Help menu whose submenu is populated with _Contents + _About. Excising it means
    # the two THUNAR_WINDOW_ACTION_HELP_MENU create-menu calls (menubar + right-click menu), the
    # thunar_window_update_help_menu populator, the _Contents/_About action-entry rows and their
    # callbacks, and the three enum values are all gone from the vendored fork.
    win_c = (fm.SOURCE_DIR / "thunar" / "thunar-window.c").read_text()
    win_h = (fm.SOURCE_DIR / "thunar" / "thunar-window.h").read_text()
    # The Help menu is no longer created in either the menubar or the context menu.
    assert "THUNAR_WINDOW_ACTION_HELP_MENU" not in win_c
    assert "THUNAR_WINDOW_ACTION_HELP_MENU" not in win_h
    # About + Contents items, their populator and callbacks are gone.
    assert "thunar_window_update_help_menu" not in win_c
    assert "thunar_window_action_contents" not in win_c
    assert "thunar_window_action_about" not in win_c
    assert "THUNAR_WINDOW_ACTION_CONTENTS" not in win_c and "THUNAR_WINDOW_ACTION_CONTENTS" not in win_h
    assert "THUNAR_WINDOW_ACTION_ABOUT" not in win_c and "THUNAR_WINDOW_ACTION_ABOUT" not in win_h
    # No stray "_Help"/"_Contents"/"_About" menu labels remain from the removed action entries.
    assert 'N_ ("_Help")' not in win_c
    assert 'N_ ("_Contents")' not in win_c
    assert 'N_ ("_About")' not in win_c


def test_mo_bytes_are_a_valid_gettext_catalog(tmp_path):
    # The pure-Python .mo generator must produce a catalog real gettext can read (the file
    # manager uses C gettext). Write it and load it back with Python's gettext (same binary format).
    import gettext
    d = tmp_path / "en_US" / "LC_MESSAGES"
    d.mkdir(parents=True)
    (d / "thunar.mo").write_bytes(locale.mo_bytes())
    t = gettext.translation("thunar", localedir=str(tmp_path), languages=["en_US"])
    for msgid, msgstr in locale.OVERRIDES.items():
        assert t.gettext(msgid) == msgstr, msgid


def test_places_header_renames_to_home_under_the_default_en_IL_locale(tmp_path):
    # The concrete step-7 contract: under the DEFAULT installed locale (en_IL, seeded by
    # calamares' Asia/Jerusalem region), the catalog resolves the "Places" sidebar header msgid
    # to "Home". This mirrors the on-box `LANG=en_IL gettext -d thunar "Places"` -> "Home" check.
    import gettext
    d = tmp_path / "en_IL" / "LC_MESSAGES"
    d.mkdir(parents=True)
    (d / "thunar.mo").write_bytes(locale.mo_bytes())
    t = gettext.translation("thunar", localedir=str(tmp_path), languages=["en_IL"])
    assert t.gettext("Places") == "Home"


def test_mo_catalog_shipped_under_generated_locales_root_owned():
    # The catalog is shipped at the standard system locale path for BOTH generated locales
    # (en_US display + en_GB date), root-owned (a system catalog, not a dotfile).
    plan = fm.emit_plan()
    by_dest = {e["dest"]: e for e in plan}
    for loc in locale.LOCALES:
        p = locale.mo_path(loc)
        assert p in by_dest, p
        assert by_dest[p]["owner"] == "root"
        assert by_dest[p]["bytes_builder"] is locale.mo_bytes
    # en_IL is the DEFAULT installed locale (calamares seeds Asia/Jerusalem), so the catalog
    # MUST ship there too or the overrides never apply out of the box -- en_US/en_GB miss it.
    assert set(locale.LOCALES) == {"en_US", "en_GB", "en_IL"}


def test_gtk_menu_images_enabled_for_open_with_icons():
    # PROMPT batch item 6: "Open With" entries show app icons only if gtk-menu-images=true.
    # It lives in ~/.config/gtk-3.0/settings.ini (the openbox shipped default + the `azzio
    # theme` CLI, kept byte-for-byte in lock-step -- see test_configuration_theme). Assert the
    # openbox default (a plain module) and the BUNDLED CLI (theme.py is a bundle module that
    # needs common.py's imports, so it is exec'd from the bundle) both carry it.
    import types
    from packages import openbox
    from packages.azzio.bundle import bundle_source
    assert "gtk-menu-images=true" in openbox.gtk3_settings_ini_default()
    cli = types.ModuleType("azzio_cli")
    exec(compile(bundle_source(), "azzio_cli", "exec"), cli.__dict__)
    assert "gtk-menu-images=true" in cli.gtk3_settings_ini(True)
    assert "gtk-menu-images=true" in cli.gtk3_settings_ini(False)


# --- uca.xml + link script (actions.py) -------------------------------------

def test_uca_xml_is_wellformed_with_the_three_actions():
    # A malformed uca.xml (e.g. an unescaped &&) makes the file manager drop actions silently. After the
    # batch (item 7), "Edit with gedit" is NOT a uca action anymore -- it comes from the built-in
    # default-opener relabelled by the gettext .mo -- so the uca set is gimp + Create Link +
    # Open Terminal (in that order).
    dom = minidom.parseString(actions.uca_xml())
    names = [n.firstChild.data for n in dom.getElementsByTagName("name")]
    assert names == [
        "Edit with gimp",
        "Create Link (Website URL or Directory or File)",
        "Open Terminal Here",
    ]
    # gedit must NOT reappear as a uca action (that was the duplicate we removed).
    assert "Edit with gedit" not in names


def test_uca_gimp_on_images_only():
    # PROMPT batch item 7: keep "Edit with gimp" on IMAGES only. (gedit is handled by the .mo
    # relabel of the built-in default-opener, tested in test_configuration_file_manager_locale-style
    # asserts below, not as a uca action.)
    dom = minidom.parseString(actions.uca_xml())
    acts = dom.getElementsByTagName("action")
    gimp_act = acts[0]
    assert gimp_act.getElementsByTagName("name")[0].firstChild.data == "Edit with gimp"
    gimp_conds = {c.tagName for c in gimp_act.childNodes if c.nodeType == c.ELEMENT_NODE}
    assert "image-files" in gimp_conds
    assert "text-files" not in gimp_conds  # gimp ONLY on images
    assert "directories" not in gimp_conds


def test_uca_folder_actions_carry_range_for_background_visibility():
    # VERIFIED: without <range>, the folder-only actions (Create Link, Open Terminal Here) do
    # NOT appear on the folder background. Every action must carry <range> (now three actions).
    xml = actions.uca_xml()
    assert xml.count("<range></range>") == 3  # one per action (gimp, Create Link, Open Terminal)


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
    # The file manager shows a built-in Desktop at the same path; adding our own would DUPLICATE it,
    # so sidebar.py skips Desktop (the built-in serves it). Verified in the VM.
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

def test_file_manager_desktop_renamed_and_custom_icon():
    # The launcher is renamed to the product name "Azzio File Manager" + custom icon.
    d = launcher.file_manager_desktop()
    assert "Name=Azzio File Manager\n" in d
    # the visible Name line is the product name, not the stock "Thunar File Manager"
    assert "Name=Thunar File Manager" not in d
    assert f"Icon={launcher.FILE_MANAGER_ICON_NAME}\n" in d
    # stock Exec + actions preserved (binary + .desktop id stay `thunar`)
    assert "Exec=thunar %U" in d
    assert "Actions=open-home;open-computer;open-trash;" in d


# --- menu cleanup (menu_cleanup.py) -----------------------------------------

def test_menu_cleanup_hides_the_extra_launchers():
    # Bulk Rename, File Manager Preferences, About Xfce hidden via NoDisplay=true. The Removable
    # Drives (thunar-volman-settings) launcher is NOT hidden here: the thunar-volman plugin that
    # owned it was dropped from the manifest, so the launcher is never installed to begin with.
    basenames = {b for b, _n, _e, _i in menu_cleanup.SUPPRESSED}
    assert "thunar-bulk-rename.desktop" in basenames
    assert "thunar-settings.desktop" in basenames
    assert "xfce4-about.desktop" in basenames
    assert "thunar-volman-settings.desktop" not in basenames
    for dest, body in menu_cleanup.builders():
        assert "NoDisplay=true" in body, dest
        assert dest.startswith("/usr/share/applications/")


# --- emit_plan (file_manager/__init__.py) -----------------------------------

def test_emit_plan_owners_and_paths():
    plan = fm.emit_plan()
    by_dest = {e["dest"]: e for e in plan}
    # HOME (skel-mirrored) config files
    for home_path in (settings.FILE_MANAGER_RC_PATH, settings.XFCONF_FILE_MANAGER_PATH, settings.GTK_CSS_PATH,
                      sidebar.GTK_BOOKMARKS_PATH, actions.UCA_PATH):
        assert by_dest[home_path]["owner"] == "home", home_path
    # SYSTEM (root) files: the link script (executable), the icon SVG, the .desktop overrides
    assert by_dest[actions.LINK_SCRIPT_DEST]["owner"] == "root"
    assert by_dest[actions.LINK_SCRIPT_DEST]["mode"] == 0o755  # executable
    assert by_dest[launcher.ICON_SCALABLE_PATH]["owner"] == "root"
    assert by_dest[launcher.FILE_MANAGER_DESKTOP_PATH]["owner"] == "root"


def test_emit_plan_ships_icon_svg_and_png_rasterizations():
    plan = fm.emit_plan()
    # the scalable SVG asset entry
    svg = next(e for e in plan if e["dest"] == launcher.ICON_SCALABLE_PATH)
    assert svg.get("asset") == launcher.ICON_ASSET
    # a PNG render per configured size
    for size in launcher.ICON_PNG_SIZES:
        dest = f"/usr/share/icons/hicolor/{size}x{size}/apps/{launcher.FILE_MANAGER_ICON_NAME}.png"
        e = next(x for x in plan if x["dest"] == dest)
        assert e.get("render") == {"asset": launcher.ICON_ASSET, "size": size}


def test_emit_plan_desktop_overrides_match_iso_app_overrides():
    # The package-owned .desktop dests (thunar.desktop + the four NoDisplay overrides) must be
    # in pacman.ISO_APP_OVERRIDES so compiler stages them post-pacstrap (not the overlay).
    import pacman
    override_targets = {t for _b, t, _r in pacman.ISO_APP_OVERRIDES}
    desktop_dests = [e["dest"] for e in fm.emit_plan()
                     if e["dest"].startswith("/usr/share/applications/")]
    assert desktop_dests, "expected some .desktop overrides"
    for dest in desktop_dests:
        assert dest in override_targets, dest


def test_mo_locale_catalog_dests_are_iso_app_overrides():
    # REGRESSION (build broke with "thunar: .../en_GB/LC_MESSAGES/thunar.mo exists in
    # filesystem"): the `thunar` package OWNS the en_GB locale catalog, so every locale .mo
    # dest the file manager emits MUST be in pacman.ISO_APP_OVERRIDES -- otherwise compiler._emit_apps
    # plants it in the airootfs overlay and pacstrap's pre-extraction file-conflict check
    # aborts the whole ISO build. This pins the fix so the .mo cannot regress back into the
    # overlay path.
    import pacman
    override_targets = {t for _b, t, _r in pacman.ISO_APP_OVERRIDES}
    mo_dests = [e["dest"] for e in fm.emit_plan()
                if e["dest"].startswith("/usr/share/locale/")
                and e["dest"].endswith("/thunar.mo")]
    assert set(mo_dests) == {locale.mo_path(l) for l in locale.LOCALES}, mo_dests
    for dest in mo_dests:
        assert dest in override_targets, dest
    # And each is NoExtract'd (the property that actually prevents the pacstrap conflict).
    noextract = pacman._ISO_NOEXTRACT
    for dest in mo_dests:
        assert dest.lstrip("/") in noextract, dest


def test_icon_asset_exists():
    import paths
    assert (paths.ASSETSDIR / launcher.ICON_ASSET).is_file()
