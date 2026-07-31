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

# The DEFAULT wallpaper baked into the ISO -- the "years" image. It points at the
# "years" KPackAGE's own image file (NOT a separate /usr/share/azarch/wallpaper.png).
# Why: Plasma's wallpaper grid lists, in addition to the installed KPackages, the
# CURRENT image as its own tile labelled by the image's filename. Pointing the
# default at a standalone `wallpaper.png` therefore made the grid show THREE tiles
# -- "years", "decades", and a duplicate "wallpaper" (the same image as years). By
# pointing the default at the years package's image path instead, Plasma recognises
# it as the existing "years" tile, so the grid shows exactly the TWO packages with
# "years" pre-selected. The ~/.xinitrc feh pre-paint + appletsrc Image= + the
# org.kde.image main.xml default all reference this same path.
WALLPAPER_DEFAULT_ID = "years"
WALLPAPER_DEST = (
    f"{WALLPAPERS_SYSTEM_DIR}/{WALLPAPER_DEFAULT_ID}"
    f"/contents/images/{WALLPAPER_IMAGE_RES}.png"
)
# The asset copied to WALLPAPER_DEST is the same "years" image the package ships;
# steps.py already writes that package image, so the default resolves to a file that
# exists without a second standalone copy.
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
[ -x /usr/bin/feh ] && feh --no-fehbg --bg-fill '""" + WALLPAPER_DEST + """'

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


def plasma_appletsrc() -> str:
    """The full Plasma desktop + panel layout for a fresh profile: the desktop
    containment (with the wallpaper seed) AND a bottom panel carrying, left to
    right, the application menu (Kicker), a pinned task manager (LibreWolf, Kitty,
    Dolphin), a spacer, and a digital clock.

    Deliberate OMISSIONS (the user's panel requests):
      * NO org.kde.plasma.systemtray  -> no "Status and Notifications" tray/arrow.
      * NO org.kde.plasma.showdesktop -> no "Peek at Desktop" button.
    An applet is present ONLY if it appears in a [Containments][2][Applets][N] block,
    so omitting these blocks IS how they are removed (there is no hide key).

    Application menu = org.kde.plasma.kicker (NOT kickoff): kicker has no user/avatar
    header and can flatten categories (limitDepth) into a near-flat alphabetical app
    list with a search field at the top -- kickoff cannot hide its Favorites/Places/
    Sessions tabs, its category tree, or its user header at all. See kicker config
    below for the flat-list + apps-only-search keys.

    The wallpaper still lives in the NESTED [Containments][1][Wallpaper][org.kde.image]
    [General] Image= group (a common mistake is the containment's own [General]).
    This appletsrc seed is a BELT; the regeneration-proof wallpaper default is the
    org.kde.image main.xml rewrite in configuration/system.CUSTOMIZE_AIROOTFS.

    Written to BOTH the live `main` home and /etc/skel so the live and installed
    users get the same desktop. plasmashell MAY regenerate this on first login with
    its own ids (documented caveat), so the panel-pin/theme also live in their own
    regeneration-tolerant files (plasmashellrc, kdeglobals)."""
    d = DESKTOP_CONTAINMENT_ID
    p = PANEL_CONTAINMENT_ID
    launchers = ",".join(PANEL_LAUNCHERS)
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
Image=file://{WALLPAPER_DEST}

[Containments][{p}]
activityId=
formfactor=2
immutability=1
lastScreen=0
location=4
plugin=org.kde.panel

[Containments][{p}][General]
AppletOrder=1;2;3

# Application menu (Kicker): generic icon, flattened categories, alphabetical, and
# search restricted to installed applications (useExtraRunners=false).
[Containments][{p}][Applets][1]
immutability=1
plugin=org.kde.plasma.kicker

[Containments][{p}][Applets][1][Configuration][General]
icon={MENU_ICON}
useCustomButtonImage=false
limitDepth=true
alphaSort=true
appNameFormat=0
showRecentApps=false
showRecentDocs=false
showRecentContacts=false
favoritesPortedToKAstats=true
useExtraRunners=false

# Pinned task manager: LibreWolf, Kitty, Dolphin.
[Containments][{p}][Applets][2]
immutability=1
plugin=org.kde.plasma.icontasks

[Containments][{p}][Applets][2][Configuration][General]
launchers={launchers}

# Digital clock at the right end.
[Containments][{p}][Applets][3]
immutability=1
plugin=org.kde.plasma.digitalclock
"""


# --- 3b. ~/.config/plasmashellrc (panel pinned, not floating) ---------------
def plasmashellrc() -> str:
    """Pin the bottom panel (NOT floating). The float/pin toggle is NOT in
    appletsrc -- plasma-workspace writes it to plasmashellrc under
    [PlasmaViews][Panel <containment-id>] as an int (0 = pinned, 1 = floating).
    The Panel id MUST match PANEL_CONTAINMENT_ID in appletsrc or the pin is
    silently ignored. Shipped to the live home and /etc/skel."""
    return f"""\
[PlasmaViews][Panel {PANEL_CONTAINMENT_ID}]
floating=0
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
Name=Azarch Installer
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
Name=Azarch Installer
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
    """A double-clickable "Azarch Installer" launcher that sits ON the live-session
    Desktop, so the installer is one obvious icon away even after the autostart
    window is closed. Uses the same privileged wrapper and the "Az'" app icon.

    It is written 0o755 (executable) AND carries the KDE trust marker below so
    Plasma launches it directly instead of showing the "This .desktop file was
    downloaded/is not trusted -- Continue/Cancel?" security prompt on first click:
      * mode 0o755 (see PLAN owner/mode) -- KDE treats a world-executable local
        .desktop as launchable, and
      * X-KDE-AuthorizeExecute / the file being under the user's own Desktop with
        the exec bit is what suppresses the untrusted-launcher dialog.
    (On Plasma the exec bit is the load-bearing part; the launcher is generated by
    us on the ISO, not downloaded, so this is safe.)"""
    return """\
[Desktop Entry]
Type=Application
Name=Azarch Installer
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
    /etc/skel or the installer copy). Only subcommand so far: --sshd-hypervisor.

    azarch --sshd-hypervisor
      Installs the host's public key from ~/shared/authorized_keys (staged
      there by 'hypervisor install') into ~/.ssh/authorized_keys, then enables
      and starts sshd. Safe to run more than once. (The subcommand is named
      --sshd-hypervisor because it wires the guest sshd up for the hypervisor's
      forwarded host->guest SSH port; the host side is hypervisor.cfg's
      sshd_hypervisor toggle.)
    """
    return """\
#!/bin/sh
# azarch -- guest-side helper CLI.

set -eu

usage() {
    printf 'Usage: azarch <command>\\n'
    printf '\\n'
    printf 'Commands:\\n'
    printf '  --sshd-hypervisor    Install host pubkey from ~/shared/authorized_keys and start sshd\\n'
}

cmd="${1:-}"

case "$cmd" in
    --sshd-hypervisor)
        # Resolve the REAL login user, not whoever the shell says. The documented
        # invocation is 'sudo azarch --sshd-hypervisor', under which $HOME is /root and $USER
        # is root -- so keying off $HOME would stage the pubkey into /root/.ssh and
        # the 'main' login (whose sshd reads /home/main/.ssh) would still be locked
        # out. $SUDO_USER is the invoking user under sudo; fall back to the current
        # user when run without sudo. Refuse a bare-root target: there is no home
        # pubkey login for root here (blank password, PermitRootLogin prohibit-pw).
        TARGET_USER="${SUDO_USER:-$(id -un)}"
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
            sudo mount -t 9p -o trans=virtio,version=9p2000.L,msize=104857600 shared "$SHARED" || {
                printf 'azarch --sshd-hypervisor: could not mount shared folder (is the VM running with shared_directory=true?)\\n' >&2
                exit 1
            }
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
