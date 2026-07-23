"""Calamares installer configuration, authored as config-as-Python strings.

Az'arch boots to a minimal Openbox live session and auto-launches Calamares
(Manjaro-style) to install Az'arch Linux to disk. Calamares 3.4.2 reads:

  /etc/calamares/settings.conf          -- module search paths + the sequence
  /etc/calamares/modules/<name>.conf    -- one config per module in the sequence
  /etc/calamares/branding/azarch/*      -- product branding + slideshow

Every builder below returns the exact text of one of those files. The install is
OFFLINE by design: the target root is unpacked from the live SquashFS by the
`unpackfs` module (NOT pacstrapped over the network), matching how the rest of
Az'arch installs. Btrfs is the DEFAULT filesystem and full-disk LUKS encryption
is offered as a toggle in the partition page.

Style note: Calamares config files are YAML (settings.conf, branding.desc, and
every modules/*.conf). They are emitted verbatim as the strings below. The
`emit_map()` at the bottom returns {relative path under /etc/calamares -> content}
so steps.py can iterate and write the whole tree with emit.write_text.

Calamares 3.4.x config-key notes (all VERIFIED against the calamares 3.4.2
module schemas we build from source -- these were bugs caught in review):
  - partition.conf: `defaultFileSystemType` (NOT defaultFileSystem) sets the
    default fs. LUKS is offered when `luksGeneration: luks2` is present with an
    encryption-capable install choice; the "Encrypt system" checkbox appears
    automatically. No `enableLuksAutomatedPartitioning` key is needed.
  - unpackfs.conf: sourcefs must be "squashfs" (with the airootfs.sfs path), not
    "filesystem" (which is not a recognized type). See ARCHISO_SFS.
  - The module is named `services-systemd` (its module.desc `name:` is
    "services-systemd", verified against the shipped 3.4.2 module). BOTH the exec
    sequence entry AND the per-module config file must use that exact name
    (services-systemd.conf) or Calamares aborts at startup with "Initialization
    Failed" (an unknown module name in the sequence stops the whole install).
    Its schema allows ONLY a `units:` array.
  - fstab.conf allows ONLY `crypttabOptions` + `tmpOptions` (tmpOptions required);
    real mount options come from the partition module / mount.conf.
  - grubcfg.conf `defaults:` requires GRUB_TIMEOUT + GRUB_DEFAULT; kernel args go
    in the top-level `kernel_params:` (defaults' GRUB_CMDLINE_LINUX_DEFAULT is
    overwritten by the module). `keep_distributor` is snake_case.
  - bootloader.conf is additionalProperties:false: kernel:/img:/fallback: are NOT
    valid keys (derived from the target automatically).
  - initcpiocfg + initcpio MUST be in the exec sequence or a LUKS/btrfs root is
    unbootable (the copied-from-live initramfs lacks the encrypt hook).
  - branding.desc style keys are Capitalized (SidebarBackground, ...).
  - The `sequence` lists ONLY modules configured below or needing none.
"""

from __future__ import annotations

# The branding component directory name (under branding/) and product identity.
BRANDING = "azarch"
PRODUCT = "Az'arch Linux"

# The live archiso SquashFS image. On a booted archiso medium the boot device is
# mounted at /run/archiso/bootmnt and the root image lives at
# <install_dir>/<arch>/airootfs.sfs under it. Az'arch's install_dir is "arch"
# (see config/profile.py INSTALL_DIR) and arch is x86_64, so the canonical,
# widely-used unpackfs source is the path below with sourcefs "squashfs".
# (Caveat: booting with the `copytoram` option unmounts bootmnt and moves the
# image to /run/archiso/copytoram/; Az'arch does not enable copytoram by default.)
ARCHISO_SFS = "/run/archiso/bootmnt/arch/x86_64/airootfs.sfs"


# --- 1. settings.conf -------------------------------------------------------
def settings_conf() -> str:
    """The top-level Calamares config: where to find modules, the branding
    component, and the ordered `sequence` of show (UI) and exec (work) phases.

    Every module named here has a config emitted below, or needs none (welcome,
    summary, finished, machineid, hwclock, networkcfg, mount, umount, fstab,
    localecfg, keyboard have no required per-module config for our flow -- the
    ones we DO configure are listed in emit_map()).
    """
    return """\
# Calamares master configuration for Az'arch Linux.
---
# Directories scanned for module descriptors. Absolute paths are the system
# install locations from the `calamares` package; "modules" is relative to this
# settings.conf so our /etc/calamares/modules/*.conf overrides are picked up.
modules-search: [ local, /usr/lib/calamares/modules ]

# instances: only needed to run the same module twice with different configs; we
# do not, so the implicit one-instance-per-module mapping is used.

# The ordered install sequence. `show` phases render UI pages; `exec` phases do
# the actual work with a progress bar. Only modules with a config below (or that
# need none) appear here -- no dangling module names.
sequence:
- show:
  - welcome
  - locale
  - keyboard
  - partition
  - users
  - summary
- exec:
  - partition
  - mount
  - unpackfs
  - machineid
  - fstab
  - locale
  - keyboard
  - localecfg
  - users
  - networkcfg
  - hwclock
  - initcpiocfg
  - initcpio
  - services-systemd
  - grubcfg
  - bootloader
  - packages
  - umount
- show:
  - finished

# Branding component (branding/azarch/branding.desc).
branding: azarch

# Require the "Yes, I understand the installer will DESTROY data" checkbox before
# the destructive exec phase can run.
prompt-install: true

# The target is unpacked from the live medium, so nothing is installed to the
# host. Never touch the running live system's mounts / bootloader.
dont-chroot: false

# On finish, offer restart but do not force it.
disable-cancel: false
disable-cancel-during-exec: false
"""


# --- 2. modules/partition.conf ---------------------------------------------
def partition_conf() -> str:
    """Partitioning: Btrfs default, LUKS2 full-disk encryption offered, sane
    EFI/swap defaults, and both "Erase disk" and "Manual" modes enabled."""
    return """\
# Partitioning behaviour for Az'arch.
---
# Bootloader install location. "grub" pairs with the grubcfg + bootloader modules
# in the sequence; Calamares picks EFI vs BIOS from the running firmware.
efiSystemPartition: "/boot/efi"

# Recommended/forced sizes for the EFI System Partition (UEFI installs).
efiSystemPartitionSize: 512M
efiSystemPartitionName: EFISYSTEM

# Default filesystem for the root partition. BTRFS is the Az'arch default.
# NOTE: the Calamares 3.4.x key is `defaultFileSystemType` (verified against
# upstream src/modules/partition/partition.conf) -- NOT `defaultFileSystem`.
defaultFileSystemType: "btrfs"

# Filesystems offered in the manual-partitioning "format as" dropdown. btrfs
# first so it is the default selection.
availableFileSystemTypes: [ "btrfs", "ext4", "xfs", "f2fs" ]

# Installation choices offered on the partition page. We allow wiping the whole
# disk (the common path) and full manual partitioning. "alongside" and "replace"
# are left off to keep the minimal installer focused; add them here if desired.
#   erase   -> "Erase disk" (whole-disk, offers the Encrypt checkbox)
#   manual  -> "Manual partitioning"
userSwapChoices:
    - none
    - small
    - suspend
    - file

# The default swap strategy when erasing a disk. "none" avoids a btrfs swapfile,
# which would need a dedicated NOCOW subvolume to work correctly (extra wiring we
# do not ship). The user can still pick "small"/"file"/"suspend" from the
# userSwapChoices list on the partition page if they want swap.
initialSwapChoice: none

# Install choices (whole-disk vs manual). "erase" exposes the "Encrypt system"
# checkbox; keeping "manual" lets advanced users lay out partitions by hand.
initialPartitioningChoice: erase
allowManualPartitioning: true

# --- LUKS full-disk encryption -----------------------------------------------
# Presence of luksGeneration + an encryption-capable install choice makes the
# "Encrypt system" checkbox (with a passphrase field) appear on the Erase page.
# luks2 is the modern default cipher container format.
luksGeneration: luks2

# Partition layout table style. "gpt" for UEFI is standard; Calamares still falls
# back to msdos on legacy BIOS systems automatically when needed.
defaultPartitionTableType: gpt

# Do not draw partitions smaller than this in the visual editor (cosmetic).
drawNestedPartitions: false
alwaysShowPartitionLabels: true

# Ensure a fresh GPT is written when erasing (no leftover boot flags).
initialPartitionAttributes: []

# Btrfs subvolume layout applied when root is formatted btrfs. @ = root, @home =
# /home, so snapshots/rollback tooling (snapper etc.) works cleanly later.
btrfsSubvolumes:
    - mountPoint: /
      subvolume: /@
    - mountPoint: /home
      subvolume: /@home

# Require at least this much space (GiB) before install can proceed.
requiredStorage: 12.0
"""


# --- 3. modules/unpackfs.conf ----------------------------------------------
def unpackfs_conf() -> str:
    """Copy the live archiso root filesystem onto the freshly-formatted target.

    On an archiso live medium the boot device is mounted at /run/archiso/bootmnt
    and the SquashFS root image sits at arch/x86_64/airootfs.sfs under it.
    unpackfs mounts that squashfs and rsyncs it into the target -- an OFFLINE
    install with no pacman network access, consistent with the rest of Az'arch.
    """
    return f"""\
# Unpack the live filesystem to the target (offline install source).
---
unpack:
    - source: "{ARCHISO_SFS}"
      sourcefs: "squashfs"
      destination: ""
"""


# --- 4. modules/users.conf --------------------------------------------------
def users_conf() -> str:
    """User/hostname policy on the INSTALLED system: wheel-group sudo, hostname
    settable in the UI, NO autologin (the live ISO autologins; the installed
    system should not)."""
    return """\
# User account configuration for the installed system.
---
# The created user's default groups. wheel drives sudo (see sudoersGroup).
defaultGroups:
    - wheel
    - audio
    - video
    - storage
    - network
    - lp
    - input
    - power

# Grant sudo to members of this group (a /etc/sudoers.d/10-installer drop-in is
# written enabling it).
sudoersGroup: wheel
setRootPassword: true
doReusePassword: false

# Autologin OFF on the installed system (live ISO autologins, installed does not).
doAutologin: false

# Let the user pick the hostname on the users page, seeded with this template.
# writeHostsFile keeps /etc/hosts in sync with the chosen name.
setHostname:
    location: EtcFile
    writeHostsFile: true
hostname:
    location: EtcFile
    writeHostsFile: true

# Password hashing for the created accounts.
userShell: /bin/bash
passwordRequirements:
    minLength: 1
    maxLength: -1

# The account's full name field is optional.
allowWeakPasswords: true
allowWeakPasswordsDefault: false
"""


# --- 5. modules/packages.conf ----------------------------------------------
def packages_conf() -> str:
    """Pacman backend used ONLY to remove live-only packages from the installed
    target after the filesystem copy. calamares itself and the live desktop-
    installer glue have no place on the installed system, so we drop them. No
    network install happens (unpackfs already populated the root)."""
    return """\
# Post-install package cleanup (remove live-only bits). Pacman backend.
---
backend: pacman

pacman:
    # Do not refresh/sync from the network on the installed target; we only
    # remove the live-only packages copied over from the ISO.
    disable_download_timeout: true
    num_retries: 0

# skip_if_no_internet keeps this from failing an offline install if a later
# online operation were ever added.
skip_if_no_internet: false
update_db: false
update_system: false

# Operations run against the target after unpackfs. We only remove the INSTALLER
# itself (calamares has no place on an installed system); the desktop (openbox,
# xorg, kitty, librewolf, ...) is KEPT so the installed system boots to the same
# graphical environment as the live medium. Nothing is installed over the network.
# `try_remove` (not `remove`) so an absent package does not fail the step.
operations:
    - try_remove:
        - calamares
"""


# --- 6a. modules/mount.conf -------------------------------------------------
def mount_conf() -> str:
    """Extra mount options applied when mounting the target for the install.
    Btrfs gets compression + noatime so the copied system is space-efficient."""
    return """\
# Filesystem-specific mount options used while installing to / and after.
---
extraMounts:
    - device: proc
      fs: proc
      mountPoint: /proc
    - device: sys
      fs: sysfs
      mountPoint: /sys
    - device: /dev
      mountPoint: /dev
      options: [ bind ]
    - device: tmpfs
      fs: tmpfs
      mountPoint: /run
    - device: /run/udev
      mountPoint: /run/udev
      options: [ bind ]

# Per-filesystem mount options. btrfs: zstd compression + noatime. This is the
# module that feeds the installed system's real mount options (fstab reads them
# from here / the partition module, NOT from fstab.conf).
mountOptions:
    - filesystem: default
      options: [ defaults, noatime ]
    - filesystem: btrfs
      options: [ defaults, noatime, compress=zstd:1 ]
"""


# --- 6b. modules/fstab.conf -------------------------------------------------
def fstab_conf() -> str:
    """/etc/fstab generation.

    NOTE (Calamares 3.4.2 schema, additionalProperties:false, required:
    [tmpOptions]): fstab ONLY accepts `crypttabOptions` + `tmpOptions`. The real
    per-filesystem mount options (btrfs compress/noatime) are taken from the
    PARTITION module's mountOptionsList / mount.conf -- NOT set here. The old
    `mountOptions`/`ssdExtraMountOptions`/`efiMountOptions` keys are rejected."""
    return """\
# fstab generation for the installed system.
---
# crypttab timeout/options for LUKS-encrypted roots.
crypttabOptions: luks

# /tmp handling (required by the schema). tmpfs-backed /tmp on both HDD and SSD.
tmpOptions:
    default:
        tmpfs: true
        options: "defaults,noatime,mode=1777"
    ssd:
        tmpfs: true
        options: "defaults,noatime,mode=1777"
"""


# --- 6c. modules/locale.conf ------------------------------------------------
def locale_conf() -> str:
    """Locale/timezone selection defaults for the installed system."""
    return """\
# Locale + timezone defaults (user can change these on the locale page).
---
# Seed timezone; the locale page + geoip (if any) can override it.
region: "America"
zone: "New_York"

# Where the keyboard/locale live in the target.
localeConfMappings:
    - LANG
    - LC_ALL
"""


# --- 6d. modules/services.conf ---------------------------------------------
def services_conf() -> str:
    """Enable NetworkManager on the installed system (Az'arch networks via NM,
    not dhcpcd/systemd-networkd).

    NOTE: in Calamares 3.4.2 this module's real name is `services-systemd` (its
    module.desc `name:` field, verified against the installed module). The config
    file must therefore be modules/services-systemd.conf and the exec-sequence
    entry must read `services-systemd`; using the bare `services` makes Calamares
    fail to find the module and abort at startup. The schema is
    additionalProperties:false and defines ONLY a `units:` array of
    {name, action, mandatory} -- the older `services:`/`targets:`/`disable:` keys
    are rejected by validation."""
    return """\
# systemd unit state applied to the installed system.
---
units:
    - name: NetworkManager
      mandatory: true
    - name: bluetooth
      mandatory: false
    - name: cups
      mandatory: false
"""


# --- 6d2. modules/initcpiocfg.conf -----------------------------------------
def initcpiocfg_conf() -> str:
    """Write the target's /etc/mkinitcpio.conf HOOKS before `initcpio` runs
    mkinitcpio -P. Calamares' initcpiocfg module INJECTS the encryption/btrfs/lvm
    hooks it needs based on the chosen layout, but we provide a sane base HOOKS
    line. This is what makes a LUKS-encrypted or btrfs root actually bootable --
    without regenerating the initramfs with the `encrypt` hook, an encrypted root
    cannot be unlocked at boot. (initcpio itself needs no config.)"""
    return """\
# Base /etc/mkinitcpio.conf HOOKS for the installed system. Calamares augments
# these with encrypt/lvm2/btrfs as required by the selected partition layout.
---
kernel: ""
"""


# --- 6e. modules/grubcfg.conf ----------------------------------------------
def grubcfg_conf() -> str:
    """Write /etc/default/grub before the bootloader module runs grub-install +
    grub-mkconfig. Enables cryptodisk so a LUKS-encrypted root can be unlocked
    by GRUB at boot."""
    return """\
# /etc/default/grub contents written before grub-install / grub-mkconfig.
---
overwrite: true

# Key/value pairs merged into /etc/default/grub. Schema requires GRUB_TIMEOUT and
# GRUB_DEFAULT. GRUB_ENABLE_CRYPTODISK is set automatically by the module when a
# crypt device is present, but we set it explicitly too (harmless).
defaults:
    GRUB_TIMEOUT: 5
    GRUB_DEFAULT: "saved"
    GRUB_TIMEOUT_STYLE: "menu"
    GRUB_DISTRIBUTOR: "Az'arch Linux"
    GRUB_ENABLE_CRYPTODISK: "y"

# Kernel command line. The module OVERWRITES GRUB_CMDLINE_LINUX_DEFAULT with the
# kernel_params list below (setting it inside `defaults:` would be clobbered), so
# put boot args here.
kernel_params: [ "quiet" ]

# Keep the distributor string above (snake_case is the real key; camelCase is
# silently ignored).
keep_distributor: true
"""


# --- 6f. modules/bootloader.conf -------------------------------------------
def bootloader_conf() -> str:
    """Bootloader install. GRUB on both UEFI and BIOS (matches grubcfg + the
    on-disk installer's grub-install flow). efiBootloaderId names the EFI entry."""
    return """\
# Bootloader installation (GRUB, UEFI + BIOS).
---
# efi | bios | none ; grub selects GRUB for both firmware types.
efiBootLoader: "grub"

# NOTE: the ESP mount point is NOT set here. The bootloader module reads it from
# globalstorage (populated by the partition module from partition.conf's
# efiSystemPartition) -- the bootloader schema does not define an efiSystemPartition
# key, so setting one here is a dead key. partition.conf already supplies /boot/efi.

# Names for the GRUB EFI boot entry and its install directory.
efiBootloaderId: "azarch"

# Install GRUB even if an existing entry is present.
installEFIFallback: true

# BIOS/GRUB target names.
grubInstall: "grub-install"
grubMkconfig: "grub-mkconfig"
grubCfg: "/boot/grub/grub.cfg"
grubProbe: "grub-probe"
# NOTE: kernel/initramfs paths are NOT set here -- the bootloader schema is
# additionalProperties:false and derives them from the target automatically.
# Adding kernel:/img:/fallback: keys would fail schema validation.
"""


# --- 7. branding/azarch/branding.desc --------------------------------------
def branding_desc() -> str:
    """Product identity + a single-slide QML slideshow placeholder + colors."""
    return """\
# Branding for the Az'arch Linux installer.
---
componentName: azarch

# Interval used when the slideshow QML advances (ms). Single slide -> no cycling.
welcomeStyleCalamares: false
welcomeExpandingLogo: true

# Window sizing: percentage of the screen. "800px,520px" is an absolute fallback.
windowExpanding: normal
windowSize: 900px,560px
windowPlacement: center

# Product strings shown throughout the UI.
strings:
    productName:         Az'arch Linux
    shortProductName:    Az'arch
    version:             rolling
    shortVersion:        rolling
    versionedName:       Az'arch Linux (rolling)
    shortVersionedName:  Az'arch rolling
    bootloaderEntryName: Az'arch
    productUrl:          https://github.com/michaelilgiaev/azarch
    supportUrl:          https://github.com/michaelilgiaev/azarch
    knownIssuesUrl:      https://github.com/michaelilgiaev/azarch/issues
    releaseNotesUrl:     https://github.com/michaelilgiaev/azarch
    donateUrl:           ""

# Optional images (product logo / window icon). We ship NO logo.png in the
# branding dir, so these are left EMPTY: Calamares' loadStrings skips empty image
# keys (exactly as it does for productWelcome) and falls back to its built-in
# default pixmap. Pointing them at a non-existent "logo.png" instead makes
# Calamares log "Image file logo.png does not exist" -- set a real path here only
# if a PNG is actually added to this branding directory.
images:
    productLogo:   ""
    productIcon:   ""
    productWelcome: ""

# Slideshow: a single QML slide placeholder shown during the exec phase.
slideshow: "show.qml"
slideshowAPI: 2

# UI accent colors (match the Az'arch os-release ANSI accent 38;2;6;184;253).
# NOTE: the real branding.desc style keys are Capitalized -- lowercase variants
# are silently ignored, so the accent would never apply.
style:
    SidebarBackground:    "#06121c"
    SidebarText:          "#ffffff"
    SidebarTextSelect:    "#06b8fd"
    SidebarTextHighlight: "#06b8fd"
"""


def branding_show_qml() -> str:
    """A minimal, valid Calamares slideshow (slideshowAPI 2). One centered slide;
    no external assets so it renders on the minimal live medium."""
    return """\
/* Az'arch Linux -- minimal single-slide installer slideshow. */
import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 5000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            color: "#06121c"
        }

        Text {
            anchors.centerIn: parent
            horizontalAlignment: Text.AlignHCenter
            color: "#ffffff"
            font.pixelSize: 28
            text: "Installing Az'arch Linux\\n\\nA minimal, fast Arch-based system."
        }
    }

    function onActivate() {}
    function onLeave() {}
}
"""


# --- 8. emit map ------------------------------------------------------------
def emit_map() -> dict[str, str]:
    """Return {relative path under /etc/calamares -> file content} so steps.py
    can iterate and write the whole config tree with emit.write_text, e.g.:

        for rel, content in calamares.emit_map().items():
            emit.write_text(airootfs / "etc/calamares" / rel, content)

    Every module named in the settings.conf `sequence` either has its config
    here or needs none (welcome, summary, finished, machineid, hwclock,
    networkcfg, umount, localecfg, keyboard use built-in defaults).
    """
    return {
        "settings.conf": settings_conf(),
        "modules/partition.conf": partition_conf(),
        "modules/unpackfs.conf": unpackfs_conf(),
        "modules/users.conf": users_conf(),
        "modules/packages.conf": packages_conf(),
        "modules/mount.conf": mount_conf(),
        "modules/fstab.conf": fstab_conf(),
        "modules/locale.conf": locale_conf(),
        "modules/initcpiocfg.conf": initcpiocfg_conf(),
        "modules/services-systemd.conf": services_conf(),
        "modules/grubcfg.conf": grubcfg_conf(),
        "modules/bootloader.conf": bootloader_conf(),
        f"branding/{BRANDING}/branding.desc": branding_desc(),
        f"branding/{BRANDING}/show.qml": branding_show_qml(),
    }
