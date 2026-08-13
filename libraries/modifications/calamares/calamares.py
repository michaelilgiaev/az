"""Calamares installer configuration, authored as configuration-as-Python strings.

Az'arch boots to a minimal OpenBox live session and auto-launches Calamares
(Manjaro-style) to install Az'arch Linux to disk. Calamares 3.4.2 reads:

  /etc/calamares/settings.conf          -- module search paths + the sequence
  /etc/calamares/modules/<name>.conf    -- one configuration per module in the sequence
  /etc/calamares/branding/azarch/*      -- product branding + slideshow

Every builder below returns the exact text of one of those files. The install is
OFFLINE by design: the target root is unpacked from the live SquashFS by the
`unpackfs` module (NOT pacstrapped over the network), matching how the rest of
Az'arch installs. Btrfs is the DEFAULT filesystem and full-disk LUKS encryption
is offered as a toggle in the partition page.

Style note: Calamares configuration files are YAML (settings.conf, branding.desc, and
every modules/*.conf). They are emitted verbatim as the strings below. The
`emit_map()` at the bottom returns {relative path under /etc/calamares -> content}
so compiler.py can iterate and write the whole tree with emit.write_text.

Calamares 3.4.x configuration-key notes (all VERIFIED against the calamares 3.4.2
module schemas we build from source -- these were bugs caught in review):
  - partition.conf: `defaultFileSystemType` (NOT defaultFileSystem) sets the
    default fs. LUKS is offered when `luksGeneration: luks2` is present with an
    encryption-capable install choice; the "Encrypt system" checkbox appears
    automatically. No `enableLuksAutomatedPartitioning` key is needed.
  - unpackfs.conf: sourcefs must be "squashfs" (with the airootfs.sfs path), not
    "filesystem" (which is not a recognized type). See ARCHISO_SFS.
  - The module is named `services-systemd` (its module.desc `name:` is
    "services-systemd", verified against the shipped 3.4.2 module). BOTH the exec
    sequence entry AND the per-module configuration file must use that exact name
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
  - shellprocess: the OFFLINE install copies the live rootfs (which already has
    the `main` user, uid 1000, baked into /etc/passwd) via unpackfs. The `users`
    module then unconditionally runs `useradd -m -U -s /bin/bash -c <name> main`
    inside the target and ABORTS with exit code 9 ("user 'main' already exists")
    -- the users module has NO skip/reuse-existing-account option (verified
    against the 3.4.2 users.so: only reuseHome/userShell/sudoersGroup/... exist).
    So a shellprocess step (dontChroot:false -> runs in the target chroot) drops
    the baked-in `main` account/group BEFORE `users` runs, letting the users
    module recreate `main` with the user-chosen password. Its home /home/main is
    left intact: Calamares' users module runs `useradd -m` unconditionally, which
    on an already-existing home merely WARNS ("home directory already exists ...
    not copying skel") and still exits 0 -- so the account is recreated and the
    files are reused. (users.conf also sets reuseHome:true to state that intent;
    in 3.4.2 that key gates a dotfiles backup, not the useradd flags, so it is
    belt-and-suspenders rather than the load-bearing part.) shellprocess `script`
    is a list of command strings; a leading "-" ignores that command's failure so
    a variant rootfs (no such line) never aborts the install.
"""

from __future__ import annotations

# The shellprocess module (the post-unpackfs `main`-account removal + archiso
# mkinitcpio-preset reset) lives in its own file -- it is the most intricate part of
# the install. Re-exported here so the public surface stays flat:
# calamares.shellprocess_conf / .LIVE_USER / .STOCK_LINUX_PRESET, and the internal
# _mkinitcpio_reset_command the tests pin.
from .calamares_shellprocess import (  # noqa: F401  (re-exported for the public API)
    LIVE_USER,
    STOCK_LINUX_PRESET,
    _boot_desparsify_command,
    _mkinitcpio_reset_command,
    shellprocess_conf,
    shellprocess_desparsify_conf,
)

# The branding component directory name (under branding/) and product identity.
BRANDING = "azarch"
PRODUCT = "Az'arch Linux"

# The Calamares WINDOW ICON (the "Az'" app tile). Shipped as a REAL PNG inside the
# branding component dir (branding/azarch/) and named by its branding-relative filename
# in branding.desc's `productIcon`. This is what makes the icon show on OpenBox's titlebar
# (the `N` in rc.xml's titleLayout): Calamares' CalamaresApplication sets the window icon
# with QIcon( Branding::imagePath(ProductIcon) ), i.e. it constructs a QIcon from the
# STORED string DIRECTLY -- so productIcon MUST resolve to a real FILE PATH, not a bare
# freedesktop icon name. Branding.cpp turns a branding-relative filename that EXISTS in the
# component dir into an absolute path (componentDir.absoluteFilePath), so QIcon(path) loads
# it; a bare theme name would only pass load-time validation (via QIcon::fromTheme) yet come
# back out of imagePath() as the bare name, and QIcon("azarch-installer") then reads it as a
# missing file -> no titlebar icon. Hence a shipped file. compiler.py rasterizes the
# standardized vector assets/icons/azarch.svg (see modifications/openbox.INSTALLER_ICON_ASSET)
# to a PNG at branding/azarch/PRODUCT_ICON_FILE, so the window icon matches the .desktop
# launcher icon (both derive from the one SVG master).
PRODUCT_ICON_FILE = "productIcon.png"

# The live archiso SquashFS image. On a booted archiso medium the boot device is
# mounted at /run/archiso/bootmnt and the root image lives at
# <install_dir>/<arch>/airootfs.sfs under it. Az'arch's install_dir is "arch"
# (see libraries/profile.py INSTALL_DIR) and arch is x86_64, so the canonical,
# widely-used unpackfs source is the path below with sourcefs "squashfs".
# (Caveat: booting with the `copytoram` option unmounts bootmnt and moves the
# image to /run/archiso/copytoram/; Az'arch does not enable copytoram by default.)
ARCHISO_SFS = "/run/archiso/bootmnt/arch/x86_64/airootfs.sfs"


# --- 1. settings.conf -------------------------------------------------------
def settings_conf() -> str:
    """The top-level Calamares configuration: where to find modules, the branding
    component, and the ordered `sequence` of show (UI) and exec (work) phases.

    Every module named here has a configuration emitted below, or needs none (welcome,
    summary, finished, machineid, hwclock, networkcfg, mount, umount, fstab,
    localecfg have no required per-module configuration for our flow -- the ones we DO
    configure, including keyboard, are listed in emit_map()).
    """
    return """\
# Calamares master configuration for Az'arch Linux.
---
# Directories scanned for module descriptors. Absolute paths are the system
# install locations from the `calamares` package; "modules" is relative to this
# settings.conf so our /etc/calamares/modules/*.conf overrides are picked up.
modules-search: [ local, /usr/lib/calamares/modules ]

# instances: run the `shellprocess` module a SECOND time with a different configuration.
# The default (id == module name) instance uses modules/shellprocess.conf (the
# pre-users/pre-initcpio fixups). The `desparse` instance -- referenced as
# `shellprocess@desparse` in the sequence -- uses modules/shellprocess-desparse.conf
# (mark /boot no-compress + rewrite the kernel/initramfs so GRUB can read them).
#
# The per-instance config-file key is `config:` -- NOT `configuration:`. Calamares'
# Settings.cpp InstanceDescription::fromSettings() reads `m.value("config")`; if that
# key is absent the instance's config filename SILENTLY DEFAULTS to `<module>.conf`
# (here shellprocess.conf). So a `configuration:` typo does NOT error -- it makes
# `shellprocess@desparse` re-run the DEFAULT shellprocess.conf (the mkinitcpio reset)
# instead of the desparse commands, the /boot fixup never runs, and the installed
# system fails to boot with "premature end of file /@/boot/vmlinuz-linux". This exact
# typo silently disabled the boot fix once already; keep it `config:`.
instances:
- id: desparse
  module: shellprocess
  config: shellprocess-desparse.conf

# The ordered install sequence. `show` phases render UI pages; `exec` phases do
# the actual work with a progress bar. Only modules with a configuration below (or that
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
  # Remove the live rootfs's baked-in `main` account so the users module can
  # recreate it (see shellprocess.conf / the module note above). MUST run after
  # unpackfs (the target must exist) and before users.
  - shellprocess
  - machineid
  # luksbootkeyfile: when the user encrypted the disk, create /crypto_keyfile.bin
  # on the target root and `cryptsetup luksAddKey` it as a second LUKS key slot,
  # so the initramfs `encrypt` hook can unlock the root from the embedded keyfile
  # instead of RE-PROMPTING for the passphrase. THIS is the fix for the
  # "type the password twice at boot" report: GRUB still prompts once to read
  # /boot (it lives on the encrypted btrfs root), but the initramfs no longer
  # prompts a second time. It is a built-in Calamares C++ job (globalstorage
  # access -- it reads the passphrase the partition page captured, which a
  # shellprocess step cannot). MUST run BEFORE `fstab` (fstab points crypttab at
  # the keyfile only if it already exists) and BEFORE `initcpiocfg` (which adds
  # /crypto_keyfile.bin to mkinitcpio FILES= only if the file is present). No-op
  # on an unencrypted install or one with an unencrypted separate /boot.
  - luksbootkeyfile
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
  # Make /boot GRUB-readable: mark it no-compress (chattr +C) and rewrite the kernel
  # + initramfs UNCOMPRESSED. The target btrfs is mounted compress=zstd:1 (mount.conf),
  # so unpackfs stores /boot/vmlinuz-linux as zstd-compressed extents, and GRUB's
  # btrfs driver -- which cannot decompress zstd -- reads it short: the install
  # completes but the target fails to boot with "premature end of file
  # /@/boot/vmlinuz-linux". (An earlier revision misdiagnosed this as a trailing
  # sparse hole; a plain in-place rewrite left the file compressed, so it never
  # booted. See calamares_shellprocess._boot_desparsify_command.)
  #
  # ORDERING invariant: keep this the LAST step that touches /boot -- after every
  # step that writes a /boot file (initcpio writes the initramfs; the `packages`
  # pacman transaction COULD, via mkinitcpio/kernel install hooks, rewrite /boot if
  # its removal set ever changes), immediately before `umount`. That way the fixup
  # always runs on the FINAL on-disk /boot state, so no later step can leave a
  # compressed file behind. (As currently configured `packages` only try_removes
  # calamares, which does not itself trigger the mkinitcpio hook -- but pinning this
  # last makes the "boot files are readable" invariant robust to future changes in
  # the removal set or step order. The chattr +C additionally keeps any file a
  # future step or update writes into /boot uncompressed.) grub.cfg (grubcfg/
  # bootloader, above) records only PATHS, not extents/lengths, so writing it before
  # this step is fine. Second shellprocess instance; its configuration is
  # modules/shellprocess-desparse.conf (see instances:).
  - shellprocess@desparse
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
#
# luks1 (NOT luks2) on purpose. /boot lives on the encrypted btrfs root (there is
# no separate unencrypted /boot), so GRUB itself must unlock the container to read
# the kernel. GRUB <= 2.12 CANNOT open a LUKS2 container whose key slot uses
# Argon2id -- and cryptsetup's LUKS2 default PBKDF is Argon2id -- so a luks2 install
# would leave GRUB unable to unlock at all (or, on GRUB 2.14, fail on Argon2's
# memory cost). This is exactly why upstream Calamares defaults luksGeneration to
# luks1. LUKS1 always uses PBKDF2, which GRUB reads fine. Combined with the
# luksbootkeyfile module (added to the sequence above), the user types the
# passphrase ONCE at the GRUB prompt and the initramfs unlocks from the embedded
# keyfile -- fixing the previous "password twice" behaviour.
luksGeneration: luks1

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


# --- 3b. modules/shellprocess.conf -----------------------------------------
# The shellprocess configuration (LIVE_USER, STOCK_LINUX_PRESET, _mkinitcpio_reset_command,
# shellprocess_conf) is defined in modifications/calamares_shellprocess/calamares_shellprocess.py and imported at
# the top of this module. It is emitted below via emit_map()'s shellprocess_conf().


# --- 4. modules/users.conf --------------------------------------------------
def users_conf() -> str:
    """User/hostname policy on the INSTALLED system: wheel-group sudo, hostname
    settable in the UI, NO autologin (the live ISO autologins; the installed
    system should not).

    reuseHome:true -- the shellprocess step removed the live `main` ACCOUNT but
    left /home/main (uid 1000) on the target. `useradd -m` (which the users module
    always runs) does NOT fail on an existing home -- it warns and skips copying
    skel, exiting 0 -- so the recreated `main` (again the first free uid >= 1000,
    i.e. 1000) just reuses those files. reuseHome is set to declare that intent;
    in Calamares 3.4.2 it gates a dotfiles backup rather than the useradd flags."""
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

# The live rootfs's /home/main survives on the target (the shellprocess step
# only removed the ACCOUNT, not the home). `useradd -m` recreates `main` and
# reuses that directory (it only warns on an existing home, exit 0). reuseHome
# declares the reuse intent (in 3.4.2 it gates a dotfiles backup, not useradd).
reuseHome: true

# Let the user pick the hostname on the users page, seeded with this template.
# writeHostsFile keeps /etc/hosts in sync with the chosen name.
#
# `template: "azarch"` is a LITERAL (no ${...} macros), so Calamares' hostname
# suggestion always expands to exactly "azarch" no matter what the user types in
# the Full Name / Login fields. Combined with our calamares source patch
# (azarch-calamares-defaults.patch), which seeds this template as the INITIAL
# hostname at module load AND marks it "custom" so the auto-derive path is
# skipped, the "What is the name of this computer?" field shows "azarch" by
# default and stays "azarch" as the other inputs change. (Upstream default is
# "${first}-${product}", which recomputes the hostname on every name keystroke --
# that reactive default is exactly what the patch/template override disables.)
setHostname:
    location: EtcFile
    writeHostsFile: true
    template: "azarch"
hostname:
    location: EtcFile
    writeHostsFile: true
    template: "azarch"

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
# itself (calamares has no place on an installed system); the desktop (plasma,
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
    Btrfs gets compression + noatime so the copied system is space-efficient.

    extraMounts also bind/mount the pseudo-filesystems the chrooted install jobs
    (initcpio, bootloader) need. The efivarfs entry is LOAD-BEARING for UEFI: the
    bootloader module runs `grub-install --target=x86_64-efi`, which shells out to
    efibootmgr to register the NVRAM boot entry, and efibootmgr can only do that if
    efivarfs is mounted RW at /sys/firmware/efi/efivars *inside the target chroot*.
    A fresh `sysfs` mount on /sys does NOT bring the efivarfs submount along, so
    without this explicit entry grub-install fails with:
        EFI variables are not supported on this system.
        grub-install: error: efibootmgr failed to register the boot entry: ...
    and Calamares aborts at the bootloader step. It must be listed AFTER the /sys
    (sysfs) entry so its mountpoint directory exists first. On a BIOS/non-UEFI host
    /sys/firmware/efi is absent; Calamares logs the failed extra mount and carries
    on, and BIOS grub-install (--target=i386-pc) never touches efivars anyway."""
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
    # efivarfs must sit UNDER /sys (mounted above) so the target chroot's
    # grub-install/efibootmgr can register the UEFI boot entry. Without it the
    # bootloader step dies with "EFI variables are not supported on this system".
    - device: efivarfs
      fs: efivarfs
      mountPoint: /sys/firmware/efi/efivars
      efi: true
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
# Seed timezone. Az'arch defaults to Asia/Jerusalem; the locale page can still
# override it. (IANA zone name is "Jerusalem".)
region: "Asia"
zone: "Jerusalem"

# Where the keyboard/locale live in the target.
localeConfMappings:
    - LANG
    - LC_ALL
"""


# --- 6c2. modules/keyboard.conf --------------------------------------------
def keyboard_conf() -> str:
    """Keyboard page: English ("us") is always the active layout; when the user
    picks a NON-English region on the Location page, the region's native layout is
    added as a switchable SECOND (Alt+Shift), live in the installer and persisted to
    the target. This is driven by the Az'arch region-keyboard SOURCE PATCH
    (packages/pkgbuild.calamares_region_keyboard_patch), enabled by the
    `regionSecondLayout: true` key below.

    HOW IT WORKS (and why guessLayout is now TRUE, reversing the earlier fix):
      * The patched locale module publishes the selected zone's ISO-3166 country
        code to GlobalStorage as "locationCountry".
      * On Keyboard-page activation, the patched keyboard module's
        guessRegionKeyboardLayout() reads "locationCountry", maps it to the region's
        xkb layout (its own table, covering Latin-script langs like Spanish/French
        that upstream's non-ascii-layouts does NOT), makes the region layout the
        PRIMARY with "us" force-added as the ADDITIONAL layout, and applies it live
        -- so the emitted order is "us,<region>" (English first/active) and the
        "Type here to test" box switches scripts on Alt+Shift. English-speaking
        regions (US/GB/AU/...) get English only.
      * `guessLayout: true` is REQUIRED for guessLocaleKeyboardLayout() (which the
        patch extends) to run at all -- it early-returns when guessLayout is false.
        The earlier "keep us, never guess" fix (guessLayout:false) is superseded:
        the guess no longer produces a lone non-ASCII layout (the old Hebrew-only,
        blank-key bug) because English is always force-kept as the primary/active
        ASCII layout; the region language is only ever the SECOND, Alt+Shift layout.

    Default region is Asia/Jerusalem (modules/locale.conf), so out of the box the
    installer shows English + Hebrew with Alt+Shift. Move the region to
    America/El_Salvador and it becomes English + Spanish; Asia/Riyadh -> English +
    Arabic; an English-speaking region -> English only.

    useLocale1:false keeps the module reading/writing the plain
    /etc/X11/xorg.conf.d/00-keyboard.conf (Az'arch is Plasma/X11); the `configure`
    block keeps kwin/gnome off (the layout is read from that xkb file directly, so
    no KWin/GNOME keyboard integration is needed)."""
    return """\
# Keyboard configuration for the Az'arch installer.
---
# Where to write the X11 keyboard configuration on the target (systemd-localed default).
xOrgConfFileName: "/etc/X11/xorg.conf.d/00-keyboard.conf"

# Path used to convert X11 keymaps to kbd format for the console.
convertedKeymapPath: "/usr/share/kbd/keymaps/xkb"

# Manage the plain xorg.conf.d file directly instead of going through
# systemd-localed. Az'arch is Plasma/X11 and the layout is read from
# /etc/X11/xorg.conf.d/00-keyboard.conf.
useLocale1: false

# Enable the locale/region guess. REQUIRED so the Az'arch region-keyboard patch's
# guessRegionKeyboardLayout() runs (guessLocaleKeyboardLayout() early-returns when
# this is false). It no longer auto-selects a lone Hebrew layout: English is always
# force-kept as the primary/active layout and the region language is only ever the
# switchable SECOND layout (see regionSecondLayout).
guessLayout: true

# Az'arch: region-driven second keyboard layout. When the user selects a non-English
# region on the Location page, add that region's native xkb layout as a switchable
# SECOND layout (English "us" stays first/active; group switch is Alt+Shift), applied
# to the LIVE installer session and persisted to the target. English-speaking regions
# get English only. Implemented by calamares_region_keyboard_patch(); this key is the
# opt-in switch it reads (upstream/other distros default it to false).
regionSecondLayout: true

# Az'arch runs Plasma on X11, but the layout is read from the plain xkb
# xorg.conf.d file we manage (useLocale1:false) -- so no KWin/GNOME keyboard
# integration needs configuring here.
configure:
    kwin: false
    gnome: false
"""


# --- 6d. modules/services.conf ---------------------------------------------
def services_conf() -> str:
    """Enable NetworkManager on the installed system (Az'arch networks via NM,
    not dhcpcd/systemd-networkd).

    NOTE: in Calamares 3.4.2 this module's real name is `services-systemd` (its
    module.desc `name:` field, verified against the installed module). The configuration
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
    """Configure the target's /etc/mkinitcpio.conf before `initcpio` runs
    mkinitcpio -P. Calamares' initcpiocfg module INJECTS the encryption/btrfs/lvm
    hooks it needs based on the chosen layout, which is what makes a LUKS-encrypted
    or btrfs root actually bootable -- without regenerating the initramfs with the
    `encrypt` hook, an encrypted root cannot be unlocked at boot.

    We set only `useSystemdHook: false` -- the VALID initcpiocfg key that keeps the
    classic busybox-based HOOKS layout (the `encrypt` hook, not sd-encrypt), which
    matches the archiso live initramfs and GRUB's cryptodisk unlock we configure in
    grubcfg. The layout-driven hook injection happens regardless. NOTE: an earlier
    version emitted `kernel: ""` here -- that is an `initcpio`-module key, NOT an
    initcpiocfg key (whose schema is additionalProperties:false), so it was silently
    ignored and would fail strict schema validation. It is removed. (initcpio itself
    also needs no configuration.)"""
    return """\
# initcpiocfg configuration for the installed system. Calamares injects the
# encrypt/lvm2/btrfs hooks required by the selected partition layout; we only pin
# the busybox (non-systemd) hook style so the `encrypt` hook + GRUB cryptodisk
# unlock line up with the rest of the install.
---
useSystemdHook: false
"""


# --- 6d3. modules/luksbootkeyfile.conf -------------------------------------
def luksbootkeyfile_conf() -> str:
    """Config for the luksbootkeyfile module (added to the exec sequence). The
    module creates /crypto_keyfile.bin on the target and `cryptsetup luksAddKey`s
    it so the initramfs `encrypt` hook unlocks the root from the embedded keyfile
    instead of prompting a SECOND time at boot -- the fix for the "password twice"
    report. See settings.conf's sequence note.

    The single valid key is `luks2Hash` (the PBKDF for the keyfile's LUKS2 key
    slot: pbkdf2 / argon2i / argon2id / default). Az'arch installs LUKS1
    (partition.conf luksGeneration: luks1, so GRUB can unlock /boot on the
    encrypted root), and LUKS1 always uses PBKDF2 -- so luks2Hash has no effect
    here. We ship it explicitly as `default` for clarity and so a future switch to
    luks2 has an obvious, documented knob (set pbkdf2 to keep GRUB-openable slots).
    The module is a no-op on an unencrypted install."""
    return """\
# luksbootkeyfile: embed a LUKS keyfile in the initramfs so the encrypted root is
# unlocked automatically after GRUB's prompt (no second passphrase prompt).
---
# PBKDF for the keyfile's key slot. Only meaningful for LUKS2; Az'arch uses LUKS1
# (always PBKDF2), so this is inert -- shipped as `default` for clarity.
luks2Hash: default
"""


# --- 6e. modules/grubcfg.conf ----------------------------------------------
def grubcfg_conf() -> str:
    """Write /etc/default/grub before the bootloader module runs grub-install +
    grub-mkconfig. Enables cryptodisk so a LUKS-encrypted root can be unlocked
    by GRUB at boot, and boots straight into the first menu entry with no wait.

    AUTO-BOOT the first option (the user's request "GRUB automatically goes into
    the first option during boot"):
      * GRUB_DEFAULT: 0        -- select the FIRST generated menu entry. (Was
        "saved", which boots whatever grub-reboot/last-boot recorded -- a moving
        target with no GRUB_SAVEDEFAULT set; pinning 0 always picks the top entry.)
      * GRUB_TIMEOUT: 0        -- do not wait; boot the default immediately.
      * GRUB_TIMEOUT_STYLE: "hidden" -- show no menu at all before booting (with a
        0 timeout "menu" would still flash the list for a frame; "hidden" goes
        straight in, and the user can still hold SHIFT/ESC to reveal the menu)."""
    return """\
# /etc/default/grub contents written before grub-install / grub-mkconfig.
---
overwrite: true

# Key/value pairs merged into /etc/default/grub. Schema requires GRUB_TIMEOUT and
# GRUB_DEFAULT. GRUB_ENABLE_CRYPTODISK is set automatically by the module when a
# crypt device is present, but we set it explicitly too (harmless).
# GRUB_DEFAULT 0 + GRUB_TIMEOUT 0 + hidden style == boot the first entry at once.
defaults:
    GRUB_TIMEOUT: 0
    GRUB_DEFAULT: 0
    GRUB_TIMEOUT_STYLE: "hidden"
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


# --- 6g. modules/finished.conf ---------------------------------------------
def finished_conf() -> str:
    """The Finish ("All done.") page. Without this configuration the page shows only a
    bare "Done" button and cannot restart into the new system -- the user asked for
    a Reboot option there. `restartNowMode: user-unchecked` shows a "Restart now"
    checkbox (defaulting to unchecked, so it never reboots unexpectedly); when the
    user ticks it and clicks Done, Calamares runs restartNowCommand.

    restartNowCommand uses `systemctl -i reboot` (the module's own documented value):
    `-i` (--ignore-inhibitors) guarantees the reboot proceeds even if a session
    inhibitor is held. We do NOT enable notifyOnFinished (the installer runs as root
    via pkexec and cannot reliably reach the live user's session bus). Schema is
    additionalProperties:false; only restartNowMode/restartNowCommand/
    restartNowChecked/restartNowEnabled/notifyOnFinished are valid keys."""
    return """\
# Finish page: offer a "Restart now" option so the user can boot straight into the
# freshly installed system (unchecked by default -- never reboots unless ticked).
---
restartNowMode: user-unchecked
restartNowCommand: "systemctl -i reboot"
notifyOnFinished: false
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

# Optional images (product logo / window icon).
#   productIcon -> the WINDOW ICON. Set to the "Az'" app tile shipped INTO this branding
#     dir as productIcon.png (see PRODUCT_ICON_FILE / compiler.py). Calamares sets the
#     window icon from QIcon(imagePath(ProductIcon)); a real file in the component dir
#     resolves to an absolute path so the icon actually loads and OpenBox draws it on the
#     titlebar (fixes the "installer has no topbar icon" report). It matches the Desktop /
#     application-menu launcher icon (both are the same source asset).
#   productLogo / productWelcome -> still EMPTY (no such PNGs shipped): Calamares skips
#     empty image keys and uses its built-in default, avoiding a "does not exist" log.
images:
    productLogo:   ""
    productIcon:   \"""" + PRODUCT_ICON_FILE + """\"
    productWelcome: ""

# Slideshow: a single QML slide placeholder shown during the exec phase.
slideshow: "show.qml"
slideshowAPI: 2

# UI colors. Minimal near-black + slate + blue theme matching the installer
# inspiration (assets/raw calameres slide): a very dark background with a blue
# "Az'" accent, muted slate labels, no decorative noise. NOTE: the real
# branding.desc style keys are Capitalized -- lowercase variants are silently
# ignored. The sidebar (#070e1b) sits a hair lighter than the page body (#030712)
# so the step list reads as a panel; the selected step is white, the rest slate
# (#64748b), and the accent is blue (#3b82f6) to match the "Az'" wordmark.
style:
    SidebarBackground:    "#070e1b"
    SidebarText:          "#64748b"
    SidebarTextSelect:    "#ffffff"
    SidebarTextHighlight: "#3b82f6"
"""


def branding_show_qml() -> str:
    """A minimal, valid Calamares slideshow (slideshowAPI 2). One static, centered
    slide -- no external assets, NO motivational/marketing copy (the user asked for
    a "get out of my way" installer): just "Installing Az'arch Linux" with the "Az'"
    wordmark blue, and a small dim status line. Matches the near-black + blue theme
    (bg #030712, brand #3b82f6, muted #64748b) of branding.desc.

    Single slide, so the Timer does not cycle (goToNextSlide would loop back to the
    same slide); it is kept only because Presentation expects the structure."""
    return """\
/* Az'arch Linux -- minimal single-slide installer slideshow (no marketing copy). */
import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 20000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        anchors.fill: parent

        Rectangle {
            anchors.fill: parent
            color: "#030712"
        }

        Column {
            anchors.centerIn: parent
            spacing: 10

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 0
                Text {
                    text: "Installing "
                    color: "#ffffff"
                    font.pixelSize: 30
                    font.weight: Font.DemiBold
                }
                Text {
                    text: "Az'"
                    color: "#3b82f6"
                    font.pixelSize: 30
                    font.weight: Font.Bold
                }
                Text {
                    text: "arch"
                    color: "#ffffff"
                    font.pixelSize: 30
                    font.weight: Font.Bold
                }
                Text {
                    text: " Linux"
                    color: "#ffffff"
                    font.pixelSize: 30
                    font.weight: Font.DemiBold
                }
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Please wait while the system is being installed."
                color: "#64748b"
                font.pixelSize: 14
            }
        }
    }

    function onActivate() {}
    function onLeave() {}
}
"""


# --- 8. emit map ------------------------------------------------------------
def emit_map() -> dict[str, str]:
    """Return {relative path under /etc/calamares -> file content} so compiler.py
    can iterate and write the whole configuration tree with emit.write_text, e.g.:

        for rel, content in calamares.emit_map().items():
            emit.write_text(airootfs / "etc/calamares" / rel, content)

    Every module named in the settings.conf `sequence` either has its configuration
    here or needs none (welcome, summary, finished, machineid, hwclock,
    networkcfg, umount, localecfg use built-in defaults).
    """
    return {
        "settings.conf": settings_conf(),
        "modules/partition.conf": partition_conf(),
        "modules/unpackfs.conf": unpackfs_conf(),
        "modules/shellprocess.conf": shellprocess_conf(),
        "modules/shellprocess-desparse.conf": shellprocess_desparsify_conf(),
        "modules/users.conf": users_conf(),
        "modules/packages.conf": packages_conf(),
        "modules/mount.conf": mount_conf(),
        "modules/fstab.conf": fstab_conf(),
        "modules/locale.conf": locale_conf(),
        "modules/keyboard.conf": keyboard_conf(),
        "modules/initcpiocfg.conf": initcpiocfg_conf(),
        "modules/luksbootkeyfile.conf": luksbootkeyfile_conf(),
        "modules/services-systemd.conf": services_conf(),
        "modules/grubcfg.conf": grubcfg_conf(),
        "modules/bootloader.conf": bootloader_conf(),
        "modules/finished.conf": finished_conf(),
        f"branding/{BRANDING}/branding.desc": branding_desc(),
        f"branding/{BRANDING}/show.qml": branding_show_qml(),
    }
