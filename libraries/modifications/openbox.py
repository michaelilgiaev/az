"""Minimal OpenBox live-session desktop, authored as configuration-as-Python strings.

KDE Plasma was REMOVED from Az'arch (it did not fit the distribution); OpenBox is
the whole desktop now. The ISO boots to a graphical OpenBox (X11) live session
WITHOUT a display manager, Manjaro-style:

    getty@tty1 autologins `main`  ->  ~/.bash_profile runs `exec startx` on
    tty1 only  ->  ~/.xinitrc paints the wallpaper (no flash) and execs
    `openbox-session`  ->  OpenBox reads rc.xml (keybinds, no decorations fuss)
    and runs ~/.config/openbox/autostart, which sets the wallpaper, starts the
    Az'arch application-menu daemon, arms the Super key (via xcape), applies the
    keyboard layouts, and opens the Calamares installer once.

There is deliberately NO PANEL (the user's "we're not going to have a bottom panel
anymore" decision) and NO desktop right-click menu (the OpenBox root menu was removed
at the user's request; right-clicking the background does nothing). The ONLY shell
surface is the Az'arch application menu -- a borderless C/GTK3 launcher centered on
the screen, opened by the Super key. Everything the old Plasma panel carried (launcher,
power actions) lives in that menu.

Everything here is a small builder function returning the CONTENT of one file.
compiler.py emits each to its airootfs destination via emit.write_text/write_exec and
iterates PLAN (below) so the mapping (path + mode) stays declarative. The /home/main
tree is chowned 1000:998 by compiler.py after emit, exactly like the fastfetch/first-boot
payloads.

Design constraints (match archiso/OpenBox/Calamares reality):
  * No emojis, ASCII only.
  * No display manager. `openbox-session` is provided by the `openbox` package; it
    is both the window manager AND the session launcher (it sources
    ~/.config/openbox/{environment,autostart} and reads rc.xml). We ship NO menu.xml
    (the root menu is removed). See libraries/packages/packages.x86_64.
  * Calamares MUST run privileged. The live medium has passwordless-sudo `main`
    and passwordless root, so the launch stays `sudo -E calamares` via the tiny
    /usr/local/bin/azarch-install wrapper the autostart runs.
  * NO cyan/black flash: ~/.xinitrc sets the X root to the SAME wallpaper image the
    session will show (feh --bg-fill) BEFORE OpenBox starts, and the autostart's own
    `feh --bg-fill` repaints the identical pixels -- so the first and only paint is
    the wallpaper. (OpenBox draws no wallpaper itself; feh owns the root pixmap.)
  * The Super key opens the menu. OpenBox cannot bind a LONE modifier, so `xcape`
    turns a solo Super_L tap into the chord Super_L+Menu, which rc.xml binds to the
    menu launcher (Super still works as a normal modifier for every other bind).
  * The two azarch wallpapers ("years"/"decades") are shipped under
    /usr/share/wallpapers as plain images; "years" is the default feh paints. Baked
    into /etc/skel too so a Calamares-created user inherits the same session.
  * startx-from-tty replaces graphical.target: _link_services needs no
    display-manager .wants symlink or graphical.target (see compiler.py STEPS_NOTE).
"""

from __future__ import annotations

# --- Branding / assets ------------------------------------------------------
# The two wallpapers shipped on the medium. Each is a plain PNG copied under
# /usr/share/wallpapers/<id>/contents/images/<W>x<H>.png (the old KPackage layout is
# kept so the assets and compiler.py emit paths do not have to change; OpenBox/feh only
# ever reads the inner file). Both source images are 1672x941 (see assets/wallpapers/).
WALLPAPERS_SYSTEM_DIR = "/usr/share/wallpapers"
WALLPAPER_IMAGE_RES = "1672x941"          # WxH of the shipped PNGs
WALLPAPER_PACKAGES = [
    {"id": "years", "asset": "wallpapers/years.png"},
    {"id": "decades", "asset": "wallpapers/decades.png"},
]

# The DEFAULT wallpaper painted on the live/installed session -- the "years" image.
# feh needs a real FILE (it cannot take a directory), so this points at the inner png.
WALLPAPER_DEFAULT_ID = "years"
WALLPAPER_IMAGE_FILE = (
    f"{WALLPAPERS_SYSTEM_DIR}/{WALLPAPER_DEFAULT_ID}"
    f"/contents/images/{WALLPAPER_IMAGE_RES}.png"
)
# The asset copied to WALLPAPER_IMAGE_FILE is the same "years" image; compiler.py already
# writes that image, so the default resolves to a file that exists.
WALLPAPER_ASSET = "wallpapers/years.png"

def _feh_wallpaper_line() -> str:
    """A POSIX-sh snippet that paints the wallpaper with feh, honouring the per-user pointer
    `azarch wallpaper` writes: read the pointer file; if it names an existing file use it,
    otherwise fall back to the shipped "years" default. Shared by ~/.xinitrc and the OpenBox
    autostart so the pre-paint (no-flash) and the session repaint choose the SAME image, and
    both follow an `azarch wallpaper` choice. `$HOME` (the SHELL variable) is used so the
    same line works for any user that inherited the config via /etc/skel."""
    # NB: the pointer path is expressed with $HOME so it resolves per-user; the default is
    # the fixed shipped path. Guard on feh existing so a missing tool never breaks startup.
    return (
        f'_azwp="$(cat "$HOME/.config/azarch/wallpaper" 2>/dev/null)"\n'
        f'[ -n "$_azwp" ] && [ -f "$_azwp" ] || _azwp=\'{WALLPAPER_IMAGE_FILE}\'\n'
        f'[ -x /usr/bin/feh ] && feh --no-fehbg --bg-fill "$_azwp"'
    )


def wallpaper_metadata_json(wp_id: str) -> str:
    """Minimal metadata.json shipped alongside each wallpaper image.

    KDE's KPackage engine is gone, so nothing reads this at runtime anymore; it is
    kept purely so the two wallpaper directories remain self-describing (authorship /
    license) and so the compiler.py emit layout for wallpapers does not have to change.
    Name == Id so any future picker still labels them "years"/"decades"."""
    return (
        "{\n"
        '    "KPlugin": {\n'
        f'        "Id": "{wp_id}",\n'
        f'        "Name": "{wp_id}",\n'
        '        "License": "CC-BY-SA-4.0",\n'
        '        "Authors": [\n'
        '            { "Name": "Az\'arch", "Email": "" }\n'
        "        ]\n"
        "    }\n"
        "}\n"
    )


# The one privileged launch path shared by the autostart + the OpenBox root menu +
# a menu launcher.
INSTALL_WRAPPER_PATH = "/usr/local/bin/azarch-install"

# The Calamares installer window's WM_CLASS. Qt sets it to two DIFFERENTLY-CASED fields:
#   * res_NAME  = argv[0] basename = "calamares" (lowercase) -- our launcher runs
#                 `exec sudo -E calamares`, so argv[0] is "calamares".
#   * res_CLASS = QApplication::applicationName() = "Calamares" (CAPITAL C) -- Calamares
#                 hardcodes setApplicationName("Calamares") (CALAMARES_APPLICATION_NAME).
# So `xprop WM_CLASS` on the installer reads: "calamares", "Calamares".
# OpenBox's <application> matching is CASE-SENSITIVE: name= matches res_name and class=
# matches res_class, so the rule MUST use the exact case of each field (a lowercase
# class="calamares" would NOT match res_class "Calamares" and the rule would silently
# no-op). rc.xml matches BOTH fields (name + class, correct case) so it targets the
# installer window precisely, to force it to open CENTERED every time (see the
# <applications> block): Calamares remembers its last window geometry, so on a REOPEN it
# would otherwise come up wherever it last sat rather than centered.
CALAMARES_WM_NAME = "calamares"   # res_name  (argv[0] basename, lowercase)
CALAMARES_WM_CLASS = "Calamares"  # res_class (applicationName, CAPITAL C)

# The system-wide application-menu launcher for the installer. Present on the LIVE medium
# so the installer can be reopened from the Az'arch menu; REMOVED from the installed system
# by the Calamares cleanup step (calamares_shellprocess) so the installer does not appear in
# the menu post-installation (calamares itself is also try_removed). Named here so the PLAN
# entry that ships it and the shellprocess step that deletes it cannot drift.
INSTALL_MENU_DESKTOP_PATH = "/usr/share/applications/azarch-install.desktop"

# Installer launcher icon. The Az'arch icon is standardized as a SCALABLE VECTOR,
# assets/icons/azarch.svg (the "Az'" wordmark on the dark app tile), living under
# assets/icons/ alongside kitty.svg -- the single place icons live, and the same
# vector-master convention kitty follows. compiler.py copies that SVG to the hicolor
# SCALABLE apps dir (the master the icon loader rasterizes) AND rasterizes it to PNGs at
# /usr/share/pixmaps and the hicolor 256x256 apps dir, so the Desktop launcher and the
# application-menu entry (Icon=azarch-installer) resolve it regardless of which path/size
# the icon loader consults. It is ALSO the Calamares window icon (branding.desc
# productIcon, a rasterized PNG QIcon can load), so the OpenBox titlebar shows it -- see
# modifications/calamares/calamares.py.
INSTALLER_ICON_ASSET = "icons/azarch.svg"
INSTALLER_ICON_NAME = "azarch-installer"
INSTALLER_ICON_PIXMAP = f"/usr/share/pixmaps/{INSTALLER_ICON_NAME}.png"
INSTALLER_ICON_HICOLOR = (
    f"/usr/share/icons/hicolor/256x256/apps/{INSTALLER_ICON_NAME}.png"
)
# The scalable (SVG) master installed alongside the PNG rasterizations, so the icon loader
# has a vector source at any size (exactly like kitty.svg -> hicolor/scalable/apps).
INSTALLER_ICON_SCALABLE = (
    f"/usr/share/icons/hicolor/scalable/apps/{INSTALLER_ICON_NAME}.svg"
)
# Square px the PNG rasterizations are rendered at (a standard icon size; the source SVG
# is 256x256 so this is 1:1 for the raster fallbacks).
INSTALLER_ICON_PNG_SIZE = 256

# Home directory of the live user; the overlay root for HOME-relative entries.
HOME = "/home/main"
# uid:gid for the live user tree (autologin group gid 998).
HOME_OWNER = (1000, 998)

# The per-user wallpaper POINTER file `azarch wallpaper` writes (packages/azarch/wallpaper.py):
# a one-line file holding the chosen image's absolute path. The session's wallpaper step
# (_feh_wallpaper_line, used by ~/.xinitrc + the OpenBox autostart) reads it and paints that
# image if it exists, else falls back to the "years" default -- so a fresh user gets "years"
# while `azarch wallpaper --decades.png` sticks across a re-login. Under ~/.config
# (XDG_CONFIG_HOME the session exports). Kept in lock-step with the command line interface's _state_file() (a
# test pins the two). The session reads it via the $HOME shell variable (per-user via skel).
WALLPAPER_POINTER_FILE = f"{HOME}/.config/azarch/wallpaper"


# --- Application menu wiring (single source of truth in application_menu.py) --
# OUR menu is the whole shell now. It ships as a resident daemon (built once, kept
# hidden) so opening it is instant; the Super key and the OpenBox root menu both run
# the launcher (/usr/local/bin/azarch-application-menu) which signals that daemon.
from packages.application_menu import application_menu as _app_menu  # noqa: E402  (the menu is OUR package)

MENU_LAUNCHER = _app_menu.MENU_LAUNCHER_SYSTEM_PATH
MENU_DAEMON_BIN = _app_menu.MENU_DAEMON_BIN_SYSTEM_PATH


# --- 1. ~/.xinitrc ----------------------------------------------------------
def xinitrc() -> str:
    """Run by `startx` (see ~/.bash_profile). Paints the wallpaper onto the X root
    BEFORE handing the session to OpenBox so nothing flashes, then execs the OpenBox
    X11 session.

    `openbox-session` (from the openbox package) is BOTH the window manager and the
    session bootstrap: it exports the OpenBox environment, runs
    ~/.config/openbox/autostart (wallpaper repaint, menu daemon, xcape, keyboard,
    installer) and reads rc.xml. logind sets XDG_SESSION_TYPE=x11; we export
    XDG_CURRENT_DESKTOP=openbox so XDG-aware tools classify the session correctly.

    The `feh --bg-fill <wallpaper>` line makes the FIRST visible frame the wallpaper
    (feh owns the root pixmap under OpenBox); the autostart repaints the identical
    image, so there is no cyan/black flash. `--no-fehbg` keeps feh from writing a
    ~/.fehbg helper we do not use."""
    return """\
#!/bin/sh
# ~/.xinitrc -- started by `startx` (see ~/.bash_profile). Hands the X session to
# OpenBox. Keep this minimal: per-app launches live in the OpenBox autostart.

# Make sure user-dir XDG paths resolve for anything the session spawns.
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

# Classify the session for XDG-aware tools (autostart .desktop OnlyShowIn, etc.).
export XDG_CURRENT_DESKTOP=openbox
export DESKTOP_SESSION=openbox

# Paint the wallpaper onto the X root FIRST so the first visible frame is the
# wallpaper, not a solid color. The OpenBox autostart repaints the same image moments
# later (identical pixels -> no visible transition, no flash). feh is shipped in the
# manifest; it owns the root pixmap under OpenBox (OpenBox draws no wallpaper itself).
# The image honours the per-user `azarch wallpaper` pointer, falling back to "years".
""" + _feh_wallpaper_line() + """

# Replace this shell with the OpenBox X11 session; when OpenBox exits, X exits and
# control returns to the login shell (which, per bash_profile, logs out the tty).
exec openbox-session
"""


# --- 2. /home/main/.bash_profile snippet ------------------------------------
def bash_profile_startx() -> str:
    """Appended to /home/main/.bash_profile. On the FIRST virtual terminal only (and
    only when not already in X) it replaces the login shell with startx, so the
    autologin drops straight into the graphical session. On any other VT or an SSH
    login $DISPLAY is set or $(tty) != /dev/tty1, so the guard is false and you get a
    normal shell -- important for rescue/maintenance use of the ISO."""
    return """\
# ~/.bash_profile -- Az'arch live session bootstrap.
# Source .bashrc for interactive niceties if present.
[[ -f ~/.bashrc ]] && . ~/.bashrc

# Auto-start the graphical live session on tty1 login ONLY. On other VTs or over
# SSH this is skipped, leaving a plain login shell for rescue/maintenance.
# We key off the controlling terminal ($(tty) == /dev/tty1) rather than
# $XDG_VTNR: the latter only exists when pam_systemd ran and set it, so on a bare
# agetty autologin it can be empty, making `-eq 1` fail. The tty check is always
# correct for the tty1 autologin and has no such dependency.
if [[ -z $DISPLAY && "$(tty)" == /dev/tty1 ]]; then
    exec startx
fi
"""


# --- 2b. ~/.themes/Azarch/openbox-3/themerc (custom OpenBox theme) ----------
# The window titlebar ("that cyan'ish colored bar") is drawn by the OpenBox THEME, not
# rc.xml. Stock Clearlooks makes a THIN bar: its title height is font(8pt) + a tiny
# padding.height(2) top and bottom, and OpenBox sizes the min/max/close BUTTONS to that
# same label height -- so the whole bar (and its buttons) come out small.
#
# We want the bar 1.5x the stock height (an earlier round DOUBLED it, which overshot).
# We ship our own theme, "Azarch": a byte-for-byte copy of the stock Clearlooks
# openbox-3 themerc with only the size-driving fields grown, landing halfway between
# stock and the (too-tall) doubled values. It is a fresh theme dir (not an edit of the
# packaged Clearlooks) so the airootfs overlay owns it and a package update to openbox
# cannot revert it:
#   * padding.height 2 -> 7    (top+bottom padding around the label -> taller bar)
#   * padding.width  3 -> 6     (matching horizontal breathing room)
#   * window.handle.width 3->0  (REMOVE the bottom handle -- see below)
#
# THE BOTTOM "THIN WHITE BAR": OpenBox draws a HANDLE -- a full-width strip along the
# BOTTOM edge of every decorated window -- whose height is window.handle.width and whose
# fill is window.*.handle.bg.color (#eaebec, a near-white). Stock Clearlooks makes it a
# few px tall; on Az'arch it read as an "unnecessary thin white bar under a window". The
# user asked for it gone, so window.handle.width is set to 0: a zero-height handle draws
# NOTHING (the near-white strip disappears). Resizing is UNAFFECTED -- the rc.xml Bottom /
# Left / Right / corner mouse contexts resize on the window's invisible border edges
# regardless of the visible handle, and keepBorder keeps the 1px frame on maximized
# windows -- so only the cosmetic strip is removed, not the ability to drag-resize.
# The dominant half of the height comes from the larger title FONT set in rc.xml's
# <theme> (size 8 -> 12, i.e. exactly 1.5x stock). Bigger font => taller label =>
# OpenBox draws bigger buttons, so the min/max/close targets grow with the bar.
# Everything else (the #8CB0DC cyan gradient, the button gradients/hover/pressed states,
# the menu/osd styling) is copied verbatim so the look is identical, only 1.5x larger.
# Az'arch ships TWO OpenBox titlebar themes -- a LIGHT one ("Azarch", the classic
# Clearlooks-cyan look) and a DARK one ("Azarch-Dark", the default). Both are generated
# from openbox_theme_rc(dark) below: identical GEOMETRY (the ~1.5x titlebar + no bottom
# handle), only the colour palette differs. rc.xml's <theme><name> selects one, and
# `azarch theme --dark|--white` rewrites that name + `openbox --reconfigure`s. Dark is the
# out-of-the-box default (rc.xml ships <name>Azarch-Dark</name>).
OPENBOX_THEME_NAME = "Azarch"            # the LIGHT theme name (classic Clearlooks-cyan)
OPENBOX_THEME_NAME_DARK = "Azarch-Dark"  # the DARK theme name (the default)
OPENBOX_THEME_DIR = f"{HOME}/.themes/{OPENBOX_THEME_NAME}/openbox-3"
OPENBOX_THEME_THEMERC = f"{OPENBOX_THEME_DIR}/themerc"
OPENBOX_THEME_DIR_DARK = f"{HOME}/.themes/{OPENBOX_THEME_NAME_DARK}/openbox-3"
OPENBOX_THEME_THEMERC_DARK = f"{OPENBOX_THEME_DIR_DARK}/themerc"
# The theme OpenBox uses out of the box (dark is the Az'arch default). rc.xml names it.
OPENBOX_THEME_DEFAULT = OPENBOX_THEME_NAME_DARK

# The two padding fields (in px) that set the titlebar height, and the resize-handle
# width. The padding fields are pinned so a test can prove the bar was grown to ~1.5x
# stock; each lands halfway between stock Clearlooks and the earlier (overshot) doubled
# value. The handle width is 0 to REMOVE the near-white bottom handle bar entirely (the
# "thin white bar under a window" the user asked to drop); resizing is unaffected (the
# rc.xml edge/corner mouse contexts do not depend on the visible handle). Shared by BOTH
# the light and dark themes (only colours differ between them).
OPENBOX_THEME_PADDING_HEIGHT = 7    # stock Clearlooks: 2 (was 12 when doubled)
OPENBOX_THEME_PADDING_WIDTH = 6     # stock Clearlooks: 3 (was 8 when doubled)
OPENBOX_THEME_HANDLE_WIDTH = 0      # stock Clearlooks: 3 -> 0 removes the bottom bar

# The LIGHT palette: the stock Clearlooks colours (unchanged -- this is the classic cyan
# "white theme" look). The DARK palette: a coherent dark grey/blue set matching the
# Az'arch application menu (bg #2a2e32 / surface #31363b / text #eff0f1) with the same
# Breeze highlight blue (#3daee9) for the active menu item, so the whole shell reads dark.
# openbox_theme_rc(dark) picks one; every field below has a light and a dark value.
_OB_LIGHT = {
    "menu_border": "#aaaaaa",
    "menu_title_bg": "#E6E7E6", "menu_title_text": "#111111",
    "menu_items_bg": "#ffffff", "menu_items_text": "#111111",
    "menu_items_disabled": "#aaaaaa",
    "menu_active_bg": "#97b8e2", "menu_active_bg_split": "#a8c5e9",
    "menu_active_bg_to": "#91b3de", "menu_active_bg_to_split": "#80a7d6",
    "menu_active_border": "#4b6e99", "menu_active_text": "#ffffff",
    "menu_sep": "#aaaaaa",
    "handle_bg": "#eaebec", "grip_bg": "#eaebec",
    "win_border": "#585a5d",
    # active_sep is the FLAT 1px line OpenBox draws at the titlebar's BOTTOM edge (between
    # titlebar and client). The title bg is a splitvertical GRADIENT, so its bottom-edge pixel
    # is the colorTo split (#7AA1D1), NOT the top color -- the separator must match THAT end or
    # a faint hairline shows where the old cyan line was. Pinned to title_bg_to_split so it is
    # invisible (same "drop the thin bar under the window" intent as window.handle.width 0).
    "active_sep": "#7AA1D1",
    "title_bg": "#8CB0DC", "title_bg_split": "#99BAE3",
    "title_bg_to": "#86ABD9", "title_bg_to_split": "#7AA1D1",
    "active_text": "#ffffff",
    "abtn_bg": "#92B4DF", "abtn_bg_split": "#B0CAEB",
    "abtn_bg_to": "#86ABD9", "abtn_bg_to_split": "#769FD0",
    "abtn_border": "#49678B", "abtn_image": "#F4F5F6",
    "abtn_hover_bg": "#b5d3ef", "abtn_hover_bg_split": "#b5d3ef",
    "abtn_hover_bg_to": "#9cbae7", "abtn_hover_bg_to_split": "#8caede",
    "abtn_hover_border": "#4A658C", "abtn_hover_image": "#ffffff",
    "abtn_pressed_bg": "#7aa1d2",
    "inactive_sep": "#96999d",
    "ititle_bg": "#E3E2E0", "ititle_bg_split": "#EBEAE9",
    "ititle_bg_to": "#DEDCDA", "ititle_bg_to_split": "#D5D3D1",
    "inactive_text": "#70747d",
    "ibtn_bg": "#ffffff", "ibtn_bg_split": "#ffffff",
    "ibtn_bg_to": "#F9F8F8", "ibtn_bg_to_split": "#E9E7E6",
    "ibtn_border": "#928F8B", "ibtn_image": "#6D6C6C",
    "osd_border": "#aaaaaa",
    "osd_bg": "#F0EFEE", "osd_bg_split": "#f5f5f4",
    "osd_bg_to": "#EAEBEC", "osd_bg_to_split": "#E7E5E4",
    "osd_bg_border": "#ffffff",
    "osd_label_bg": "#efefef", "osd_label_border": "#9c9e9c", "osd_label_text": "#444",
    "osd_ilabel_text": "#70747d",
    "osd_hi_bg": "#9ebde5", "osd_hi_bg_to": "#749dcf",
    "osd_unhi_bg": "#BABDB6", "osd_unhi_bg_to": "#efefef",
}
_OB_DARK = {
    "menu_border": "#1b1e21",
    "menu_title_bg": "#31363b", "menu_title_text": "#eff0f1",
    "menu_items_bg": "#2a2e32", "menu_items_text": "#eff0f1",
    "menu_items_disabled": "#6a6f75",
    "menu_active_bg": "#3daee9", "menu_active_bg_split": "#4fb8ec",
    "menu_active_bg_to": "#2b9fdd", "menu_active_bg_to_split": "#2596d4",
    "menu_active_border": "#1f6c93", "menu_active_text": "#ffffff",
    "menu_sep": "#3a3f44",
    "handle_bg": "#2a2e32", "grip_bg": "#2a2e32",
    "win_border": "#15181b",
    # active_sep is the FLAT 1px line OpenBox draws at the titlebar's BOTTOM edge (between
    # titlebar and client). It USED to be #1f6c93, a stray bright-cyan bar under a focused,
    # non-maximized window (the reported visual bug). The title bg is a splitvertical GRADIENT
    # whose bottom-edge pixel is the colorTo split (#2a2e32) -- matching the top color (#3b4045)
    # would leave a faint LIGHT hairline where the cyan was, so it is pinned to the BOTTOM value
    # (#2a2e32) instead; the line then draws the same colour as the titlebar pixel above it and
    # is invisible (same "drop the thin bar under the window" intent as window.handle.width 0).
    "active_sep": "#2a2e32",
    "title_bg": "#3b4045", "title_bg_split": "#42474c",
    "title_bg_to": "#31363b", "title_bg_to_split": "#2a2e32",
    "active_text": "#ffffff",
    "abtn_bg": "#3b4045", "abtn_bg_split": "#42474c",
    "abtn_bg_to": "#31363b", "abtn_bg_to_split": "#2a2e32",
    "abtn_border": "#15181b", "abtn_image": "#eff0f1",
    "abtn_hover_bg": "#3daee9", "abtn_hover_bg_split": "#4fb8ec",
    "abtn_hover_bg_to": "#2b9fdd", "abtn_hover_bg_to_split": "#2596d4",
    "abtn_hover_border": "#1f6c93", "abtn_hover_image": "#ffffff",
    "abtn_pressed_bg": "#2596d4",
    "inactive_sep": "#15181b",
    "ititle_bg": "#2a2e32", "ititle_bg_split": "#31363b",
    "ititle_bg_to": "#26292d", "ititle_bg_to_split": "#212427",
    "inactive_text": "#9aa0a6",
    "ibtn_bg": "#2a2e32", "ibtn_bg_split": "#31363b",
    "ibtn_bg_to": "#26292d", "ibtn_bg_to_split": "#212427",
    "ibtn_border": "#15181b", "ibtn_image": "#9aa0a6",
    "osd_border": "#1b1e21",
    "osd_bg": "#2a2e32", "osd_bg_split": "#31363b",
    "osd_bg_to": "#26292d", "osd_bg_to_split": "#212427",
    "osd_bg_border": "#15181b",
    "osd_label_bg": "#31363b", "osd_label_border": "#15181b", "osd_label_text": "#eff0f1",
    "osd_ilabel_text": "#9aa0a6",
    "osd_hi_bg": "#3daee9", "osd_hi_bg_to": "#2b9fdd",
    "osd_unhi_bg": "#3a3f44", "osd_unhi_bg_to": "#31363b",
}


def openbox_theme_rc(dark: bool = True) -> str:
    """One Az'arch OpenBox themerc -- the DARK palette (default) when dark=True, else the
    LIGHT (classic Clearlooks-cyan) palette.

    Both share the stock Clearlooks GEOMETRY with the titlebar-height fields grown
    (padding.height/width) and the bottom resize handle REMOVED (window.handle.width 0, so
    the near-white bottom bar does not draw). Paired with the larger title <font> in rc.xml
    (size 12), this grows the bar to about 1.5x stock and the min/max/close buttons OpenBox
    sizes to the label. ONLY the colours differ between dark and light (see _OB_DARK /
    _OB_LIGHT); the light theme keeps the exact Clearlooks originals.

    Shipped to ~/.themes/<name>/openbox-3/themerc (a user theme search path OpenBox scans
    alongside /usr/share/themes) and mirrored into /etc/skel so the installed user inherits
    both themes. rc.xml names the dark one by default; `azarch theme` swaps between them."""
    c = _OB_DARK if dark else _OB_LIGHT
    variant = "DARK (the default)" if dark else "LIGHT (classic Clearlooks-cyan)"
    return f"""\
# Az'arch OpenBox theme -- {variant}. ~1.5x titlebar, NO bottom handle.
# Generated by modifications.openbox (edit the Python, not this file). Geometry matches stock
# Clearlooks (padding.height/width grown; window.handle.width 0 removes the bottom bar);
# only the colour palette differs between the dark and light Az'arch themes. The larger
# title FONT is set in rc.xml's <theme>.

# Fonts (halos)
*.font: shadow=n
window.active.label.text.font:shadow=y:shadowtint=30:shadowoffset=1
window.inactive.label.text.font:shadow=y:shadowtint=00:shadowoffset=0
menu.items.font:shadow=y:shadowtint=0:shadowoffset=1

# general stuff -- padding.height/width GROWN to ~1.5x the titlebar (was 2 / 3),
# handle width set to 0 to REMOVE the near-white bottom handle bar (was 3).
border.width: 1
padding.width: {OPENBOX_THEME_PADDING_WIDTH}
padding.height: {OPENBOX_THEME_PADDING_HEIGHT}
window.handle.width: {OPENBOX_THEME_HANDLE_WIDTH}
window.client.padding.width: 0
menu.overlap: 2
*.justify: center

# shadows
*.bg.highlight: 50
*.bg.shadow:    05

window.active.title.bg.highlight: 35
window.active.title.bg.shadow:    05

window.inactive.title.bg.highlight: 30
window.inactive.title.bg.shadow:    05

window.*.grip.bg.highlight: 50
window.*.grip.bg.shadow:    30

window.*.handle.bg.highlight: 50
window.*.handle.bg.shadow:    30

# Menu settings
menu.border.color: {c["menu_border"]}
menu.border.width: 1

menu.title.bg: solid flat
menu.title.bg.color: {c["menu_title_bg"]}
menu.title.text.color: {c["menu_title_text"]}

menu.items.bg: Flat Solid
menu.items.bg.color: {c["menu_items_bg"]}
menu.items.text.color: {c["menu_items_text"]}
menu.items.disabled.text.color: {c["menu_items_disabled"]}

menu.items.active.bg: Flat Gradient splitvertical border

menu.items.active.bg.color: {c["menu_active_bg"]}
menu.items.active.bg.color.splitTo: {c["menu_active_bg_split"]}

menu.items.active.bg.colorTo: {c["menu_active_bg_to"]}
menu.items.active.bg.colorTo.splitTo: {c["menu_active_bg_to_split"]}
menu.items.active.bg.border.color: {c["menu_active_border"]}
menu.items.active.text.color: {c["menu_active_text"]}

menu.separator.width: 1
menu.separator.padding.width: 0
menu.separator.padding.height: 3
menu.separator.color: {c["menu_sep"]}

# handles
window.*.handle.bg: Raised solid
window.*.handle.bg.color: {c["handle_bg"]}

window.*.grip.bg: Raised solid
window.*.grip.bg.color: {c["grip_bg"]}

# Active
window.*.border.color: {c["win_border"]}

window.active.title.separator.color: {c["active_sep"]}

*.title.bg: Raised Gradient splitvertical
*.title.bg.color: {c["title_bg"]}
*.title.bg.color.splitTo: {c["title_bg_split"]}
*.title.bg.colorTo: {c["title_bg_to"]}
*.title.bg.colorTo.splitTo: {c["title_bg_to_split"]}

window.active.label.bg: Parentrelative
window.active.label.text.color: {c["active_text"]}

window.active.button.*.bg: Flat Gradient splitvertical Border

window.active.button.*.bg.color: {c["abtn_bg"]}
window.active.button.*.bg.color.splitTo: {c["abtn_bg_split"]}
window.active.button.*.bg.colorTo: {c["abtn_bg_to"]}
window.active.button.*.bg.colorTo.splitTo: {c["abtn_bg_to_split"]}

window.active.button.*.bg.border.color: {c["abtn_border"]}
window.active.button.*.image.color: {c["abtn_image"]}

window.active.button.hover.bg.color: {c["abtn_hover_bg"]}
window.active.button.hover.bg.color.splitTo: {c["abtn_hover_bg_split"]}
window.active.button.hover.bg.colorTo: {c["abtn_hover_bg_to"]}
window.active.button.hover.bg.colorTo.splitTo: {c["abtn_hover_bg_to_split"]}
window.active.button.hover.bg.border.color: {c["abtn_hover_border"]}
window.active.button.hover.image.color: {c["abtn_hover_image"]}

window.active.button.pressed.bg: Flat solid Border
window.active.button.pressed.bg.color: {c["abtn_pressed_bg"]}

# inactive
window.inactive.title.separator.color: {c["inactive_sep"]}

window.inactive.title.bg: Raised Gradient splitvertical
window.inactive.title.bg.color: {c["ititle_bg"]}
window.inactive.title.bg.color.splitTo: {c["ititle_bg_split"]}
window.inactive.title.bg.colorTo: {c["ititle_bg_to"]}
window.inactive.title.bg.colorTo.splitTo: {c["ititle_bg_to_split"]}

window.inactive.label.bg: Parentrelative
window.inactive.label.text.color: {c["inactive_text"]}

window.inactive.button.*.bg: Flat Gradient splitVertical Border
window.inactive.button.*.bg.color: {c["ibtn_bg"]}
window.inactive.button.*.bg.color.splitto: {c["ibtn_bg_split"]}
window.inactive.button.*.bg.colorTo: {c["ibtn_bg_to"]}
window.inactive.button.*.bg.colorTo.splitto: {c["ibtn_bg_to_split"]}
window.inactive.button.*.bg.border.color: {c["ibtn_border"]}
window.inactive.button.*.image.color: {c["ibtn_image"]}

# osd
osd.border.width: 1
osd.border.color:  {c["osd_border"]}

osd.bg: flat border gradient splitvertical
osd.bg.color: {c["osd_bg"]}
osd.bg.color.splitto: {c["osd_bg_split"]}
osd.bg.colorTo: {c["osd_bg_to"]}
osd.bg.colorTo.splitto: {c["osd_bg_to_split"]}

osd.bg.border.color: {c["osd_bg_border"]}

osd.active.label.bg: parentrelative
osd.active.label.bg.color: {c["osd_label_bg"]}
osd.active.label.bg.border.color: {c["osd_label_border"]}
osd.active.label.text.color: {c["osd_label_text"]}

osd.inactive.label.bg: parentrelative
osd.inactive.label.text.color: {c["osd_ilabel_text"]}

osd.hilight.bg: flat vertical gradient
osd.hilight.bg.color: {c["osd_hi_bg"]}
osd.hilight.bg.colorTo: {c["osd_hi_bg_to"]}
osd.unhilight.bg: flat vertical gradient
osd.unhilight.bg.color: {c["osd_unhi_bg"]}
osd.unhilight.bg.colorTo: {c["osd_unhi_bg_to"]}
"""


def openbox_theme_rc_dark() -> str:
    """PLAN builder for the DARK Az'arch OpenBox theme (the default)."""
    return openbox_theme_rc(dark=True)


def openbox_theme_rc_light() -> str:
    """PLAN builder for the LIGHT Az'arch OpenBox theme (classic Clearlooks-cyan)."""
    return openbox_theme_rc(dark=False)


# --- 2c. System theme DEFAULT: the freedesktop / GTK dark standard ----------
# Az'arch ships DARK as the default, using the EXISTING freedesktop / GTK standard so any
# downloaded app that honours it is configured for free. Three layers, all defaulting dark:
#   * The GTK theme files (gtk-3.0/gtk-4.0 settings.ini + ~/.gtkrc-2.0): Adwaita-dark +
#     gtk-application-prefer-dark-theme=1. GTK2/3/4 apps read these at startup. HOME files
#     (skel-mirrored). These are the DEFAULT; `azarch theme --white` rewrites them to light.
#   * The dconf SYSTEM default for org.gnome.desktop.interface color-scheme='prefer-dark'
#     (the freedesktop "appearance" signal GTK4/libadwaita/portal apps read). Shipped as a
#     /etc/dconf keyfile + profile and compiled by `dconf update` in the customize hook
#     (post-pacstrap, where dconf exists). A per-user `gsettings set` from `azarch theme`
#     OVERRIDES this system default and persists, so a user who picks white keeps white.
# These builders MUST stay byte-for-byte in lock-step with the azarch command line interface's theme.py dark
# output (a test bundles the command line interface and asserts equality) so the shipped default and a later
# `azarch theme --dark` produce identical files.
GTK3_SETTINGS_PATH = f"{HOME}/.config/gtk-3.0/settings.ini"
GTK4_SETTINGS_PATH = f"{HOME}/.config/gtk-4.0/settings.ini"
GTKRC2_PATH = f"{HOME}/.gtkrc-2.0"
# The dconf system-default keyfile + profile + the marker the customize hook greps for.
DCONF_THEME_KEYFILE_PATH = "/etc/dconf/db/local.d/00-azarch-theme"
DCONF_PROFILE_USER_PATH = "/etc/dconf/profile/user"


def gtk3_settings_ini_default() -> str:
    """~/.config/gtk-3.0/settings.ini shipped default (DARK). Matches theme.gtk3_settings_ini(True)."""
    return (
        "# Az'arch GTK3 theme. Generated by `azarch theme` (edit via the command, not\n"
        "# this file). gtk-application-prefer-dark-theme is the GTK3 dark switch.\n"
        "[Settings]\n"
        "gtk-theme-name=Adwaita-dark\n"
        "gtk-application-prefer-dark-theme=1\n"
        "gtk-icon-theme-name=Adwaita\n"
    )


def gtk4_settings_ini_default() -> str:
    """~/.config/gtk-4.0/settings.ini shipped default (DARK). Matches theme.gtk4_settings_ini(True)."""
    return (
        "# Az'arch GTK4 theme. Generated by `azarch theme`.\n"
        "[Settings]\n"
        "gtk-theme-name=Adwaita-dark\n"
        "gtk-application-prefer-dark-theme=1\n"
        "gtk-icon-theme-name=Adwaita\n"
    )


def gtkrc2_default() -> str:
    """~/.gtkrc-2.0 shipped default (DARK). Matches theme.gtkrc2(True)."""
    return (
        "# Az'arch GTK2 theme. Generated by `azarch theme`.\n"
        'gtk-theme-name="Adwaita-dark"\n'
        'gtk-icon-theme-name="Adwaita"\n'
    )


def dconf_theme_keyfile() -> str:
    """/etc/dconf/db/local.d/00-azarch-theme -- the dconf SYSTEM default that makes the
    freedesktop color-scheme 'prefer-dark' for every user out of the box. A per-user
    `gsettings set` (what `azarch theme` runs) overrides it and persists. Compiled into the
    binary db by `dconf update` in the customize hook (post-pacstrap, dconf present)."""
    return (
        "# Az'arch dark theme -- freedesktop color-scheme system default. Compiled by\n"
        "# `dconf update`. A per-user `gsettings set` (azarch theme) overrides this.\n"
        "[org/gnome/desktop/interface]\n"
        "color-scheme='prefer-dark'\n"
        "gtk-theme='Adwaita-dark'\n"
    )


def dconf_profile_user() -> str:
    """/etc/dconf/profile/user -- the dconf profile so the `local` system db (above) backs
    the user db. Without this profile, the system default keyfile is never consulted."""
    return (
        "# Az'arch dconf profile: user db on top, the system `local` db (color-scheme\n"
        "# default) beneath it. Generated by modifications.openbox.\n"
        "user-db:user\n"
        "system-db:local\n"
    )


# --- 3. ~/.config/openbox/rc.xml --------------------------------------------
# The Super key is armed via xcape: a lone Super_L tap is turned into the chord
# Super_L+Menu (see openbox_autostart), and THIS keybind runs the menu launcher on
# that chord. OpenBox cannot bind a bare modifier itself, so this indirection is how
# "Super opens the menu" works while Super still behaves as a normal modifier for
# every other bind. The Menu keysym is bound both with W- (the xcape chord) and bare
# (belt: some keyboards' physical Menu/Apps key) so either opens the menu.
SUPER_MENU_KEYSYM = "Menu"

# The title font size (points). The dominant half of the ~1.5x titlebar: stock OpenBox
# defaults to 8pt for the window label; a 12pt label (exactly 1.5x) makes a taller bar
# AND (because OpenBox sizes the min/max/close buttons to the label height) bigger
# buttons. Set in rc.xml's <theme> <font> blocks below. Pinned so a test can prove the
# 1.5x scale (an earlier round used 16pt, which doubled the bar and overshot).
TITLE_FONT_SIZE = 12


def openbox_rc_xml() -> str:
    """OpenBox rc.xml: window-manager behaviour + keybinds for a panel-less session.

    Uses the Az'arch theme (Clearlooks with a ~1.5x titlebar, see openbox_theme_rc)
    plus a larger title font, and wires the Az'arch bits:
      * W-Menu / Menu -> run the application-menu launcher (the Super key, via xcape).
      * A small, sensible keybind set (close window, alt-tab, workspace switch, a
        terminal on W-Return) so the session is usable without a panel.
      * FULL titlebar-button mouse bindings (Iconify/Maximize/Close/Icon/...): OpenBox
        draws the min/max/close buttons from the theme's titleLayout, but they DO NOTHING
        unless rc.xml binds a click action to each button's mouse context -- the previous
        rc.xml bound only the Titlebar context, so the buttons rendered but were dead.
      * FULL window edge/corner RESIZE bindings (Top/Bottom/Left/Right + the four
        corners): same bug shape as the dead buttons -- OpenBox draws a resize border but
        dragging an edge/corner does nothing unless its context is bound. The previous
        rc.xml bound only the Frame's Alt+Right drag; now a plain edge/corner grab resizes
        the window (each side to its edge, corners in both axes), Alt+Right kept too.
      * NO desktop right/middle-click menu: the "Root" mouse context is intentionally
        EMPTY so right-clicking the background does nothing (the OpenBox root menu was
        removed per the user's request; the Super key remains the only way to the menu).
    There is NO dock/panel configuration -- the Az'arch menu is the only shell.

    Placed at ~/.config/openbox/rc.xml (and /etc/skel) so the live and installed users
    share it. OpenBox re-reads it on `openbox --reconfigure`."""
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!-- Az'arch OpenBox configuration. Panel-less: the Az'arch application menu (Super key)
     is the only shell surface, and the desktop right-click menu is disabled. Generated
     by modifications.openbox (edit the Python, not this file). -->
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <resistance>
    <strength>10</strength>
    <screen_edge_strength>20</screen_edge_strength>
  </resistance>
  <focus>
    <focusNew>yes</focusNew>
    <followMouse>no</followMouse>
    <focusLast>yes</focusLast>
    <underMouse>no</underMouse>
    <focusDelay>200</focusDelay>
    <raiseOnFocus>no</raiseOnFocus>
  </focus>
  <placement>
    <policy>Smart</policy>
    <center>yes</center>
    <monitor>Primary</monitor>
    <primaryMonitor>1</primaryMonitor>
  </placement>
  <theme>
    <!-- The Az'arch theme with a ~1.5x-height titlebar (openbox_theme_rc, shipped to
         ~/.themes/{OPENBOX_THEME_NAME} and ~/.themes/{OPENBOX_THEME_NAME_DARK}). DARK is
         the default; `azarch theme` (white / dark) rewrites this name element to
         "{OPENBOX_THEME_NAME}" or "{OPENBOX_THEME_NAME_DARK}". titleLayout NLIMC = icon,
         label, iconify, maximize, close. -->
    <name>{OPENBOX_THEME_DEFAULT}</name>
    <titleLayout>NLIMC</titleLayout>
    <keepBorder>yes</keepBorder>
    <animateIconify>yes</animateIconify>
    <!-- Larger title font (the dominant half of the ~1.5x bar): a taller label makes a
         taller titlebar, and OpenBox sizes the min/max/close buttons to the label. -->
    <font place="ActiveWindow">
      <name>sans</name>
      <size>{TITLE_FONT_SIZE}</size>
      <weight>bold</weight>
      <slant>normal</slant>
    </font>
    <font place="InactiveWindow">
      <name>sans</name>
      <size>{TITLE_FONT_SIZE}</size>
      <weight>bold</weight>
      <slant>normal</slant>
    </font>
  </theme>
  <desktops>
    <number>2</number>
    <firstdesk>1</firstdesk>
    <names>
      <name>one</name>
      <name>two</name>
    </names>
    <popupTime>0</popupTime>
  </desktops>
  <resize>
    <drawContents>yes</drawContents>
    <popupShow>Nonpixel</popupShow>
  </resize>
  <keyboard>
    <!-- The Super key: xcape emits Super_L+Menu on a lone Super tap; bind that chord
         (and the bare Menu/Apps key) to the Az'arch application-menu launcher. -->
    <keybind key="W-{SUPER_MENU_KEYSYM}">
      <action name="Execute">
        <command>{MENU_LAUNCHER}</command>
      </action>
    </keybind>
    <keybind key="{SUPER_MENU_KEYSYM}">
      <action name="Execute">
        <command>{MENU_LAUNCHER}</command>
      </action>
    </keybind>
    <!-- A terminal without the menu (kitty is the primary terminal). -->
    <keybind key="W-Return">
      <action name="Execute">
        <command>kitty</command>
      </action>
    </keybind>
    <!-- Window management basics so the session is usable panel-less. -->
    <keybind key="A-F4">
      <action name="Close"/>
    </keybind>
    <keybind key="A-Tab">
      <action name="NextWindow"/>
    </keybind>
    <keybind key="A-S-Tab">
      <action name="PreviousWindow"/>
    </keybind>
    <keybind key="W-d">
      <action name="ToggleShowDesktop"/>
    </keybind>
    <keybind key="C-A-Left">
      <action name="GoToDesktop"><to>left</to><wrap>no</wrap></action>
    </keybind>
    <keybind key="C-A-Right">
      <action name="GoToDesktop"><to>right</to><wrap>no</wrap></action>
    </keybind>
    <!-- FN media keys -> the `azarch` volume/brightness controls (7.5% steps, a centered
         cyan on-screen bar). We bind the X "XF86" media KEYSYMS the keyboard emits, NOT a
         fixed FN+F2/F3, because that physical mapping DIFFERS per machine: on the user's PC
         keyboard FN+F2/F3 emit the AUDIO keysyms (volume), while on their laptop FN+F2/F3 emit
         the BRIGHTNESS keysyms (dim/brighten). Binding the keysyms means each machine's FN keys
         "just work" without us resolving the layout. Brightness is a LAPTOP-ONLY control, so
         `azarch brightness` self-gates: on a PC (no backlight) these brightness binds harmlessly
         do nothing, exactly as intended (a desktop has no screen backlight to dim). -->
    <keybind key="XF86AudioRaiseVolume">
      <action name="Execute"><command>{AZARCH_BIN_PATH} volume up</command></action>
    </keybind>
    <keybind key="XF86AudioLowerVolume">
      <action name="Execute"><command>{AZARCH_BIN_PATH} volume down</command></action>
    </keybind>
    <keybind key="XF86AudioMute">
      <action name="Execute"><command>{AZARCH_BIN_PATH} volume mute</command></action>
    </keybind>
    <keybind key="XF86MonBrightnessUp">
      <action name="Execute"><command>{AZARCH_BIN_PATH} brightness up</command></action>
    </keybind>
    <keybind key="XF86MonBrightnessDown">
      <action name="Execute"><command>{AZARCH_BIN_PATH} brightness down</command></action>
    </keybind>
  </keyboard>
  <mouse>
    <dragThreshold>8</dragThreshold>
    <doubleClickTime>200</doubleClickTime>
    <screenEdgeWarpTime>0</screenEdgeWarpTime>
    <context name="Frame">
      <mousebind button="A-Left" action="Press"><action name="Focus"/><action name="Raise"/></mousebind>
      <mousebind button="A-Left" action="Drag"><action name="Move"/></mousebind>
      <mousebind button="A-Right" action="Drag"><action name="Resize"/></mousebind>
    </context>
    <context name="Titlebar">
      <mousebind button="Left" action="Press"><action name="Focus"/><action name="Raise"/></mousebind>
      <mousebind button="Left" action="Drag"><action name="Move"/></mousebind>
      <mousebind button="Left" action="DoubleClick"><action name="ToggleMaximize"/></mousebind>
    </context>
    <!-- Titlebar BUTTON contexts. OpenBox draws the min/max/close buttons from the
         theme's titleLayout, but a button only DOES something if its mouse context is
         bound here (the old rc.xml bound only Titlebar, so the buttons were dead). These
         are the canonical OpenBox bindings: click iconify/maximize/close to act, and the
         window icon opens the client menu. -->
    <context name="Iconify">
      <mousebind button="Left" action="Press"><action name="Focus"/><action name="Raise"/></mousebind>
      <mousebind button="Left" action="Click"><action name="Iconify"/></mousebind>
    </context>
    <context name="Maximize">
      <mousebind button="Left" action="Press"><action name="Focus"/><action name="Raise"/><action name="Unshade"/></mousebind>
      <mousebind button="Left" action="Click"><action name="ToggleMaximize"/></mousebind>
      <mousebind button="Middle" action="Click"><action name="ToggleMaximize"><direction>vertical</direction></action></mousebind>
      <mousebind button="Right" action="Click"><action name="ToggleMaximize"><direction>horizontal</direction></action></mousebind>
    </context>
    <context name="Close">
      <mousebind button="Left" action="Press"><action name="Focus"/><action name="Raise"/><action name="Unshade"/></mousebind>
      <mousebind button="Left" action="Click"><action name="Close"/></mousebind>
    </context>
    <context name="Icon">
      <mousebind button="Left" action="Press"><action name="Focus"/><action name="Raise"/><action name="Unshade"/><action name="ShowMenu"><menu>client-menu</menu></action></mousebind>
      <mousebind button="Right" action="Press"><action name="Focus"/><action name="Raise"/><action name="ShowMenu"><menu>client-menu</menu></action></mousebind>
    </context>
    <!-- Window EDGE + CORNER resize contexts. Same shape of bug as the dead buttons above:
         OpenBox draws a resize border/handle around every decorated window, but dragging an
         edge or corner does NOTHING unless that edge/corner mouse context is bound here. The
         previous rc.xml bound only the Frame's Alt+Right drag, so a plain edge/corner grab
         was dead. These are the canonical OpenBox default bindings: each side drags that one
         edge (Resize with an <edge>), each corner drags freely in both axes (Resize, no
         edge). The Alt+Right whole-window resize on Frame (above) is kept too. The keepBorder
         theme option leaves the 1px border on maximized windows so this stays reachable. -->
    <context name="Top">
      <mousebind button="Left" action="Drag"><action name="Resize"><edge>top</edge></action></mousebind>
    </context>
    <context name="Left">
      <mousebind button="Left" action="Drag"><action name="Resize"><edge>left</edge></action></mousebind>
    </context>
    <context name="Right">
      <mousebind button="Left" action="Drag"><action name="Resize"><edge>right</edge></action></mousebind>
    </context>
    <context name="Bottom">
      <mousebind button="Left" action="Drag"><action name="Resize"><edge>bottom</edge></action></mousebind>
    </context>
    <context name="TRCorner BRCorner TLCorner BLCorner">
      <mousebind button="Left" action="Press"><action name="Focus"/><action name="Raise"/><action name="Unshade"/></mousebind>
      <mousebind button="Left" action="Drag"><action name="Resize"/></mousebind>
    </context>
    <!-- Desktop right/middle click: INTENTIONALLY does nothing. The OpenBox root menu was
         removed per the user's request, so the Root context binds no ShowMenu. -->
    <context name="Root">
    </context>
    <context name="Client">
      <mousebind button="Left" action="Press"><action name="Focus"/><action name="Raise"/></mousebind>
    </context>
  </mouse>
  <applications>
    <!-- The Az'arch application menu is a borderless override-redirect Tk window; it
         manages its own placement (centered) and needs no OpenBox decorations. -->
    <application name="*azarch*menu*">
      <decor>no</decor>
    </application>
    <!-- The Calamares installer: ALWAYS open CENTERED, even on a REOPEN. Calamares saves
         its last window geometry (Qt session state), so the second time it is launched it
         comes up wherever it last sat, ignoring branding.desc's windowPlacement:center
         (which only steers the FIRST map). OpenBox's global placement (Smart/center) also
         only applies when the client does not request a position, and a window with
         remembered geometry does request one. A per-application position with force="yes"
         OVERRIDES the client's requested position on every map, so the installer is
         re-centred each time it opens. Matched on BOTH WM_CLASS fields with their exact
         case (res_name "calamares" via name=, res_class "Calamares" via class="); OpenBox
         matching is case-sensitive, so the capitalisation must be exact or the rule silently
         no-ops and the installer opens off-centre. -->
    <application name="{CALAMARES_WM_NAME}" class="{CALAMARES_WM_CLASS}">
      <position force="yes">
        <x>center</x>
        <y>center</y>
      </position>
    </application>
  </applications>
</openbox_config>
"""


# --- 4. (removed) ~/.config/openbox/menu.xml --------------------------------
# The OpenBox ROOT menu (right/middle click on the desktop) was REMOVED per the user's
# request ("remove the right click menu ... disable that menu completely"). rc.xml's
# Root mouse context is now empty (no ShowMenu), so right-clicking the desktop does
# nothing, and no menu.xml is emitted. The Az'arch application menu (Super key) remains
# the only shell surface; its launcher, installer, and power actions live there.

# --- 5. ~/.config/openbox/autostart -----------------------------------------
# Keyboard layouts for the LIVE session: US English (default) + Hebrew, Alt+Shift to
# toggle. Applied with setxkbmap in the autostart (the DE-independent equivalent of
# the old Plasma kxkbrc). Kept as constants so a test can pin them.
KEYBOARD_LAYOUTS = ["us", "il"]           # xkb codes, us first == default
KEYBOARD_TOGGLE = "grp:alt_shift_toggle"  # Alt+Shift cycles layouts


# The three autostart blocks common to BOTH the live and the installed session:
# wallpaper (feh), the Super key (xcape), and the resident menu daemon. Factored out so
# the live and installed autostarts cannot drift on the parts they share.
def _openbox_autostart_common() -> str:
    return f"""\
# 1. Wallpaper: repaint the same image ~/.xinitrc pre-painted (no flash; also covers a
#    re-login where the X root pixmap was reset). feh owns the root pixmap on OpenBox. The
#    image honours the per-user `azarch wallpaper` pointer, falling back to the "years"
#    default -- so an `azarch wallpaper --decades.png` choice survives a re-login.
{_feh_wallpaper_line()} &

# 2. Super key -> application menu. OpenBox cannot bind a lone modifier, so xcape turns
#    a solo Super_L tap into the chord Super_L+Menu, which rc.xml binds to the menu
#    launcher. Super keeps working as a normal modifier for every other bind (xcape
#    suppresses the tap whenever Super is pressed WITH another key). -t 500: a tap fires
#    the instant Super is released; the generous 500ms window means an ordinary, slightly
#    lingering press still counts as a tap instead of being silently dropped -- the old
#    200ms cap made a normal Super press "sometimes do nothing", which felt laggy/buggy.
command -v xcape >/dev/null 2>&1 && \\
    xcape -t 500 -e 'Super_L=Super_L|Menu' &

# 3. Az'arch application-menu daemon: build the menu once and keep it hidden so the
#    first Super press is instant (the C/GTK3 daemon, see application_menu/menu.c).
[ -x '{MENU_DAEMON_BIN}' ] && \\
    setsid '{MENU_DAEMON_BIN}' >/dev/null 2>&1 < /dev/null &"""


def openbox_autostart() -> str:
    """~/.config/openbox/autostart for the LIVE session -- run by openbox-session once
    the WM is up.

    Does everything the old Plasma session did via autostart/services, but for a
    panel-less OpenBox desktop: the shared wallpaper/xcape/menu-daemon block PLUS two
    LIVE-ONLY behaviours that must NOT survive onto an installed system:
      * setxkbmap us,il grp:alt_shift_toggle: the US + Hebrew layouts (Alt+Shift to
        switch), the DE-independent replacement for Plasma's kxkbrc. Live-only because
        an install picks a region keyboard (written to /etc/X11/xorg.conf.d) that this
        fixed us,il would otherwise override at every login.
      * launch the Calamares installer ONCE (Manjaro-style first-run). Live-only: an
        installed system must not re-open the installer at every login.

    So the Calamares OFFLINE install OVERWRITES this file (home + skel) with
    openbox_autostart_installed() -- which drops exactly those two lines -- via the
    modifications/calamares_shellprocess cleanup step. Each line is guarded
    (`command -v` / `[ -x ]`) so a missing tool never aborts the session. Shipped to the
    live home and /etc/skel."""
    layouts = ",".join(KEYBOARD_LAYOUTS)
    return f"""\
#!/bin/sh
# ~/.config/openbox/autostart -- Az'arch OpenBox LIVE session startup (panel-less).
# Run by openbox-session after the window manager is up. Keep every line guarded so a
# missing tool never breaks the session. The Calamares install overwrites this with the
# "installed" variant (no fixed keyboard, no installer) -- see calamares_shellprocess.py.

{_openbox_autostart_common()}

# 4. LIVE-ONLY -- keyboard layouts: US English (default) + Hebrew, Alt+Shift to toggle.
#    An install writes a region keyboard to /etc/X11/xorg.conf.d/00-keyboard.conf, so
#    this fixed us,il is stripped from the installed autostart (it would override it).
command -v setxkbmap >/dev/null 2>&1 && \\
    setxkbmap -layout '{layouts}' -option '{KEYBOARD_TOGGLE}' &

# 5. LIVE-ONLY -- Calamares installer, once, a couple seconds in (Manjaro-style
#    first-run). The wrapper elevates via passwordless sudo on the live medium. Stripped
#    from the installed autostart so an installed system never re-opens the installer.
if [ -x '{INSTALL_WRAPPER_PATH}' ]; then
    ( sleep 2; '{INSTALL_WRAPPER_PATH}' ) &
fi
"""


def openbox_autostart_installed() -> str:
    """The INSTALLED-system ~/.config/openbox/autostart: the shared wallpaper/xcape/menu-
    daemon block ONLY. The Calamares OFFLINE install overwrites the live autostart (which
    the target inherits verbatim via unpackfs) with THIS content -- dropping the two
    live-only lines (the fixed us,il setxkbmap and the first-run Calamares launch) so the
    installed system uses its chosen region keyboard and never re-opens the installer. It
    is written to BOTH /home/main and /etc/skel by the shellprocess cleanup step. Emitted
    to a staging path on the ISO (installer_autostart.sh) so the shellprocess can `cp` it
    into place inside the target chroot without needing any `$`-expansion."""
    return f"""\
#!/bin/sh
# ~/.config/openbox/autostart -- Az'arch OpenBox INSTALLED session startup (panel-less).
# Written by the Calamares install (calamares_shellprocess.py) over the live autostart:
# the shared wallpaper/xcape/menu-daemon block only -- NO fixed us,il keyboard (the
# region keyboard in /etc/X11/xorg.conf.d governs) and NO first-run installer launch.

{_openbox_autostart_common()}
"""


# Where the "installed" autostart is staged on the ISO so the Calamares shellprocess can
# copy it over the target's inherited live autostart (home + skel) inside the chroot.
INSTALLED_AUTOSTART_STAGING_PATH = "/usr/local/share/azarch/openbox-autostart-installed"


def openbox_environment() -> str:
    """~/.config/openbox/environment -- sourced by openbox-session before autostart.

    A minimal, stable place for session env vars. We re-assert XDG_CURRENT_DESKTOP
    (also set in ~/.xinitrc) so it is correct even if OpenBox is started by some other
    path than our startx, keep the XDG base dirs defined, AND bridge Qt apps onto the
    system theme.

    QT_QPA_PLATFORMTHEME=gtk3 is the SYSTEM-THEME bridge for Qt: without a KDE/Plasma
    stack (no kdeglobals, no qt6ct, no xdg-desktop-portal on this medium), Qt6/KF6 apps
    like Dolphin (the file manager) and Calamares would otherwise render with Qt's stock
    LIGHT Fusion palette regardless of the freedesktop color-scheme. The Qt `gtk3`
    platform theme plugin (libqgtk3.so, shipped with qt6-base) makes those Qt apps read
    the GTK theme instead -- so they follow the SAME Adwaita-dark/Adwaita + prefer-dark
    signal `azarch theme` sets for GTK, and switch dark<->light with the rest of the
    session. This is what makes Dolphin (and any downloaded Qt app) obey `azarch theme`."""
    return """\
# ~/.config/openbox/environment -- sourced by openbox-session before autostart.
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_CURRENT_DESKTOP=openbox
# Bridge Qt/KF6 apps (Dolphin, Calamares, any downloaded Qt app) onto the system theme:
# the Qt gtk3 platform theme makes them follow the GTK theme (Adwaita-dark/Adwaita) that
# `azarch theme` sets, so they honour dark/white like everything else. Without this Qt
# apps render light regardless of the freedesktop color-scheme (no KDE/portal stack here).
export QT_QPA_PLATFORMTHEME=gtk3
"""


# --- 6. Menu daemon usage seed (single source of truth in application_menu.py) --
def az_menu_usage_seed_json() -> str:
    """Seed launch-frequency store for OUR menu, fixing the STARTING top of the list on
    a fresh profile (the menu otherwise sorts alphabetically until the user has opened
    things). Content is owned by packages/application_menu/application_menu.py; this module just
    places it under ~/.local/share and mirrors it into /etc/skel. It stays dynamic: the
    daemon re-sorts as apps are opened."""
    return _app_menu.usage_seed_json()


# --- 7. /usr/share/applications/azarch-install.desktop ----------------------
def install_menu_desktop() -> str:
    """A launcher in the application menu so the installer can be re-opened after it is
    closed, sharing the same privileged wrapper. Lands in /usr/share/applications
    (system-wide), so it is not a per-user file and is picked up by the Az'arch menu's
    application scan."""
    return """\
[Desktop Entry]
Type=Application
Name=Az'arch Linux Installer
GenericName=System Installer
Comment=Install Az'arch Linux to disk
Exec=""" + INSTALL_WRAPPER_PATH + """
Icon=""" + INSTALLER_ICON_NAME + """
Terminal=false
Categories=System;
Keywords=install;calamares;setup;
"""


# --- 7b. ~/Desktop/azarch-install.desktop (live-session Desktop launcher) ----
def desktop_installer_launcher() -> str:
    """A double-clickable "Az'arch Linux Installer" launcher that sits ON the live
    Desktop, so the installer is one obvious icon away even after the autostart window
    is closed. Uses the same privileged wrapper and the "Az'" app icon.

    Ships EXECUTABLE (PLAN mode 0o755 + a profile.py FILE_PERMISSIONS pin) so any file
    manager that honours the exec bit runs it without a "not trusted" prompt -- archiso
    normalizes overlay modes to 0644 in the squashfs unless a path is pinned (the same
    gotcha documented for /usr/local/bin/azarch-install), so the pin is required."""
    return """\
[Desktop Entry]
Type=Application
Name=Az'arch Linux Installer
GenericName=System Installer
Comment=Install Az'arch Linux to disk
Exec=""" + INSTALL_WRAPPER_PATH + """
Icon=""" + INSTALLER_ICON_NAME + """
Terminal=false
Categories=System;
Keywords=install;calamares;setup;
"""


# --- 8. /usr/local/bin/azarch (guest-side command line interface) ------------------------------
# The `azarch` guest command line interface is its OWN Python PACKAGE now, libraries/packages/azarch/ (all
# Python -- no shell). It grew a `theme` subcommand (and more to come), so the single module
# was split into small modules (common/country_table/resolver/theme/sshd/command_line_interface). This module
# no longer AUTHORS the command line interface; it (a) asks the package to BUNDLE those modules into one
# self-contained script (bundle.bundle_source()), then (b) injects the country->locale table
# from modifications/calamares/locale (the single source of truth) between the AZARCH_CC markers,
# and ships the result to /usr/local/bin/azarch. See paths.AZARCH_COMMAND_LINE_INTERFACE_DIR and packages/azarch/.
AZARCH_BIN_PATH = "/usr/local/bin/azarch"

# The media OSD indicator (the centered cyan volume/brightness bar) is a STANDALONE tkinter
# script -- it is a separate, long-lived GUI process that `azarch volume/brightness` launches
# and feeds one JSON line, exactly like the speech-to-text REC indicator. It is NOT part of the
# bundled `azarch` script (which would drag tkinter into the fast command line interface path); it ships as its
# own file next to the C terminal user interface binary in the azarch lib dir, so the two travel together. Kept
# in lock-step with packages/azarch/media.py OSD_INDICATOR_BIN (a test pins the two).
AZARCH_OSD_SYSTEM_PATH = "/usr/local/lib/azarch/azarch-osd"

# Marker lines (in the bundled source, originally from country_table.py) bracketing the
# generated COUNTRY_TABLE literal.
_AZARCH_CC_START = "# AZARCH_CC_TABLE_START"
_AZARCH_CC_END = "# AZARCH_CC_TABLE_END"


def azarch_command_line_interface() -> str:
    """The `azarch` guest command line interface (Python), BUNDLED from the libraries/packages/azarch/ package
    into one self-contained script and shipped to /usr/local/bin/azarch. The COUNTRY_TABLE
    dict literal between the AZARCH_CC markers is REGENERATED from
    modifications/calamares/locale.RESOLVER_COUNTRY_TABLE so the guest resolver's
    country->locale/layout map stays in lock-step with that single source of truth. The
    package already carries a working copy of the table, so it is self-contained/runnable on
    its own; this re-injection just guarantees no drift.

    Subcommands (see packages/azarch/ for the full behavior):
      theme [--dark|--white]  set the system colour theme (dark default); no arg prints it
      --sshd-hypervisor   install host pubkey from ~/shared/authorized_keys, start sshd
      --resolve-date-time geolocate by IP (pick a server) and set the timezone
      --resolve-language  geolocate by IP and set English + the region language
      --resolve-region    do both
    """
    from modifications.calamares.locale import resolver_country_table_py  # noqa: E402 (locale lives with the calamares modification)
    from packages.azarch.bundle import bundle_source  # noqa: E402 (the command line interface package's bundler)

    src = bundle_source()
    start = src.index(_AZARCH_CC_START) + len(_AZARCH_CC_START)
    end = src.index(_AZARCH_CC_END)
    generated = (
        "\nCOUNTRY_TABLE: dict[str, tuple[str, str, str, int]] = {\n"
        + resolver_country_table_py()
        + "\n}\n"
    )
    return src[:start] + generated + src[end:]


# --- 8b. /usr/local/lib/azarch/azarch-osd (the media OSD indicator) ---------
def azarch_osd() -> str:
    """The media OSD indicator (packages/azarch/osd_indicator.py) shipped VERBATIM as the
    standalone /usr/local/lib/azarch/azarch-osd script. It is the centered cyan bar shown when
    the FN keys change the volume/brightness: `azarch volume/brightness` launches it detached and
    writes it one JSON line. It carries its own `#!/usr/bin/env python3` shebang and uses only
    the standard library + tkinter (present in the system python), so it runs as an executable
    with no venv. Emitted whole (not bundled into `azarch`) because it is a separate GUI process,
    exactly like the speech-to-text indicator it is modelled on."""
    import paths  # noqa: E402 (repo path roots; imported lazily like the bundler above)
    return (paths.AZARCH_COMMAND_LINE_INTERFACE_DIR / "osd_indicator.py").read_text(encoding="utf-8")


# --- 9. /usr/local/bin/azarch-install (privileged Calamares launcher) -------
def install_wrapper_sh() -> str:
    """The single privileged launch path for Calamares, used by both the OpenBox
    autostart and the application-menu / Desktop installer launchers. On the live medium `main` has
    passwordless sudo, so `sudo -E calamares` is the correct, dependency-free way to
    get root for the GUI installer.

    -E preserves the X env (DISPLAY, XAUTHORITY, XDG_*) so the root-owned Calamares Qt
    process can connect to `main`'s X server.

    We deliberately do NOT pass `-c /etc/calamares`. Despite its name, `-c` is a
    testing-only flag that overrides Calamares' *application data* directory, not just
    the configuration tree: once set, Calamares looks for qml/, branding/ and
    settings.conf ONLY under that dir and skips the normal /usr/share/calamares
    fallback. Our QML ships at /usr/share/calamares/qml (there is no /etc/calamares/qml),
    so `-c /etc/calamares` made Calamares die at startup with "FATAL: explicitly
    configured application data directory is missing qml/". With no `-c`, Calamares
    reads /etc/calamares/settings.conf and branding by default (that IS the sysconfdir
    it checks first) and finds QML under /usr/share, so the installer launches."""
    return """\
#!/bin/sh
# azarch-install -- privileged Calamares launcher for the live session.
# `main` has passwordless sudo on the live medium, so this needs no polkit agent.
#
# XDG_RUNTIME_DIR is unset before elevating: `sudo -E` would otherwise pass main's
# /run/user/1000 through to the root Qt process, which then logs a "runtime directory
# is owned by uid 1000, not 0" warning. DISPLAY/XAUTHORITY (the load-bearing X vars)
# are still preserved by -E, and root can read main's ~/.Xauthority, so Calamares
# connects to the running X server fine.
#
# No `-c /etc/calamares`: that flag overrides the app-data dir and makes Calamares look
# for qml/ under /etc/calamares (which does not exist), a fatal startup error.
# Calamares already reads /etc/calamares/settings.conf and branding by default.
unset XDG_RUNTIME_DIR
exec sudo -E calamares
"""


# --- 10. Emit plan ----------------------------------------------------------
# Declarative map so compiler.py can iterate. Each entry: the builder function that
# produces the content, the DESTINATION (absolute, or $HOME-relative for the live
# `main` user), and the file MODE. `owner` records the intended chown so compiler.py knows
# which files fall under the /home/main (uid 1000, gid 998) handback.
#
# HOME-relative paths are given relative to /home/main so the airootfs overlay lands
# them under airootfs/home/main/...; compiler.py chowns that whole tree 1000:998 after
# emit (as it already does for the fastfetch/first-boot payloads). Absolute paths
# (/usr/local/bin/..., /usr/share/...) stay root-owned (0:0) -- do NOT chown them.

# scripts -> 0o755, configs -> 0o644.
_EXEC = 0o755
_CONF = 0o644

# Each PLAN entry is a dict for readability in compiler.py:
#   builder: callable() -> str content
#   dest:    absolute path in the airootfs (already resolved under /home/main for user
#            files, so compiler.py just prefixes the airootfs root)
#   mode:    octal file mode
#   owner:   "home" (chown 1000:998 with the rest of /home/main) or "root"
PLAN = [
    {
        "builder": xinitrc,
        "dest": f"{HOME}/.xinitrc",
        "mode": _EXEC,
        "owner": "home",
    },
    {
        # OpenBox window-manager config: keybinds (Super -> menu via xcape's W-Menu),
        # window management, the doubled-titlebar theme + title font, and the FULL
        # titlebar-button mouse bindings (so min/max/close work). The desktop right-click
        # menu is disabled (empty Root context). No panel/dock config -- the Az'arch menu
        # is the only shell. Home-owned; mirrored into /etc/skel. rc.xml is a plain
        # config (0644).
        "builder": openbox_rc_xml,
        "dest": f"{HOME}/.config/openbox/rc.xml",
        "mode": _CONF,
        "owner": "home",
    },
    {
        # The DARK Az'arch OpenBox THEME (the default; ~1.5x-height titlebar). Ships to
        # ~/.themes/Azarch-Dark/openbox-3/themerc (a user theme search path); rc.xml's
        # <theme> names it "Azarch-Dark" out of the box. Home-owned; mirrored into
        # /etc/skel. Plain data (0o644).
        "builder": openbox_theme_rc_dark,
        "dest": OPENBOX_THEME_THEMERC_DARK,
        "mode": _CONF,
        "owner": "home",
    },
    {
        # The LIGHT Az'arch OpenBox THEME (classic Clearlooks-cyan). Ships to
        # ~/.themes/Azarch/openbox-3/themerc so `azarch theme --white` can switch rc.xml's
        # <theme><name> to "Azarch" and have the themerc already present. Home-owned;
        # mirrored into /etc/skel. Plain data (0o644).
        "builder": openbox_theme_rc_light,
        "dest": OPENBOX_THEME_THEMERC,
        "mode": _CONF,
        "owner": "home",
    },
    {
        # System theme DEFAULT (DARK) -- GTK3 theme file. The freedesktop/GTK standard any
        # downloaded GTK3 app reads at startup; `azarch theme --white` rewrites it. Home file.
        "builder": gtk3_settings_ini_default,
        "dest": GTK3_SETTINGS_PATH,
        "mode": _CONF,
        "owner": "home",
    },
    {
        # System theme DEFAULT (DARK) -- GTK4 theme file (same, for GTK4 apps that read it).
        "builder": gtk4_settings_ini_default,
        "dest": GTK4_SETTINGS_PATH,
        "mode": _CONF,
        "owner": "home",
    },
    {
        # System theme DEFAULT (DARK) -- GTK2 theme file (~/.gtkrc-2.0, older GTK2 apps).
        "builder": gtkrc2_default,
        "dest": GTKRC2_PATH,
        "mode": _CONF,
        "owner": "home",
    },
    {
        # System theme DEFAULT (DARK) -- dconf keyfile making color-scheme 'prefer-dark' the
        # system default (compiled by `dconf update` in the customize hook). Root-owned /etc.
        "builder": dconf_theme_keyfile,
        "dest": DCONF_THEME_KEYFILE_PATH,
        "mode": _CONF,
        "owner": "root",
    },
    {
        # The dconf profile so the system `local` db backs the user db. Root-owned /etc.
        "builder": dconf_profile_user,
        "dest": DCONF_PROFILE_USER_PATH,
        "mode": _CONF,
        "owner": "root",
    },
    {
        # OpenBox session autostart: wallpaper (feh), keyboard layouts (setxkbmap),
        # Super key (xcape), the application-menu daemon, and the first-run installer.
        # Sourced by openbox-session, so it must be EXECUTABLE (0o755). Home-owned;
        # mirrored into /etc/skel. (openbox-session runs it via /bin/sh, but shipping
        # it executable matches the shebang and is harmless.)
        "builder": openbox_autostart,
        "dest": f"{HOME}/.config/openbox/autostart",
        "mode": _EXEC,
        "owner": "home",
    },
    {
        # OpenBox session environment (sourced before autostart): XDG base dirs +
        # XDG_CURRENT_DESKTOP=openbox. Home-owned; mirrored into /etc/skel.
        "builder": openbox_environment,
        "dest": f"{HOME}/.config/openbox/environment",
        "mode": _CONF,
        "owner": "home",
    },
    {
        # The "installed" OpenBox autostart, STAGED on the ISO (root-owned system path,
        # NOT a per-user file). The Calamares OFFLINE install copies it over the target's
        # inherited live autostart (home + skel) so the installed system drops the two
        # live-only lines (fixed us,il keyboard + first-run installer). Executable so the
        # copied-into-place file is runnable by openbox-session.
        "builder": openbox_autostart_installed,
        "dest": INSTALLED_AUTOSTART_STAGING_PATH,
        "mode": _EXEC,
        "owner": "root",
    },
    {
        # Seed OUR menu's launch-frequency store so a fresh profile opens with System
        # Settings, LibreWolf, kitty, Dolphin at the top (it otherwise sorts
        # alphabetically with no history). Home-owned data file (0o644), mirrored into
        # /etc/skel so a Calamares-installed user inherits the same starting order.
        # Fully dynamic afterwards -- the daemon re-sorts as apps are opened.
        "builder": az_menu_usage_seed_json,
        "dest": _app_menu.MENU_USAGE_SEED_SYSTEM_PATH,
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": install_menu_desktop,
        "dest": INSTALL_MENU_DESKTOP_PATH,
        "mode": _CONF,
        "owner": "root",
    },
    {
        # The Desktop launcher must be EXECUTABLE (0o755) so a file manager launches it
        # on double-click without an untrusted-.desktop prompt.
        "builder": desktop_installer_launcher,
        "dest": f"{HOME}/Desktop/azarch-install.desktop",
        "mode": _EXEC,
        "owner": "home",
    },
    {
        "builder": install_wrapper_sh,
        "dest": INSTALL_WRAPPER_PATH,
        "mode": _EXEC,
        "owner": "root",
    },
    {
        "builder": azarch_command_line_interface,
        "dest": AZARCH_BIN_PATH,
        "mode": _EXEC,
        "owner": "root",
    },
    {
        # The media OSD indicator (centered cyan volume/brightness bar), shipped as a
        # standalone executable Python script next to the C terminal user interface binary.
        # `azarch volume/brightness` launches it. Root-owned system path; EXECUTABLE (0o755)
        # so it runs directly (it carries a python3 shebang). Pinned 0755 in FILE_PERMISSIONS
        # too, since archiso would otherwise normalize it to 0644 in the squashfs and the
        # launcher (which checks os.access X_OK) would silently skip the on-screen bar.
        "builder": azarch_osd,
        "dest": AZARCH_OSD_SYSTEM_PATH,
        "mode": _EXEC,
        "owner": "root",
    },
]

# The .bash_profile snippet is handled separately from PLAN because it is not a
# whole-file replacement conceptually (it is the login bootstrap). compiler.py still
# writes it as the full file content of /home/main/.bash_profile (there is no stock one
# in the airootfs to preserve), mode 0644, owner "home".
BASH_PROFILE_DEST = f"{HOME}/.bash_profile"


def emit_plan() -> list[dict]:
    """Return the PLAN list (builder/dest/mode/owner) plus the .bash_profile entry, so
    compiler.py can iterate a single sequence. Kept as a function (not just the module
    constant) to mirror the builder-function style of the other configuration modules
    and to keep the .bash_profile special-case in one place."""
    return PLAN + [
        {
            "builder": bash_profile_startx,
            "dest": BASH_PROFILE_DEST,
            "mode": _CONF,
            "owner": "home",
        },
    ]
