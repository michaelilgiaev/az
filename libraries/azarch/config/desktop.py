"""Minimal Openbox live-session desktop, authored as config-as-Python strings.

The overhaul boots the ISO to a graphical live session WITHOUT a display
manager, Manjaro-style:

    getty@tty1 autologins `main`  ->  ~/.bash_profile runs `exec startx` on
    tty1 only  ->  ~/.xinitrc execs openbox-session  ->  Openbox autostart
    launches picom (compositor), xsetroot (solid wallpaper), nm-applet (network),
    and the Calamares installer once (the live "Install" window that auto-opens).

Everything here is a small builder function returning the CONTENT of one file.
steps.py emits each to its airootfs destination via emit.write_text/write_exec
and iterates PLAN (below) so the mapping (path + mode) stays declarative. The
/home/main tree is chowned 1000:998 by steps.py after emit, exactly like the
fastfetch/first-boot payloads.

Design constraints (match archiso/Openbox/Calamares reality):
  * No emojis, ASCII only.
  * Calamares MUST run privileged. On a live medium with a passwordless-sudo
    `main` and passwordless root, the simplest correct launch is `sudo -E
    calamares` from the Openbox autostart (polkit's pkexec would need a GUI
    auth agent running, which this minimal session deliberately omits). We
    provide a tiny /usr/local/bin/azarch-install wrapper so the menu entry and
    autostart share one privileged launch path.
  * startx-from-tty replaces graphical.target: _link_services no longer needs a
    display-manager .wants symlink or graphical.target (see STEPS_NOTE).
"""

from __future__ import annotations

# --- Branding ---------------------------------------------------------------
# Az'arch accent color (matches os-release ANSI_COLOR 6,184,253 -> #06b8fd),
# used as the solid xsetroot wallpaper so no image asset needs shipping. If a logo
# image is later added under /usr/share/azarch/, swap the xsetroot line in
# openbox_autostart() to `feh --bg-scale /usr/share/azarch/wallpaper.png`.
ACCENT_HEX = "#06b8fd"

# The one privileged launch path shared by autostart + the menu entry.
INSTALL_WRAPPER_PATH = "/usr/local/bin/azarch-install"


# --- 1. ~/.xinitrc ----------------------------------------------------------
def xinitrc() -> str:
    """Run by `startx`. Sets a couple of sane env bits then execs the Openbox
    SESSION (openbox-session, not bare openbox -- the -session variant sources
    autostart and the menu/rc config and wires up the SM/XDG dirs)."""
    return """\
#!/bin/sh
# ~/.xinitrc -- started by `startx` (see ~/.bash_profile). Hands the X session
# to Openbox. Keep this minimal: per-app launches live in the Openbox autostart.

# Make sure user-dir XDG paths resolve for anything the session spawns.
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"

# A neutral cursor and a sane DPI-agnostic setup; harmless if xsetroot/xrdb are
# absent (they ship with xorg). This sets the solid background early to avoid the
# default X stipple flashing; the autostart re-applies the same solid via xsetroot.
[ -x /usr/bin/xsetroot ] && xsetroot -solid '""" + ACCENT_HEX + """' -cursor_name left_ptr

# Replace this shell with the Openbox session; when Openbox exits, X exits and
# control returns to the login shell (which, per bash_profile, logs out the tty).
exec openbox-session
"""


# --- 2. /home/main/.bash_profile snippet ------------------------------------
def bash_profile_startx() -> str:
    """Appended to /home/main/.bash_profile. On the FIRST virtual terminal only
    (and only when not already in X) it replaces the login shell with startx, so
    the autologin drops straight into the graphical session. On any other VT or
    an SSH login $DISPLAY is set or $XDG_VTNR != 1, so the guard is false and you
    get a normal shell -- important for rescue/maintenance use of the ISO."""
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


# --- 3. ~/.config/openbox/rc.xml --------------------------------------------
def openbox_rc_xml() -> str:
    """Minimal-but-sane Openbox config. One desktop, no decorations fuss, a few
    keybinds (kitty on W-Return, close on A-F4, menu on right-click via menu.xml)
    and a right-click root menu. Kept close to Openbox's shipped rc.xml so it is
    schema-valid against openbox-3."""
    return """\
<?xml version="1.0" encoding="UTF-8"?>
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
    <name>Clearlooks</name>
    <titleLayout>NLIMC</titleLayout>
    <keepBorder>yes</keepBorder>
    <animateIconify>yes</animateIconify>
    <font place="ActiveWindow">
      <name>sans</name>
      <size>9</size>
      <weight>bold</weight>
      <slant>normal</slant>
    </font>
    <font place="InactiveWindow">
      <name>sans</name>
      <size>9</size>
      <weight>bold</weight>
      <slant>normal</slant>
    </font>
    <font place="MenuHeader">
      <name>sans</name>
      <size>9</size>
      <weight>normal</weight>
      <slant>normal</slant>
    </font>
    <font place="MenuItem">
      <name>sans</name>
      <size>9</size>
      <weight>normal</weight>
      <slant>normal</slant>
    </font>
  </theme>
  <desktops>
    <number>1</number>
    <firstdesk>1</firstdesk>
    <names>
      <name>Az'arch</name>
    </names>
    <popupTime>875</popupTime>
  </desktops>
  <resize>
    <drawContents>yes</drawContents>
    <popupShow>Nonpixel</popupShow>
    <popupPosition>Center</popupPosition>
  </resize>
  <keyboard>
    <keybind key="W-Return">
      <action name="Execute">
        <command>kitty</command>
      </action>
    </keybind>
    <keybind key="W-e">
      <action name="Execute">
        <command>pcmanfm</command>
      </action>
    </keybind>
    <keybind key="W-w">
      <action name="Execute">
        <command>librewolf</command>
      </action>
    </keybind>
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
  </keyboard>
  <mouse>
    <dragThreshold>8</dragThreshold>
    <doubleClickTime>200</doubleClickTime>
    <screenEdgeWarpTime>400</screenEdgeWarpTime>
    <context name="Frame">
      <mousebind button="A-Left" action="Press">
        <action name="Focus"/>
        <action name="Raise"/>
      </mousebind>
      <mousebind button="A-Left" action="Drag">
        <action name="Move"/>
      </mousebind>
      <mousebind button="A-Right" action="Drag">
        <action name="Resize"/>
      </mousebind>
    </context>
    <context name="Titlebar">
      <mousebind button="Left" action="Press">
        <action name="Focus"/>
        <action name="Raise"/>
      </mousebind>
      <mousebind button="Left" action="Drag">
        <action name="Move"/>
      </mousebind>
      <mousebind button="Left" action="DoubleClick">
        <action name="ToggleMaximize"/>
      </mousebind>
    </context>
    <context name="Client">
      <mousebind button="Left" action="Press">
        <action name="Focus"/>
        <action name="Raise"/>
      </mousebind>
    </context>
    <context name="Desktop">
      <mousebind button="Right" action="Press">
        <action name="ShowMenu">
          <menu>root-menu</menu>
        </action>
      </mousebind>
      <mousebind button="Middle" action="Press">
        <action name="ShowMenu">
          <menu>root-menu</menu>
        </action>
      </mousebind>
    </context>
    <context name="Root">
      <mousebind button="Right" action="Press">
        <action name="ShowMenu">
          <menu>root-menu</menu>
        </action>
      </mousebind>
    </context>
  </mouse>
  <menu>
    <file>menu.xml</file>
    <hideDelay>200</hideDelay>
    <middle>no</middle>
    <submenuShowDelay>100</submenuShowDelay>
    <submenuHideDelay>400</submenuHideDelay>
    <showIcons>yes</showIcons>
    <manageDesktops>no</manageDesktops>
  </menu>
  <applications>
    <!-- Center and focus the live installer window when it opens. -->
    <application name="calamares">
      <focus>yes</focus>
      <position force="yes">
        <x>center</x>
        <y>center</y>
      </position>
    </application>
  </applications>
</openbox_config>
"""


# --- 4. ~/.config/openbox/menu.xml ------------------------------------------
def openbox_menu_xml() -> str:
    """Right-click root menu. Top entry is the live installer (shares the
    privileged wrapper), then terminal/browser/file-manager, then session
    controls. `openbox --reconfigure` reloads this without a restart."""
    return """\
<?xml version="1.0" encoding="UTF-8"?>
<openbox_menu xmlns="http://openbox.org/3.4/menu">
  <menu id="root-menu" label="Az'arch">
    <item label="Install Az'arch">
      <action name="Execute">
        <command>""" + INSTALL_WRAPPER_PATH + """</command>
      </action>
    </item>
    <separator/>
    <item label="Terminal">
      <action name="Execute">
        <command>kitty</command>
      </action>
    </item>
    <item label="Browser">
      <action name="Execute">
        <command>librewolf</command>
      </action>
    </item>
    <item label="File Manager">
      <action name="Execute">
        <command>pcmanfm</command>
      </action>
    </item>
    <separator/>
    <item label="Reconfigure Openbox">
      <action name="Reconfigure"/>
    </item>
    <separator/>
    <item label="Reboot">
      <action name="Execute">
        <command>systemctl reboot</command>
      </action>
    </item>
    <item label="Power Off">
      <action name="Execute">
        <command>systemctl poweroff</command>
      </action>
    </item>
    <item label="Exit (log out)">
      <action name="Exit">
        <prompt>yes</prompt>
      </action>
    </item>
  </menu>
</openbox_menu>
"""


# --- 5. ~/.config/openbox/autostart -----------------------------------------
def openbox_autostart() -> str:
    """Openbox autostart (sh, sourced by openbox-session at session start). Each
    persistent helper is backgrounded with `&`; the installer launches ONCE via
    the privileged wrapper. `command -v` guards keep the session from erroring if
    an optional helper is missing on a stripped build."""
    return """\
#!/bin/sh
# ~/.config/openbox/autostart -- sourced by openbox-session at login.

# Compositor: tear-free, light config (see ~/.config/picom.conf).
if command -v picom >/dev/null 2>&1; then
    picom --config "$HOME/.config/picom.conf" &
fi

# Wallpaper: solid Az'arch accent color (no image asset shipped). feh has NO
# solid-color flag (its --bg-* options all require an IMAGE), so a solid fill is
# set with xsetroot -solid (xorg-xsetroot ships; already used in ~/.xinitrc). If a
# logo image is later added, swap this for `feh --bg-scale /usr/share/azarch/wallpaper.png &`.
if command -v xsetroot >/dev/null 2>&1; then
    xsetroot -solid '""" + ACCENT_HEX + """' &
fi

# Network tray applet (NetworkManager).
if command -v nm-applet >/dev/null 2>&1; then
    nm-applet &
fi

# Auto-launch the Calamares installer ONCE, Manjaro-style, via the privileged
# wrapper (Calamares must run as root; see """ + INSTALL_WRAPPER_PATH + """).
# Run via the exec bit when present, else fall back to `sh <wrapper>` so a lost
# exec bit (archiso normalizes overlay modes) can never silently stop the
# installer from opening -- the wrapper is a plain /bin/sh script either way.
if [ -x """ + INSTALL_WRAPPER_PATH + """ ]; then
    """ + INSTALL_WRAPPER_PATH + """ &
elif [ -r """ + INSTALL_WRAPPER_PATH + """ ]; then
    sh """ + INSTALL_WRAPPER_PATH + """ &
fi
"""


# --- 5b. /usr/local/bin/azarch-install (privileged Calamares launcher) ------
def install_wrapper_sh() -> str:
    """The single privileged launch path for Calamares, used by both the Openbox
    autostart and the menu entry. On the live medium `main` has passwordless
    sudo, so `sudo -E calamares` is the correct, dependency-free way to get root
    for the GUI installer (pkexec would require a running polkit auth agent,
    which this minimal Openbox session intentionally does not run).

    -E preserves the X env (DISPLAY, XAUTHORITY, XDG_*) so the root-owned
    Calamares Qt process can connect to `main`'s X server. -c points Calamares at
    its config tree (default /etc/calamares); passing it explicitly is harmless
    and future-proofs a custom branding dir."""
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
unset XDG_RUNTIME_DIR
exec sudo -E calamares -c /etc/calamares
"""


# --- 6. ~/.config/picom.conf ------------------------------------------------
def picom_conf() -> str:
    """Minimal picom: a compositor for tear-free rendering with light shadows and
    a touch of fade, no blur/rounded-corner heaviness. Uses the modern
    `backend = "glx"`; falls back gracefully to xrender if GLX is unavailable
    (picom auto-detects). Valid for picom >= 10 (libconfig syntax)."""
    return """\
# ~/.config/picom.conf -- minimal compositor config for the Az'arch live session.

backend = "glx";
vsync = true;

# Light shadows on floating windows (menus/tooltips excluded).
shadow = true;
shadow-radius = 7;
shadow-opacity = 0.35;
shadow-offset-x = -7;
shadow-offset-y = -7;
shadow-exclude = [
  "class_g = 'Conky'",
  "_GTK_FRAME_EXTENTS@:c",
  "window_type = 'dock'",
  "window_type = 'desktop'",
  "window_type = 'menu'",
  "window_type = 'dropdown_menu'",
  "window_type = 'popup_menu'",
  "window_type = 'tooltip'"
];

# Subtle fade on open/close so the installer window does not pop harshly.
fading = true;
fade-in-step = 0.06;
fade-out-step = 0.06;
fade-delta = 8;

# Keep everything else default/off for a light footprint.
detect-rounded-corners = true;
detect-client-opacity = true;
detect-transient = true;
use-damage = true;

wintypes:
{
  tooltip = { fade = true; shadow = false; };
  dock = { shadow = false; };
  dnd = { shadow = false; };
  popup_menu = { shadow = false; };
  dropdown_menu = { shadow = false; };
};
"""


# --- 7. Emit plan -----------------------------------------------------------
# Declarative map so steps.py can iterate. Each entry: the builder function that
# produces the content, the DESTINATION (absolute, or $HOME-relative for the live
# `main` user), and the file MODE. `owner` records the intended chown so steps.py
# knows which files fall under the /home/main (uid 1000, gid 998) handback.
#
# HOME-relative paths are given relative to /home/main so the airootfs overlay
# lands them under airootfs/home/main/...; steps.py chowns that whole tree
# 1000:998 after emit (as it already does for the fastfetch/first-boot payloads).
# Absolute paths (/usr/local/bin/...) stay root-owned (0:0) -- do NOT chown them.

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
        "builder": openbox_rc_xml,
        "dest": f"{HOME}/.config/openbox/rc.xml",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": openbox_menu_xml,
        "dest": f"{HOME}/.config/openbox/menu.xml",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": openbox_autostart,
        "dest": f"{HOME}/.config/openbox/autostart",
        "mode": _EXEC,
        "owner": "home",
    },
    {
        "builder": picom_conf,
        "dest": f"{HOME}/.config/picom.conf",
        "mode": _CONF,
        "owner": "home",
    },
    {
        "builder": install_wrapper_sh,
        "dest": INSTALL_WRAPPER_PATH,
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
    config modules and to keep the .bash_profile special-case in one place."""
    return PLAN + [
        {
            "builder": bash_profile_startx,
            "dest": BASH_PROFILE_DEST,
            "mode": _CONF,
            "owner": "home",
        },
    ]
