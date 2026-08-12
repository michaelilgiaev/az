"""GIMP preload patch -- warm GIMP at login so it opens INSTANTLY and CLEANLY, and
re-warm it invisibly after the user closes it.

GIMP is heavy to start cold: on first launch in a session it queries every plug-in,
builds the font cache, and loads brushes/gradients/patterns/palettes -- the several-second
stall. Az'arch wants GIMP to feel instant, so we PRELOAD a warm instance at login, kept
INVISIBLE, and lean on GIMP 3.x being single-instance (a GApplication): launching
`gimp-3.2` again with NO `--new-instance` does not start a second process -- it forwards to
the running one, which raises/loads into its existing window.

THREE things this patch gets right that a naive `exec gimp-3.2` + OpenBox `<iconic>` rule
did NOT (all verified live on the hypervisor):

  1. NO SPLASH, NO WELCOME DIALOG. `gimp-3.2 --no-splash` suppresses the splash, but GIMP
     3.2.4 ALSO pops a "Welcome to GIMP 3.2.4" dialog every start (and a tips dialog),
     which --no-splash does not hide. So we ALSO ship a gimprc (the REAL user config dir is
     ~/.config/GIMP/3.2/, not 3.0/) turning both off: (show-welcome-dialog no)
     (show-tips no). `--console-messages` keeps plug-in warnings off-screen too.

  2. INSTANT, CLEAN OPEN (no transparent middle). The old approach started the window
     ICONIC (minimized/unmapped). An unmapped GTK/GEGL window never paints its canvas, so
     the first un-minimize showed a HALF-DRAWN, transparent-middle window for ~1-2s -- the
     exact bug the user reported. The fix: keep the warm window MAPPED but OFF-SCREEN. A
     mapped off-screen window renders fully (GTK3 client-side surfaces), so when the user
     opens GIMP we just move it back on-screen already-painted -> instant and clean. The
     move is done by azarch-gimp-winmove, a tiny X11 helper using ONLY libX11 via ctypes
     (python is in base, libX11 ships with X) -- no xdotool/wmctrl dependency.

  3. RE-WARM ON CLOSE. When the user closes GIMP the process exits; a plain `exec gimp` had
     nothing left to relaunch. Instead the preload is a SUPERVISE LOOP: it launches the
     warm GIMP, waits for it to exit, then relaunches (with crash backoff and a settle so
     the GApplication D-Bus name is released before the next start). So after every close
     GIMP re-warms invisibly and is ready again.

HOW OPENING WORKS. The gimp.desktop launcher Exec is replaced with the azarch-gimp wrapper:
it moves the warm window ON-SCREEN (azarch-gimp-winmove show) and then runs `gimp-3.2 "$@"`
which -- single-instance -- present()s/raises that window (and loads any file). Result: an
instant, fully-painted GIMP. If no warm instance exists yet (e.g. mid-re-warm), the wrapper
just starts GIMP normally.

OPENBOX. patches/openbox.py's GIMP window rule no longer uses <iconic> (which caused the
transparent middle). It keeps the warm window unfocused and off the taskbar/pager
(<focus>no>, <skip_taskbar>, <skip_pager>); the OFF-SCREEN hide is what keeps it invisible.
GIMP_WM_CLASS_MATCH here is the shared constant that rule targets.

WHERE THINGS GO (all HOME files unless noted; compiler.py chowns them 1000:998 and mirrors
them into /etc/skel so a Calamares-created user inherits the same behaviour):
    ~/.local/bin/azarch-gimp-winmove              the X11 hide/show helper (executable)
    ~/.local/bin/azarch-gimp-preload              the preload + re-warm supervisor (exec)
    ~/.local/bin/azarch-gimp                       the open wrapper (executable)
    ~/.config/autostart/azarch-gimp-preload.desktop  the XDG autostart entry
    ~/.config/GIMP/3.2/gimprc                       welcome/tips off
    /usr/share/applications/gimp.desktop           launcher override (Exec = azarch-gimp)  [root]

Pure standard library (returns strings) + one shipped ctypes helper. compiler.py iterates
emit_plan() exactly like patches/openbox and patches/librewolf.
"""

from __future__ import annotations

# The live user's home (matches openbox.HOME / the airootfs /home/main tree).
HOME = "/home/main"

# The real GIMP binary the gimp.desktop Exec uses (gimp-3.2). Pinned so the preload +
# wrapper launch the SAME binary -- all three then share the one single-instance process.
GIMP_BINARY = "gimp-3.2"

# GIMP's window WM_CLASS is "gimp" (gimp.desktop StartupWMClass=gimp). openbox.py's window
# rule matches this to keep the warm window unfocused/off the taskbar; exported here as the
# single source of truth so the two modules cannot disagree. The trailing * lets the
# OpenBox rule match either WM_CLASS field ("gimp"/"Gimp").
GIMP_WM_CLASS_MATCH = "gimp*"

# GIMP 3.2's REAL per-user config dir is versioned 3.2 (NOT 3.0 -- verified on the guest:
# ~/.config/GIMP/3.0/gimprc is ignored, ~/.config/GIMP/3.2/gimprc is read). The gimprc we
# ship turns off the welcome + tips dialogs so the warm-up (and every start) is silent.
GIMP_CONFIG_DIR = f"{HOME}/.config/GIMP/3.2"
GIMP_GIMPRC_PATH = f"{GIMP_CONFIG_DIR}/gimprc"

# The three HOME helper scripts and the XDG autostart entry.
WINMOVE_HELPER_PATH = f"{HOME}/.local/bin/azarch-gimp-winmove"
PRELOAD_HELPER_PATH = f"{HOME}/.local/bin/azarch-gimp-preload"
OPEN_WRAPPER_PATH = f"{HOME}/.local/bin/azarch-gimp"
AUTOSTART_DESKTOP_PATH = f"{HOME}/.config/autostart/azarch-gimp-preload.desktop"

# The system gimp.desktop launcher we override so opening GIMP goes through our wrapper.
GIMP_DESKTOP_PATH = "/usr/share/applications/gimp.desktop"

# Seconds to wait after login before warming GIMP, so the preload never competes with the
# wallpaper/menu-daemon/installer startup the OpenBox autostart fires first.
PRELOAD_DELAY_SECONDS = 8

# The winmove helper source (shipped verbatim). It is read from the source tree next to
# this module so the Python is the single source of truth (openable/eyeballable).
import paths  # noqa: E402 (local import; gimp.py otherwise has no module-level paths use)

_WINMOVE_SRC = paths.PATCHESDIR / "gimp_winmove.py"


def winmove_helper_py() -> str:
    """~/.local/bin/azarch-gimp-winmove -- the X11 hide/show helper, verbatim from the
    source tree. Uses only libX11 via ctypes (no xdotool/wmctrl): `hide` moves GIMP's main
    window OFF-SCREEN (mapped, so it renders fully -> a clean instant reveal later), `show`
    moves it back on-screen and raises it. Installed executable (0o755)."""
    return _WINMOVE_SRC.read_text(encoding="utf-8")


def gimprc() -> str:
    """~/.config/GIMP/3.2/gimprc -- turn off the welcome + tips dialogs so the warm-up (and
    every GIMP start) is silent. GIMP rewrites gimprc on exit but preserves these keys, so
    shipping them here is enough. (The 3.2 dir is the real one; 3.0 is ignored.)"""
    return """\
# Az'arch GIMP config -- generated by patches/gimp.py (edit the Python, not this file).
# Keep GIMP's warm-up (and every start) silent: no splash-follow-up welcome dialog, no
# tips-of-the-day dialog. --no-splash (in the preload/wrapper) suppresses the splash; these
# suppress the two dialogs --no-splash does not.
(show-welcome-dialog no)
(show-tips no)
"""


def preload_helper_sh() -> str:
    """~/.local/bin/azarch-gimp-preload -- warm GIMP at login and RE-WARM it after close.

    A supervise loop (NOT `exec`, which would leave nothing to relaunch): it launches the
    warm GIMP with --no-splash, moves its window OFF-SCREEN the moment it maps (so it paints
    invisibly -- no on-screen flash, and no transparent-middle on the eventual open), then
    waits for the process to exit and relaunches. Crash backoff stops a relaunch storm if
    GIMP dies fast; a pgrep-poll settle lets the GApplication D-Bus name release before the
    next start (relaunching too fast makes the new instance forward to the dying one and
    exit). Guarded so it does nothing if GIMP is missing."""
    return f"""\
#!/bin/sh
# Az'arch GIMP preload + re-warm supervisor. Generated by patches/gimp.py (edit the Python,
# not this file). Started by the XDG autostart entry azarch-gimp-preload.desktop.

# Do nothing if GIMP is not installed (defensive; it is in the package manifest).
command -v {GIMP_BINARY} >/dev/null 2>&1 || exit 0

# Let the desktop settle first (wallpaper, menu daemon, installer all start at login).
sleep {PRELOAD_DELAY_SECONDS}

fails=0
while :; do
    # Launch the warm GIMP as a CHILD of this shell (so `wait` returns on its real exit).
    {GIMP_BINARY} --no-splash --console-messages >/dev/null 2>&1 &
    gpid=$!

    # As soon as the main window maps, move it OFF-SCREEN so it paints invisibly (no flash,
    # and a clean instant reveal on open). Poll briefly; give up quietly if it never appears
    # (e.g. GIMP crashed) -- the wait below then handles the exit.
    i=0
    while [ $i -lt 100 ]; do
        out=$("{WINMOVE_HELPER_PATH}" hide 2>/dev/null || true)
        case "$out" in
            HID*) break ;;
        esac
        i=$((i + 1))
        sleep 0.1
    done

    start=$(date +%s)
    wait "$gpid"                 # returns only when the warm GIMP actually exits
    end=$(date +%s)

    # Crash backoff: if GIMP died fast (<15s up), count it; after 3 fast deaths, stop trying
    # so a broken GIMP does not spin a relaunch storm.
    if [ $((end - start)) -lt 15 ]; then
        fails=$((fails + 1))
    else
        fails=0
    fi
    [ "$fails" -ge 3 ] && exit 0

    # Settle: wait until the old process is truly gone and give the GApplication D-Bus name
    # a moment to release, so the relaunch becomes the PRIMARY instance (not a remote that
    # forwards to the dying one and exits immediately).
    while pgrep -x {GIMP_BINARY} >/dev/null 2>&1; do sleep 0.2; done
    sleep 1
done
"""


def open_wrapper_sh() -> str:
    """~/.local/bin/azarch-gimp -- the OPEN wrapper the gimp.desktop launcher runs.

    Moves the warm GIMP window ON-SCREEN (azarch-gimp-winmove show) and then runs
    `gimp-3.2 "$@"` which -- single-instance -- present()s/raises that already-painted window
    (and loads any file passed). Result: an instant, cleanly-drawn GIMP. If no warm instance
    exists yet (e.g. mid-re-warm), `show` is a no-op and gimp-3.2 just starts normally."""
    return f"""\
#!/bin/sh
# Az'arch GIMP open wrapper. Generated by patches/gimp.py (edit the Python, not this file).
# Bring the warm (off-screen) GIMP window on-screen, then let gimp-3.2 present/raise it (and
# open any file). Single-instance, so this reuses the warm process -- instant and clean.
"{WINMOVE_HELPER_PATH}" show >/dev/null 2>&1 || true
exec {GIMP_BINARY} "$@"
"""


def autostart_desktop() -> str:
    """~/.config/autostart/azarch-gimp-preload.desktop -- run the preload supervisor at login.

    A standard XDG autostart entry. X-GNOME-Autostart-enabled and the OpenBox session's
    autostart handling both honour it; it simply runs the supervisor. Kept discoverable in
    ~/.config/autostart so the user can disable the warm-up by removing/toggling it."""
    return f"""\
[Desktop Entry]
Type=Application
Name=GIMP preload
Comment=Warm GIMP in the background at login so it opens instantly (Az'arch)
Exec={PRELOAD_HELPER_PATH}
Terminal=false
X-GNOME-Autostart-enabled=true
NoDisplay=true
"""


def desktop_entry() -> str:
    """/usr/share/applications/gimp.desktop -- the launcher override.

    The stock gimp launcher with Exec pointed at our open wrapper (azarch-gimp) so opening
    GIMP brings the warm window on-screen and present()s it (instant + clean) instead of
    starting cold. Identity fields (Icon, StartupWMClass, categories) are kept so GIMP still
    looks/associates exactly as before. %U passes files to the wrapper."""
    return f"""\
[Desktop Entry]
# Az'arch GIMP launcher override. Generated by patches/gimp.py (edit the Python, not this
# file). Exec runs the azarch-gimp wrapper, which surfaces the warm (off-screen) GIMP window
# and lets gimp-3.2 present it -- an instant, cleanly-drawn open.
Type=Application
Name=GNU Image Manipulation Program
GenericName=Image Editor
Comment=Create images and edit photographs
Exec={OPEN_WRAPPER_PATH} %U
TryExec={OPEN_WRAPPER_PATH}
Icon=gimp
Terminal=false
Categories=Graphics;2DGraphics;RasterGraphics;GTK;
Keywords=GIMP;graphic;design;illustration;painting;
StartupNotify=true
StartupWMClass=gimp
MimeType=image/bmp;image/g3fax;image/gif;image/x-fits;image/x-pcx;image/x-portable-anymap;image/x-portable-bitmap;image/x-portable-graymap;image/x-portable-pixmap;image/x-psd;image/x-sgi;image/x-tga;image/x-xbitmap;image/x-xwindowdump;image/x-xcf;image/x-compressed-xcf;image/x-gimp-gbr;image/x-gimp-pat;image/x-gimp-gih;image/tiff;image/jpeg;image/png;image/x-icon;image/x-xpixmap;image/svg+xml;application/pdf;image/x-wmf;image/jp2;image/x-xcursor;
"""


# --- Emit plan --------------------------------------------------------------
# Declarative map (builder -> dest -> mode -> owner), the same shape compiler.py iterates
# for patches/openbox and patches/librewolf. HOME files (owner="home", chowned + skel-
# mirrored): the winmove/preload/open helpers (executable), the autostart .desktop and the
# gimprc (plain data). The gimp.desktop override is a root-owned SYSTEM file. compiler.py
# writes/chowns them; no compile step.
_EXEC = 0o755
_CONF = 0o644


def emit_plan() -> list[dict]:
    """Return the emit plan for the GIMP preload/re-warm: the X11 winmove helper, the
    preload supervisor, the open wrapper (all executable HOME scripts), the XDG autostart
    entry, the gimprc (welcome/tips off), and the system gimp.desktop launcher override.

    Shape matches openbox.emit_plan()/librewolf.emit_plan() (builder/dest/mode/owner) so
    compiler.py can emit them with the same loop (and skel-mirror the home files). Returns
    FRESH dicts so a caller cannot mutate module state."""
    return [
        {
            "builder": winmove_helper_py,
            "dest": WINMOVE_HELPER_PATH,
            "mode": _EXEC,
            "owner": "home",
        },
        {
            "builder": preload_helper_sh,
            "dest": PRELOAD_HELPER_PATH,
            "mode": _EXEC,
            "owner": "home",
        },
        {
            "builder": open_wrapper_sh,
            "dest": OPEN_WRAPPER_PATH,
            "mode": _EXEC,
            "owner": "home",
        },
        {
            "builder": autostart_desktop,
            "dest": AUTOSTART_DESKTOP_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        {
            "builder": gimprc,
            "dest": GIMP_GIMPRC_PATH,
            "mode": _CONF,
            "owner": "home",
        },
        {
            "builder": desktop_entry,
            "dest": GIMP_DESKTOP_PATH,
            "mode": _CONF,
            "owner": "root",
        },
    ]
