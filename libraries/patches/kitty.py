"""Kitty terminal icon patch -- swap the cat-in-a-terminal logo for a clean "> _" glyph.

Kitty (the ONE terminal Az'arch ships, bound to Super+Return / opened from the
application menu) draws a cute mascot by default: a terminal window with a cat's
face and whiskers poking out of it. Az'arch wants the cleanest possible monochrome
mark that reads as a terminal -- literally a chevron and an underscore cursor,
"> _", black on transparent, no window chrome and no color. Kitty upstream ships NO
cat-less icon and NO kitty.conf switch to disable the cat (the maintainer considers
the cat a permanent tribute), so the ONLY supported route is to REPLACE the icon
files the desktop icon loader reads and, for the in-window titlebar icon, ship
~/.config/kitty/kitty.app.png (kitty loads it at startup to set the window icon on
X11/Wayland -- confirmed via the kitty FAQ).

SINGLE SOURCE OF TRUTH. The glyph lives as a real repo asset,
assets/icons/kitty.svg (git-tracked, survives `git clean -Xdf`, openable/eyeballable),
following the same convention as patches/fastfetch.py reading paths.ASSETSDIR. This
module does NOT embed the SVG text: it references the asset by path and hands
compiler._emit_apps declarative "copy this asset" / "rasterize this asset to PNG"
entries. The SVG asset is the one place the icon is defined; both the vector system
icon and every PNG (the titlebar icon) are derived from it.

WHERE THE DESKTOP ICON COMES FROM. kitty's .desktop is `Icon=kitty`, which the icon
loader resolves, in order, against the icon-theme dirs and then /usr/share/pixmaps.
The kitty package ships three files that back that name:

    /usr/share/icons/hicolor/scalable/apps/kitty.svg   (the master, vector)
    /usr/share/icons/hicolor/256x256/apps/kitty.png    (a rasterization)
    /usr/share/pixmaps/kitty.png                        (legacy fallback)

We OVERWRITE the scalable SVG with our asset and DELETE the two PNGs so nothing stale
outranks the SVG: with the same-size PNG gone, the scalable SVG is the highest-quality
source the loader has, so every surface (menu tile, Alt-Tab, window icon) renders our
"> _". Shipping our own file into the airootfs overlay means a `pacman -Syu` of kitty
that reships its own icons cannot silently revert us on the LIVE medium (the overlay
wins at build time); on an installed system a kitty upgrade could re-drop its icon,
which is acceptable -- this is a cosmetic default, and re-running the patch restores it.

THE IN-WINDOW TITLEBAR ICON. The DESKTOP icon (files above) does NOT change the icon
kitty sets on its OWN top-level window at runtime -- that is the cat baked into the
binary. kitty's documented override is ~/.config/kitty/kitty.app.png: if present, kitty
loads it at startup and uses it as the window icon (the top-left titlebar/Alt-Tab image
the WM shows). So we rasterize the SAME asset SVG to a PNG and ship it there (owner
"home", mirrored into /etc/skel), giving the open kitty window the clean "> _" instead
of the cat. It is rasterized at 128px because X11 caps the OS-window icon at 128x128 --
kitty refuses a larger PNG and falls back to the WM's broken/default icon (see
KITTY_APP_ICON_SIZE).

compiler._emit_apps iterates emit_plan() (builder/dest/mode/owner shape), now honouring
three declarative extras so this module stays pure-data:
  * "asset":  copy assets/<asset> verbatim to dest (the scalable SVG).
  * "render": {"asset","size"} -- rasterize assets/<asset> to a <size>px PNG at dest
              (the titlebar kitty.app.png).
  * "remove": True -- delete dest instead of writing (the two stale cat PNGs).
No package rebuild -- the overlay simply lands on top of the kitty package's files.
"""

from __future__ import annotations

# --- The single-source-of-truth icon asset ---------------------------------
# The clean "> _" glyph (black on transparent, no chrome, no color). Referenced by
# path the same way patches/fastfetch.py references paths.ASSETSDIR assets; the SVG is
# NOT inlined here so the art has ONE definition (the file you can open and eyeball).
ICON_ASSET = "icons/kitty.svg"

# --- Where the desktop icon loader reads `Icon=kitty` from ------------------
# The three files the kitty package ships to back the name "kitty". The SVG is the
# master we overwrite (with our asset); the two PNGs are removed so they cannot outrank
# the SVG.
ICON_SVG_PATH = "/usr/share/icons/hicolor/scalable/apps/kitty.svg"
ICON_PNG_HICOLOR_PATH = "/usr/share/icons/hicolor/256x256/apps/kitty.png"
ICON_PNG_PIXMAP_PATH = "/usr/share/pixmaps/kitty.png"

# --- The in-window titlebar icon kitty loads at startup ---------------------
# ~/.config/kitty/kitty.app.png -- kitty reads this on X11/Wayland and uses it as the
# window icon (the top-left titlebar / Alt-Tab image), overriding the cat baked into the
# binary. Rasterized from ICON_ASSET so it matches the desktop icon exactly. A HOME file
# (owner "home"): compiler.py chowns it 1000:998 and mirrors it into /etc/skel.
HOME = "/home/main"
KITTY_APP_ICON_PATH = f"{HOME}/.config/kitty/kitty.app.png"
# Square size (px) the titlebar PNG is rasterized to. MUST be 128: on X11 the maximum
# OS-window icon is 128x128, and kitty REFUSES a larger one -- it prints "The window icon
# is too large (256x256). On X11 max window icon size is: 128x128" and leaves the window
# with the WM's broken/default icon (the exact titlebar bug that was reported when this was
# 256). 128px fills any titlebar/Alt-Tab surface, so cap it here.
KITTY_APP_ICON_SIZE = 128


# --- Emit plan --------------------------------------------------------------
# Declarative map (builder -> dest -> mode -> owner), the same shape compiler.py
# iterates for patches/openbox and patches/librewolf, PLUS the "asset"/"render"/"remove"
# extras documented in the module docstring. The SVG entry COPIES our asset to the
# scalable system path; the two PNG entries carry "remove": True (they are deleted so the
# scalable SVG wins); the kitty.app.png entry RENDERS the asset to a PNG in the live
# user's kitty config (owner "home", skel-mirrored) for the in-window titlebar icon.
_CONF = 0o644


def emit_plan() -> list[dict]:
    """Return the emit plan for the kitty icon: copy our "> _" SVG asset over the system
    scalable icon, remove the two stale cat PNGs that would outrank it, and rasterize the
    same asset to ~/.config/kitty/kitty.app.png so the open kitty WINDOW's titlebar icon
    is the clean glyph too.

    Shape matches openbox.emit_plan()/librewolf.emit_plan() (builder/dest/mode/owner),
    with the declarative extras compiler._emit_apps honours: "asset" (copy an asset file),
    "render" (rasterize an SVG asset to a PNG), and "remove" (delete the dest). builder is
    None on every entry -- there is no generated text; the icon's single source of truth is
    the SVG asset. Returns FRESH dicts so a caller cannot mutate module state."""
    return [
        {
            # Overwrite the system scalable icon with our asset SVG (the master the loader
            # rasterizes once the same-size PNG is removed).
            "builder": None,
            "asset": ICON_ASSET,
            "dest": ICON_SVG_PATH,
            "mode": _CONF,
            "owner": "root",
        },
        {
            # Remove the stale 256px cat PNG so it cannot outrank the scalable SVG.
            "builder": None,
            "dest": ICON_PNG_HICOLOR_PATH,
            "mode": _CONF,
            "owner": "root",
            "remove": True,
        },
        {
            # Remove the legacy pixmap cat PNG for the same reason.
            "builder": None,
            "dest": ICON_PNG_PIXMAP_PATH,
            "mode": _CONF,
            "owner": "root",
            "remove": True,
        },
        {
            # The in-window titlebar icon: rasterize the SAME asset to a PNG kitty loads at
            # startup. HOME file (owner "home") so compiler.py chowns it and mirrors it into
            # /etc/skel for the installed user.
            "builder": None,
            "render": {"asset": ICON_ASSET, "size": KITTY_APP_ICON_SIZE},
            "dest": KITTY_APP_ICON_PATH,
            "mode": _CONF,
            "owner": "home",
        },
    ]
