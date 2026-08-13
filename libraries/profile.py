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

# ISO base names per build variant. mkarchiso names the artifact
# <iso_name>-<version>-<arch>.iso, so these drive the two output filenames:
#   base -> azarch-<ver>-x86_64.iso        (the normal live/install medium)
#   sshd -> azarch-sshd-<ver>-x86_64.iso   (same, but auto-runs
#                                           `azarch --sshd-hypervisor` at boot)
ISO_NAME = "azarch"
ISO_NAME_SSHD = "azarch-sshd"

# The set of recognized build variants -> iso_name. A single build assembles ALL
# of these (see compiler.VARIANTS): compiler.run loops over them, calling iso_name_for
# per variant to name each ISO. There is no build-time flag to pick one.
ISO_NAMES = {
    "base": ISO_NAME,
    "sshd": ISO_NAME_SSHD,
}

ISO_PUBLISHER = "michaelilgiaev <https://github.com/michaelilgiaev/azarch>"
ISO_APPLICATION = "Az'arch Installer/Az'arch Linux Live/Rescue DVD"
INSTALL_DIR = "arch"


def iso_name_for(variant: str = "base") -> str:
    """The mkarchiso iso_name for a build variant (unknown -> base 'azarch')."""
    return ISO_NAMES.get(variant, ISO_NAME)

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
    # The Az'arch timedate launcher (run by azarch-timedate.service, which ExecStart's it
    # to serve the Flask Time + Calendar home page at localhost:49154). SAME archiso mode-
    # normalization as azarch-install above: timedate.PLAN emits it 0755, but the squashfs
    # ships it 0644 (non-executable) unless pinned here -- and then systemd fails the unit
    # with status=203/EXEC (Permission denied) and the home page never listens, so a new
    # tab / the browser home page lands on a dead port. Verified on the built ISO.
    "/usr/local/bin/azarch-timedate": "0:0:755",
    # The COMPILED application-menu daemon binary (built by application_menu.build_daemon
    # and started from the OpenBox autostart). Same archiso mode-normalization: it is
    # installed 0755, but the squashfs would ship it 0644 unless pinned -- and the
    # autostart's `[ -x ... ]` guard would then skip it, so the menu is never pre-built
    # and the first Super press does nothing / starts nothing.
    "/usr/local/lib/azarch-application-menu/azarch-application-menu-daemon": "0:0:755",
    # The COMPILED bare-`azarch` TERMINAL UI binary (built by azarch_tui.build_tui and
    # EXEC'd by the `azarch` CLI for the no-argument case). Same archiso mode-normalization
    # as the menu daemon above: it is installed 0755, but the squashfs would ship it 0644
    # unless pinned -- and then the `azarch` launcher's os.access(..., X_OK) guard fails and
    # bare `azarch` silently falls back to the pointer message instead of opening the UI.
    "/usr/local/lib/azarch-tui/azarch-tui": "0:0:755",
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
    # Vendored ckbcomp (libraries/modifications/ckbcomp.py), a Python 3 port of the
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


def profiledef_sh(variant: str = "base") -> str:
    bootmodes = " ".join(f"'{m}'" for m in BOOTMODES)
    perms = "\n".join(f'  ["{p}"]="{v}"' for p, v in FILE_PERMISSIONS.items())
    iso_name = iso_name_for(variant)
    return f"""\
#!/usr/bin/env bash
# shellcheck disable=SC2034
#
# Generated by modifications.profile -- edit the Python, not this file.

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
