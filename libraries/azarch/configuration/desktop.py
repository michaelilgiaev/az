"""Minimal KDE Plasma live-session desktop, authored as configuration-as-Python strings.

The ISO boots to a graphical Plasma (X11) live session WITHOUT a display
manager, Manjaro-style:

    getty@tty1 autologins `main`  ->  ~/.bash_profile runs `exec startx` on
    tty1 only  ->  ~/.xinitrc paints the wallpaper (no flash) and execs
    `startplasma-x11`  ->  Plasma launches the panel/launcher/kwin_x11, and a
    ~/.config/autostart entry opens the Calamares installer once.

Everything here is a small builder function returning the CONTENT of one file.
steps.py emits each to its airootfs destination via emit.write_text/write_exec
and iterates PLAN (below) so the mapping (path + mode) stays declarative. The
/home/main tree is chowned 1000:998 by steps.py after emit, exactly like the
fastfetch/first-boot payloads.

Design constraints (match archiso/Plasma/Calamares reality):
  * No emojis, ASCII only.
  * No display manager. `startplasma-x11` is provided by plasma-workspace; the
    X11 window manager is kwin_x11 (package kwin-x11, listed explicitly in the
    manifest because it is only an optdepend of plasma-workspace). The Wayland
    kwin comes in via plasma-workspace but is unused here (we start the X11
    session). See libraries/data/packages.x86_64.
  * Calamares MUST run privileged. Plasma DOES ship polkit-kde-agent (pulled by
    plasma-desktop), so pkexec would work -- but the live medium has a
    passwordless-sudo `main` and passwordless root, so the simplest correct,
    dependency-order-free launch stays `sudo -E calamares` via the tiny
    /usr/local/bin/azarch-install wrapper the autostart entry runs.
  * NO cyan/black flash: the old Openbox session did `xsetroot -solid <cyan>`,
    which flashed a solid color before the desktop painted. Instead ~/.xinitrc
    sets the X root to the SAME wallpaper image Plasma will show (feh --bg-fill),
    and ksplashrc disables KSplash, so the first and only paint is the wallpaper.
  * The default Plasma wallpaper is baked per-user (appletsrc) into the live
    `main` home AND /etc/skel, so a Calamares-created user inherits it too.
  * startx-from-tty replaces graphical.target: _link_services needs no
    display-manager .wants symlink or graphical.target (see steps.py STEPS_NOTE).
"""

from __future__ import annotations

# --- Branding / assets ------------------------------------------------------
# Selectable wallpapers shown in Plasma's "Desktop and Wallpaper" grid. Each is a
# KPackage under /usr/share/wallpapers/<Id>/ (metadata.json + contents/images/
# <W>x<H>.png). We ship exactly TWO -- the azarch "years" and "decades" images --
# and REMOVE the stock Plasma "Next" wallpaper (see system.CUSTOMIZE_AIROOTFS) so
# the grid shows only these. Both source images are 1672x941 (see
# assets/wallpapers/), so the packaged image is images/1672x941.png.
WALLPAPERS_SYSTEM_DIR = "/usr/share/wallpapers"
WALLPAPER_IMAGE_RES = "1672x941"          # WxH of the shipped PNGs
WALLPAPER_PACKAGES = [
    {"id": "years", "asset": "wallpapers/years.png"},
    {"id": "decades", "asset": "wallpapers/decades.png"},
]

# The DEFAULT wallpaper baked into the ISO -- the "years" image.
#
# THE DUPLICATE-TILE BUG (see ISSUE/ screenshot: a third selected tile labelled by
# the image RESOLUTION "1672x941" appeared next to "years" and "decades"):
# Plasma 6's org.kde.image grid is a QConcatenateTablesProxyModel over TWO source
# models -- a package model (dirs under /usr/share/wallpapers) and a loose-image
# model (files). ImageProxyModel routes the CONFIGURED Image= by filesystem type:
# a DIRECTORY is matched against the package model (-> the existing "years" tile),
# but a FILE PATH is handed to the loose-image model, which -- when the path matches
# no existing tile -- force-injects it as its OWN tile labelled by the file's
# basename. Because the previous default pointed Image= at the package's INNER png
# (.../years/contents/images/1672x941.png), Plasma added that loose "1672x941" tile:
# the duplicate. (The earlier code comment claimed the inner-png path would be
# "recognised as the years tile" -- the Plasma source proves the opposite; only a
# DIRECTORY path matches a package.)
#
# FIX: point every Plasma `Image=` (appletsrc + the org.kde.image main.xml default in
# system.CUSTOMIZE_AIROOTFS) at the package DIRECTORY (trailing slash), so Plasma
# selects the "years" package tile and injects no loose tile -> the grid shows
# exactly "years" (selected) and "decades". feh needs a real FILE, so the ~/.xinitrc
# pre-paint keeps the inner-png path; hence the two separate constants below.
WALLPAPER_DEFAULT_ID = "years"
# The package DIRECTORY -- what Plasma's Image= must point at to select the package
# tile without adding a duplicate loose tile (trailing slash: KPackage path()s are
# slash-normalised, and PackageListModel::indexOf matches the normalised dir).
WALLPAPER_PACKAGE_DIR = f"{WALLPAPERS_SYSTEM_DIR}/{WALLPAPER_DEFAULT_ID}/"
# The actual image FILE inside that package -- what feh --bg-fill paints (feh cannot
# take a package dir). Same pixels Plasma shows, so the pre-paint is flash-free.
WALLPAPER_IMAGE_FILE = (
    f"{WALLPAPERS_SYSTEM_DIR}/{WALLPAPER_DEFAULT_ID}"
    f"/contents/images/{WALLPAPER_IMAGE_RES}.png"
)
# The asset copied to WALLPAPER_IMAGE_FILE is the same "years" image the package
# ships; steps.py already writes that package image, so the default resolves to a
# file that exists without a second standalone copy.
WALLPAPER_ASSET = "wallpapers/years.png"


def wallpaper_metadata_json(wp_id: str) -> str:
    """Minimal KPackage metadata.json for a custom image wallpaper. Only the
    KPlugin block is required for an image wallpaper (the org.kde.image engine
    reads contents/images/<W>x<H>.png); Id + Name are what the grid shows and what
    the desktop config stores. Name == Id so the grid label reads "years"/"decades"."""
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

# The one privileged launch path shared by the autostart entry + a menu launcher.
INSTALL_WRAPPER_PATH = "/usr/local/bin/azarch-install"

# Installer launcher icon. steps.py copies assets/logo/azarch_installer_icon.png
# (the "Az'" wordmark rendered as a 256x256 app tile) to a SYSTEM icon path so the
# Desktop launcher, the application-menu entry, and the autostart entry can all name
# it. Installed to /usr/share/pixmaps (a standard icon search path that needs no
# theme-cache rebuild) AND to the hicolor 256x256 apps dir; the .desktop files name
# it by its basename ("azarch-installer") so the icon loader resolves either.
INSTALLER_ICON_ASSET = "logo/azarch_installer_icon.png"
INSTALLER_ICON_NAME = "azarch-installer"
INSTALLER_ICON_PIXMAP = f"/usr/share/pixmaps/{INSTALLER_ICON_NAME}.png"
INSTALLER_ICON_HICOLOR = (
    f"/usr/share/icons/hicolor/256x256/apps/{INSTALLER_ICON_NAME}.png"
)


# --- 1. ~/.xinitrc ----------------------------------------------------------
def xinitrc() -> str:
    """Run by `startx` (see ~/.bash_profile). Paints the wallpaper onto the X
    root BEFORE handing the session to Plasma so nothing flashes, then execs the
    Plasma X11 session.

    `DESKTOP_SESSION=plasma` is the one env var the Arch Wiki has you export for
    a startx Plasma session; `startplasma-x11` sets XDG_CURRENT_DESKTOP=KDE
    itself and logind sets XDG_SESSION_TYPE=x11, so nothing else is needed.

    The `feh --bg-fill <wallpaper>` line replaces the old `xsetroot -solid
    <cyan>`: feh can show a PNG (xsetroot only does solid colors), and painting
    the SAME image Plasma will show makes Plasma's own wallpaper repaint
    invisible (identical pixels) -- so there is no cyan/black flash. `--no-fehbg`
    keeps feh from writing a ~/.fehbg helper we do not use."""
    return """\
#!/bin/sh
# ~/.xinitrc -- started by `startx` (see ~/.bash_profile). Hands the X session
# to Plasma (X11). Keep this minimal: per-app launches live in Plasma autostart.

# Make sure user-dir XDG paths resolve for anything the session spawns.
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

# Paint the wallpaper onto the X root FIRST so the first visible frame is the
# wallpaper, not a solid color. Plasma repaints the same image over it moments
# later (identical pixels -> no visible transition, no cyan/black flash). feh is
# shipped in the manifest; xsetroot cannot display a PNG, only solid colors.
[ -x /usr/bin/feh ] && feh --no-fehbg --bg-fill '""" + WALLPAPER_IMAGE_FILE + """'

# The one env var the Arch Wiki has you set for a startx Plasma session.
export DESKTOP_SESSION=plasma

# Replace this shell with the Plasma X11 session; when Plasma exits, X exits and
# control returns to the login shell (which, per bash_profile, logs out the tty).
exec startplasma-x11
"""


# --- 2. /home/main/.bash_profile snippet ------------------------------------
def bash_profile_startx() -> str:
    """Appended to /home/main/.bash_profile. On the FIRST virtual terminal only
    (and only when not already in X) it replaces the login shell with startx, so
    the autologin drops straight into the graphical session. On any other VT or
    an SSH login $DISPLAY is set or $(tty) != /dev/tty1, so the guard is false and
    you get a normal shell -- important for rescue/maintenance use of the ISO."""
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


# --- 3. ~/.config/plasma-org.kde.plasma.desktop-appletsrc -------------------
# Fixed containment ids used across appletsrc + plasmashellrc. Pinned to constants
# so the panel-pin key in plasmashellrc ([PlasmaViews][Panel PANEL_ID]) always
# matches the panel containment number here (a mismatch = the pin is silently
# ignored). 1 = desktop, 2 = bottom panel.
DESKTOP_CONTAINMENT_ID = 1
PANEL_CONTAINMENT_ID = 2

# The three apps pinned to the bottom panel's task manager, in order. The .desktop
# ids are the ones shipped on the installed system: LibreWolf -> librewolf.desktop,
# Kitty -> kitty.desktop, Dolphin -> org.kde.dolphin.desktop (reverse-DNS).
PANEL_LAUNCHERS = [
    "applications:librewolf.desktop",
    "applications:kitty.desktop",
    "applications:org.kde.dolphin.desktop",
]

# Generic, minimal application-menu button icon (NOT the KDE/Plasma "start-here"
# logo the user asked to drop). "application-menu" is a plain hamburger glyph that
# ships with Breeze.
MENU_ICON = "application-menu"

# Kickoff footer power buttons, as session-action ids (systemFavorites). The user
# asked for shutdown/restart/sleep with SLEEP replacing logout. The ids are verified
# from powerdevil/plasma-desktop SystemModel: "suspend" == Sleep, "reboot" == Restart,
# "shutdown" == Shut Down (kickoff labels them exactly that with showActionButtonCaptions).
# NOTE: kickoff renders these in a FIXED order (Suspend, Reboot, Shutdown), not the
# order of this list -- which happens to be the desired left-to-right Sleep/Restart/
# Shut Down anyway; the list's job is only to pick WHICH three appear (no logout).
KICKOFF_SYSTEM_FAVORITES = ["suspend", "reboot", "shutdown"]

# The status widgets on the RIGHT of the panel, placed as STANDALONE panel applets
# (NOT inside an org.kde.plasma.systemtray container). Why standalone instead of a
# tray: the user wanted the internet/audio/etc icons visible but with NO overflow "^"
# expand-arrow AND with the notifications widget gone ENTIRELY. A systemtray fights
# both goals -- it AUTO-DISCOVERS every installed tray plasmoid on first login (so it
# re-adds notifications, plus a camera/virtual-keyboard the user never asked for) and
# it shows the "^" arrow whenever any item is passive. Placing each wanted widget as
# its own panel applet sidesteps all of that: exactly these icons, always visible, no
# arrow, no auto-discovered extras (verified live in a booted VM). Left-to-right on
# the right side (after an expanding spacer), ending at the clock:
#   keyboard-layout, device-notifier, brightness, network, volume.
# Plugin ids verified against plasma-nm/plasma-pa/plasma-workspace/powerdevil.
# The KEYBOARD-LAYOUT indicator is the LEFTMOST of these (the user asked for it "to
# the left of all the icons on the right"); it shows "US"/"HE" from the two configured
# layouts (see kxkbrc()) and clicking it cycles them. Clipboard and battery/power were
# deliberately dropped at the user's request (no clipboard history; power is reached
# from the application menu).
PANEL_STATUS_APPLETS = [
    "org.kde.plasma.keyboardlayout",      # US/HE layout indicator (leftmost)
    "org.kde.plasma.devicenotifier",      # removable devices
    "org.kde.plasma.brightness",          # powerdevil -- brightness
    "org.kde.plasma.networkmanagement",   # plasma-nm  -- internet
    "org.kde.plasma.volume",              # plasma-pa  -- audio
]
# The notifications plasmoid -- the "notification thingy" the user wants gone from the
# WHOLE distro. It is NOT placed on the panel here, and (because it would otherwise be
# auto-discoverable by any systemtray) its plasmoid .so is DELETED from the image
# entirely in configuration/system.CUSTOMIZE_AIROOTFS. Named here so a test can pin
# both that it is not a panel applet and that system.py removes it.
NOTIFICATIONS_APPLET_ID = "org.kde.plasma.notifications"

# The two keyboard layouts the indicator switches between: US English and Hebrew.
# xkb layout codes -> display labels shown in the applet. Alt+Shift toggles them, and
# clicking the panel indicator cycles them. Shipped via ~/.config/kxkbrc; the keyboard
# KDED module reads it at session start, so BOTH layouts are active from first login
# (verified live -- switching updates the indicator US<->HE).
KEYBOARD_LAYOUTS = [
    {"code": "us", "label": "US"},   # English
    {"code": "il", "label": "HE"},   # Hebrew (xkb layout "il")
]
KEYBOARD_TOGGLE = "grp:alt_shift_toggle"

# The keyboard-layout applet's display mode. It exposes exactly ONE config key,
# `displayStyle` (0 = Label/text, 1 = Flag, 2 = LabelOverFlag). In text (Label) mode the
# "US"/"HE" label hangs LOW and looks tilted: the applet centers the text line-box with Qt
# AlignVCenter, which centers the whole line box (including descender space) rather than the
# visible caps, so the letters sit below the tray icons at ANY panel height/scale (this is
# intrinsic to text mode, not a fractional-scaling bug -- scale here is 100%). Flag mode
# renders a flag ICON instead (icons use anchors.fill and center correctly), so it sits
# vertically centered with the other tray icons. Value 1 = Flag -> the US layout shows a
# centered USA flag (screenshot-verified on the live VM; the user specifically likes it).
KEYBOARD_DISPLAY_STYLE = 1  # 1 = Flag (centered icon), fixes the low-hanging text label


# Fixed applet ids in the panel. 1 = menu, 2 = task manager, 3 = expanding spacer,
# then the standalone status applets (PANEL_STATUS_APPLETS) at 4.., then the digital
# clock last. Computed so a change to PANEL_STATUS_APPLETS keeps the clock id / order
# correct.
_MENU_ID = 1
_TASKS_ID = 2
_SPACER_ID = 3
_STATUS_ID_BASE = 4


def plasma_appletsrc() -> str:
    """The full Plasma desktop + panel layout for a fresh profile: the desktop
    containment (with the wallpaper seed) AND a bottom panel carrying, left to right:
    the application menu (Kickoff), a pinned task manager (LibreWolf, Kitty, Dolphin),
    an expanding spacer, then the STANDALONE status applets (keyboard-layout,
    device-notifier, brightness, network, volume), and finally a digital clock.

    NO system tray container. The status widgets are placed as individual panel
    applets on purpose (see PANEL_STATUS_APPLETS): the user wanted these icons visible
    but with NO overflow "^" expand-arrow and NO notifications widget at all. A
    systemtray would auto-discover extra plasmoids (notifications, camera, virtual
    keyboard) and show the "^" arrow for passive items; standalone applets give
    exactly this set, always visible, no arrow (verified live in a booted VM).

    Deliberate OMISSIONS (the user's panel requests):
      * NO org.kde.plasma.showdesktop / minimizeall -> no "Peek at Desktop" button.
      * NO org.kde.plasma.notifications anywhere (also DELETED from the image in
        system.CUSTOMIZE_AIROOTFS) -> notifications gone from the whole distro.
      * NO clipboard and NO battery/power applet (power is reached from the menu).

    Application menu = org.kde.plasma.kickoff (NOT kicker): the user asked for the
    shutdown/restart/sleep buttons on the RIGHT with TEXT LABELS and SLEEP instead of
    logout. That footer -- right-aligned buttons rendered TextBesideIcon -- is a
    kickoff feature (showActionButtonCaptions=true, primaryActions=0 Power,
    systemFavorites=suspend,reboot,shutdown -> "Sleep / Restart / Shut Down"); kicker
    can only draw icon-only power buttons on the LEFT and has no caption key at all.
    For "no categories, just the applications" we use kickoff's List view
    (applicationsDisplay=1) + alphaSort, whose "All Applications" entry is a flat
    A-Z app list (kickoff hardcodes flat:true, so there is no category drill-down).

    The wallpaper lives in the NESTED [Containments][1][Wallpaper][org.kde.image]
    [General] Image= group (a common mistake is the containment's own [General]) and
    points at the package DIRECTORY (WALLPAPER_PACKAGE_DIR), not the inner png, so
    Plasma matches the existing "years" tile instead of injecting a duplicate loose
    tile (see the WALLPAPER_* note above). This appletsrc seed is a BELT; the
    regeneration-proof wallpaper default is the org.kde.image main.xml rewrite in
    configuration/system.CUSTOMIZE_AIROOTFS.

    Written to BOTH the live `main` home and /etc/skel so the live and installed
    users get the same desktop. plasmashell MAY regenerate this on first login with
    its own ids (documented caveat), so the panel-pin/thickness/theme also live in
    their own regeneration-tolerant files (plasmashellrc, kdeglobals)."""
    d = DESKTOP_CONTAINMENT_ID
    p = PANEL_CONTAINMENT_ID
    launchers = ",".join(PANEL_LAUNCHERS)
    system_favorites = ",".join(KICKOFF_SYSTEM_FAVORITES)
    # Status applets get ids 4, 5, ...; the clock is the id right after the last one.
    status_ids = [_STATUS_ID_BASE + i for i in range(len(PANEL_STATUS_APPLETS))]
    clock_id = _STATUS_ID_BASE + len(PANEL_STATUS_APPLETS)
    applet_order = ";".join(
        str(i) for i in [_MENU_ID, _TASKS_ID, _SPACER_ID, *status_ids, clock_id]
    )
    # One block per standalone status applet (keyboard-layout, device-notifier, ...).
    # The keyboard-layout applet additionally gets a [Configuration][General] block
    # pinning displayStyle=Flag (KEYBOARD_DISPLAY_STYLE) so it shows a centered flag
    # icon instead of the low-hanging "US"/"HE" text label (see KEYBOARD_DISPLAY_STYLE).
    _block_parts = []
    for i, item in enumerate(PANEL_STATUS_APPLETS):
        _block_parts.append(
            f"[Containments][{p}][Applets][{status_ids[i]}]\n"
            f"immutability=1\n"
            f"plugin={item}\n"
        )
        if item == "org.kde.plasma.keyboardlayout":
            _block_parts.append(
                f"[Containments][{p}][Applets][{status_ids[i]}][Configuration][General]\n"
                f"displayStyle={KEYBOARD_DISPLAY_STYLE}\n"
            )
    status_blocks = "\n".join(_block_parts)
    return f"""\
[Containments][{d}]
activityId=
formfactor=0
immutability=1
lastScreen=0
location=0
plugin=org.kde.desktopcontainment
wallpaperplugin=org.kde.image

[Containments][{d}][Wallpaper][org.kde.image][General]
Image=file://{WALLPAPER_PACKAGE_DIR}

[Containments][{p}]
activityId=
formfactor=2
immutability=1
lastScreen=0
location=4
plugin=org.kde.panel

[Containments][{p}][General]
AppletOrder={applet_order}

# 1. Application menu (Kickoff): generic icon, flat alphabetical app List, footer
# power buttons labelled on the right = Sleep / Restart / Shut Down (sleep replaces
# logout).
[Containments][{p}][Applets][{_MENU_ID}]
immutability=1
plugin=org.kde.plasma.kickoff

[Containments][{p}][Applets][{_MENU_ID}][Configuration][General]
icon={MENU_ICON}
applicationsDisplay=1
favoritesDisplay=1
alphaSort=true
primaryActions=0
systemFavorites={system_favorites}
showActionButtonCaptions=true
showRecentApps=false
showRecentDocs=false

# 2. Pinned task manager: LibreWolf, Kitty, Dolphin.
[Containments][{p}][Applets][{_TASKS_ID}]
immutability=1
plugin=org.kde.plasma.icontasks

[Containments][{p}][Applets][{_TASKS_ID}][Configuration][General]
launchers={launchers}

# 3. Expanding spacer -- pushes the status applets + clock to the right edge.
[Containments][{p}][Applets][{_SPACER_ID}]
immutability=1
plugin=org.kde.plasma.panelspacer

[Containments][{p}][Applets][{_SPACER_ID}][Configuration][General]
expanding=true

# Standalone status applets (no system tray, no "^" arrow): keyboard-layout (US/HE)
# is the leftmost, then device-notifier, brightness, network, volume.
{status_blocks}
# Digital clock at the right end.
[Containments][{p}][Applets][{clock_id}]
immutability=1
plugin=org.kde.plasma.digitalclock
"""


# Bottom panel height in pixels. Plasma 6's default panel is 44 px; the user asked to
# make the bottom bar bigger. This ALSO sizes the left launcher/task icons: on Plasma
# there is no independent icon-size key for the kickoff launcher + icontasks manager --
# their icons are the panel thickness minus small margins, so a taller panel = bigger
# left icons. The settled-on value is 60 (an initial 2x/88 looked too tall in the VM;
# 55 was an intermediate value, then bumped to 60 for ~10% bigger left icons -- both
# verified live via ffmpeg x11grab screenshots).
#
# CRUCIAL Plasma-6 quirk (verified against plasma-workspace shell/panelview.cpp AND
# empirically in a booted VM): the panel HEIGHT key `thickness` is read from the
# SCREEN-INDEPENDENT nested group [PlasmaViews][Panel <id>][Defaults] -- NOT the flat
# [PlasmaViews][Panel <id>] group. `floating` IS read from the flat group. Writing
# thickness in the flat group (the obvious place) is SILENTLY IGNORED -- the panel
# stays 44 px. So floating goes flat, thickness goes under [Defaults].
PANEL_DEFAULT_THICKNESS = 44
PANEL_THICKNESS = 60   # taller than the 44 px default (bigger left icons), verified live


# --- 3b. ~/.config/plasmashellrc (panel pinned, not floating) ---------------
def plasmashellrc() -> str:
    """Pin the bottom panel (NOT floating) and set its HEIGHT. Neither is in appletsrc
    -- plasma-workspace writes them to plasmashellrc under [PlasmaViews][Panel <id>]:

      * `floating` (0 = pinned, 1 = floating) in the FLAT [PlasmaViews][Panel <id>] group.
      * `thickness` (panel height px) in the NESTED [PlasmaViews][Panel <id>][Defaults]
        subgroup. Plasma 6's PanelView::restore() reads thickness from configDefaults()
        == the "Defaults" subgroup; a flat `thickness=` is silently ignored (verified
        live: the panel stayed 44 px until the key moved under [Defaults]).

    The Panel id MUST match PANEL_CONTAINMENT_ID in appletsrc or the keys are ignored.
    thickness=60 makes the bottom bar taller than the 44 px default (and the left
    launcher/task icons ~10% bigger, since their size tracks the panel height), per the
    user's "make it bigger / bigger left icons" request. Shipped to the live home and
    /etc/skel."""
    return f"""\
[PlasmaViews][Panel {PANEL_CONTAINMENT_ID}]
floating=0

[PlasmaViews][Panel {PANEL_CONTAINMENT_ID}][Defaults]
thickness={PANEL_THICKNESS}
"""


# --- 3c. ~/.config/kdeglobals (Breeze Dark global theme) --------------------
def kdeglobals() -> str:
    """Set the global theme to Breeze Dark for a fresh profile. The look-and-feel
    package + color scheme are what darken the whole session; the icon theme and
    widget style are seeded too so nothing falls back to a light default before the
    LnF fully applies. Shipped to the live home and /etc/skel."""
    return """\
[General]
ColorScheme=BreezeDark
Name=Breeze Dark

[Icons]
Theme=breeze-dark

[KDE]
LookAndFeelPackage=org.kde.breezedark.desktop
widgetStyle=Breeze
"""


# --- 3d. ~/.config/krunnerrc (menu/search: installed applications only) ------
def krunnerrc() -> str:
    """Restrict search to INSTALLED APPLICATIONS only. Kicker's useExtraRunners=false
    already limits its own search to the applications runner, but this is the
    system-level belt: disable every KRunner plugin except the applications
    (krunner_services) runner, so neither the menu search nor Alt-Space surfaces
    files, bookmarks, shell commands, web shortcuts, etc. Shipped to live home and
    /etc/skel."""
    disabled = [
        "baloosearch", "krunner_bookmarksrunner", "krunner_recentdocuments",
        "krunner_locations", "krunner_places", "krunner_shell", "krunner_kill2",
        "krunner_powerdevil", "krunner_sessions", "krunner_calculator",
        "krunner_unitconverter", "krunner_dictionary", "krunner_webshortcuts",
        "krunner_windows", "krunner_appstream", "krunner_activities",
        "krunner_charrunner", "krunner_katesessions", "krunner_konsoleprofiles",
    ]
    lines = ["[Plugins]", "krunner_servicesEnabled=true"]
    lines += [f"{name}Enabled=false" for name in disabled]
    return "\n".join(lines) + "\n"


# --- 3e. ~/.config/kxkbrc (keyboard layouts: US + Hebrew) -------------------
def kxkbrc() -> str:
    """Configure the two keyboard layouts the panel's keyboard-layout applet switches
    between: US English and Hebrew (xkb "us" + "il"), shown as "US"/"HE". The Plasma
    keyboard KDED module reads this at session start, so BOTH layouts are active from
    first login and the panel indicator + Alt+Shift toggle (and clicking the indicator)
    switch between them (verified live: switching updates the indicator US<->HE).

    Keys (Plasma keyboard KCM / kxkbrc [Layout] group):
      * Use=true              -- enable custom layout configuration.
      * LayoutList=us,il      -- the xkb layout codes, in order (us first == default).
      * DisplayNames=US,HE    -- the labels the applet shows for each layout.
      * Options=grp:alt_shift_toggle -- Alt+Shift cycles layouts.
      * SwitchMode=Global     -- one active layout for the whole session (not per-window).
    Shipped to the live home and /etc/skel.

    LIVE-SESSION ONLY: this fixed us,il is correct for the live medium's default
    (Asia/Jerusalem) desktop, but on a Calamares INSTALL it must NOT survive -- the
    OFFLINE install copies /home/main verbatim (unpackfs/reuseHome), and on the
    installed Plasma session kded reads ~/.config/kxkbrc as AUTHORITATIVE, overriding
    the region-correct /etc/X11/xorg.conf.d/00-keyboard.conf Calamares wrote for the
    user's chosen region (so every install would come up us,il regardless of region).
    The Calamares shellprocess step therefore DELETES this file (home + skel) on the
    target so the region keyboard governs -- see configuration/calamares_shellprocess.
    INSTALLED_KXKBRC. (The archinstall path is English-only "us" and unaffected.)"""
    codes = ",".join(l["code"] for l in KEYBOARD_LAYOUTS)
    labels = ",".join(l["label"] for l in KEYBOARD_LAYOUTS)
    return f"""\
[Layout]
Use=true
LayoutList={codes}
DisplayNames={labels}
Options={KEYBOARD_TOGGLE}
ResetOldOptions=true
SwitchMode=Global
"""


# --- 3f. ~/.config/plasma-localerc (Plasma date format: d/m/y) --------------
# The date/time locale Plasma uses to FORMAT the digital clock + calendar, kept
# equal to the system LC_TIME (configuration/locale.DEFAULT_TIME_LOCALE) so the KDE
# clock reads day/month/year like the rest of the system. Imported so the two never
# drift.
from .locale import DEFAULT_TIME_LOCALE as _TIME_LOCALE  # noqa: E402


def plasma_localerc() -> str:
    """Set the Plasma per-session date/time format to day/month/year, matching the
    system LC_TIME (en_GB.UTF-8) so the panel's digital clock and calendar show
    dates as d/m/y (the user's "modify timedate from m/d/y to d/m/y" request) --
    not the en_US m/d/y default.

    Plasma's regional-formats KCM writes ~/.config/plasma-localerc; the digital
    clock reads its date/time format from the [Formats] group's LC_TIME. Setting
    LC_TIME=en_GB.UTF-8 there (English, but d/m/y) flips the clock's date order
    without changing the display language. `useDetailedLocales=true` tells Plasma to
    honour the per-category [Formats] overrides rather than a single global locale.

    This is the Plasma complement to the system-wide LC_TIME set for the LIVE ISO in
    configuration/locale; both use DEFAULT_TIME_LOCALE so the live desktop clock reads
    d/m/y. (On a Calamares install the target's LC_* now follows the region the user
    picked on the Location page -- the old forced-en_GB shellprocess step was removed
    so the region's date/number locale survives; see configuration/calamares.) Shipped
    to the live home and /etc/skel so live/default users inherit the d/m/y clock."""
    return f"""\
[Formats]
LC_TIME={_TIME_LOCALE}
useDetailedLocales=true
"""


# --- 3g. ~/.config/powerdevilrc (PowerDevil power policy, Plasma 6 schema) ---
# Idle-suspend delay on battery, in SECONDS. Plasma 6's PowerDevil profile schema
# (PowerDevilProfileSettings.kcfg -> kcfgfile "powerdevilrc") uses the key
# AutoSuspendIdleTimeoutSec in SECONDS -- NOT the old Plasma-5
# [SuspendSession] idleTime in milliseconds. 15 minutes == 900. Kept equal to the
# logind IdleActionSec the console policy uses (configuration/system.SLEEP_POLICY_IDLE_SECONDS),
# so Plasma and the bare console agree on the 15-minute laptop-on-battery timeout.
POWERDEVIL_BATTERY_IDLE_SECONDS = 900  # 15 minutes

# PowerDevil action enum values (daemon/powerdevilenums.h, verified against
# powerdevil 6.7.4): NoAction=0, Sleep=1 (suspend-to-RAM), Hibernate=2, Shutdown=8.
# Shared by AutoSuspendAction / PowerButtonAction / PowerDownAction (all UInt).
_POWERDEVIL_NO_ACTION = 0        # never / do nothing
_POWERDEVIL_SLEEP = 1            # suspend-to-RAM
_POWERDEVIL_SHUTDOWN = 8         # clean poweroff

# IMPORTANT (Plasma 6 vs Plasma 5): the file that PowerDevil 6 actually reads for
# live per-profile policy is `powerdevilrc` (PowerDevilProfileSettings.kcfg declares
# <kcfgfile name="powerdevilrc">). The old `powermanagementprofilesrc` is read ONCE by
# daemon/powerdevilmigrateconfig.cpp for a one-shot Plasma-5 -> 6 migration and then
# ignored for policy. Its subgroup schema ([<profile>][SuspendSession] with idleTime in
# ms, suspendType) is the DEAD Plasma-5 format. Shipping only that file silently does
# nothing on a fresh Plasma-6 install (and worse: an EMPTY [AC] group is skipped by the
# migrator, so AC falls to PowerDevil-6 defaults = suspend-on-AC + screen-off, the exact
# OPPOSITE of "PC never sleeps"). So the real settings go in `powerdevilrc` below, and
# powermanagement_migration_flag() ships the migration-done flag so a first-boot
# migration can never re-run and layer stale deltas onto our hand-written powerdevilrc.


def powerdevilrc() -> str:
    """PowerDevil per-profile power policy for the INSTALLED Plasma desktop (Plasma 6
    `powerdevilrc` schema), aligning KDE's own power manager with the user's requests
    (PROMPT.md sections 1-3) and the PC-vs-laptop sleep rule:

      * AC profile (plugged in, and the ONLY active profile on a desktop PC with no
        battery):
          - Display -> TurnOffDisplayWhenIdle=false: the screen NEVER turns off on AC.
            This key DEFAULTS TO TRUE in Plasma 6, so omitting it would blank the screen
            (~5-10 min default) -- it MUST be written false explicitly (PROMPT.md #1).
          - SuspendAndShutdown -> AutoSuspendAction=0 (NoAction): never idle-suspend on
            AC. Unlike the old schema, omitting this does NOT mean "never" -- the Plasma-6
            default idle-suspends on AC, so 0 is written explicitly (PROMPT.md #3).
          - SuspendAndShutdown -> PowerButtonAction=8 (Shutdown): the power button does a
            clean poweroff (PROMPT.md #2). PowerDevil block-inhibits logind's
            handle-power-key, so in a Plasma session THIS key -- not the logind drop-in --
            governs the button; the logind HandlePowerKey=poweroff (system.py) still
            covers the bare console / non-Plasma case.
          - SuspendAndShutdown -> PowerDownAction=0 (NoAction): pinned off for safety
            (its default is the logout-prompt); matches the VM's applied config.
        Net: "PC never sleeps", "laptop plugged in never sleeps", screen never blanks.

      * Battery profile (laptop, unplugged):
          - Display -> DimDisplayWhenIdle=false + TurnOffDisplayWhenIdle=false: do not
            dim or blank on battery either (matches the applied VM config).
          - SuspendAndShutdown -> AutoSuspendAction=1 (Sleep) + AutoSuspendIdleTimeoutSec
            =900 (SECONDS): suspend-to-RAM after 15 minutes idle == "laptop unplugged
            sleeps after 15 minutes".
          - PowerButtonAction=8: the power button shuts down on battery too (deliberate
            parity with AC, rather than leaving the Plasma-6 logout-prompt default).

    PowerDevil auto-detects the chassis: on a battery-less PC the Battery profile is
    never activated (there is no battery to be on), so only the AC profile ever applies
    -> the PC never sleeps without any explicit chassis check here. On a laptop,
    unplugging switches PowerDevil to the Battery profile (15-min suspend) and plugging
    in switches back to the AC profile (no suspend), live.

    This is the Plasma-session complement to the DE-independent logind IdleAction policy
    (configuration/system.SLEEP_POLICY_SCRIPT), which covers the bare console / live ISO;
    both encode the same 15-minute-on-battery / never-on-AC rule so behaviour is identical
    whether or not Plasma is running. Shipped to the live home and /etc/skel (so installed
    users inherit it).

    Schema note (Plasma 6): on-disk headers are [<profile>][Display] and
    [<profile>][SuspendAndShutdown] with PascalCase keys; the profile id is literally
    AC / Battery. Verified against powerdevil 6.7.4 (PowerDevilProfileSettings.kcfg,
    daemon/powerdevilenums.h) AND read back from the live VM's applied ~/.config/powerdevilrc."""
    return f"""\
[AC][Display]
TurnOffDisplayWhenIdle=false

[AC][SuspendAndShutdown]
AutoSuspendAction={_POWERDEVIL_NO_ACTION}
PowerButtonAction={_POWERDEVIL_SHUTDOWN}
PowerDownAction={_POWERDEVIL_NO_ACTION}

[Battery][Display]
DimDisplayWhenIdle=false
TurnOffDisplayWhenIdle=false

[Battery][SuspendAndShutdown]
AutoSuspendAction={_POWERDEVIL_SLEEP}
AutoSuspendIdleTimeoutSec={POWERDEVIL_BATTERY_IDLE_SECONDS}
PowerButtonAction={_POWERDEVIL_SHUTDOWN}
PowerDownAction={_POWERDEVIL_NO_ACTION}
"""


# --- 3g-bis. ~/.config/powermanagementprofilesrc (migration-done flag only) --
def powermanagement_migration_flag() -> str:
    """Ship `powermanagementprofilesrc` containing ONLY the Plasma-5 -> 6
    migration-done flag, so PowerDevil's one-shot migrator never runs on first boot.

    Why this is needed as a BELT for powerdevilrc: PowerDevil calls migrateProfilesConfig()
    on every daemon start; it is gated solely by `if migrationGroup.hasKey("Migrated
    ProfilesToPlasma6") return;`. If that flag is ABSENT on a fresh install, the migrator
    runs -- and although with no old profile groups it writes nothing (so it would not, in
    fact, clobber our hand-written powerdevilrc), shipping the flag makes the outcome
    independent of that reasoning and of any future stray old-schema file: the migrator is
    a guaranteed no-op. Value string is exactly what a migrated system records
    (verified on the live VM: `[Migration] MigratedProfilesToPlasma6=powerdevilrc`).

    This file therefore carries NO power policy at all (that lives in powerdevilrc); it is
    purely the migration guard. Shipped to the live home and /etc/skel."""
    return """\
[Migration]
MigratedProfilesToPlasma6=powerdevilrc
"""


# --- 3h. ~/.config/kscreenlockerrc (disable screen auto-lock) ---------------
def kscreenlockerrc() -> str:
    """Disable KDE's automatic screen locker.

    This is a DIFFERENT subsystem from PowerDevil and was the ACTUAL cause of the
    screen "going to sleep" (PROMPT.md #4): the KScreenLocker daemon defaults to
    auto-lock ON at 5 minutes, and locking BLANKS the display -- so even with
    PowerDevil's screen-off disabled and idle-suspend off, the screen still went black
    after ~5 min. It is NOT a real suspend (proven via journalctl: zero
    "Entering sleep"/"Starting Suspend" events); it is the locker blanking the screen.
    KScreenLocker reads ~/.config/kscreenlockerrc; when that file is ABSENT, KDE uses
    its built-in default (auto-lock ON, 5 min), so the fix is to SHIP the file with
    auto-lock turned off.

    Keys (KScreenLocker [Daemon] group):
      * Autolock=false     -- do not auto-lock the session at all.
      * Timeout=0          -- belt: zero-minute timeout (no idle lock) even if Autolock
                              were re-enabled.
      * LockOnResume=false -- do not force a lock screen after resume/wake.

    Three independent KDE subsystems can black the screen -- PowerDevil "Turn off
    screen" (Display), PowerDevil idle-suspend (SuspendAndShutdown), and this screen
    LOCKER -- and fixing one does not fix the others; all three are handled (powerdevilrc
    + this file). Shipped to the live home and /etc/skel so live/default users inherit
    a lock-free desktop."""
    return """\
[Daemon]
Autolock=false
LockOnResume=false
Timeout=0
"""


# --- 4. ~/.config/ksplashrc -------------------------------------------------
def ksplashrc() -> str:
    """Disable the Plasma startup splash (KSplash). `startplasma-x11` would
    otherwise show a full-screen splash while the session loads; turning it off
    means the only thing painted between the wallpaper root-pixmap (set in
    ~/.xinitrc) and the live desktop is the wallpaper itself -- no splash frame,
    no flash. Shipped to the live home and /etc/skel."""
    return """\
[KSplash]
Engine=none
Theme=None
"""


# --- 5. ~/.config/autostart/azarch-install.desktop --------------------------
def autostart_install_desktop() -> str:
    """Plasma autostart entry that opens the Calamares installer ONCE at session
    login, Manjaro-style, via the privileged wrapper (Calamares must run as root;
    see INSTALL_WRAPPER_PATH). Plasma reads ~/.config/autostart/*.desktop and
    runs each `Exec=` after the session is up.

    X-KDE-autostart-phase=2 delays it until the desktop/panel are ready so the
    installer window has a session to map into. It is a normal .desktop launcher,
    so it does not depend on the wrapper's exec bit the way a sourced sh autostart
    did."""
    return """\
[Desktop Entry]
Type=Application
Name=Az'arch Linux Installer
Comment=Launch the Az'arch Linux installer
Exec=""" + INSTALL_WRAPPER_PATH + """
Icon=""" + INSTALLER_ICON_NAME + """
Terminal=false
X-KDE-autostart-phase=2
X-GNOME-Autostart-enabled=true
NoDisplay=false
"""


# --- 6. /usr/share/applications/azarch-install.desktop ----------------------
def install_menu_desktop() -> str:
    """A launcher in the application menu (Kickoff) so the installer can be
    re-opened after it is closed, sharing the same privileged wrapper. Lands in
    /usr/share/applications (system-wide), so it is not a per-user file."""
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


# --- 6b. ~/Desktop/azarch-install.desktop (live-session Desktop launcher) ----
def desktop_installer_launcher() -> str:
    """A double-clickable "Az'arch Linux Installer" launcher that sits ON the live-session
    Desktop, so the installer is one obvious icon away even after the autostart
    window is closed. Uses the same privileged wrapper and the "Az'" app icon.

    TRUST (no warning badge, no launch prompt): KDE Plasma paints an
    "emblem-important" WARNING BADGE over a Desktop .desktop launcher -- and prompts
    before running it -- whenever KDesktopFile::isAuthorizedDesktopFile() is false,
    which for a user-owned Exec= launcher means "not executable". The badge is what
    the user saw ("weird warning icon that disappears once you open the installer" --
    it vanishes because the first launch marks the file trusted). The launcher must
    therefore ship EXECUTABLE. Two things are required and BOTH matter:
      * PLAN mode 0o755 (below), and -- crucially --
      * an /etc/skel + /home/main FILE_PERMISSIONS pin in configuration/profile.py,
        because archiso NORMALIZES overlay modes to 0644 in the squashfs unless a
        path is pinned there. The 0o755 in PLAN alone is silently downgraded to 0644
        by mkarchiso (the exact same gotcha documented for /usr/local/bin/azarch-
        install), which is why the badge appeared even though PLAN said 0o755.
    (KDE reads NO `user.xdg.trusted` xattr -- that is a GNOME concept; the exec bit /
    root ownership is the only trust signal. The launcher is generated by us on the
    ISO, not downloaded, so shipping it pre-trusted is safe.)"""
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


# --- 7. /usr/local/bin/azarch (guest-side CLI) ------------------------------
AZARCH_BIN_PATH = "/usr/local/bin/azarch"


def azarch_sh() -> str:
    """Guest-side CLI shipped on the live ISO (and the installed system via
    /etc/skel or the installer copy). Subcommands:

    azarch --sshd-hypervisor
      Installs the host's public key from ~/shared/authorized_keys (staged
      there by 'hypervisor install') into ~/.ssh/authorized_keys, then enables
      and starts sshd. Safe to run more than once. (The subcommand is named
      --sshd-hypervisor because it wires the guest sshd up for the hypervisor's
      forwarded host->guest SSH port; the host side is hypervisor.cfg's
      sshd_hypervisor toggle.)

    azarch --resolve-region / --resolve-date-time / --resolve-language
      The ONLY things that ping an external server to geolocate the machine and
      update its region settings (everything else in Az'arch is static/user-chosen
      -- the installer and boot never auto-resolve). Each presents a list of 5
      SHUFFLED IP-geolocation servers; the user picks one, it is queried for the
      country code + timezone, and the system is updated:
        --resolve-date-time  set the timezone to match the IP.
        --resolve-language   set the language to English + the region's language
                             (English ONLY if the region is English-speaking), i.e.
                             a second keyboard layout with Alt+Shift + the locale.
        --resolve-region     do both.
      The country -> (locale, keyboard layout) map is embedded from
      configuration/locale.RESOLVER_COUNTRY_TABLE (the single source of truth).
    """
    # Embed the resolver's country table (CC|locale|layout|keymap|english) so the
    # shell can map an IP-geolocated country onto a locale + keyboard layout without
    # any Python at runtime. Single source of truth: configuration/locale.
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

    # Enable + generate the needed locales (English always; the region locale too
    # when non-English). LANG stays English (en_US) -- only the region format locale
    # (LC_*) follows the country, matching the installer's "English UI + region
    # numbers/dates" behaviour.
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

    # Keyboard: English ("us") first/active; the region layout as a switchable
    # SECOND (Alt+Shift) when non-English. English-speaking -> "us" only.
    if [ "$english" = "0" ] && [ "$layout" != "us" ]; then
        xkb_layout="us,$layout"
        xkb_opts='    Option "XkbOptions" "grp:alt_shift_toggle"'
        vconsole_map="$keymap"
    else
        xkb_layout="us"
        xkb_opts=""
        vconsole_map="us"
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

    # Apply the keyboard to the LIVE X11 session too (so it takes effect now, not
    # just after re-login), when an X server + setxkbmap are available.
    if [ -n "${{DISPLAY:-}}" ] && command -v setxkbmap >/dev/null 2>&1; then
        if [ "$xkb_layout" = "us" ]; then
            setxkbmap -layout us 2>/dev/null || true
        else
            setxkbmap -layout "$xkb_layout" -option grp:alt_shift_toggle 2>/dev/null || true
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
        # invocation is 'sudo azarch --sshd-hypervisor', under which $HOME is /root and $USER
        # is root -- so keying off $HOME would stage the pubkey into /root/.ssh and
        # the 'main' login (whose sshd reads /home/main/.ssh) would still be locked
        # out. $SUDO_USER is the invoking user under sudo; fall back to the current
        # user when run without sudo. Refuse a bare-root target: there is no home
        # pubkey login for root here (blank password, PermitRootLogin prohibit-pw).
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
        # host->guest :22 connection is dropped unless we open it here. Do this
        # before starting sshd so the port is reachable the moment it listens.
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


# --- 8. /usr/local/bin/azarch-install (privileged Calamares launcher) -------
def install_wrapper_sh() -> str:
    """The single privileged launch path for Calamares, used by both the Plasma
    autostart entry and the application-menu launcher. On the live medium `main`
    has passwordless sudo, so `sudo -E calamares` is the correct, dependency-free
    way to get root for the GUI installer. Plasma DOES run polkit-kde-agent (so
    pkexec would also work), but keeping `sudo -E` avoids depending on the agent
    being up before the autostart phase fires and matches the prior behavior.

    -E preserves the X env (DISPLAY, XAUTHORITY, XDG_*) so the root-owned
    Calamares Qt process can connect to `main`'s X server.

    We deliberately do NOT pass `-c /etc/calamares`. Despite its name, `-c` is a
    testing-only flag that overrides Calamares' *application data* directory, not
    just the configuration tree: once set, Calamares looks for qml/, branding/ and
    settings.conf ONLY under that dir and skips the normal /usr/share/calamares
    fallback. Our QML ships at /usr/share/calamares/qml (there is no
    /etc/calamares/qml), so `-c /etc/calamares` made Calamares die at startup with
    "FATAL: explicitly configured application data directory is missing qml/".
    With no `-c`, Calamares reads /etc/calamares/settings.conf and branding by
    default (that IS the sysconfdir it checks first) and finds QML under
    /usr/share, so the installer launches correctly."""
    return """\
#!/bin/sh
# azarch-install -- privileged Calamares launcher for the live session.
# `main` has passwordless sudo on the live medium, so this needs no polkit agent.
#
# XDG_RUNTIME_DIR is unset before elevating: `sudo -E` would otherwise pass
# main's /run/user/1000 through to the root Qt process, which then logs a
# "runtime directory is owned by uid 1000, not 0" warning. DISPLAY/XAUTHORITY
# (the load-bearing X vars) are still preserved by -E, and root can read main's
# ~/.Xauthority, so Calamares connects to the running X server fine.
#
# No `-c /etc/calamares`: that flag overrides the app-data dir and makes Calamares
# look for qml/ under /etc/calamares (which does not exist), a fatal startup error.
# Calamares already reads /etc/calamares/settings.conf and branding by default.
unset XDG_RUNTIME_DIR
exec sudo -E calamares
"""


# --- 9. Emit plan -----------------------------------------------------------
# Declarative map so steps.py can iterate. Each entry: the builder function that
# produces the content, the DESTINATION (absolute, or $HOME-relative for the live
# `main` user), and the file MODE. `owner` records the intended chown so steps.py
# knows which files fall under the /home/main (uid 1000, gid 998) handback.
#
# HOME-relative paths are given relative to /home/main so the airootfs overlay
# lands them under airootfs/home/main/...; steps.py chowns that whole tree
# 1000:998 after emit (as it already does for the fastfetch/first-boot payloads).
# Absolute paths (/usr/local/bin/..., /usr/share/...) stay root-owned (0:0) --
# do NOT chown them.

# scripts -> 0o755, configs -> 0o644.
_EXEC = 0o755
_CONF = 0o644

# Home directory of the live user; the overlay root for HOME-relative entries.
HOME = "/home/main"
# uid:gid for the live user tree (autologin group gid 998).
HOME_OWNER = (1000, 998)

# Each PLAN entry is a dict for readability in steps.py:
#   builder: callable() -> str content
#   dest:    absolute path in the airootfs (already resolved under /home/main
#            for user files, so steps.py just prefixes the airootfs root)
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
        "builder": plasma_appletsrc,
        "dest": f"{HOME}/.config/plasma-org.kde.plasma.desktop-appletsrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": ksplashrc,
        "dest": f"{HOME}/.config/ksplashrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": plasmashellrc,
        "dest": f"{HOME}/.config/plasmashellrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": kdeglobals,
        "dest": f"{HOME}/.config/kdeglobals",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": krunnerrc,
        "dest": f"{HOME}/.config/krunnerrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": kxkbrc,
        "dest": f"{HOME}/.config/kxkbrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        # Plasma date format: day/month/year in the clock/calendar (matches system
        # LC_TIME). The user's "modify timedate from m/d/y to d/m/y" request.
        "builder": plasma_localerc,
        "dest": f"{HOME}/.config/plasma-localerc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        # PowerDevil power policy (Plasma 6 `powerdevilrc` schema): never suspend or
        # blank the screen on AC/PC, suspend after 15 min on battery (laptop unplugged),
        # power button = Shut Down. Plasma-session complement to the logind policy.
        "builder": powerdevilrc,
        "dest": f"{HOME}/.config/powerdevilrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        # Migration-done flag ONLY (no policy): stops PowerDevil's one-shot Plasma-5 ->
        # 6 migrator from ever running on first boot, so it can never layer stale deltas
        # onto the hand-written powerdevilrc above.
        "builder": powermanagement_migration_flag,
        "dest": f"{HOME}/.config/powermanagementprofilesrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        # Disable KDE's automatic screen locker -- the ACTUAL cause of the ~5-min screen
        # blank (a locker default, separate from PowerDevil). Without this file KDE
        # auto-locks at 5 min and blanks the display.
        "builder": kscreenlockerrc,
        "dest": f"{HOME}/.config/kscreenlockerrc",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": autostart_install_desktop,
        "dest": f"{HOME}/.config/autostart/azarch-install.desktop",
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
        # The Desktop launcher must be EXECUTABLE (0o755) so Plasma launches it on
        # double-click without the untrusted-.desktop security prompt.
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
# writes it as the full file content of /home/main/.bash_profile (there is no
# stock one in the airootfs to preserve), mode 0644, owner "home".
BASH_PROFILE_DEST = f"{HOME}/.bash_profile"


def emit_plan() -> list[dict]:
    """Return the PLAN list (builder/dest/mode/owner) plus the .bash_profile
    entry, so steps.py can iterate a single sequence. Kept as a function (not
    just the module constant) to mirror the builder-function style of the other
    configuration modules and to keep the .bash_profile special-case in one place."""
    return PLAN + [
        {
            "builder": bash_profile_startx,
            "dest": BASH_PROFILE_DEST,
            "mode": _CONF,
            "owner": "home",
        },
    ]
