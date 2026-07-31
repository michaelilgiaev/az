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
# The desktop wallpaper baked into the ISO. steps.py copies
# assets/wallpapers/wallpaper_years.png here (emit.copy_asset) and the Plasma
# appletsrc + the ~/.xinitrc root-pixmap pre-paint both point at this path, so
# the first paint IS the wallpaper (no solid-color flash).
WALLPAPER_DEST = "/usr/share/azarch/wallpaper.png"
WALLPAPER_ASSET = "wallpapers/wallpaper_years.png"

# The one privileged launch path shared by the autostart entry + a menu launcher.
INSTALL_WRAPPER_PATH = "/usr/local/bin/azarch-install"


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
def plasma_appletsrc() -> str:
    """Seed the Plasma desktop wallpaper for a fresh profile (a BELT; the primary,
    regeneration-proof mechanism is the org.kde.image `main.xml` default rewritten
    by customize_airootfs.sh -- see configuration/system.CUSTOMIZE_AIROOTFS).

    The wallpaper image lives in the `org.kde.image` wallpaper plugin's configuration,
    which for a containment is the NESTED group
    `[Containments][1][Wallpaper][org.kde.image][General]` with an `Image=`
    file:// URI -- NOT the containment's own `[General]` group (a common mistake
    that silently does nothing). Containment number 1 is arbitrary but the
    `[Containments][1]` block and its `[Containments][1][Wallpaper]...` block
    must share the same number.

    NOTE this seed is best-effort: plasmashell may REGENERATE this file on first
    login with its own containment ids, orphaning the seeded block. That is why it
    is only a belt -- the load-bearing wallpaper default lives in main.xml (which
    Plasma consults for any containment without an explicit image, so it holds
    regardless of regeneration). This file is written to BOTH the live `main` home
    and /etc/skel so it applies to the live and installed users on the runs where
    it is honored."""
    return """\
[Containments][1]
plugin=org.kde.desktopcontainment
wallpaperplugin=org.kde.image

[Containments][1][Wallpaper][org.kde.image][General]
Image=file://""" + WALLPAPER_DEST + """
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
Name=Install Az'arch
Comment=Launch the Az'arch Linux installer
Exec=""" + INSTALL_WRAPPER_PATH + """
Icon=system-software-install
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
Name=Install Az'arch
GenericName=System Installer
Comment=Install Az'arch Linux to disk
Exec=""" + INSTALL_WRAPPER_PATH + """
Icon=system-software-install
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
