"""System-level configs: users, sudoers, OS branding, boot menus, and systemd
units. Each is authored here as a Python string.

Kept byte-faithful to the originals under the old conf/system/. The user/group
databases and sudoers files in particular are security-sensitive; the modes are
applied by compiler.py / profiledef (shadow 0400, sudoers 0440).
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
# deletes it -- so it never ships on the ISO. We use it to plant the branded
# os-release. Doing it here (post-pacstrap) avoids the file-conflict that pre-placing
# /usr/lib/os-release in the airootfs overlay would trigger against the owning
# `filesystem` package; see compiler.py step 7. The staged sources live under
# /root/azarch/ in the chroot. NoExtract (libraries/pacman.py) already kept
# `filesystem` from writing its own "Arch Linux" os-release, so usr/lib/os-release is
# absent until this cp lands ours.
#
# Wallpaper: the desktop is OpenBox now (KDE Plasma was removed), and OpenBox paints no
# wallpaper of its own -- feh sets the X root pixmap from the OpenBox autostart /
# ~/.xinitrc (see patches/openbox.py). So there is NO Plasma org.kde.image default
# to rewrite here anymore, and no bundled Plasma "Next" wallpaper / notifications
# plasmoid / krunner / kmenuedit to delete (those packages are gone from the manifest).
# The two azarch wallpaper images ship as plain files under /usr/share/wallpapers via
# compiler.py; feh reads the "years" image directly.
CUSTOMIZE_AIROOTFS = """\
#!/usr/bin/env bash
set -euo pipefail

# Brand the live system as Az'arch Linux. /etc/os-release symlinks to this path.
cp /root/azarch/os-release /usr/lib/os-release
chmod 0644 /usr/lib/os-release

# System theme DEFAULT (dark): compile the dconf keyfile (color-scheme='prefer-dark',
# from patches/openbox) into the binary /etc/dconf/db/local so the freedesktop appearance
# default is dark for every user out of the box. Runs here (post-pacstrap) because dconf is
# only installed inside the pacstrapped rootfs, not the airootfs overlay. A per-user
# `gsettings set` from `azarch theme` overrides this system default and persists.
if command -v dconf >/dev/null 2>&1; then
    dconf update || true
fi
"""

# getty@tty1 autologin override. The releng base autologins ROOT on tty1; the
# graphical live session must instead autologin the unprivileged `main` user, whose
# ~/.bash_profile execs startx into the OpenBox session. Running the desktop as root
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
# systemd-boot (UEFI) entries + syslinux (BIOS) configuration. %INSTALL_DIR% and
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

# systemd-boot loader.conf. Overrides the releng default (timeout/default/beep only)
# so the first-boot UEFI menu is SKIPPED entirely -- it boots straight into the
# default Az'arch entry with no menu shown, which is what the user asked for.
#
# `timeout 0` (menu-force disabled): systemd-boot does NOT render the menu and boots
# `default` immediately. The menu is still reachable by holding a key (Space) during
# firmware->loader handoff, so this is a skip, not a permanent removal.
#
# The auto-entry suppressions stay so that IF the user does force the menu open, it
# shows ONLY our two Az'arch entries -- none of the extra rows the earlier screenshot
# had:
#   * "EFI Shell"                     -- systemd-boot AUTO-discovers shell*.efi on the
#                                        ESP (mkarchiso plants shellx64.efi at /); this
#                                        auto entry (and systemd-boot's own self-entry)
#                                        is what `auto-entries no` hides.
#   * "Reboot Into Firmware Interface"-- systemd-boot AUTO-generates it when the firmware
#                                        supports it; `auto-firmware no` hides it (it is
#                                        still reachable with the `f` key).
# The third extra row, "Memtest86+", is NOT auto-discovered -- it is the explicit
# releng entry 03-archiso-memtest86+x64.conf, which compiler.py deletes from the profile
# (see step 4). `auto-entries no` does NOT touch our explicit 01/02 entries. `beep off`
# because the releng `beep on` is a leftover we don't want on the live medium.
BOOT_UEFI_LOADER = """\
timeout 0
default 01-archiso-linux.conf
beep off
auto-entries no
auto-firmware no
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

# syslinux top-level config (archiso_sys.cfg) -- the BIOS counterpart of the UEFI
# loader.conf skip. releng ships this with `TIMEOUT 150` (15s menu wait); we overlay
# it with `TIMEOUT 1` so BIOS boots the default entry effectively immediately too,
# matching the UEFI `timeout 0` skip. (syslinux `TIMEOUT 0` means wait FOREVER -- the
# opposite of a skip -- so `1` = 1/10s is the correct "boot now" value.) Kept
# byte-faithful to releng's archiso_sys.cfg except the TIMEOUT value; the INCLUDE
# lines must stay so the head/entries/tail still compose the menu when it is forced.
BOOT_BIOS_SYSLINUX_SYS = """\
INCLUDE archiso_head.cfg

DEFAULT arch64
TIMEOUT 1

INCLUDE archiso_sys-linux.cfg

INCLUDE archiso_tail.cfg
"""
# NOTE: `DEFAULT arch64` MUST name a LABEL that BOOT_BIOS_SYSLINUX defines. releng
# pairs `DEFAULT arch` with its `LABEL arch`, but our BOOT_BIOS_SYSLINUX renamed the
# labels to `arch64`/`arch64speech`, so the DEFAULT was retargeted to match. There is
# no ONTIMEOUT, so the TIMEOUT-1 auto-boot resolves to this DEFAULT -- a dangling label
# here would leave BIOS on the menu (or fail to auto-boot) instead of skipping. A test
# (test_bios_syslinux_default_resolves_to_a_real_label) guards the pairing.

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

# --- Power management: lid / power button (STATIC logind drop-in) -----------
# A systemd-logind drop-in shipped root-owned under airootfs/etc, so it governs
# BOTH the live ISO (bare console + OpenBox) AND the installed system -- the OFFLINE
# Calamares install rsyncs the live rootfs verbatim via unpackfs, so an /etc file
# on the medium lands on the target unchanged (no separate installer step needed).
#
# The user's requests:
#   * Closing the laptop lid does NOTHING (HandleLidSwitch=ignore, and the
#     external-power / docked variants too, so it is ignored regardless of AC or
#     dock state -- otherwise logind would still suspend on lid-close when on
#     battery, the default).
#   * The POWER BUTTON shuts the machine down cleanly (HandlePowerKey=poweroff,
#     which is systemd's default, pinned here so it is explicit and cannot drift).
#
# The idle-suspend policy (PC vs laptop, AC-aware) is NOT here: it depends on
# runtime chassis/AC state, so it is written dynamically by SLEEP_POLICY_SCRIPT
# into a SEPARATE drop-in (20-azarch-sleep.conf) and does not collide with this
# static file (10-*, lower number, both are merged by logind).
LOGIND_POWER_DROPIN = """\
# Az'arch power/lid/button policy (static half). Idle-suspend (PC vs laptop) is
# written separately by azarch-sleep-policy at 20-azarch-sleep.conf.
[Login]
# Closing the lid does nothing, on battery OR AC OR docked (default would suspend).
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
# The power button shuts the machine down (clean poweroff). This is also systemd's
# default; pinned explicitly so it is unambiguous.
HandlePowerKey=poweroff
"""


# --- Power management: PC-vs-laptop idle-sleep policy (DYNAMIC) --------------
# The user's request:
#   * PC (no battery)                 -> NEVER sleep.
#   * Laptop, unplugged (on battery)  -> sleep after 15 minutes idle.
#   * Laptop, plugged in (on AC)      -> NEVER sleep.
#
# This depends on RUNTIME state (is a battery present? is AC online?), so it cannot
# be a static file. A tiny script decides the policy and writes it into a logind
# drop-in, then reloads logind (SIGHUP re-reads its config -- no session kill). It
# runs once at boot AND on every AC-adapter hotplug (the udev rule below triggers
# the same service), so unplugging the charger arms the 15-minute idle timer and
# plugging it back in disarms it, live.
#
# WHY logind IdleAction: logind is the single idle manager that works on BOTH the
# bare-console live ISO and the OpenBox desktop, and it is DE-independent -- exactly
# the deterministic behaviour the request describes. With KDE's PowerDevil removed,
# logind is now the ONLY idle-suspend manager on the system. IdleActionSec=900 == 15
# minutes.
#
# Detection:
#   * "laptop" == at least one /sys/class/power_supply/* of type "Battery". This is
#     the reliable runtime signal (DMI chassis type via hostnamectl is frequently
#     wrong/unset on real hardware and in VMs); a battery is what actually makes
#     "sleep on battery" meaningful.
#   * "on AC" == at least one supply of type "Mains" with online == 1.
# The two enumerations are plain shell globs over sysfs -- no `$(...)` gymnastics --
# and the script is defensive (missing files, no supplies at all -> treated as PC).
SLEEP_POLICY_DROPIN_PATH = "/etc/systemd/logind.conf.d/20-azarch-sleep.conf"
SLEEP_POLICY_IDLE_SECONDS = 900  # 15 minutes

SLEEP_POLICY_SCRIPT = f"""\
#!/bin/bash
# azarch-sleep-policy -- auto-detect PC vs laptop and set the idle-sleep policy.
#
#   PC (no battery)                -> never sleep   (IdleAction=ignore)
#   laptop on battery (unplugged)  -> sleep in 15m  (IdleAction=suspend, {SLEEP_POLICY_IDLE_SECONDS}s)
#   laptop on AC (plugged in)      -> never sleep   (IdleAction=ignore)
#
# Writes {SLEEP_POLICY_DROPIN_PATH} and reloads systemd-logind so the change is
# live. Invoked at boot and by a udev rule on AC-adapter changes (plug/unplug).
set -u

DROPIN="{SLEEP_POLICY_DROPIN_PATH}"
IDLE_SECS={SLEEP_POLICY_IDLE_SECONDS}
SUPPLY=/sys/class/power_supply

has_battery() {{
    local ps t
    for ps in "$SUPPLY"/*; do
        [ -r "$ps/type" ] || continue
        t=$(cat "$ps/type" 2>/dev/null)
        [ "$t" = "Battery" ] && return 0
    done
    return 1
}}

on_ac() {{
    # True if any Mains (AC adapter) supply reports online == 1. A machine with a
    # battery but no Mains entry (or all Mains offline) counts as unplugged.
    local ps t online
    for ps in "$SUPPLY"/*; do
        [ -r "$ps/type" ] || continue
        t=$(cat "$ps/type" 2>/dev/null)
        [ "$t" = "Mains" ] || continue
        online=$(cat "$ps/online" 2>/dev/null)
        [ "$online" = "1" ] && return 0
    done
    return 1
}}

# Decide the action. Default: never sleep (covers PC and laptop-on-AC).
action="ignore"
secs=0
if has_battery && ! on_ac; then
    # Laptop, unplugged -> suspend after the idle delay.
    action="suspend"
    secs="$IDLE_SECS"
fi

mkdir -p "$(dirname "$DROPIN")"
cat > "$DROPIN" <<EOF
# Generated by azarch-sleep-policy (do not edit; regenerated at boot and on
# AC-adapter change). PC/laptop-on-AC -> ignore; laptop-on-battery -> suspend 15m.
[Login]
IdleAction=$action
IdleActionSec=$secs
EOF

# Re-read logind config live (SIGHUP); harmless if logind is not up yet (boot
# ordering already places us After it, and the udev-triggered runs are post-boot).
systemctl reload systemd-logind 2>/dev/null || true
"""

# The systemd unit that runs the sleep-policy script. Type=oneshot, run at boot
# (WantedBy multi-user.target) AND pulled by the udev rule on AC changes. It orders
# After systemd-logind so the reload lands on a running logind at boot; the
# udev-triggered invocations happen well after boot, when logind is already up.
SLEEP_POLICY_SERVICE = """\
[Unit]
Description=Az'arch PC/laptop idle-sleep policy (auto-detect battery + AC)
After=systemd-logind.service
Wants=systemd-logind.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/azarch-sleep-policy
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
"""

# udev rule: re-run the policy whenever an AC adapter (power_supply of type Mains)
# changes -- i.e. the charger is plugged in or unplugged. Matched on the power_supply
# subsystem and POWER_SUPPLY_TYPE=="Mains" so only AC plug/unplug (not battery-level
# ticks) retriggers it.
#
# We `RUN systemctl --no-block restart` rather than `ENV{SYSTEMD_WANTS}+=...`:
# plug/unplug fires an ACTION=="change" uevent on the SAME, already-active Mains
# `.device` unit, and systemd only acts on a device's `Wants=` when it FIRST becomes
# active -- a `Wants=` re-added on an already-active device is IGNORED
# (systemd.device(5): "will not act on them if they are added to devices that are
# already active"). So SYSTEMD_WANTS would run the oneshot once at boot and never
# again on plug/unplug -- the timer would never re-arm. `systemctl restart` runs the
# oneshot unconditionally every time (even from its normal inactive/dead state, since
# RemainAfterExit=no), so the policy is genuinely re-evaluated on each AC change.
# `--no-block` returns immediately so udev event processing is never stalled by the
# (fast, self-terminating) oneshot -- the "RUN can't do a long/settling task"
# constraint does not apply because we only kick a unit asynchronously, we do not run
# the work inline. Absolute systemctl path (udev RUN has a minimal PATH).
SLEEP_POLICY_UDEV_RULE = """\
# Re-evaluate the Az'arch idle-sleep policy when the AC adapter is plugged/unplugged.
SUBSYSTEM=="power_supply", ENV{POWER_SUPPLY_TYPE}=="Mains", ACTION=="change", RUN+="/usr/bin/systemctl --no-block restart azarch-sleep-policy.service"
"""


# --- sshd-hypervisor variant only -------------------------------------------
# Baked into the `azarch-sshd` ISO ONLY (compiler.py emits + enables it only when
# variant == "sshd"). It runs `azarch --sshd-hypervisor` automatically at boot --
# the whole point of that variant ("sudo azarch --sshd-hypervisor on by default").
#
# It runs as ROOT with Environment=SUDO_USER=main (rather than User=main) on
# purpose. The azarch CLI resolves its target user from ${SUDO_USER:-$(id -un)} and
# REFUSES a bare-root target, so SUDO_USER=main makes it stage the pubkey into
# /home/main/.ssh (the account sshd accepts) exactly as an interactive
# `sudo azarch --sshd-hypervisor` would. Running the UNIT as root avoids the PAM
# session a `User=main` unit would need for the CLI's internal `sudo` calls (mount
# the 9p share, ssh-keygen -A, ufw, systemctl enable --now sshd): as root those
# `sudo` invocations are trivial no-op elevations and the `install -o main` calls
# still hand the key files to `main`.
#
# It orders After the pkgs-setup oneshot because setup-pkgs.sh runs `ufw enable`
# with a default-reject-incoming policy; running after it means our `ufw allow ssh`
# is the final word and the forwarded host->guest :22 is actually reachable.
# NOTE: no `After=multi-user.target` -- this unit is itself WantedBy that target, and
# ordering after the target that pulls it in would push it past boot completion (or
# risk an ordering cycle). After=pkgs-setup.service (also WantedBy=multi-user.target)
# is sufficient and correct.
#
# Failure is non-fatal to boot: the guest still boots to the desktop if the shared
# folder / host pubkey is absent (e.g. booted without the hypervisor's shared dir).
# The azarch CLI exits non-zero in that case, but Type=oneshot + no other unit
# depending on it means the system carries on; the user can re-run it by hand.
SSHD_HYPERVISOR_SETUP_SERVICE = """\
[Unit]
Description=Az'arch sshd-hypervisor auto-setup (install host pubkey + start sshd)
After=pkgs-setup.service
Wants=pkgs-setup.service
ConditionPathExists=/usr/local/bin/azarch

[Service]
Type=oneshot
Environment=SUDO_USER=main
ExecStart=/usr/local/bin/azarch --sshd-hypervisor
RemainAfterExit=true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
