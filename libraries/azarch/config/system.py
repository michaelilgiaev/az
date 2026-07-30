"""System-level configs: users, sudoers, OS branding, boot menus, and systemd
units. Each is authored here as a Python string.

Kept byte-faithful to the originals under the old conf/system/. The user/group
databases and sudoers files in particular are security-sensitive; the modes are
applied by steps.py / profiledef (shadow 0400, sudoers 0440).
"""

from __future__ import annotations

# --- User / group databases -------------------------------------------------
# Baked into airootfs/etc so the live ISO has the `main` autologin user (uid 1000,
# gid 998=autologin) and a passwordless root. Blank password fields = no password.

PASSWD = """\
root:x:0:0:root:/root:/usr/bin/bash
main:x:1000:998::/home/main:/usr/bin/bash
"""

SHADOW = """\
root::14871::::::
main::14871::::::
"""

GSHADOW = """\
root:!*::
autologin:!*::
main:!*::
"""

GROUP = """\
root:x:0:
autologin:x:998:
main:x:1000:
"""

# --- sudoers ----------------------------------------------------------------
# 00-main: passwordless sudo for the live user. 00-rootpw: sudo asks for the ROOT
# password, not the user's (matches the blank-password live setup). Mode 0440.

SUDOERS_MAIN = "main ALL=(ALL) NOPASSWD: ALL\n"
SUDOERS_ROOTPW = "Defaults rootpw\n"
SUDOERS_SECURE_PATH = "Defaults secure_path=\"/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\"\n"

# --- OS branding ------------------------------------------------------------
# What fastfetch (and any os-release reader) shows as the distro name. Written to
# airootfs/usr/lib/os-release, the REAL file that /etc/os-release symlinks to.
# The stock file comes from the `filesystem` package and says "Arch Linux"; our
# airootfs copy overlays on top of the pacstrapped rootfs so it wins. mkarchiso
# still appends IMAGE_ID / IMAGE_VERSION lines of its own after this.
#
# ID stays `arch` on purpose: pacman, AUR helpers, and countless scripts key on
# ID=arch to treat the system as Arch. Only NAME/PRETTY_NAME (the human strings
# fastfetch prints) change to the azarch brand. ID_LIKE reinforces the lineage.
OS_RELEASE = """\
NAME="Az'arch Linux"
PRETTY_NAME="Az'arch Linux"
ID=arch
ID_LIKE=arch
BUILD_ID=rolling
ANSI_COLOR="38;2;6;184;253"
HOME_URL="https://github.com/michaelilgiaev/azarch"
SUPPORT_URL="https://github.com/michaelilgiaev/azarch"
BUG_REPORT_URL="https://github.com/michaelilgiaev/azarch/issues"
LOGO=archlinux-logo
"""

# Post-pacstrap customization hook. mkarchiso runs airootfs/root/customize_airootfs.sh
# INSIDE the pacstrapped rootfs (arch-chroot) AFTER packages are installed, then
# deletes it -- so it never ships on the ISO. We use it purely to plant the branded
# os-release: doing this here (post-pacstrap) avoids the file-conflict that pre-
# placing it in the airootfs overlay triggers against the `filesystem` package (see
# steps.py step 7). The staged source lives at /root/azarch/os-release in the chroot.
# NoExtract (config/pacman.py) already kept `filesystem` from writing its own
# "Arch Linux" copy, so usr/lib/os-release is absent until this cp lands ours.
CUSTOMIZE_AIROOTFS = """\
#!/usr/bin/env bash
set -euo pipefail

# Brand the live system as Az'arch Linux. /etc/os-release symlinks to this path.
cp /root/azarch/os-release /usr/lib/os-release
chmod 0644 /usr/lib/os-release
"""

# getty@tty1 autologin override. The releng base autologins ROOT on tty1; the
# graphical live session must instead autologin the unprivileged `main` user, whose
# ~/.bash_profile execs startx into the Openbox session. Running the desktop as root
# is wrong (Calamares/Qt dislike it, and the live user model expects `main`). The
# empty first ExecStart= clears the unit's default before we set ours (systemd
# requires the reset to override ExecStart in a drop-in).
GETTY_TTY1_AUTOLOGIN = """\
[Service]
ExecStart=
ExecStart=-/usr/bin/agetty --noreset --noclear --autologin main - $TERM
"""

# System hostname. The archiso releng base ships `archiso`; we overlay `azarch`
# so the shell prompt and fastfetch title read main@azarch instead of main@archiso.
# (We deliberately do NOT rename the `archiso` build TOOLING or the ISO's internal
# install_dir -- those are functional identifiers from the archiso project, not
# branding.) The plain `azarch` here is the live-ISO hostname; the on-disk
# installer sets the installed system's hostname separately.
HOSTNAME = "azarch\n"

# --- Boot menu entries ------------------------------------------------------
# systemd-boot (UEFI) entries + syslinux (BIOS) config. %INSTALL_DIR% and
# %ARCHISO_UUID% are archiso placeholders substituted by mkarchiso.

BOOT_UEFI_LINUX = """\
title    Az'arch Linux install medium (x86_64, UEFI)
sort-key 01
linux    /%INSTALL_DIR%/boot/x86_64/vmlinuz-linux
initrd   /%INSTALL_DIR%/boot/x86_64/initramfs-linux.img
options  archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID% cow_spacesize=4G
"""

BOOT_UEFI_SPEECH = """\
title    Az'arch Linux install medium (x86_64, UEFI) with speech
sort-key 02
linux    /%INSTALL_DIR%/boot/x86_64/vmlinuz-linux
initrd   /%INSTALL_DIR%/boot/x86_64/initramfs-linux.img
options  archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID% accessibility=on cow_spacesize=4G
"""

BOOT_BIOS_SYSLINUX = """\
LABEL arch64
TEXT HELP
Boot the Az'arch Linux install medium on BIOS.
It allows you to install Az'arch Linux or perform system maintenance.
ENDTEXT
MENU LABEL Az'arch Linux install medium (x86_64, BIOS)
LINUX /%INSTALL_DIR%/boot/x86_64/vmlinuz-linux
INITRD /%INSTALL_DIR%/boot/x86_64/initramfs-linux.img
APPEND archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID% cow_spacesize=4G

# Accessibility boot option
LABEL arch64speech
TEXT HELP
Boot the Az'arch Linux install medium on BIOS with speakup screen reader.
It allows you to install Az'arch Linux or perform system maintenance with speech feedback.
ENDTEXT
MENU LABEL Az'arch Linux install medium (x86_64, BIOS) with ^speech
LINUX /%INSTALL_DIR%/boot/x86_64/vmlinuz-linux
INITRD /%INSTALL_DIR%/boot/x86_64/initramfs-linux.img
APPEND archisobasedir=%INSTALL_DIR% archisosearchuuid=%ARCHISO_UUID% accessibility=on cow_spacesize=4G
"""

# syslinux (BIOS) menu chrome. The releng archiso_head.cfg sets `MENU TITLE Arch
# Linux`; the build overlays this rebranded head so the BIOS boot screen title
# reads Az'arch. Kept byte-faithful to releng's head.cfg except the MENU TITLE.
BOOT_BIOS_SYSLINUX_HEAD = """\
SERIAL 0 115200
UI vesamenu.c32
MENU TITLE Az'arch Linux
MENU BACKGROUND splash.png

MENU WIDTH 78
MENU MARGIN 4
MENU ROWS 7
MENU VSHIFT 10
MENU TABMSGROW 14
MENU CMDLINEROW 14
MENU HELPMSGROW 16
MENU HELPMSGENDROW 29

# Refer to https://wiki.syslinux.org/wiki/index.php/Comboot/menu.c32

MENU COLOR border       30;44   #40ffffff #a0000000 std
MENU COLOR title        1;36;44 #9033ccff #a0000000 std
MENU COLOR sel          7;37;40 #e0ffffff #20ffffff all
MENU COLOR unsel        37;44   #50ffffff #a0000000 std
MENU COLOR help         37;40   #c0ffffff #a0000000 std
MENU COLOR timeout_msg  37;40   #80ffffff #00000000 std
MENU COLOR timeout      1;37;40 #c0ffffff #00000000 std
MENU COLOR msg07        37;40   #90ffffff #a0000000 std
MENU COLOR tabmsg       31;40   #30ffffff #00000000 std

MENU CLEAR
MENU IMMEDIATE
"""

# --- systemd units ----------------------------------------------------------
# Two oneshot services baked into the LIVE ISO: setup-locale (auto-detect
# locale/keyboard/timezone from IP) and setup-pkgs (firewall + theme tweaks).

LOCALE_SETUP_SERVICE = """\
[Unit]
Description=Auto-detect locale, keyboard, and timezone
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/root/azarch/setup-locale.sh
StandardOutput=journal
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""

PKGS_SETUP_SERVICE = """\
[Unit]
Description=Configure Packages
After=network.target
ConditionPathExists=/root/azarch/setup-pkgs.sh

[Service]
Type=oneshot
ExecStart=/root/azarch/setup-pkgs.sh
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
"""
