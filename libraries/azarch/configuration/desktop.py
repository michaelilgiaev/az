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
surface is the Az'arch application menu -- a borderless Tkinter launcher centered on
the screen, opened by the Super key. Everything the old Plasma panel carried (launcher,
power actions) lives in that menu.

Everything here is a small builder function returning the CONTENT of one file.
steps.py emits each to its airootfs destination via emit.write_text/write_exec and
iterates PLAN (below) so the mapping (path + mode) stays declarative. The /home/main
tree is chowned 1000:998 by steps.py after emit, exactly like the fastfetch/first-boot
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
    display-manager .wants symlink or graphical.target (see steps.py STEPS_NOTE).
"""

from __future__ import annotations

# --- Branding / assets ------------------------------------------------------
# The two wallpapers shipped on the medium. Each is a plain PNG copied under
# /usr/share/wallpapers/<id>/contents/images/<W>x<H>.png (the old KPackage layout is
# kept so the assets and steps.py emit paths do not have to change; OpenBox/feh only
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
# The asset copied to WALLPAPER_IMAGE_FILE is the same "years" image; steps.py already
# writes that image, so the default resolves to a file that exists.
WALLPAPER_ASSET = "wallpapers/years.png"


def wallpaper_metadata_json(wp_id: str) -> str:
    """Minimal metadata.json shipped alongside each wallpaper image.

    KDE's KPackage engine is gone, so nothing reads this at runtime anymore; it is
    kept purely so the two wallpaper directories remain self-describing (authorship /
    license) and so the steps.py emit layout for wallpapers does not have to change.
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

# Installer launcher icon. steps.py copies assets/logo/azarch_installer_icon.png (the
# "Az'" wordmark rendered as a 256x256 app tile) to SYSTEM icon paths so the Desktop
# launcher and the application-menu entry can name it. Installed to /usr/share/pixmaps
# (a standard icon search path) AND to the hicolor 256x256 apps dir; the .desktop files
# name it by its basename ("azarch-installer") so the icon loader resolves either.
INSTALLER_ICON_ASSET = "logo/azarch_installer_icon.png"
INSTALLER_ICON_NAME = "azarch-installer"
INSTALLER_ICON_PIXMAP = f"/usr/share/pixmaps/{INSTALLER_ICON_NAME}.png"
INSTALLER_ICON_HICOLOR = (
    f"/usr/share/icons/hicolor/256x256/apps/{INSTALLER_ICON_NAME}.png"
)

# Home directory of the live user; the overlay root for HOME-relative entries.
HOME = "/home/main"
# uid:gid for the live user tree (autologin group gid 998).
HOME_OWNER = (1000, 998)


# --- Application menu wiring (single source of truth in application_menu.py) --
# OUR menu is the whole shell now. It ships as a resident daemon (built once, kept
# hidden) so opening it is instant; the Super key and the OpenBox root menu both run
# the launcher (/usr/local/bin/azarch-application-menu) which signals that daemon.
from . import application_menu as _app_menu  # noqa: E402  (kept next to its users)

MENU_LAUNCHER = _app_menu.MENU_LAUNCHER_SYSTEM_PATH
MENU_DAEMON_PY = _app_menu.MENU_DAEMON_PY_SYSTEM_PATH


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
[ -x /usr/bin/feh ] && feh --no-fehbg --bg-fill '""" + WALLPAPER_IMAGE_FILE + """'

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
#   * window.handle.width 3->5  (the bottom resize handle, kept proportional)
# The dominant half of the height comes from the larger title FONT set in rc.xml's
# <theme> (size 8 -> 12, i.e. exactly 1.5x stock). Bigger font => taller label =>
# OpenBox draws bigger buttons, so the min/max/close targets grow with the bar.
# Everything else (the #8CB0DC cyan gradient, the button gradients/hover/pressed states,
# the menu/osd styling) is copied verbatim so the look is identical, only 1.5x larger.
OPENBOX_THEME_NAME = "Azarch"
OPENBOX_THEME_DIR = f"{HOME}/.themes/{OPENBOX_THEME_NAME}/openbox-3"
OPENBOX_THEME_THEMERC = f"{OPENBOX_THEME_DIR}/themerc"

# The two padding fields (in px) that set the titlebar height, and the resize-handle
# width. Pinned as constants so a test can prove the bar was grown to ~1.5x stock.
# Each lands halfway between stock Clearlooks and the earlier (overshot) doubled value.
OPENBOX_THEME_PADDING_HEIGHT = 7    # stock Clearlooks: 2 (was 12 when doubled)
OPENBOX_THEME_PADDING_WIDTH = 6     # stock Clearlooks: 3 (was 8 when doubled)
OPENBOX_THEME_HANDLE_WIDTH = 5      # stock Clearlooks: 3 (was 6 when doubled)


def openbox_theme_rc() -> str:
    """~/.themes/Azarch/openbox-3/themerc -- the Az'arch OpenBox theme.

    The stock Clearlooks themerc with ONLY the titlebar-height fields grown
    (padding.height/width and the handle width); every colour/gradient/state line is
    the Clearlooks original so the bar keeps its familiar cyan look, just ~1.5x the
    height. Paired with the larger title <font> in rc.xml (size 12), this grows the
    bar to about 1.5x stock and the min/max/close buttons OpenBox sizes to the label.

    Shipped to ~/.themes (a user theme search path OpenBox scans alongside
    /usr/share/themes) and mirrored into /etc/skel so the installed user inherits it."""
    return f"""\
# Az'arch OpenBox theme -- Clearlooks with a ~1.5x titlebar. Generated by
# azarch.configuration.desktop (edit the Python, not this file). Only the size-driving
# fields (padding.height/width, handle width) differ from stock Clearlooks; the larger
# title FONT is set in rc.xml's <theme>. All colours are the Clearlooks originals.

# Fonts (halos)
*.font: shadow=n
window.active.label.text.font:shadow=y:shadowtint=30:shadowoffset=1
window.inactive.label.text.font:shadow=y:shadowtint=00:shadowoffset=0
menu.items.font:shadow=y:shadowtint=0:shadowoffset=1

# general stuff -- padding.height/width GROWN to ~1.5x the titlebar (was 2 / 3),
# handle width grown to stay proportional (was 3).
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
menu.border.color: #aaaaaa
menu.border.width: 1

menu.title.bg: solid flat
menu.title.bg.color: #E6E7E6
menu.title.text.color: #111111

menu.items.bg: Flat Solid
menu.items.bg.color: #ffffff
menu.items.text.color: #111111
menu.items.disabled.text.color: #aaaaaa

menu.items.active.bg: Flat Gradient splitvertical border

menu.items.active.bg.color: #97b8e2
menu.items.active.bg.color.splitTo: #a8c5e9

menu.items.active.bg.colorTo: #91b3de
menu.items.active.bg.colorTo.splitTo: #80a7d6
menu.items.active.bg.border.color: #4b6e99
menu.items.active.text.color: #ffffff

menu.separator.width: 1
menu.separator.padding.width: 0
menu.separator.padding.height: 3
menu.separator.color: #aaaaaa

# handles
window.*.handle.bg: Raised solid
window.*.handle.bg.color: #eaebec

window.*.grip.bg: Raised solid
window.*.grip.bg.color: #eaebec

# Active
window.*.border.color: #585a5d

window.active.title.separator.color: #4e76a8

*.title.bg: Raised Gradient splitvertical
*.title.bg.color: #8CB0DC
*.title.bg.color.splitTo: #99BAE3
*.title.bg.colorTo: #86ABD9
*.title.bg.colorTo.splitTo: #7AA1D1

window.active.label.bg: Parentrelative
window.active.label.text.color: #ffffff

window.active.button.*.bg: Flat Gradient splitvertical Border

window.active.button.*.bg.color: #92B4DF
window.active.button.*.bg.color.splitTo: #B0CAEB
window.active.button.*.bg.colorTo: #86ABD9
window.active.button.*.bg.colorTo.splitTo: #769FD0

window.active.button.*.bg.border.color: #49678B
window.active.button.*.image.color: #F4F5F6

window.active.button.hover.bg.color: #b5d3ef
window.active.button.hover.bg.color.splitTo: #b5d3ef
window.active.button.hover.bg.colorTo: #9cbae7
window.active.button.hover.bg.colorTo.splitTo: #8caede
window.active.button.hover.bg.border.color: #4A658C
window.active.button.hover.image.color: #ffffff

window.active.button.pressed.bg: Flat solid Border
window.active.button.pressed.bg.color: #7aa1d2

window.active.button.hover.bg.border.color: #4A658C

# inactive
window.inactive.title.separator.color: #96999d

window.inactive.title.bg: Raised Gradient splitvertical
window.inactive.title.bg.color: #E3E2E0
window.inactive.title.bg.color.splitTo: #EBEAE9
window.inactive.title.bg.colorTo: #DEDCDA
window.inactive.title.bg.colorTo.splitTo: #D5D3D1

window.inactive.label.bg: Parentrelative
window.inactive.label.text.color: #70747d

window.inactive.button.*.bg: Flat Gradient splitVertical Border
window.inactive.button.*.bg.color: #ffffff
window.inactive.button.*.bg.color.splitto: #ffffff
window.inactive.button.*.bg.colorTo: #F9F8F8
window.inactive.button.*.bg.colorTo.splitto: #E9E7E6
window.inactive.button.*.bg.border.color: #928F8B
window.inactive.button.*.image.color: #6D6C6C

# osd
osd.border.width: 1
osd.border.color:  #aaaaaa

osd.bg: flat border gradient splitvertical
osd.bg.color: #F0EFEE
osd.bg.color.splitto: #f5f5f4
osd.bg.colorTo: #EAEBEC
osd.bg.colorTo.splitto: #E7E5E4

osd.bg.border.color: #ffffff

osd.active.label.bg: parentrelative
osd.active.label.bg.color: #efefef
osd.active.label.bg.border.color: #9c9e9c
osd.active.label.text.color: #444

osd.inactive.label.bg: parentrelative
osd.inactive.label.text.color: #70747d

osd.hilight.bg: flat vertical gradient
osd.hilight.bg.color: #9ebde5
osd.hilight.bg.colorTo: #749dcf
osd.unhilight.bg: flat vertical gradient
osd.unhilight.bg.color: #BABDB6
osd.unhilight.bg.colorTo: #efefef
"""


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
     by azarch.configuration.desktop (edit the Python, not this file). -->
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
    <!-- The Az'arch theme: Clearlooks with a ~1.5x-height titlebar (openbox_theme_rc,
         shipped to ~/.themes/Azarch). titleLayout NLIMC = icon, label, iconify,
         maximize, close. -->
    <name>{OPENBOX_THEME_NAME}</name>
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
#    re-login where the X root pixmap was reset). feh owns the root pixmap on OpenBox.
[ -x /usr/bin/feh ] && feh --no-fehbg --bg-fill '{WALLPAPER_IMAGE_FILE}' &

# 2. Super key -> application menu. OpenBox cannot bind a lone modifier, so xcape turns
#    a solo Super_L tap into the chord Super_L+Menu, which rc.xml binds to the menu
#    launcher. Super keeps working as a normal modifier for every other bind. -t 200:
#    only a tap under 200ms fires (a held Super does not).
command -v xcape >/dev/null 2>&1 && \\
    xcape -t 200 -e 'Super_L=Super_L|Menu' &

# 3. Az'arch application-menu daemon: build the menu once and keep it hidden so the
#    first Super press is instant (see application_menu/daemon.py).
[ -f '{MENU_DAEMON_PY}' ] && \\
    setsid python3 '{MENU_DAEMON_PY}' >/dev/null 2>&1 < /dev/null &"""


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
    configuration/calamares_shellprocess cleanup step. Each line is guarded
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
    path than our startx, and keep the XDG base dirs defined."""
    return """\
# ~/.config/openbox/environment -- sourced by openbox-session before autostart.
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_CURRENT_DESKTOP=openbox
"""


# --- 6. Menu daemon usage seed (single source of truth in application_menu.py) --
def az_menu_usage_seed_json() -> str:
    """Seed launch-frequency store for OUR menu, fixing the STARTING top of the list on
    a fresh profile (the menu otherwise sorts alphabetically until the user has opened
    things). Content is owned by configuration/application_menu.py; this module just
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


# --- 8. /usr/local/bin/azarch (guest-side CLI) ------------------------------
AZARCH_BIN_PATH = "/usr/local/bin/azarch"


def azarch_sh() -> str:
    """Guest-side CLI shipped on the live ISO (and the installed system via /etc/skel
    or the installer copy). Subcommands:

    azarch --sshd-hypervisor
      Installs the host's public key from ~/shared/authorized_keys (staged there by
      'hypervisor install') into ~/.ssh/authorized_keys, then enables and starts sshd.
      Safe to run more than once. (The subcommand is named --sshd-hypervisor because it
      wires the guest sshd up for the hypervisor's forwarded host->guest SSH port; the
      host side is hypervisor.cfg's sshd_hypervisor toggle.)

    azarch --resolve-region / --resolve-date-time / --resolve-language
      The ONLY things that ping an external server to geolocate the machine and update
      its region settings (everything else in Az'arch is static/user-chosen -- the
      installer and boot never auto-resolve). Each presents a list of 5 SHUFFLED
      IP-geolocation servers; the user picks one, it is queried for the country code +
      timezone, and the system is updated:
        --resolve-date-time  set the timezone to match the IP.
        --resolve-language   set the language to English + the region's language
                             (English ONLY if the region is English-speaking), i.e. a
                             second keyboard layout with Alt+Shift + the locale.
        --resolve-region     do both.
      The country -> (locale, keyboard layout) map is embedded from
      configuration/locale.RESOLVER_COUNTRY_TABLE (the single source of truth).
    """
    # Embed the resolver's country table (CC|locale|layout|keymap|english) so the shell
    # can map an IP-geolocated country onto a locale + keyboard layout without any
    # Python at runtime. Single source of truth: configuration/locale.
    from .locale import resolver_country_table_sh  # noqa: E402  (kept next to its user)

    country_table = resolver_country_table_sh()
    return f"""\
#!/bin/sh
# azarch -- guest-side helper CLI.

set -eu

usage() {{
    printf 'Usage: azarch <command>\\n'
    printf '\\n'
    printf 'Commands:\\n'
    printf '  --sshd-hypervisor    Install host pubkey from ~/shared/authorized_keys and start sshd\\n'
    printf '  --resolve-region     Geolocate by IP (pick a server) and set BOTH timezone and language\\n'
    printf '  --resolve-date-time  Geolocate by IP (pick a server) and set the timezone\\n'
    printf '  --resolve-language   Geolocate by IP (pick a server) and set English + the region language\\n'
}}

# --- resolver: country -> locale + keyboard layout table --------------------
# Embedded from configuration/locale.RESOLVER_COUNTRY_TABLE. Lines are
# CC|locale|xkb_layout|vconsole_keymap|english(1/0). `english` 1 means the country
# is English-speaking -> English ONLY (no second layout/locale).
azarch_country_table() {{
    cat <<'AZARCH_CC_EOF'
{country_table}
AZARCH_CC_EOF
}}

# The 5 IP-geolocation servers offered (shuffled before display). Each line is
# LABEL|URL|COUNTRY_JQ|TZ_JQ -- the jq filters that pull the ISO-3166 country code
# and the IANA timezone out of that server's JSON response. ipapi.co and ipquery.io
# were called out in issue #46; the rest are well-known free equivalents.
azarch_resolver_servers() {{
    cat <<'AZARCH_SRV_EOF'
ipapi.co|https://ipapi.co/json/|.country_code|.timezone
ipquery.io|https://api.ipquery.io/?format=json|.location.country_code|.location.timezone
ip-api.com|http://ip-api.com/json/|.countryCode|.timezone
ipinfo.io|https://ipinfo.io/json|.country|.timezone
ipwho.is|https://ipwho.is/|.country_code|.timezone
AZARCH_SRV_EOF
}}

# Prompt the user to choose one of the 5 shuffled servers, query it, and echo the
# resolved "COUNTRY TIMEZONE" (uppercased country). Returns non-zero on any failure
# (no network, bad/empty response). Writes prompts/errors to stderr so stdout stays
# just the result. Requires curl + jq (both shipped on the ISO).
azarch_resolve_via_server() {{
    if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
        printf 'azarch: curl and jq are required to resolve the region\\n' >&2
        return 1
    fi
    # Shuffle the 5 servers (shuf if present, else awk-random) into a numbered menu.
    shuffled=$(azarch_resolver_servers | {{ shuf 2>/dev/null || awk 'BEGIN{{srand()}}{{print rand()"\\t"$0}}' | sort | cut -f2-; }})
    printf 'Pick a server to geolocate this machine (1-5):\\n' >&2
    i=0
    printf '%s\\n' "$shuffled" | while IFS='|' read -r label url cjq tjq; do
        i=$((i + 1))
        printf '  %d) %s\\n' "$i" "$label" >&2
    done
    printf 'Server number: ' >&2
    read -r choice
    case "$choice" in
        1|2|3|4|5) : ;;
        *) printf 'azarch: invalid selection %s\\n' "$choice" >&2; return 1 ;;
    esac
    line=$(printf '%s\\n' "$shuffled" | sed -n "${{choice}}p")
    if [ -z "$line" ]; then
        printf 'azarch: invalid selection\\n' >&2
        return 1
    fi
    label=$(printf '%s' "$line" | cut -d'|' -f1)
    url=$(printf '%s' "$line" | cut -d'|' -f2)
    cjq=$(printf '%s' "$line" | cut -d'|' -f3)
    tjq=$(printf '%s' "$line" | cut -d'|' -f4)
    printf 'Querying %s ...\\n' "$label" >&2
    json=$(curl -fsS --max-time 15 "$url" 2>/dev/null) || {{
        printf 'azarch: could not reach %s\\n' "$label" >&2
        return 1
    }}
    country=$(printf '%s' "$json" | jq -r "$cjq // empty" 2>/dev/null | tr '[:lower:]' '[:upper:]')
    tz=$(printf '%s' "$json" | jq -r "$tjq // empty" 2>/dev/null)
    if [ -z "$country" ] || [ -z "$tz" ]; then
        printf 'azarch: %s did not return a country + timezone\\n' "$label" >&2
        return 1
    fi
    printf '%s %s\\n' "$country" "$tz"
}}

# Apply a timezone to the running system (and, when systemd is present, via
# timedatectl so the change is live). Falls back to the /etc/localtime symlink.
azarch_apply_timezone() {{
    tz="$1"
    if [ ! -e "/usr/share/zoneinfo/$tz" ]; then
        printf 'azarch: unknown timezone %s\\n' "$tz" >&2
        return 1
    fi
    if command -v timedatectl >/dev/null 2>&1 && timedatectl set-timezone "$tz" 2>/dev/null; then
        :
    else
        sudo ln -sf "/usr/share/zoneinfo/$tz" /etc/localtime
    fi
    printf 'Timezone set to %s\\n' "$tz"
}}

# Apply the language for a country code: English + the region's language as a second
# keyboard layout (Alt+Shift) and the region format locale -- or English ONLY if the
# country is English-speaking. Mirrors the Calamares region-keyboard behaviour.
azarch_apply_language() {{
    country="$1"
    row=$(azarch_country_table | grep -i "^${{country}}|" | head -1 || true)
    if [ -z "$row" ]; then
        # Unknown/unsupported country -> English only (safe default).
        printf 'azarch: no language mapping for %s; keeping English only\\n' "$country" >&2
        loc="en_US.UTF-8"; layout="us"; keymap="us"; english=1
    else
        loc=$(printf '%s' "$row" | cut -d'|' -f2)
        layout=$(printf '%s' "$row" | cut -d'|' -f3)
        keymap=$(printf '%s' "$row" | cut -d'|' -f4)
        english=$(printf '%s' "$row" | cut -d'|' -f5)
    fi

    # Enable + generate the needed locales (English always; the region locale too when
    # non-English). LANG stays English (en_US) -- only the region format locale (LC_*)
    # follows the country, matching the installer's "English UI + region numbers/dates".
    sudo sed -i 's/^#\\s*en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen 2>/dev/null || true
    if [ "$english" = "0" ]; then
        sudo sed -i "s/^#\\s*${{loc}} UTF-8/${{loc}} UTF-8/" /etc/locale.gen 2>/dev/null || true
        grep -q "^${{loc}} UTF-8" /etc/locale.gen 2>/dev/null || printf '%s UTF-8\\n' "$loc" | sudo tee -a /etc/locale.gen >/dev/null
    fi
    sudo locale-gen >/dev/null 2>&1 || true

    # /etc/locale.conf: English UI, region format locale (LC_*) when non-English.
    {{
        printf 'LANG=en_US.UTF-8\\n'
        if [ "$english" = "0" ]; then
            for k in LC_NUMERIC LC_TIME LC_MONETARY LC_PAPER LC_MEASUREMENT; do
                printf '%s=%s\\n' "$k" "$loc"
            done
        fi
    }} | sudo tee /etc/locale.conf >/dev/null

    # Keyboard: English ("us") first/active; the region layout as a switchable SECOND
    # (Alt+Shift) when non-English. English-speaking -> "us" only. Written to the X11
    # config AND applied live via setxkbmap (the session runs OpenBox, no Plasma KCM).
    if [ "$english" = "0" ] && [ "$layout" != "us" ]; then
        xkb_layout="us,$layout"
        xkb_opts='    Option "XkbOptions" "grp:alt_shift_toggle"'
        vconsole_map="$keymap"
        live_layout="us,$layout"
    else
        xkb_layout="us"
        xkb_opts=""
        vconsole_map="us"
        live_layout="us"
    fi
    sudo mkdir -p /etc/X11/xorg.conf.d
    {{
        printf 'Section "InputClass"\\n'
        printf '    Identifier "system-keyboard"\\n'
        printf '    MatchIsKeyboard "on"\\n'
        printf '    Option "XkbLayout" "%s"\\n' "$xkb_layout"
        [ -n "$xkb_opts" ] && printf '%s\\n' "$xkb_opts"
        printf 'EndSection\\n'
    }} | sudo tee /etc/X11/xorg.conf.d/00-keyboard.conf >/dev/null
    printf 'KEYMAP=%s\\n' "$vconsole_map" | sudo tee /etc/vconsole.conf >/dev/null

    # Apply the keyboard to the LIVE X11 session too (so it takes effect now, not just
    # after re-login), when an X server + setxkbmap are available.
    if [ -n "${{DISPLAY:-}}" ] && command -v setxkbmap >/dev/null 2>&1; then
        if [ "$live_layout" = "us" ]; then
            setxkbmap -layout us 2>/dev/null || true
        else
            setxkbmap -layout "$live_layout" -option grp:alt_shift_toggle 2>/dev/null || true
        fi
    fi

    if [ "$english" = "0" ]; then
        printf 'Language set to English + %s (Alt+Shift to switch layouts)\\n' "$layout"
    else
        printf 'Language set to English only\\n'
    fi
}}

cmd="${{1:-}}"

case "$cmd" in
    --sshd-hypervisor)
        # Resolve the REAL login user, not whoever the shell says. The documented
        # invocation is 'sudo azarch --sshd-hypervisor', under which $HOME is /root and
        # $USER is root -- so keying off $HOME would stage the pubkey into /root/.ssh and
        # the 'main' login (whose sshd reads /home/main/.ssh) would still be locked out.
        # $SUDO_USER is the invoking user under sudo; fall back to the current user when
        # run without sudo. Refuse a bare-root target: there is no home pubkey login for
        # root here (blank password, PermitRootLogin prohibit-pw).
        TARGET_USER="${{SUDO_USER:-$(id -un)}}"
        if [ "$TARGET_USER" = "root" ]; then
            printf 'azarch --sshd-hypervisor: run as a normal user via sudo (got root); cannot stage a login key for root\\n' >&2
            exit 1
        fi
        TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
        if [ -z "$TARGET_HOME" ]; then
            printf 'azarch --sshd-hypervisor: could not resolve home for user %s\\n' "$TARGET_USER" >&2
            exit 1
        fi
        SHARED="$TARGET_HOME/shared"
        KEY="$SHARED/authorized_keys"
        if ! mountpoint -q "$SHARED" 2>/dev/null; then
            mkdir -p "$SHARED"
            sudo mount -t 9p -o trans=virtio,version=9p2000.L,msize=104857600 shared "$SHARED" || {{
                printf 'azarch --sshd-hypervisor: could not mount shared folder (is the VM running with shared_directory=true?)\\n' >&2
                exit 1
            }}
        fi
        if [ ! -f "$KEY" ]; then
            printf 'azarch --sshd-hypervisor: %s not found -- stage a host pubkey there first\\n' "$KEY" >&2
            exit 1
        fi
        # Install the key into the TARGET user's ~/.ssh and hand ownership to them:
        # under sudo these are created as root, and root-owned ~/.ssh/authorized_keys
        # trips sshd StrictModes, so the pubkey would be ignored on login.
        sudo install -d -m 700 -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.ssh"
        sudo install -m 600 -o "$TARGET_USER" -g "$TARGET_USER" "$KEY" "$TARGET_HOME/.ssh/authorized_keys"
        printf 'Installed pubkey -> %s/.ssh/authorized_keys\\n' "$TARGET_HOME"
        sudo ssh-keygen -A
        # setup-pkgs.sh sets 'ufw default reject incoming', so the forwarded
        # host->guest :22 connection is dropped unless we open it here. Do this before
        # starting sshd so the port is reachable the moment it listens.
        sudo ufw allow ssh
        sudo systemctl enable --now sshd
        printf 'sshd enabled and started -- ssh in as %s.\\n' "$TARGET_USER"
        ;;
    --resolve-date-time)
        # Ping a user-picked server, set the timezone to match the IP.
        result=$(azarch_resolve_via_server) || exit 1
        country=$(printf '%s' "$result" | cut -d' ' -f1)
        tz=$(printf '%s' "$result" | cut -d' ' -f2)
        printf 'Resolved: country=%s timezone=%s\\n' "$country" "$tz"
        azarch_apply_timezone "$tz"
        ;;
    --resolve-language)
        # Ping a user-picked server, set English + the region's language.
        result=$(azarch_resolve_via_server) || exit 1
        country=$(printf '%s' "$result" | cut -d' ' -f1)
        printf 'Resolved: country=%s\\n' "$country"
        azarch_apply_language "$country"
        ;;
    --resolve-region)
        # Ping a user-picked server ONCE and set BOTH timezone and language.
        result=$(azarch_resolve_via_server) || exit 1
        country=$(printf '%s' "$result" | cut -d' ' -f1)
        tz=$(printf '%s' "$result" | cut -d' ' -f2)
        printf 'Resolved: country=%s timezone=%s\\n' "$country" "$tz"
        azarch_apply_timezone "$tz"
        azarch_apply_language "$country"
        ;;
    -h|--help|help)
        usage
        ;;
    "")
        usage
        exit 1
        ;;
    *)
        printf 'azarch: unknown command: %s\\n' "$cmd" >&2
        usage >&2
        exit 2
        ;;
esac
"""


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
# Declarative map so steps.py can iterate. Each entry: the builder function that
# produces the content, the DESTINATION (absolute, or $HOME-relative for the live
# `main` user), and the file MODE. `owner` records the intended chown so steps.py knows
# which files fall under the /home/main (uid 1000, gid 998) handback.
#
# HOME-relative paths are given relative to /home/main so the airootfs overlay lands
# them under airootfs/home/main/...; steps.py chowns that whole tree 1000:998 after
# emit (as it already does for the fastfetch/first-boot payloads). Absolute paths
# (/usr/local/bin/..., /usr/share/...) stay root-owned (0:0) -- do NOT chown them.

# scripts -> 0o755, configs -> 0o644.
_EXEC = 0o755
_CONF = 0o644

# Each PLAN entry is a dict for readability in steps.py:
#   builder: callable() -> str content
#   dest:    absolute path in the airootfs (already resolved under /home/main for user
#            files, so steps.py just prefixes the airootfs root)
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
        # The Az'arch OpenBox THEME (Clearlooks with a doubled-height titlebar). Ships to
        # ~/.themes/Azarch/openbox-3/themerc (a user theme search path); rc.xml's <theme>
        # names it "Azarch". Home-owned; mirrored into /etc/skel. Plain data (0o644).
        # (Replaces the removed menu.xml entry -- the OpenBox root menu is gone.)
        "builder": openbox_theme_rc,
        "dest": OPENBOX_THEME_THEMERC,
        "mode": _CONF,
        "owner": "home",
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
        "dest": "/usr/share/applications/azarch-install.desktop",
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
        "builder": azarch_sh,
        "dest": AZARCH_BIN_PATH,
        "mode": _EXEC,
        "owner": "root",
    },
]

# The .bash_profile snippet is handled separately from PLAN because it is not a
# whole-file replacement conceptually (it is the login bootstrap). steps.py still
# writes it as the full file content of /home/main/.bash_profile (there is no stock one
# in the airootfs to preserve), mode 0644, owner "home".
BASH_PROFILE_DEST = f"{HOME}/.bash_profile"


def emit_plan() -> list[dict]:
    """Return the PLAN list (builder/dest/mode/owner) plus the .bash_profile entry, so
    steps.py can iterate a single sequence. Kept as a function (not just the module
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
