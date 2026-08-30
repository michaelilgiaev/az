"""Partition the package manifest by product line (desktop vs. server).

``packages/packages.x86_64`` stays the single, VERBATIM superset the build always
warms into the offline cache -- the cache-completeness and download-coverage logic
(downloader.py, compiler.cache_is_complete) is unchanged and keeps operating on
that full list. What differs between the DESKTOP line and the headless SERVER line
is only WHICH of those cached packages each one's pacstrap actually installs:

    desktop  ->  the full manifest (base + the GUI stack)
    server   ->  the full manifest MINUS DESKTOP_ONLY (console-only)

Keeping one physical manifest file (rather than splitting it in two) means the
offline repo is a superset of BOTH airootfs needs -- always a valid cache for
either line -- and none of the cache machinery has to learn about lines. Only the
pacstrap manifest STAGED into a given airootfs is filtered, here, at emit time.

DESKTOP_ONLY is the set of package NAMES that exist purely to serve the graphical
session and have no place on a headless server: the X11 server + client libs, the
OpenBox desktop, the Calamares GUI installer and its Qt6/KDE-Frameworks toolkit,
and the shipped GUI applications. It is deliberately CONSERVATIVE -- anything
dual-use (GPU/compute drivers, filesystem/partition tools, networking, gnupg) stays
in the base set so the server keeps every non-graphical capability. A name here
that is not in the manifest is simply inert (the filter is a set-difference), but a
GUI package OMITTED here would wrongly ship on the server, so the set is derived
directly from the AZ'ARCH ADDITIONS "desktop"/"Calamares"/"Thunar"/"xviewer"
groupings in packages.x86_64.
"""

from __future__ import annotations

import downloader

# Package names that belong ONLY to the graphical desktop line. Grouped to mirror
# the commented sections of packages.x86_64 so the two stay auditable side by side.
DESKTOP_ONLY: frozenset[str] = frozenset({
    # --- X11 server, session bootstrap, and the client libraries the desktop needs
    "xorg-server",
    "xorg-xinit",
    "xorg-xrandr",
    "xorg-xrdb",
    "xorg-xsetroot",
    "xorg-xset",
    "libx11",
    "libxrandr",
    "libxft",
    "libxcomposite",
    "libxdamage",
    "libxrender",
    "picom",
    "xcb-util-cursor",
    "mesa",            # GL for the X session; server is headless (compute GPU stacks stay in base)
    "feh",             # wallpaper painter (X only)
    "xcape",           # lone-Super -> Super+Menu, OpenBox keybind helper (X only)
    "xdotool",         # X11 automation CLI
    "xclip",           # X11 clipboard (the desktop clip-it workflow)
    # --- OpenBox desktop shell + its GTK theme/icon/cursor assets
    "openbox",
    "adwaita-icon-theme",
    "gnome-themes-extra",
    "xcursor-themes",
    "webp-pixbuf-loader",   # GdkPixbuf webp loader for the GTK apps/thumbnails
    # --- Fonts shipped for the GUI (a console needs only the kernel/terminus font in base)
    "ttf-dejavu",
    "ttf-liberation",
    "noto-fonts",
    # --- The terminal emulator (GUI); server uses the real VT console
    "kitty",
    # --- Calamares graphical installer + its Qt6 / KDE-Frameworks / GTK toolkit.
    # The SERVER installs via the headless CLI installer (azarch-install-cli.sh), so the
    # whole GUI installer toolkit is desktop-only. The partition/filesystem tools Calamares
    # ALSO lists (parted, gptfdisk, cryptsetup, lvm2, dosfstools, e2fsprogs, btrfs-progs,
    # ntfs-3g, exfatprogs, efibootmgr, grub, mkinitcpio, rsync, squashfs-tools) are NOT here:
    # they are dual-use and the CLI installer needs them too, so they stay in the base set.
    "calamares",
    "kpmcore",
    "qt6-base",
    "qt6-svg",
    "qt6-declarative",
    "qt6-5compat",
    "kconfig",
    "kcoreaddons",
    "ki18n",
    "kcrash",
    "kwidgetsaddons",
    "kiconthemes",
    "kpackage",
    "yaml-cpp",
    "polkit-qt6",
    "hwinfo",          # Calamares hardware page
    "gtk3",
    "nss",
    "libnotify",
    "libpulse",
    # --- Shipped GUI applications (browser, office, media, editor, image tools)
    "librewolf",
    "libreoffice-fresh",
    "vlc",
    "vlc-plugin-ffmpeg",
    "vlc-plugin-x264",
    "vlc-plugin-x265",
    "vlc-plugin-upnp",
    "dotnet-sdk",
    "dotnet-runtime",
    "dotnet-host",
    "gedit",
    "gimp",
    "xviewer",
    "qalculate-gtk",
    # --- Thunar file manager + its GUI helpers
    "thunar",
    "thunar-volman",
    "thunar-archive-plugin",
    "tumbler",
    "zenity",
    "exo",
})


def manifest_for(is_gui: bool) -> list[str]:
    """The pacstrap package list for a line: the full manifest for the desktop
    (is_gui True), or the manifest minus DESKTOP_ONLY for the headless server.
    Order is preserved from the manifest so the emitted packages.x86_64 reads the
    same as the source for the packages it keeps."""
    pkgs = downloader.manifest_packages()
    if is_gui:
        return pkgs
    return [p for p in pkgs if p not in DESKTOP_ONLY]


def manifest_text_for(is_gui: bool) -> str:
    """The pacstrap packages.x86_64 CONTENTS for a line -- newline-joined names with
    a trailing newline, the plain one-name-per-line format mkarchiso and the on-disk
    installer parse. This is what compiler.py stages into the airootfs / installer
    payload instead of copying packages.x86_64 verbatim, so a server airootfs never
    pulls the GUI stack. The desktop text is byte-equivalent to the manifest's own
    package lines (comments dropped), so the desktop build is unchanged."""
    return "\n".join(manifest_for(is_gui)) + "\n"
