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
# deletes it -- so it never ships on the ISO. We use it to (1) plant the branded
# os-release and (2) set the DEFAULT Plasma wallpaper. Doing both here (post-pacstrap)
# avoids the file-conflicts that pre-placing files in the airootfs overlay triggers
# against the owning packages (filesystem / plasma-workspace); see steps.py step 7.
# The staged sources live under /root/azarch/ in the chroot. NoExtract
# (configuration/pacman.py) already kept `filesystem` from writing its own "Arch Linux"
# os-release, so usr/lib/os-release is absent until this cp lands ours.
#
# Wallpaper: rather than seeding a per-user appletsrc Image= (which plasmashell
# regenerates on first login, orphaning the seed -> the desktop falls back to a
# black/default background), we rewrite the DEFAULT of the org.kde.image wallpaper
# plugin (owned by plasma-workspace at a stable path). That default is what Plasma
# uses for any containment with no explicit image, so it survives appletsrc
# regeneration and applies to every user. unpackfs copies this edited file onto the
# installed target, so the installed system inherits the same default -- no separate
# Calamares step needed. The edit is idempotent and a no-op if Plasma is absent.
CUSTOMIZE_AIROOTFS = """\
#!/usr/bin/env bash
set -euo pipefail

# Brand the live system as Az'arch Linux. /etc/os-release symlinks to this path.
cp /root/azarch/os-release /usr/lib/os-release
chmod 0644 /usr/lib/os-release

# Set the default Plasma wallpaper by rewriting the org.kde.image plugin's Image
# default (the fallback Plasma uses when a containment has no explicit image). This
# is regeneration-proof, unlike a per-user appletsrc Image= seed.
# WALLPAPER points at the "years" KPackage DIRECTORY (== desktop.WALLPAPER_PACKAGE_DIR),
# NOT its inner image file: Plasma 6's wallpaper grid routes a DIRECTORY to the package
# model (matched to the existing "years" tile) but routes a FILE path to the loose-
# image model, which injects it as a THIRD, duplicate tile labelled by the filename
# ("1672x941"). Using the package dir keeps the grid to exactly "years"/"decades"
# with "years" as the default. (test_configuration_system pins this equality.)
IMG_MAIN_XML="/usr/share/plasma/wallpapers/org.kde.image/contents/config/main.xml"
WALLPAPER="/usr/share/wallpapers/years/"
# The wallpaper is not build-critical, so a parse surprise must not abort the ISO
# build: guard the edit with `|| true`. `-d "$WALLPAPER"` (a directory now).
if [ -f "$IMG_MAIN_XML" ] && [ -d "$WALLPAPER" ]; then
    python3 - "$IMG_MAIN_XML" "file://$WALLPAPER" <<'PYEOF' || true
import re
import sys

path, uri = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    xml = fh.read()

# Replace the <default>...</default> (or self-closing <default/>) INSIDE the
# <entry name="Image" ...> ... </entry> block only, leaving every other entry
# untouched. Anchored on the Image entry so no other wallpaper option is affected.
entry = re.compile(r'(<entry\\s+name="Image".*?</entry>)', re.DOTALL)


def fix(m):
    block = m.group(1)
    if "<default" not in block:
        # Insert a default right after the entry's opening tag if none exists.
        return re.sub(r'(<entry\\s+name="Image"[^>]*>)',
                      r'\\1\\n      <default>%s</default>' % uri, block, count=1)
    block = re.sub(r'<default\\s*/>', '<default>%s</default>' % uri, block, count=1)
    block = re.sub(r'<default>.*?</default>', '<default>%s</default>' % uri,
                   block, count=1, flags=re.DOTALL)
    return block


new = entry.sub(fix, xml, count=1)
if new != xml:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
PYEOF
fi

# Remove the stock Plasma "Next" wallpaper so the "Desktop and Wallpaper" grid
# shows ONLY the azarch wallpapers ("years", "decades") shipped as KPackages under
# /usr/share/wallpapers. "Next" is bundled with plasma-workspace (not a separate
# removable package), so it must be deleted here rather than dropped from the
# manifest. Guarded so a layout change upstream never aborts the build.
rm -rf /usr/share/wallpapers/Next || true

# Remove the Plasma NOTIFICATIONS applet ENTIRELY -- the distro ships with no
# notifications ("i straight up dont need notifications on the distro, remove it
# entirely"). Deleting the plasmoid .so means plasmashell cannot load or
# auto-discover it into any system tray, so no notification widget can appear. It is
# bundled inside plasma-workspace (a core package that cannot be dropped from the
# manifest), so the applet file is deleted here. Guarded with `|| true` so a path
# change upstream never aborts the ISO build. The `.so` is the loadable applet; the
# glob also clears any packaged metadata/plasmoid dir if present.
rm -f /usr/lib/qt6/plugins/plasma/applets/org.kde.plasma.notifications.so || true
rm -rf /usr/share/plasma/plasmoids/org.kde.plasma.notifications || true
"""

# getty@tty1 autologin override. The releng base autologins ROOT on tty1; the
# graphical live session must instead autologin the unprivileged `main` user, whose
# ~/.bash_profile execs startx into the Plasma session. Running the desktop as root
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

# --- Power management: lid / power button (STATIC logind drop-in) -----------
# A systemd-logind drop-in shipped root-owned under airootfs/etc, so it governs
# BOTH the live ISO (bare console + Plasma) AND the installed system -- the OFFLINE
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
# WHY logind IdleAction (not PowerDevil): logind is the single idle manager that
# works on BOTH the bare-console live ISO and the installed Plasma desktop, and it
# is DE-independent -- exactly the deterministic behaviour the request describes.
# IdleActionSec=900 == 15 minutes.
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
# Baked into the `azarch-sshd` ISO ONLY (steps.py emits + enables it only when
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
