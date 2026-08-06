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
# of these (see steps.VARIANTS): steps.run loops over them, calling iso_name_for
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
    # (the sudo convention) rather than letting them ship 0644. steps.py emits
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
    # The Calamares launcher the Plasma autostart .desktop runs on live login.
    # archiso NORMALIZES overlay file modes when it packs the squashfs -- only
    # paths listed here keep an explicit mode. Without this entry the wrapper ships
    # 0644 (non-executable), so the autostart .desktop's Exec= cannot run it and
    # Calamares never auto-launches. THIS is what breaks the live installer.
    "/usr/local/bin/azarch-install": "0:0:755",
    "/usr/local/bin/azarch": "0:0:755",
    # The Az'arch application-menu launcher the panel icon Exec's (via the
    # org.kde.plasma.icon backing .desktop). SAME archiso mode-normalization as
    # azarch-install above: application_menu.PLAN emits it 0755, but the squashfs
    # ships it 0644 (non-executable) unless pinned here -- and then clicking the
    # panel icon runs a non-executable file and the menu never opens (the other half
    # of the "icon does nothing" bug, alongside the Type=Link backing-file fix).
    "/usr/local/bin/azarch-application-menu": "0:0:755",
    # The live-session Desktop "Az'arch Linux Installer" launcher. Same archiso mode-
    # normalization as azarch-install above: steps.py emits it 0755, but the squashfs
    # ships it 0644 unless pinned here. A 0644 (non-executable) .desktop on the Desktop
    # is UNTRUSTED to KDE -- KDesktopFile::isAuthorizedDesktopFile() returns false for a
    # user-owned, non-executable Exec= launcher, so Plasma's Folder View paints an
    # "emblem-important" WARNING BADGE over it (and prompts on first launch) until the
    # user marks it executable. THIS is the "weird warning icon that disappears once
    # you open the installer" report: the badge is gone after the first launch trusts
    # it. Pinning 0755 makes the shipped file executable -> authorized -> no badge, no
    # prompt, from first boot. Both the live-user copy (uid 1000:998) and the /etc/skel
    # copy (root-owned; root-owned is ALSO trusted) are pinned.
    "/home/main/Desktop/azarch-install.desktop": "1000:998:755",
    "/etc/skel/Desktop/azarch-install.desktop": "0:0:755",
    # The org.kde.plasma.icon backing .desktop for OUR menu applet (its localPath).
    # SAME trust rule as the Desktop launcher above: KDE's
    # KDesktopFile::isAuthorizedDesktopFile() treats a NON-executable Type=Application
    # file as UNTRUSTED, so the panel icon's KIO click path pops a modal "not trusted,
    # execute?" dialog (a "noisy error") and launches NOTHING. archiso normalizes home
    # files to 0644 in the squashfs, so without these pins the icon does nothing on a
    # fresh ISO. Pin both the live-user copy (1000:998) and the /etc/skel copy (root)
    # to 0755 -> executable -> trusted -> launches on first click.
    "/home/main/.local/share/plasma_icons/azarch-application-menu.desktop": "1000:998:755",
    "/etc/skel/.local/share/plasma_icons/azarch-application-menu.desktop": "0:0:755",
    # Vendored ckbcomp (libraries/azarch/ckbcomp), a Python 3 port of the upstream
    # Perl ckbcomp. Same archiso mode-normalization as azarch-install above: without
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
# Generated by azarch.configuration.profile -- edit the Python, not this file.

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
