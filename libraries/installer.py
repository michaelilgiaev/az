"""The on-disk install pipeline scripts, authored in Python and emitted as the
real .sh/.conf/.service files the ISO ships.

  installer_sh()             azarch-iso-installer.sh: partition, CLONE the live rootfs
                             verbatim into the target, run chroot-setup
  chroot_setup_sh()          runs inside arch-chroot: locale, bootloader, services
  setup_pkgs_sh()            live-ISO oneshot: firewall tweaks
  first_boot_sh/service/conf first-boot-once mechanism on the installed system

WHY A VERBATIM ROOTFS CLONE (not pacstrap): the Az'arch desktop shell is a set of
COMPILED C daemons + generated helper binaries (the application-menu daemon, the
window-switcher daemon, the terminal UI, the OSD, the /usr/local/bin launchers, the
wallpapers, /etc/xdg/azarch-picom.conf, the timedate app, ...). The compiler emits
them as root-owned files straight into the ISO airootfs; NONE are owned by a pacman
package. So a fresh `pacstrap` of packages.x86_64 + a hand-copy of a few files (the
old approach) left every one of those binaries ABSENT on the installed system: X and
OpenBox came up to a gray root window, but the autostart's guarded daemon launches
silently no-op'd and the Super-key menu launcher failed ("Openbox error"). The
Calamares GUI never had this bug because its `unpackfs` module rsyncs the ENTIRE live
squashfs rootfs verbatim into the target. This scripted installer now does the same
thing -- rsync the live running `/` into `/mnt` -- so the CLI/SSH install reaches the
exact same end-state as Calamares by construction (same binaries, same desktop, same
config), instead of trying to re-enumerate every root-owned artifact by hand.
"""

from __future__ import annotations

import shlex

import installer_identity
from packages.calamares import calamares_shellprocess as _csp
from packages.calamares.locale import _detect_and_apply_locale_block


# Paths excluded from the live-rootfs -> target rsync. The kernel/virtual filesystems
# (/proc, /sys, /dev) hold no real files; the runtime trees (/run -- which on archiso
# holds the cow/bootmnt SquashFS overlay under /run/archiso -- and /tmp, /var/tmp) are
# transient; /mnt is the TARGET itself (excluding it prevents the rsync from recursing
# into its own destination); /media and /lost+found are irrelevant. This is the same set
# archiso/Calamares' unpackfs skip for a faithful clone. Kept as a constant so the bash
# generator stays readable and the exclude set is unit-testable in one place.
LIVE_ROOTFS_RSYNC_EXCLUDES = (
    "/proc", "/sys", "/dev", "/run", "/mnt", "/media", "/tmp", "/var/tmp", "/lost+found",
)


# --- The instant (unattended auto-install) autorun --------------------------
# The `instant` variants boot straight into an automatic install: target the
# largest non-USB disk, user `main`, hostname `azarch`, timezone from the compile
# flag (default Asia/Jerusalem), and either the ssh password (ssh variants) or a
# LOCKED `!*` account (non-ssh -- Ubuntu-style: the account exists, no password
# login). It is the SAME scripted installer the CLI/SSH path runs, just driven by
# the AZ_INSTALL_* pre-seed env the installer + identity steps already honour -- so
# instant reuses all of that (largest-disk detection, the rootfs clone, chroot
# setup) rather than reimplementing any of it. It is console-only (no X), so it
# works identically on the headed AND the headless line.

def instant_install_sh(timezone: str = "Asia/Jerusalem", ssh: bool = False,
                       encrypt: bool = False, user: str = "main",
                       passphrase: str | None = None) -> str:
    """The instant autorun script (staged under /root/azarch, ExecStart'd by
    system.INSTANT_INSTALL_SERVICE on the live medium). It exports the AZ_INSTALL_*
    pre-seed and execs the CLI installer unattended.

    timezone: the installed system's timezone (compile-time --timezone; validated on
    the build host before it reaches here). Baked into AZ_INSTALL_TIMEZONE, which the
    identity chroot step re-points /etc/localtime to.

    user: the installed login name (compile-time --user, default `main`). Baked into
    AZ_INSTALL_USERNAME so the identity chroot step renames the cloned `main` to it.

    ssh: True for the *-instant-ssh variants. The ssh variant already baked the
    operator's --ssh password hash into the LIVE `main` shadow, and the verbatim
    rootfs clone copies that hash onto the target -- so the installed `main` inherits
    the ssh password with NO password pre-seed here (we must NOT pass a lock
    sentinel, or we would relock the account the operator wants to log into). For a
    NON-ssh instant variant we pass AZ_INSTALL_LOCK=1 so the identity chroot step
    LOCKS `main` (and root) to `!` instead of setting any password -- the Ubuntu `!*`
    default the prompt asks for. Root is locked in BOTH cases.

    encrypt: True for --encrypt builds. Exports AZ_INSTALL_ENCRYPT=1 so the disk step
    LUKS-formats the target with the ONE password. For an ssh variant the passphrase is
    the already-cloned account password (no plaintext needed here); for a NON-ssh
    encrypted variant the account is LOCKED yet LUKS still needs the secret, so the
    compiler threads the plaintext `passphrase` and it is exported as AZ_INSTALL_PASSWORD
    (used ONLY for the LUKS passphrase -- login stays locked via AZ_INSTALL_LOCK). This
    script is root-owned mode 0700 in the image; the passphrase is the unattended
    install's secret and lives only there.

    The largest-disk auto-target + skip-confirmation come from AZ_INSTALL_CHOICE=1
    (installer.installer_sh honours it), so the whole run is non-interactive."""
    # Password posture. Non-ssh -> LOCK the account (`!*`, no password login). ssh -> KEEP the
    # password already cloned from the live medium (the operator's --ssh hash was baked into
    # `main`'s shadow and the verbatim rootfs clone carried it onto the target), so we neither
    # prompt nor change it. Exactly one sentinel is set, so the identity step never falls into
    # an interactive password read under this TTY-less service.
    password_line = "export AZ_INSTALL_KEEP_PASSWORD=1\n" if ssh else "export AZ_INSTALL_LOCK=1\n"
    # Encryption pre-seed. AZ_INSTALL_ENCRYPT drives the LUKS branch in installer_sh; a
    # non-ssh encrypted variant also needs the passphrase (the locked account carries none),
    # so export it here from the compile-time password. shlex.quote keeps an odd password safe.
    encrypt_line = ""
    if encrypt:
        encrypt_line = "export AZ_INSTALL_ENCRYPT=1\n"
        if passphrase:
            encrypt_line += f"export AZ_INSTALL_PASSWORD={shlex.quote(passphrase)}\n"
    return f"""\
#!/bin/bash
# Az'arch INSTANT unattended install. Runs once, on the live medium, from
# system.INSTANT_INSTALL_SERVICE. Non-interactive: every answer is pre-seeded.
set -o pipefail

echo
echo "=== Az'arch instant install ==="
echo "Targeting the largest non-USB disk and installing automatically."
echo "User '{user}', hostname 'azarch', timezone '{timezone}'."
echo

# Largest non-USB disk, no confirmation prompt (installer.installer_sh honours these).
export AZ_INSTALL_CHOICE=1
# Identity defaults (installer_identity honours these; unset fields would prompt).
export AZ_INSTALL_USERNAME={user}
export AZ_INSTALL_HOSTNAME=azarch
export AZ_INSTALL_TIMEZONE={timezone!r}
{password_line}{encrypt_line}# Hand off to the SAME scripted installer the CLI/SSH path uses.
exec bash /root/azarch/azarch-install-cli.sh
"""


# --- The disk installer (runs in the live session) --------------------------
def installer_sh() -> str:
    body = """\
#!/bin/bash

set -o pipefail

cd /

# ANSI color codes
LIGHT_BLUE='\\033[1;34m'
RED='\\033[1;31m'
RESET='\\033[0m'

echo -e "${LIGHT_BLUE}Welcome to azarch Installation${RESET}"
echo -e "${RED}WARNING:${RESET} This will erase everything on the targeted disk using wipefs -a, removing all filesystem, RAID, and partition-table signatures${RESET}"
echo "Select an installation option:"
echo "1. Automatically detect largest disk (excludes USB drives) and install azarch"
echo "2. Manually select disk to erase and install azarch"
# Non-interactive pre-seed (used by `azarch-install --cli --auto` / `--disk`, so an SSH
# install can run unattended): if AZ_INSTALL_CHOICE is set we use it instead of prompting;
# AZ_INSTALL_DISK pre-answers the manual device prompt. Unset -> the interactive read runs,
# so a plain `azarch-install --cli` over SSH still works step by step.
if [ -n "$AZ_INSTALL_CHOICE" ]; then
    choice="$AZ_INSTALL_CHOICE"
    echo "Enter option (1 or 2): $choice (pre-seeded)"
else
    read -p "Enter option (1 or 2): " choice
fi

# Convert size strings to bytes
convert_to_bytes() {
    local size=$1
    local unit=${size: -1}
    local num=${size%[A-Za-z]*}

    case $unit in
        T) awk "BEGIN {printf \\"%.0f\\", $num * 1024 * 1024 * 1024 * 1024}" ;;
        G) awk "BEGIN {printf \\"%.0f\\", $num * 1024 * 1024 * 1024}" ;;
        M) awk "BEGIN {printf \\"%.0f\\", $num * 1024 * 1024}" ;;
        K) awk "BEGIN {printf \\"%.0f\\", $num * 1024}" ;;
        *) awk "BEGIN {printf \\"%.0f\\", $num}" ;;
    esac
}

if [ "$choice" = "2" ]; then
    echo "Available disks:"
    echo "----------------"
    lsblk -d -e7,11 -o NAME,SIZE,MODEL | while read -r line; do
        echo "$line"
    done
    echo "----------------"
    if [ -n "$AZ_INSTALL_DISK" ]; then
        manual_disk="$AZ_INSTALL_DISK"
        echo "Enter the device name (e.g., sda or nvme0n1): $manual_disk (pre-seeded)"
    else
        read -p "Enter the device name (e.g., sda or nvme0n1): " manual_disk
    fi
    if [ ! -b "/dev/$manual_disk" ]; then
        echo "Invalid disk selected!"
        exit 1
    fi

    if mount | grep -q "/dev/$manual_disk"; then
        echo "Selected disk is mounted. Aborting."
        exit 1
    fi

    largest_disk="/dev/$manual_disk"
else
    echo "Searching for largest storage device..."

    largest_size=0
    largest_disk=""

    while read -r disk hotplug size; do
        if [[ "$hotplug" -eq 1 || "$disk" == loop* ]]; then
            continue
        fi
        if lsblk -d -o NAME,MOUNTPOINTS -n "/dev/$disk" | grep -q "[[:space:]]\\+/"; then
            echo "Skipping $disk (contains mounted partitions)"
            continue
        fi
        size_bytes=$(convert_to_bytes "$size")
        if [ "$size_bytes" -gt "$largest_size" ]; then
            largest_size=$size_bytes
            largest_disk="/dev/$disk"
        fi
    done < <(lsblk -d -o NAME,HOTPLUG,SIZE -n)

    if [ -z "$largest_disk" ]; then
        echo "No suitable disk found!"
        exit 1
    fi

    human_size=$(lsblk -d -o SIZE -n "$largest_disk")
    echo "Largest disk detected: $largest_disk ($human_size)"
fi

is_uefi=0
if [ -d "/sys/firmware/efi" ]; then
  is_uefi=1
fi

# Collect the account / hostname / timezone answers (Calamares Users + Location parity) NOW,
# before anything destructive -- a mistyped answer costs nothing while the disk is untouched.
%IDENTITY_COLLECT%

# Final confirmation before the irreversible wipe (skipped when a disk was pre-seeded for an
# unattended install -- AZ_INSTALL_CHOICE/DISK imply "proceed without asking").
if [ -z "$AZ_INSTALL_CHOICE" ]; then
    echo
    echo -e "${RED}About to ERASE $largest_disk and install azarch as host '$az_hostname' (user '$az_username').${RESET}"
    read -rp "Type YES to proceed: " az_confirm
    if [ "$az_confirm" != "YES" ]; then
        echo "Aborted; no changes were made."
        exit 1
    fi
fi

echo "Erasing $largest_disk with 'wipefs -a'..."
wipefs -a "$largest_disk"

if [ $is_uefi -eq 1 ]; then
  echo "Partitioning $largest_disk for UEFI..."
  echo -e "g\\nn\\n\\n\\n+1G\\nt\\n1\\nn\\n\\n\\n\\nw" | fdisk "$largest_disk"
else
  echo "Partitioning $largest_disk for BIOS..."
  echo -e "g\\nn\\n\\n\\n+1M\\nt\\n4\\nn\\n\\n\\n\\nw" | fdisk "$largest_disk"
fi

if [[ $largest_disk =~ ^/dev/nvme ]]; then
    part1="${largest_disk}p1"
    part2="${largest_disk}p2"
else
    part1="${largest_disk}1"
    part2="${largest_disk}2"
fi

# Optional full-disk encryption (AZ_INSTALL_ENCRYPT=1, from the instant --encrypt path).
# LUKS1 (not luks2) so GRUB can unlock /boot on the encrypted root, matching the Calamares
# luksGeneration:luks1 choice. Format part2 as the container with the ONE password, open it,
# and use the mapper device as the root target. az_root_dev is the device everything below
# (mkfs, mount, crypttab) works against, so a non-encrypted install is unchanged.
az_root_dev="$part2"
az_crypt_uuid=""
if [ "$AZ_INSTALL_ENCRYPT" = "1" ] && [ -n "$AZ_INSTALL_PASSWORD" ]; then
    echo "Encrypting $part2 with LUKS1..."
    printf '%s' "$AZ_INSTALL_PASSWORD" | cryptsetup luksFormat --type luks1 --batch-mode "$part2" -
    printf '%s' "$AZ_INSTALL_PASSWORD" | cryptsetup open "$part2" azarch_root -
    az_root_dev="/dev/mapper/azarch_root"
    az_crypt_uuid="$(blkid -s UUID -o value "$part2")"
fi

echo "Formatting partitions..."
if [ $is_uefi -eq 1 ]; then
  mkfs.fat -F32 "$part1"
fi
mkfs.ext4 "$az_root_dev"

echo "Mounting partitions..."
mkdir -p /mnt
mount "$az_root_dev" /mnt
if [ $is_uefi -eq 1 ]; then
  mkdir -p /mnt/boot/EFI
  mount "$part1" /mnt/boot/EFI
fi

echo "Cloning the live system onto the target (this is the whole desktop)..."
# CLONE THE LIVE ROOTFS VERBATIM into the mounted target -- the Calamares `unpackfs` path,
# done with rsync. The live running `/` is the SquashFS root plus the live overlay: it already
# contains EVERYTHING the installed system needs -- every compiled Az'arch daemon/binary under
# /usr/local, the wallpapers, /etc/xdg/azarch-picom.conf, the branded /usr/lib/os-release, the
# planted per-app overrides (kitty icon, gedit launcher), the fastfetch config, the first-boot
# unit + script, the /home/main desktop dotfiles (.bash_profile -> exec startx, .xinitrc,
# .config/openbox/*, themes), the getty@tty1 autologin drop-in, the /etc/{passwd,shadow,group}
# accounts (so `main` exists with the --ssh password hash on the ssh variant), the sudoers
# drop-ins, AND -- on the ssh variant -- the sshd-hypervisor-setup enable-link under
# /etc/systemd/system/multi-user.target.wants. So there is NO per-file hand-copy here anymore:
# the single rsync supersedes all of it, which is exactly why the installed CLI system now
# matches the live desktop instead of booting to a gray screen. -aAXH preserves perms/owners,
# ACLs, xattrs and hardlinks; --exclude keeps the virtual/runtime trees and the target itself
# out (see LIVE_ROOTFS_RSYNC_EXCLUDES).
rsync -aAXH %RSYNC_EXCLUDES% / /mnt/

echo "Regenerating fstab for the installed disk..."
# The cloned /etc/fstab is the archiso live one (its root is the SquashFS/cow overlay, wrong
# for a real disk). Regenerate it for the ACTUAL target partitions, or the installed system
# cannot mount its own root. genfstab appends; the clone's fstab is emptied first so we do not
# stack a stale archiso entry under the real ones.
: > /mnt/etc/fstab
genfstab -U /mnt >> /mnt/etc/fstab

# Drop the install_info markers AFTER the clone so they sit ON TOP of the copied /etc (the
# chroot step reads disk / is_uefi / the identity answers from here). /etc/install_info does
# not exist on the live medium, so the rsync above never touches it -- writing it here keeps
# it robust regardless of rsync flags.
mkdir -p /mnt/etc/install_info
echo "$largest_disk" > /mnt/etc/install_info/disk
echo "$is_uefi" > /mnt/etc/install_info/is_uefi
# Encryption markers for the chroot step (crypttab + GRUB cryptodisk). Only present when
# the disk was actually LUKS-formatted above; az_crypt_uuid is the LUKS container's UUID.
if [ -n "$az_crypt_uuid" ]; then
    echo "1" > /mnt/etc/install_info/encrypt
    echo "$az_crypt_uuid" > /mnt/etc/install_info/crypt_uuid
fi
%IDENTITY_WRITE%

# RECREATE THE VIRTUAL/RUNTIME MOUNT POINTS the rsync excluded. --exclude drops not just the
# CONTENTS of /proc /sys /dev /run /tmp but the DIRECTORY NODES themselves, so on the fresh ext4
# target these dirs do not exist. arch-chroot bind-mounts /proc onto /mnt/proc (and /sys, /dev,
# /run likewise); without the mount points it dies with "mount: /mnt/proc: mount point does not
# exist" and the whole install aborts. Recreate them empty (Calamares' mount module makes the
# same nodes). /tmp gets the world-writable sticky mode any chrooted tool expects.
mkdir -p /mnt/proc /mnt/sys /mnt/dev /mnt/run /mnt/tmp
chmod 1777 /mnt/tmp

echo "Copying chroot setup..."
cp /root/azarch/chroot-setup.sh /mnt/chroot-setup.sh
chmod +x /mnt/chroot-setup.sh

echo "Running chroot setup..."
arch-chroot /mnt /bin/bash /chroot-setup.sh
rm /mnt/chroot-setup.sh

umount -R /mnt
"""
    # Splice in the identity collection/persist fragments (Calamares Users + Location parity)
    # and the rsync exclude flags. Prefix /mnt: the installer targets the mounted new root.
    body = body.replace("%IDENTITY_COLLECT%", installer_identity.identity_collect_sh().strip("\n"))
    body = body.replace("%IDENTITY_WRITE%", installer_identity.identity_write_sh().strip("\n"))
    excludes = " ".join(f"--exclude={p}" for p in LIVE_ROOTFS_RSYNC_EXCLUDES)
    return body.replace("%RSYNC_EXCLUDES%", excludes)


# --- Runs inside the arch-chroot after the rootfs clone ---------------------
def chroot_setup_sh(is_gui: bool = True) -> str:
    """The chroot-setup script the on-disk installer runs inside arch-chroot.

    is_gui: True for the headed line, False for the headless line. The ONE
    difference is the OpenBox live-installer-state cleanup at the end: it strips the live
    OpenBox autostart's installer-relaunch lines and swaps in the installed-system
    autostart (openbox-autostart-installed). That staged file and that whole GUI-session
    cleanup exist ONLY on the headed line (compiler._emit_desktop stages the source; the
    headless line skips it). Running the cleanup on a headless line would `cp` a file that
    was never staged and, under the block's `set -e`, ABORT the whole install. So the
    headless chroot omits the GUI-session cleanup entirely -- there is no OpenBox autostart
    to fix on a headless system, and the live-only installer .desktop/wrapper it also
    removed never existed on the headless line either."""
    chroot = f"""\
#!/bin/bash

{_detect_and_apply_locale_block()}

# FRESH MACHINE-ID. The rootfs clone copied the LIVE /etc/machine-id verbatim, so every
# system installed from this ISO would otherwise share one id -- breaking DHCP leases,
# systemd journal ids and anything keyed on machine-id. Empty the file so systemd
# regenerates a unique id on the installed system's first boot (the documented reset:
# `systemd-machine-id-setup` reads an empty/absent file and mints a new one).
: > /etc/machine-id

pacman-key --init
pacman-key --populate archlinux

# Mark setup complete
touch /var/log/.locale_set

# UNDO THE ARCHISO MKINITCPIO STATE BEFORE building the initramfs. The verbatim clone carries
# archiso's mkinitcpio artifacts, and a plain `mkinitcpio -P` on them yields an UNBOOTABLE
# installed system. This is the SAME reset the Calamares path runs post-unpackfs -- and to
# guarantee the two install paths can never drift, the CLI does not re-derive it: it EMBEDS the
# exact shared command block from packages/calamares (a single source of truth). That block:
#   A. reinstates /boot/vmlinuz-linux from /usr/lib/modules/<kver>/vmlinuz (mkarchiso empties
#      /boot; the `linux` package's install hook that would repopulate it never runs offline),
#   B. replaces the ARCHISO preset (PRESETS=('archiso') + the archiso.conf HOOKS drop-in) with
#      the STOCK `linux` preset and drops archiso.conf, so `mkinitcpio -P` below builds a
#      disk-bootable image against the installed /etc/mkinitcpio.conf.
{_csp._mkinitcpio_reset_command()}

# ENCRYPTED ROOT (install_info/encrypt): teach the initramfs to unlock the LUKS container.
# The cloned /etc/mkinitcpio.conf is the STOCK mkinitcpio default, whose HOOKS line is
# systemd-based: `base systemd autodetect microcode modconf kms keyboard sd-vconsole block
# filesystems fsck`. A systemd initramfs uses the `sd-encrypt` hook (NOT the busybox
# `encrypt` hook), and it unlocks from /etc/crypttab.initramfs BAKED INTO the image (the
# file sd-encrypt reads at boot) -- so insert sd-encrypt before `filesystems` and write both
# crypttab.initramfs (for the initramfs unlock) and /etc/crypttab (for the booted system).
# Guarded on the marker so a plain install is untouched.
if [ "$(cat /etc/install_info/encrypt 2>/dev/null)" = "1" ]; then
    az_cu="$(cat /etc/install_info/crypt_uuid 2>/dev/null)"
    if ! grep -q '^HOOKS=.*\\bsd-encrypt\\b' /etc/mkinitcpio.conf; then
        sed -i 's/\\(^HOOKS=.*\\)\\bfilesystems\\b/\\1sd-encrypt filesystems/' /etc/mkinitcpio.conf
    fi
    # crypttab.initramfs is embedded into the initramfs and consumed by sd-encrypt to open
    # `azarch_root` from its UUID at boot (prompting for the passphrase). /etc/crypttab is the
    # booted-system copy. `none` = prompt; `luks` = the type.
    if [ -n "$az_cu" ]; then
        echo "azarch_root UUID=$az_cu none luks" > /etc/crypttab.initramfs
        echo "azarch_root UUID=$az_cu none luks" > /etc/crypttab
    fi
fi

# Regenerate the initramfs for the INSTALLED system (now against the stock preset + the
# installed /etc/mkinitcpio.conf, so it boots from the real disk).
mkinitcpio -P

is_uefi=$(cat /etc/install_info/is_uefi)
disk=$(cat /etc/install_info/disk)

# Write /etc/default/grub BEFORE grub-install. grub-install reads GRUB_ENABLE_CRYPTODISK
# from this file at startup; on an encrypted root (where /boot lives inside the LUKS
# container) it ABORTS with "attempt to install to encrypted disk without cryptodisk
# enabled" unless the flag is already set -- so the flag MUST be written first, then
# grub-install embeds the cryptodisk modules into core.img, then grub-mkconfig writes the
# menu. GRUB_DEFAULT/TIMEOUT auto-boot the first entry with no menu (Calamares grubcfg parity).
# Rewrite the key if present, else append it, so this is idempotent regardless of the stock
# /etc/default/grub the `grub` package shipped.
set_grub_default() {{
  key="$1"; val="$2"
  if grep -q "^#\\?${{key}}=" /etc/default/grub; then
    sed -i "s|^#\\?${{key}}=.*|${{key}}=${{val}}|" /etc/default/grub
  else
    echo "${{key}}=${{val}}" >> /etc/default/grub
  fi
}}
set_grub_default GRUB_DEFAULT 0
set_grub_default GRUB_TIMEOUT 0
set_grub_default GRUB_TIMEOUT_STYLE hidden

# ENCRYPTED ROOT: enable cryptodisk in GRUB and pass the initramfs the cryptdevice + mapper
# root on the kernel cmdline. This MUST precede grub-install (see above). Guarded on the
# marker so a plain install keeps its stock GRUB defaults.
if [ "$(cat /etc/install_info/encrypt 2>/dev/null)" = "1" ]; then
    az_cu="$(cat /etc/install_info/crypt_uuid 2>/dev/null)"
    set_grub_default GRUB_ENABLE_CRYPTODISK y
    if [ -n "$az_cu" ]; then
        # systemd initramfs: sd-encrypt opens the container from the embedded
        # crypttab.initramfs, and rd.luks.name=<uuid>=azarch_root names it explicitly; the
        # kernel then mounts the opened mapper as root. (cryptdevice=... is the busybox-hook
        # syntax and is intentionally NOT used here -- this is an sd-encrypt initramfs.)
        # OUTER real quotes keep the space-containing value ONE argument to set_grub_default
        # (its `val="$2"` reads a single word) while $az_cu still expands; INNER \\" are the
        # literal quotes written into /etc/default/grub around the multi-word cmdline value.
        set_grub_default GRUB_CMDLINE_LINUX "\\"rd.luks.name=$az_cu=azarch_root root=/dev/mapper/azarch_root\\""
    fi
fi

if [ $is_uefi -eq 1 ]; then
  grub-install --target=x86_64-efi --bootloader-id=grub_uefi --recheck --efi-directory=/boot/EFI
else
  grub-install --target=i386-pc "$disk"
fi

grub-mkconfig -o /boot/grub/grub.cfg

systemctl enable NetworkManager

# FIRST-BOOT ONESHOT (NTP-on-first-boot). The compiler stages these three files ONLY under
# /root/azarch on the ISO (never at their runtime paths), so the verbatim clone does NOT place
# them -- we must install them from /root/azarch here (the old pacstrap installer hand-copied
# them the same way). Home paths use /home/main because this runs BEFORE the identity rename;
# the identity step below re-points the unit's ExecStart + the script's CONFIG_FILE to
# /home/$az_login if the account was renamed (see installer_identity.identity_chroot_sh).
mkdir -p /home/main/.config/first-boot
cp /root/azarch/first-boot-setup.sh /home/main/.config/first-boot/first-boot-setup.sh
cp /root/azarch/first-boot-setup.conf /home/main/.config/first-boot/first-boot-setup.conf
cp /root/azarch/first-boot-setup.service /etc/systemd/system/first-boot-setup.service
chown 1000:998 /home/main/.config
chmod 755 /home/main/.config/first-boot/first-boot-setup.sh
chmod 644 /etc/systemd/system/first-boot-setup.service
# 644, not world-writable: first-boot-setup.service runs as root (no User=), so root rewrites
# First_Boot=TRUE->FALSE here just fine -- there is no reason to make this config world-writable.
chmod 644 /home/main/.config/first-boot/first-boot-setup.conf
systemctl enable first-boot-setup.service

# NOTE: there is deliberately NO recursive world-open chmod sweep over /home here. The verbatim
# rootfs clone (rsync -aAXH) already reproduced the live home's correct perms and ownership
# (dirs 755, files their real modes, owned main:main); a blanket chmod would only RE-INTRODUCE
# a world-writable $HOME (the local security hole this unification removed) and mark every file
# executable. Calamares does not do it, so neither does the CLI path. If a post-rename chown is
# ever needed it is handled per-account by the identity step below (usermod/mv preserve
# ownership), not with a recursive world-open chmod.

pacman -Sy
%IDENTITY_CHROOT%
%DESKTOP_CLEANUP%
echo -e "\\e[94mazarch disk installation complete, you can reboot now.\\e[0m"
"""
    # DESKTOP-ONLY cleanup block. Strips the LIVE-ONLY OpenBox installer state from the clone
    # (the autostart lines that RE-LAUNCH the disk-erasing installer at every login + force a
    # fixed us,il keyboard, plus the installer's Desktop icon / app-menu entry / privileged
    # wrapper), then swaps in the installed-system OpenBox autostart. It EMBEDS the SAME shared
    # command block Calamares' shellprocess emits so the two install paths never drift. This is
    # entirely GUI-session-specific: openbox-autostart-installed is staged ONLY by _emit_desktop,
    # and the headless line has no OpenBox autostart / installer .desktop to clean -- so on the
    # headless line we emit NOTHING here (running it would `cp` an unstaged file and, under its
    # `set -e`, abort the install). Runs AFTER the identity step, so re-derive the (possibly renamed) login.
    if is_gui:
        desktop_cleanup = (
            '\naz_login="$(cat /etc/install_info/username 2>/dev/null)"\n'
            'az_login="${az_login:-main}"\n'
            'mkdir -p "/home/$az_login/.config/openbox" /etc/skel/.config/openbox\n'
            + _csp.installer_cleanup_command("/home/$az_login") + "\n"
        )
    else:
        desktop_cleanup = (
            "\n# (headless line: no OpenBox autostart / installer desktop entry to strip -- "
            "the GUI-session cleanup is intentionally omitted.)\n"
        )
    chroot = chroot.replace("%DESKTOP_CLEANUP%", desktop_cleanup)
    # Apply the collected identity (user/passwords/hostname/timezone) as the LAST step, AFTER
    # the `main`-hardcoded home setup above (so those lines still see the original account and
    # /home/main) and AFTER the static locale block (so the chosen timezone override wins).
    # Spliced by name to avoid f-string brace-escaping the fragment's shell `${...}`/`{...}`.
    return chroot.replace("%IDENTITY_CHROOT%", installer_identity.identity_chroot_sh().rstrip("\n"))


# --- Live-ISO post-boot tweaks ----------------------------------------------
def setup_pkgs_sh() -> str:
    """Live-ISO oneshot: firewall setup + SSH host keys.

    Firewall baseline (the Az'arch default the `azarch network firewall` command later
    manages live): ENABLED, incoming DENY (silent drop, not reject -- no ICMP telling a
    scanner the box is here), outgoing ALLOW, and port 49154 explicitly DENIED. 49154 is
    the Az'arch timedate home page (Flask on localhost:49154); it must stay reachable ONLY
    by the machine itself, so the deny rule guarantees it is never exposed off-box even if a
    later rule loosens the default. The sshd variant opens :22 afterwards via its own oneshot
    (system.SSHD_HYPERVISOR_SETUP_SERVICE runs `ufw allow ssh`), so ssh works there without
    weakening this base policy."""
    return """\
#!/bin/bash

# Fix firewall configuration
sudo ufw enable
sudo ufw default deny incoming
sudo ufw default allow outgoing
# Close the timedate home-page port (localhost:49154) to everything off-box.
sudo ufw deny 49154

# Generate SSH host keys so sshd can complete the handshake
sudo ssh-keygen -A
"""


# --- First-boot-once mechanism (installed system) ---------------------------
def first_boot_conf() -> str:
    return """\
# Set to TRUE to enable first boot shell script.
# as the name suggests, first boot will only run once after boot and then disable itself.
# This file is checked upon startup.
First_Boot=TRUE
"""


def first_boot_service() -> str:
    return """\
[Unit]
Description=First boot configuration
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/home/main/.config/first-boot/first-boot-setup.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""


def first_boot_sh() -> str:
    return """\
#!/bin/bash

CONFIG_FILE="/home/main/.config/first-boot/first-boot-setup.conf"

# Check if configuration file exists and contains First_Boot=TRUE
if grep -q '^First_Boot=TRUE' "$CONFIG_FILE"; then
    echo "First boot setup enabled. Running setup..."

    # Wait up to 15 seconds for internet connection
    timeout 15s bash -c "until ping -c 1 archlinux.org >/dev/null 2>&1; do sleep 1; done" || { echo "No internet connection after 15s"; }
    [ $? -eq 0 ] && timedatectl set-ntp true

    # Set First_Boot=FALSE
    sed -i 's/^First_Boot=TRUE/First_Boot=FALSE/' "$CONFIG_FILE"
    echo "First boot setup complete. Config updated."
else
    echo "First boot setup not enabled. Skipping."
fi
"""
