"""profiledef.sh -- the archiso profile definition mkarchiso sources.

mkarchiso REQUIRES this to be a bash script it can `source` (it reads iso_name,
bootmodes, file_permissions, etc. as shell variables), so we can't make it Python.
Instead we AUTHOR it in Python (the values live in a dict/list here) and emit the
bash file. That keeps the source of truth in Python like everything else.

Notably this carries the zstd squashfs workaround for the sporadic
"xz uncompress failed with error code 9" and the file_permissions map that locks
down shadow/gshadow/sudoers in the ISO.
"""

from __future__ import annotations

import variants as _variants

# ISO base names. mkarchiso names the artifact <iso_name>-<version>-<arch>.iso, so the
# iso_name is the filename stem. The NAMES themselves now live in variants.Variant (the
# single source of truth for the whole {headed,headless} x {plain,instant} x {plain,ssh}
# matrix); this module only forwards to it. ISO_NAME / ISO_NAME_SSHD stay as named
# constants for the two legacy cells because tests and a few call sites reference them:
#   base -> azarch-headed-<ver>-x86_64.iso      (the normal live/install medium)
#   sshd -> azarch-headed-ssh-<ver>-x86_64.iso  (same, but ssh is ENABLED and `main`
#                                                 has the operator's --ssh password)
# The ISOs are separated in output/ by the digit-anchored glob "{iso_name}-[0-9]*.iso":
# "azarch-headed-2026..." matches azarch-headed, "azarch-headed-ssh-..." does not (the
# char after "azarch-headed-" is 's', not a digit). The headless/instant names extend the
# same scheme (azarch-headless, azarch-headed-instant, ...); see variants.Variant.iso_name.
ISO_NAME = _variants.from_legacy_key("base").iso_name       # "azarch-headed"
ISO_NAME_SSHD = _variants.from_legacy_key("sshd").iso_name  # "azarch-headed-ssh"

ISO_PUBLISHER = "michaelilgiaev <https://github.com/michaelilgiaev/azarch>"
ISO_APPLICATION = "Az'arch Installer/Az'arch Linux Live/Rescue DVD"
INSTALL_DIR = "arch"


def iso_name_for(variant: "_variants.Variant | str" = "base") -> str:
    """The mkarchiso iso_name for a build variant. Accepts a variants.Variant OR a legacy
    key string ("base"/"sshd"); an unknown string falls back to the headed base point
    ('azarch-headed'), preserving the old behaviour."""
    return _variants.coerce(variant).iso_name

BOOTMODES = (
    "bios.syslinux.mbr",
    "bios.syslinux.eltorito",
    "uefi-ia32.systemd-boot.esp",
    "uefi-x64.systemd-boot.esp",
    "uefi-ia32.systemd-boot.eltorito",
    "uefi-x64.systemd-boot.eltorito",
)

# path -> "owner:group:octal" baked into the squashfs by mkarchiso.
FILE_PERMISSIONS = {
    "/etc/shadow": "0:0:400",
    "/etc/gshadow": "0:0:400",
    # sudoers drop-ins: archiso normalizes overlay modes, so pin these to 0440
    # (the sudo convention) rather than letting them ship 0644. compiler.py emits
    # them 0440 but that mode is lost in the squashfs without an entry here.
    "/etc/sudoers.d/00-main": "0:0:440",
    "/etc/sudoers.d/00-rootpw": "0:0:440",
    "/root": "0:0:750",
    "/root/azarch": "0:0:750",
    "/root/.automated_script.sh": "0:0:755",
    "/root/.gnupg": "0:0:700",
    "/usr/local/bin/choose-mirror": "0:0:755",
    "/usr/local/bin/Installation_guide": "0:0:755",
    "/usr/local/bin/livecd-sound": "0:0:755",
    # The Calamares launcher the OpenBox autostart runs on live login. archiso
    # NORMALIZES overlay file modes when it packs the squashfs -- only paths listed
    # here keep an explicit mode. Without this entry the wrapper ships 0644
    # (non-executable), so the autostart's `[ -x ... ]` guard skips it and Calamares
    # never auto-launches. THIS is what breaks the live installer.
    "/usr/local/bin/azarch-install": "0:0:755",
    "/usr/local/bin/azarch": "0:0:755",
    # The Az'arch application-menu launcher (run by the Super key via OpenBox's rc.xml
    # keybind). SAME archiso mode-normalization as
    # azarch-install above: application_menu.PLAN emits it 0755, but the squashfs ships
    # it 0644 (non-executable) unless pinned here -- and then the Super key runs a
    # non-executable file and the menu never opens.
    "/usr/local/bin/azarch-application-menu": "0:0:755",
    # The Az'arch window-switcher launcher (run by OpenBox's A-Tab/A-S-Tab
    # <action name="Execute"> -- OUR replacement for the built-in NextWindow list). SAME
    # archiso mode-normalization as azarch-application-menu above: window_switcher.PLAN emits
    # it 0755, but the squashfs ships it 0644 (non-executable) unless pinned here -- and then
    # OpenBox's /bin/sh -c on the launcher fails with "Permission denied", which OpenBox
    # surfaces as an error popup INSTEAD of the alt-tab overlay (the reported bug). Verified
    # 0644 on the built ISO.
    "/usr/local/bin/azarch-window-switcher": "0:0:755",
    # The Az'arch timedate launcher (run by azarch-timedate.service, which ExecStart's it
    # to serve the Flask Time + Calendar home page at localhost:49154). SAME archiso mode-
    # normalization as azarch-install above: timedate.PLAN emits it 0755, but the squashfs
    # ships it 0644 (non-executable) unless pinned here -- and then systemd fails the unit
    # with status=203/EXEC (Permission denied) and the home page never listens, so a new
    # tab / the browser home page lands on a dead port. Verified on the built ISO.
    "/usr/local/bin/azarch-timedate": "0:0:755",
    # The Az'arch `passwords` launcher (the encrypted terminal password manager the user
    # runs by typing `passwords`). SAME archiso mode-normalization as azarch-install above:
    # packages/passwords/packaging.PLAN emits it 0755, but the squashfs ships it 0644
    # (non-executable) unless pinned here -- and then typing `passwords` fails with
    # "Permission denied" (the shell needs the exec bit to run it) on BOTH the live ISO and
    # the installed system. Root-owned on PATH, so every user gets the command.
    "/usr/local/bin/passwords": "0:0:755",
    # The Az'arch `backup`/`unpack` launchers (the home-directory backup the user runs by
    # typing `backup`, and the restore command `unpack`). SAME archiso mode-normalization as
    # azarch-install/passwords above: packages/backup/packaging.emit_plan() emits both 0755,
    # but the squashfs ships them 0644 (non-executable) unless pinned here -- and then typing
    # `backup` (or `unpack`) fails with "command not found"/"Permission denied" even by full
    # path (this was the last build's bug #1). Root-owned on PATH, so every user gets them.
    "/usr/local/bin/backup": "0:0:755",
    "/usr/local/bin/unpack": "0:0:755",
    # The Az'arch `hypervisor` launcher (the per-directory QEMU/KVM VM runner the user runs
    # by typing `hypervisor`). SAME archiso mode-normalization as passwords/backup above:
    # packages/hypervisor/packaging.emit_plan() emits it 0755, but the squashfs ships it 0644
    # (non-executable) unless pinned here -- and then typing `hypervisor` fails with
    # "Permission denied". Root-owned on PATH, so every user gets the command.
    "/usr/local/bin/hypervisor": "0:0:755",
    # The COMPILED application-menu daemon binary (built by application_menu.build_daemon
    # and started from the OpenBox autostart). Same archiso mode-normalization: it is
    # installed 0755, but the squashfs would ship it 0644 unless pinned -- and the
    # autostart's `[ -x ... ]` guard would then skip it, so the menu is never pre-built
    # and the first Super press does nothing / starts nothing.
    "/usr/local/lib/azarch-application-menu/azarch-application-menu-daemon": "0:0:755",
    # The COMPILED window-switcher daemon binary (built by window_switcher.build_daemon and
    # started from the OpenBox autostart, which keeps the alt-tab overlay hidden so the first
    # Alt+Tab is instant). Same archiso mode-normalization as the menu daemon above: it is
    # installed 0755, but the squashfs would ship it 0644 unless pinned -- and then the
    # autostart's `[ -x ... ]` guard skips it, so the daemon is never pre-built and Alt+Tab
    # starts nothing.
    "/usr/local/lib/azarch-window-switcher/azarch-window-switcher-daemon": "0:0:755",
    # The COMPILED bare-`azarch` TERMINAL UI binary (built by terminal_user_interface_build.build_terminal_user_interface from the
    # azarch package's C sources and EXEC'd by the `azarch` command line interface for the no-argument case).
    # Same archiso mode-normalization
    # as the menu daemon above: it is installed 0755, but the squashfs would ship it 0644
    # unless pinned -- and then the `azarch` launcher's os.access(..., X_OK) guard fails and
    # bare `azarch` silently falls back to the pointer message instead of opening the UI.
    "/usr/local/lib/azarch/azarch": "0:0:755",
    # The media OSD indicator (/usr/local/lib/azarch/azarch-osd), the bottom-middle cyan
    # volume/brightness bar `azarch volume/brightness` launches. A COMPILED C binary now (on_screen_display.c),
    # built + installed by terminal_user_interface_build.build_osd() like the terminal UI binary.
    # Same archiso mode-normalization as that binary: the build installs it 0755, but the squashfs
    # would ship it 0644 unless pinned -- and then media.py's os.access(..., X_OK) guard fails and
    # the FN keys change the volume/brightness with NO on-screen bar.
    "/usr/local/lib/azarch/azarch-osd": "0:0:755",
    # The live Thunar-sidebar sync helper (/usr/local/lib/azarch/azarch-sidebar-sync), which
    # regenerates ~/.config/gtk-3.0/bookmarks from the live home contents and (with --watch)
    # keeps Thunar's Places pane in sync. SAME archiso mode-normalization as the binaries above:
    # live_sidebar.emit_plan() emits it 0755, but the squashfs ships it 0644 unless pinned here --
    # and then the OpenBox autostart's `[ -x '/usr/local/lib/azarch/azarch-sidebar-sync' ]` guard
    # FAILS, so the --watch daemon never launches and Places never updates when a folder is added
    # or removed (the reported "Places does not update" bug: the file-monitor theory was sound,
    # but the watcher that rewrites the file was never even running because it shipped non-exec).
    "/usr/local/lib/azarch/azarch-sidebar-sync": "0:0:755",
    # The OpenBox session autostart (~/.config/openbox/autostart). openbox-session runs
    # it via /bin/sh, but it carries a shebang and openbox.PLAN emits it 0755, so pin it
    # executable here too (archiso would otherwise normalize it to 0644). Pin both the
    # live-user copy (1000:998) and the /etc/skel copy (root-owned).
    "/home/main/.config/openbox/autostart": "1000:998:755",
    "/etc/skel/.config/openbox/autostart": "0:0:755",
    # The live-session Desktop "Az'arch Linux Installer" launcher. Same archiso mode-
    # normalization as azarch-install above: compiler.py emits it 0755, but the squashfs
    # ships it 0644 unless pinned here. Shipping it EXECUTABLE means a file manager that
    # honours the exec bit launches it on double-click without a "not trusted" prompt.
    # Both the live-user copy (uid 1000:998) and the /etc/skel copy (root-owned) are
    # pinned.
    "/home/main/Desktop/azarch-install.desktop": "1000:998:755",
    "/etc/skel/Desktop/azarch-install.desktop": "0:0:755",
    # Vendored ckbcomp (libraries/packages/calamares/ckbcomp.py), a Python 3 port of the
    # upstream Perl ckbcomp. Same archiso mode-normalization as azarch-install above: without
    # an explicit 0755 here it ships 0644, Calamares' `QProcess::start("ckbcomp")`
    # cannot execute it, and the keyboard-page preview stays BLANK ("ckbcomp not
    # found, keyboard preview disabled"). This entry keeps the exec bit so the preview
    # renders key legends.
    "/usr/bin/ckbcomp": "0:0:755",
    "/etc/sudoers.d/00-secure-path": "0:0:440",
    "/root/azarch/setup-locale.sh": "0:0:755",
    "/etc/systemd/system/locale-setup.service": "0:0:644",
    "/root/azarch/setup-pkgs.sh": "0:0:755",
    "/etc/systemd/system/pkgs-setup.service": "0:0:644",
}

# The HEADED-ONLY subset of FILE_PERMISSIONS: paths compiler.py plants into the
# airootfs ONLY on the GUI (headed) line, all inside its `if is_gui:` block
# (_emit_desktop / _emit_homedir / _emit_apps / _emit_calamares + the vendored
# ckbcomp copy). The HEADLESS line ships no GUI, so none of these files
# exist in its tree. mkarchiso's file_permissions pass chmods EVERY listed path and
# aborts the whole build if one is missing ("Failed to set permissions on
# .../usr/bin/ckbcomp. Outside of valid path." -- the exact headless-build failure),
# so the headless profiledef must list ONLY paths it actually plants. These keys are
# therefore filtered OUT of the headless map by permissions_for(); the headed map is
# the full FILE_PERMISSIONS above, unchanged. Anything NOT in this set is universal
# (releng base + the always-run compiler steps: shadow/gshadow, the sudoers.d
# drop-ins, /root*, choose-mirror/Installation_guide/livecd-sound, and the
# locale/pkgs setup scripts and units) and stays in BOTH lines.
_HEADED_ONLY_PERMISSION_PATHS = frozenset({
    # Calamares' vendored ckbcomp keyboard-preview helper (its keyboard page shells out to
    # it) -- emitted in _emit_desktop only, alongside the Calamares GUI.
    "/usr/bin/ckbcomp",
    # The GUI-shell launchers + compiled daemons (application menu, window switcher, sidebar
    # sync, timedate Flask home page) -- all emitted in _emit_desktop (headed line only).
    "/usr/local/lib/azarch/azarch-sidebar-sync",
    "/usr/local/bin/azarch-application-menu",
    "/usr/local/lib/azarch-application-menu/azarch-application-menu-daemon",
    "/usr/local/bin/azarch-window-switcher",
    "/usr/local/lib/azarch-window-switcher/azarch-window-switcher-daemon",
    "/usr/local/bin/azarch-timedate",
    # The OpenBox session autostart (live user + /etc/skel) -- _emit_desktop.
    "/home/main/.config/openbox/autostart",
    "/etc/skel/.config/openbox/autostart",
    # The Desktop "Az'arch Linux Installer" launcher (live user + /etc/skel).
    "/home/main/Desktop/azarch-install.desktop",
    "/etc/skel/Desktop/azarch-install.desktop",
})

# CAUTION -- the `azarch` COMMAND core is UNIVERSAL and must NOT be listed above. These paths
# (the azarch + azarch-install wrappers, the compiled azarch terminal UI + OSD binaries, and
# the passwords/backup/unpack/hypervisor commands) are emitted on BOTH lines by
# _emit_azarch_commands in compiler.py. mkarchiso copies the airootfs overlay with
# `cp -af --no-preserve=ownership,mode` (it DISCARDS the on-disk 0755 mode) and re-applies
# executability ONLY to paths present in this FILE_PERMISSIONS map. So if any of these were
# filtered out of the headless map they would ship 0644 (non-executable) on the headless line:
# `azarch` (a python3 script) would die "Permission denied", and worse, the sshd auto-setup
# unit -- whose ExecStart=/usr/local/bin/azarch --sshd-hypervisor now PASSES its
# ConditionPathExists (the file exists) -- would fail 203/EXEC and never enable sshd. That is
# the exact "headless-ssh has no ssh" bug, so these deliberately STAY universal:
#   /usr/local/bin/azarch, /usr/local/bin/azarch-install, /usr/local/lib/azarch/azarch,
#   /usr/local/lib/azarch/azarch-osd, /usr/local/bin/{passwords,backup,unpack,hypervisor}.


def permissions_for(variant: "_variants.Variant | str" = "base") -> dict[str, str]:
    """The file_permissions map for a build variant. The headed (GUI) line gets the
    full FILE_PERMISSIONS; the headless line gets it MINUS the headed-only
    paths it never plants (see _HEADED_ONLY_PERMISSION_PATHS) so mkarchiso does not
    abort trying to chmod files that are absent from the headless airootfs. Insertion
    order is preserved for a stable, diffable profiledef."""
    if _variants.coerce(variant).is_gui:
        return dict(FILE_PERMISSIONS)
    return {
        p: v
        for p, v in FILE_PERMISSIONS.items()
        if p not in _HEADED_ONLY_PERMISSION_PATHS
    }


def profiledef_sh(variant: "_variants.Variant | str" = "base") -> str:
    bootmodes = " ".join(f"'{m}'" for m in BOOTMODES)
    perms = "\n".join(f'  ["{p}"]="{v}"' for p, v in permissions_for(variant).items())
    iso_name = iso_name_for(variant)
    return f"""\
#!/usr/bin/env bash
# shellcheck disable=SC2034
#
# Generated by profile.py -- edit the Python, not this file.

iso_name="{iso_name}"
iso_label="AZARCH_$(date --date="@${{SOURCE_DATE_EPOCH:-$(date +%s)}}" +%Y%m)"
iso_publisher="{ISO_PUBLISHER}"
iso_application="{ISO_APPLICATION}"
iso_version="$(date --date="@${{SOURCE_DATE_EPOCH:-$(date +%s)}}" +%Y.%m.%d)"
install_dir="{INSTALL_DIR}"
buildmodes=('iso')
bootmodes=({bootmodes})
arch="x86_64"
cow_spacesize="4G"
pacman_conf="pacman.conf"
airootfs_image_type="squashfs"

### This line fixes an odd bug that appeared out of nowhere
### \"\"\"FATAL ERROR: xz uncompress failed with error code 9\"\"\"
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '15')
###

bootstrap_tarball_compression=('zstd' '-c' '-T0' '--auto-threads=logical' '--long' '-19')
file_permissions=(
{perms}
)
"""
