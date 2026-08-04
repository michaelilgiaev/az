"""Calamares `shellprocess` module configuration -- the post-unpackfs target fixups the
OFFLINE (copy-the-live-rootfs) install needs.

Split out of configuration/calamares.py because it is the most intricate part of the
install: it undoes two archiso-only artifacts the live SquashFS carries so the
target boots. calamares.py imports shellprocess_conf() (and re-exports the
constants tests pin) so the public surface stays `calamares.shellprocess_conf`,
`calamares.LIVE_USER`, `calamares.STOCK_LINUX_PRESET`.

Two fixups, both run INSIDE the target chroot (dontChroot: false) after unpackfs
and before `users` / `initcpiocfg` / `initcpio`:
  1. Remove the live rootfs's baked-in `main` account so the `users` module can
     recreate it with the user-chosen password (/home/main preserved).
  2. Make the target's initramfs buildable: reinstate /boot/vmlinuz-linux and
     replace the copied-in *archiso* mkinitcpio preset with the stock `linux`
     preset (+ drop archiso.conf) -- otherwise Calamares' `initcpio` step
     (`mkinitcpio -p linux`) fails or builds an unbootable archiso-hooked image.
"""

from __future__ import annotations

# The exact login name baked into the live rootfs (configuration/system.py PASSWD/GROUP).
# Kept as a module-level constant so the shellprocess script and any test agree on
# the account being removed.
LIVE_USER = "main"

# The live session ships an "Az'arch Linux Installer" launcher ON the Desktop and a Plasma
# autostart entry that opens Calamares once at login. The OFFLINE install copies the
# live /home/main VERBATIM via unpackfs (and reuseHome:true keeps it), so WITHOUT the
# cleanup below the INSTALLED system would still carry the installer icon on its
# Desktop AND re-launch the installer on every login -- both wrong on a system that is
# already installed. This shellprocess step (target chroot, post-unpackfs) deletes
# both artifacts from the live user's reused home and from /etc/skel (so any later-
# created user is clean too). `rm -f` is a no-op if a path is absent. The system-wide
# application-menu launcher (/usr/share/applications/azarch-install.desktop) is LEFT
# in place: re-running the installer from the menu on an installed system is harmless
# and the user only asked for the DESKTOP icon (and the auto-launch) to be gone.
INSTALLER_DESKTOP_LAUNCHER = f"/home/{LIVE_USER}/Desktop/azarch-install.desktop"
INSTALLER_AUTOSTART_ENTRY = (
    f"/home/{LIVE_USER}/.config/autostart/azarch-install.desktop"
)
INSTALLER_SKEL_LAUNCHER = "/etc/skel/Desktop/azarch-install.desktop"
INSTALLER_SKEL_AUTOSTART = "/etc/skel/.config/autostart/azarch-install.desktop"


def _installer_cleanup_command() -> str:
    """A single shellprocess command (target chroot) that removes the live-session
    installer artifacts so the INSTALLED system has no "Az'arch Linux Installer" Desktop icon
    and does not auto-launch Calamares at login. Deletes the Desktop launcher + the
    Plasma autostart entry from the reused /home/main AND from /etc/skel. `set -e` with
    plain `rm -f` (a no-op on an absent path) -- there is nothing here that can
    legitimately fail, and NO `$` (Calamares macro-expands $WORD and aborts on an
    unknown one -- see _mkinitcpio_reset_command), so only fixed paths are used."""
    return (
        "set -e\n"
        f"rm -f {INSTALLER_DESKTOP_LAUNCHER}\n"
        f"rm -f {INSTALLER_AUTOSTART_ENTRY}\n"
        f"rm -f {INSTALLER_SKEL_LAUNCHER}\n"
        f"rm -f {INSTALLER_SKEL_AUTOSTART}"
    )

# The OFFLINE install copies the live archiso rootfs verbatim via unpackfs, which
# leaves the target's /boot and mkinitcpio configuration in an ISO-only state that makes
# Calamares' `initcpio` step fail. (That step runs `mkinitcpio -p linux` -- the
# module's default `kernel: linux` -- which reads /etc/mkinitcpio.d/linux.preset;
# archiso REPLACED that stock preset with PRESETS=('archiso'), and its per-preset
# archiso_config forces `-c archiso.conf`, which entirely bypasses the
# /etc/mkinitcpio.conf that Calamares' initcpiocfg writes.) TWO distinct archiso
# artifacts are to blame, and BOTH must be undone before initcpio runs:
#
#   A. /boot is EMPTY. mkarchiso's `_cleanup_pacstrap_dir` deletes everything under
#      the rootfs's /boot before it squashes airootfs.sfs (verified in
#      /usr/bin/mkarchiso). The kernel therefore survives ONLY as the modules-tree
#      copy /usr/lib/modules/<kver>/vmlinuz (pkgbase file alongside names it, e.g.
#      "linux"); there is NO /boot/vmlinuz-linux in the unpacked target. This is the
#      real cause of the observed failure:
#          ==> ERROR: Invalid option -k -- '/boot/vmlinuz-linux' must be readable
#      mkinitcpio's ALL_kver points at /boot/vmlinuz-<pkgbase>, which does not exist.
#      An installed system normally gets /boot/vmlinuz-linux from the `linux`
#      package's 90-mkinitcpio-install.hook (`install -Dm644 .../vmlinuz
#      /boot/vmlinuz-<pkgbase>`); an offline rsync install never runs that pacman
#      hook, so we replicate it here.
#
#   B. The mkinitcpio PRESET is the *archiso* one: /etc/mkinitcpio.d/linux.preset is
#      PRESETS=('archiso') with archiso_config=/etc/mkinitcpio.conf.d/archiso.conf,
#      and archiso.conf's HOOKS carry `archiso archiso_loop_mnt ...`. Even with a
#      kernel present, that preset builds an archiso-hooked initramfs that cannot
#      boot an installed disk (it expects the live SquashFS/cow overlay). We replace
#      it with the STANDARD `linux` preset (default + fallback images, no archiso_*
#      keys) and remove archiso.conf so its HOOKS -- a conf.d drop-in sourced LAST,
#      which would otherwise OVERRIDE the /etc/mkinitcpio.conf that Calamares'
#      initcpiocfg writes -- no longer apply. initcpiocfg then injects the
#      encrypt/btrfs hooks the chosen layout needs into a clean HOOKS line.
#
# STOCK_LINUX_PRESET is the content the `linux` package installs as its preset
# (mkinitcpio's %KERNELBASE% -> "linux").
STOCK_LINUX_PRESET = """\
# mkinitcpio preset file for the 'linux' package

ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux"

PRESETS=('default' 'fallback')

#default_config="/etc/mkinitcpio.conf"
default_image="/boot/initramfs-linux.img"
#default_options=""

#fallback_config="/etc/mkinitcpio.conf"
fallback_image="/boot/initramfs-linux-fallback.img"
fallback_options="-S autodetect"
"""

# Absolute (target-chroot) paths the reset touches.
_PRESET_PATH = "/etc/mkinitcpio.d/linux.preset"
_ARCHISO_CONF_PATH = "/etc/mkinitcpio.conf.d/archiso.conf"

# The /boot files GRUB reads at boot. A SECOND shellprocess instance rewrites these
# UNCOMPRESSED (and marks /boot no-compress) AFTER the initcpio module regenerates
# the initramfs, so GRUB's btrfs driver -- which cannot decompress zstd -- can read
# them in full (see _boot_desparsify_command / settings.conf's shellprocess@desparse).
_BOOT_KERNEL = "/boot/vmlinuz-linux"
_BOOT_INITRAMFS = "/boot/initramfs-linux.img"
_BOOT_INITRAMFS_FALLBACK = "/boot/initramfs-linux-fallback.img"


# Where the copied-in rootfs keeps the kernel image (mkarchiso empties /boot but
# leaves the modules tree). `find ... -exec` (NOT a shell glob or a Calamares/shell
# variable -- see the no-`$` note in _mkinitcpio_reset_command) copies the installed
# kernel image. `find` is used rather than `install -Dm644 <glob> <dest>` because a
# glob that matched two kernels would make `install` treat the last path as a target
# DIRECTORY and fail under `set -e`; `find -exec ... {} <dest> \;` runs the copy once
# per match, so it is correct for the single kernel Az'arch ships (pkgbase `linux`,
# matching STOCK_LINUX_PRESET, verified against the built airootfs.sfs) and stays
# safe if a second kernel is ever added. -maxdepth 2 keeps it to /usr/lib/modules/
# <kver>/vmlinuz (not deeper build/ copies).
_MODULES_DIR = "/usr/lib/modules"
_TARGET_KERNEL = "/boot/vmlinuz-linux"


def _mkinitcpio_reset_command() -> str:
    """A single shellprocess command (a YAML literal-block list item -> one shell
    invocation in the target chroot) that makes Calamares' `initcpio` step
    (`mkinitcpio -p linux`, reading /etc/mkinitcpio.d/linux.preset) succeed on the
    unpacked target. Steps, in order:

    1. Reinstate the kernel image the pacman install hook would have placed. The
       `linux` package's 90-mkinitcpio-install.hook copies /usr/lib/modules/<kver>/
       vmlinuz to /boot/vmlinuz-linux; the OFFLINE install skips that hook, so we
       replicate it. `find /usr/lib/modules -maxdepth 2 -name vmlinuz -exec install
       -Dm644 {} /boot/vmlinuz-linux \\;` copies the single installed kernel (Az'arch
       ships one, pkgbase `linux`) creating /boot at mode 644 -- and, unlike a glob
       passed straight to `install`, does not abort under `set -e` if a second kernel
       is ever present. A following `test -r /boot/vmlinuz-linux` re-arms the hard
       failure the glob had: `find -exec` exits 0 even when it matches nothing, so
       without this a missing kernel would slip past `set -e` and only surface later.
    2. Overwrite the inherited archiso preset with the stock one. A quoted heredoc
       (``<<'EOF'``) writes every byte of STOCK_LINUX_PRESET verbatim -- including
       the single quotes in ``PRESETS=('default' 'fallback')`` -- with no expansion.
    3. Remove the archiso conf.d drop-in (`rm -f` is a no-op if it is absent).

    CRITICAL -- no `$` anywhere: Calamares runs each shellprocess command through a
    KWordMacroExpander (escape char `$`) BEFORE the shell sees it. Any bare `$WORD`
    that is not a Calamares variable makes the whole job ABORT ("Missing variables")
    without running a single command, and the only way to get a literal `$` through
    is `$$`, which the expander turns into a SHELL-escaped `\\$` -- i.e. `\\$x` is a
    literal `$x`, not a variable expansion. So shell variables / `$(...)` cannot be
    used here at all; this command is written entirely with globs and fixed paths.
    `set -e` (no `$`) makes a missing kernel or a failed write a HARD error (per the
    failure policy in shellprocess_conf) rather than a silent skip that would only
    surface as an obscure `initcpio` failure later."""
    return (
        f"set -e\n"
        # A. reinstate the kernel image the pacman install hook would have placed.
        #    find -exec (not a glob) so multiple kernels never break `install`.
        f"find {_MODULES_DIR} -maxdepth 2 -name vmlinuz -exec install -Dm644 {{}} {_TARGET_KERNEL} \\;\n"
        #    find returns 0 even when it matches nothing, so `set -e` would NOT catch
        #    a missing kernel; assert the image landed (mkinitcpio needs it readable).
        f"test -r {_TARGET_KERNEL}\n"
        # B. install the stock preset (replacing the archiso one).
        f"mkdir -p /etc/mkinitcpio.d\n"
        f"cat > {_PRESET_PATH} <<'EOF'\n"
        f"{STOCK_LINUX_PRESET}"
        f"EOF\n"
        # C. drop the archiso conf.d override.
        f"rm -f {_ARCHISO_CONF_PATH}"
    )


def _boot_desparsify_command() -> str:
    """Rewrite the /boot files GRUB reads so GRUB's btrfs driver can read them IN
    FULL, and mark /boot no-compress so future kernel updates stay readable. Runs in
    the target chroot as the LAST step that touches /boot -- after `initcpio` (which
    generates the initramfs) and after every other /boot-writing step, immediately
    before `umount` -- so it always operates on the FINAL on-disk /boot state and no
    later step can reintroduce the problem (see settings.conf's ordering note).

    THE BUG this fixes (found by booting the installed disk):
        error: loader/efi/linux.c:grub_cmd_linux:551: premature end of file
               /@/boot/vmlinuz-linux
        error: ... you need to load the kernel first.
    -> GRUB reads the kernel short and the system will not boot.

    ROOT CAUSE (the REAL one -- an earlier revision MISdiagnosed this as a trailing
    sparse hole and its `cp --sparse=never` "fix" did NOT work): the target btrfs
    root is mounted `compress=zstd:1` (configuration/calamares.mount_conf ->
    mountOptions), so `unpackfs` writes /boot/vmlinuz-linux as ZSTD-COMPRESSED btrfs
    extents (a bzImage is highly compressible, so btrfs really does compress it --
    verified: every extent is flagged `encoded` in `filefrag -v`). GRUB 2.14's btrfs
    driver CANNOT decompress zstd extents ("compression type 0x3 not supported"), so
    it returns the file short and aborts with "premature end of file". This is a
    well-known class of failure (btrfs `compress=zstd` + GRUB /boot); the standard
    remedy is to keep /boot UNCOMPRESSED. Rewriting the file IN PLACE under the same
    compressed mount (the old approach) just re-compresses it -- which is exactly why
    the bug survived the previous fix and the user hit it twice.

    FIX (two parts, both required):
      1. `chattr +C /boot` -- set the btrfs no-compress (NOCOW) attribute on the
         /boot directory. New files created in a +C directory are stored
         UNCOMPRESSED. This must run BEFORE the rewrites below (so the fresh temp
         copies land uncompressed) AND it makes every kernel/initramfs a FUTURE
         `pacman -Syu` writes into /boot uncompressed too -- so the system keeps
         booting across kernel updates, not just on the first boot. (`+C` also drops
         checksums/CoW for those files, which is fine and conventional for /boot.)
      2. For each /boot file GRUB reads, rewrite it so its on-disk extents are
         rewritten uncompressed: `cp --reflink=never --sparse=never src tmp` creates
         a FRESH copy in the now-+C /boot dir (a plain, non-reflink copy, so it gets
         brand-new uncompressed extents rather than sharing the old compressed ones),
         then `mv tmp src` renames it over the original. `--sparse=never` additionally
         guarantees no trailing EOF hole (the original, secondary concern), so the
         result is a single hole-free uncompressed extent that reaches i_size. Safe
         for a bzImage (its header carries its own length, trailing bytes ignored) and
         a cpio/zstd initramfs (its decoder stops at its own end marker). The fallback
         initramfs (200+ MB, generated by initcpio) is rewritten too -- same risk.

    Why here and not in the earlier (pre-initcpio) shellprocess: the initramfs images
    do not exist until `initcpio` runs, and are written into the same compressed
    mount, so the fixup MUST run after it. A single, well-tested step owns the whole
    "make /boot GRUB-readable" invariant (kernel + both initramfs + the +C attr).

    CRITICAL -- each `cp`/`mv` is its OWN statement, NOT chained with `&&`. Under
    `set -e` a command that is the LEFT operand of `&&` is a "tested" command whose
    failure is IGNORED (bash would not abort), so `cp ... && mv ...` would let a
    failed kernel `cp` (ENOSPC, read-only /boot, I/O error) slip through, the script
    would exit 0, and Calamares would ship the very unbootable system this step
    exists to prevent. Writing them as separate lines makes `set -e` actually fatal
    on the load-bearing kernel rewrite. The initramfs images are OPTIONAL, so each is
    wrapped in an `if [ -f ... ]; then ... fi` (its body still uses separate,
    set -e-covered statements) -- a preset that emitted only one image never aborts
    the install, but a real cp/mv failure on a present image does.

    Same no-`$` rule as _mkinitcpio_reset_command: Calamares macro-expands `$WORD`
    and aborts the job on an unknown one, so this is written with fixed paths only
    (no shell variables / `$(...)`). `-f` on cp/mv avoids interactive prompts."""
    def rewrite_lines(path: str) -> list[str]:
        # cp then mv as TWO separate statements (see the set -e note above), so a
        # failure of either aborts under `set -e`. --reflink=never forces brand-new
        # (uncompressed, since /boot is now +C) extents rather than sharing the old
        # compressed ones; --sparse=never additionally leaves no trailing EOF hole.
        tmp = path + ".nosparse"
        return [
            f"cp --reflink=never --sparse=never -f {path} {tmp}",
            f"mv -f {tmp} {path}",
        ]

    lines = ["set -e"]
    # Mark /boot no-compress BEFORE any rewrite so the fresh temp copies -- and every
    # kernel a future update writes here -- are stored uncompressed (GRUB cannot read
    # zstd-compressed extents). Must precede the kernel rewrite below. `|| true`
    # (no `$`, so the macro-expander is happy): on the real btrfs target this always
    # succeeds and is load-bearing, but on a filesystem that lacks the attribute
    # (e.g. a hand-partitioned ext4 /boot, which has no compression to defeat anyway)
    # `chattr +C` returns non-zero, and it must NOT abort the fixup under `set -e`.
    lines.append("chattr +C /boot || true")
    # The kernel is always present by now (reinstated pre-initcpio); rewrite it
    # unconditionally so GRUB reads a whole, uncompressed bzImage. Separate cp/mv
    # statements keep `set -e` fatal here.
    lines += rewrite_lines(_BOOT_KERNEL)
    # initcpio generated these; rewrite both images uncompressed. Guarded with
    # `if [ -f ]` (optional), but a real failure on a present image still aborts
    # (set -e inside).
    for img in (_BOOT_INITRAMFS, _BOOT_INITRAMFS_FALLBACK):
        lines.append(f"if [ -f {img} ]; then")
        lines += [f"    {stmt}" for stmt in rewrite_lines(img)]
        lines.append("fi")
    # Flush the rewritten /boot files to disk before the target is unmounted. cp+mv
    # leave the fresh, uncompressed extents in the page cache; `sync` forces them out
    # so the very first real boot reads the uncompressed data off disk, not a state
    # that could still be settling. Plain `sync` (no `$`).
    lines.append("sync")
    return "\n".join(lines)


def shellprocess_desparsify_conf() -> str:
    """Second `shellprocess` instance (shellprocess@desparse in settings.conf),
    scheduled as the LAST step that touches /boot -- after `initcpio` AND after
    `packages` (see the settings.conf ordering note), immediately before `umount`.
    It marks /boot no-compress and rewrites the /boot kernel + initramfs UNCOMPRESSED
    so GRUB's btrfs driver (which cannot decompress zstd) can read them in full --
    without it the install completes but the target fails to boot with GRUB
    "premature end of file /@/boot/vmlinuz-linux". See _boot_desparsify_command for
    the full root-cause note (the target btrfs is mounted compress=zstd:1).

    NOT prefixed "-" (and uses `set -e`): making /boot GRUB-readable is load-bearing,
    so a failure here must stop the install with a clear error rather than ship an
    unbootable system."""
    cmd = _boot_desparsify_command()
    block = "\n".join("        " + line for line in cmd.splitlines())
    return f"""\
# Post-initcpio /boot fixup for the OFFLINE install (runs in the target chroot):
# mark /boot no-compress (chattr +C) and rewrite /boot/vmlinuz-linux + the initramfs
# images UNCOMPRESSED. The target btrfs is mounted compress=zstd:1, so unpackfs
# stores the kernel as zstd-compressed extents; GRUB's btrfs driver cannot decompress
# zstd and fails to boot with "premature end of file /@/boot/vmlinuz-linux". The +C
# attr also keeps FUTURE (pacman) kernel updates uncompressed. MUST run as the LAST
# step to touch /boot -- after `initcpio` and every other /boot-writing step, right
# before `umount`. Uses NO `$` (Calamares macro-expands $WORD and aborts on an
# unknown one -- see calamares_shellprocess.py).
---
dontChroot: false
# Generous timeout: this cp-rewrites three files, one of which (the fallback
# initramfs) is 200+ MB. On a slow target disk (spinning rust, a loaded VM's
# qcow2) three sequential copies of ~370 MB can take well over the old 120 s, and
# if Calamares KILLS the step mid-cp the `mv` leaves a truncated file -- the very
# unbootable state this step exists to prevent. 600 s leaves ample headroom while
# still bounding a genuinely hung copy.
timeout: 600
verbose: true
script:
    - |
{block}
"""


# --- LC_TIME (d/m/y date format) fixup for the Calamares path ---------------
# The user wants dates as day/month/year, not the en_US month/day/year default. We
# set LC_TIME=en_GB.UTF-8 (English, but d/m/y) system-wide. The live ISO already
# does this in configuration/locale._detect_and_apply_locale_block (it writes
# /etc/locale.conf), but Calamares' `localecfg` module OVERWRITES /etc/locale.conf
# wholesale from the locale page -- it sets every LC_* (including LC_TIME) to the
# ONE chosen locale (en_US.UTF-8 by default), clobbering the live value. So on the
# Calamares path we must RE-assert LC_TIME in the target AFTER localecfg runs. This
# shellprocess instance (shellprocess@lctime in settings.conf) does exactly that,
# scheduled right after `localecfg`.
#
# The single source of truth for the locale is configuration/locale.DEFAULT_TIME_LOCALE;
# imported here so the Calamares and live paths can never drift.
from .locale import DEFAULT_TIME_LOCALE  # noqa: E402  (kept next to its user)

# The en_GB.UTF-8 line as it appears (commented) in a stock Arch /etc/locale.gen.
_TIME_LOCALE_GEN_LINE = f"{DEFAULT_TIME_LOCALE} UTF-8"
_TARGET_LOCALE_CONF = "/etc/locale.conf"
_TARGET_LOCALE_GEN = "/etc/locale.gen"


def _lc_time_command() -> str:
    """A single shellprocess command (target chroot) that forces the system date
    format to day/month/year by setting LC_TIME=en_GB.UTF-8 in the target's
    /etc/locale.conf -- re-asserting it AFTER Calamares' localecfg overwrote the file
    with the locale page's (en_US, m/d/y) values. Steps:

      1. Ensure en_GB.UTF-8 is enabled in /etc/locale.gen and generated (LC_TIME is
         inert unless the locale exists). `sed` uncomments the stock line; if the
         line is absent entirely (a non-stock locale.gen) it is appended.
      2. Drop any existing LC_TIME= line, then append LC_TIME=en_GB.UTF-8, so the
         key is set exactly once regardless of what localecfg wrote.

    CRITICAL -- no `$` anywhere (same rule as _mkinitcpio_reset_command): Calamares
    macro-expands `$WORD` before the shell runs and ABORTS the whole job on an
    unknown one. This command uses only fixed literals, sed patterns (which need no
    `$`), and printf -- no shell variables / `$(...)`. `set -e` makes a real failure
    (e.g. locale-gen error) stop the install rather than silently ship m/d/y dates."""
    return (
        "set -e\n"
        # 1. enable + generate en_GB.UTF-8 (idempotent: uncomment if present, else append).
        f"sed -i 's/^#\\s*{_TIME_LOCALE_GEN_LINE}/{_TIME_LOCALE_GEN_LINE}/' {_TARGET_LOCALE_GEN}\n"
        f"grep -q '^{_TIME_LOCALE_GEN_LINE}' {_TARGET_LOCALE_GEN} || echo '{_TIME_LOCALE_GEN_LINE}' >> {_TARGET_LOCALE_GEN}\n"
        "locale-gen\n"
        # 2. set LC_TIME exactly once (remove any prior line localecfg wrote, then append).
        f"sed -i '/^LC_TIME=/d' {_TARGET_LOCALE_CONF}\n"
        f"printf 'LC_TIME={DEFAULT_TIME_LOCALE}\\n' >> {_TARGET_LOCALE_CONF}"
    )


def shellprocess_lctime_conf() -> str:
    """Third `shellprocess` instance (shellprocess@lctime in settings.conf),
    scheduled RIGHT AFTER `localecfg` in the exec sequence. It forces the target's
    date format to day/month/year by setting LC_TIME=en_GB.UTF-8 in
    /etc/locale.conf (and generating that locale), re-asserting it after localecfg
    overwrote the file with the locale page's m/d/y en_US values. See
    _lc_time_command for the full rationale and the no-`$` constraint.

    NOT prefixed "-" (uses `set -e`): the user explicitly asked for d/m/y dates, so a
    real failure (locale-gen error, unwritable locale.conf) should surface rather
    than silently leaving m/d/y."""
    cmd = _lc_time_command()
    block = "\n".join("        " + line for line in cmd.splitlines())
    return f"""\
# Force day/month/year dates on the installed system (runs in the target chroot,
# AFTER localecfg): set LC_TIME=en_GB.UTF-8 in /etc/locale.conf and generate that
# locale. Calamares' localecfg overwrites /etc/locale.conf from the locale page
# (en_US == m/d/y), so LC_TIME must be re-asserted here. Uses NO `$` (Calamares
# macro-expands $WORD and aborts on an unknown one -- see calamares_shellprocess.py).
---
dontChroot: false
timeout: 120
verbose: true
script:
    - |
{block}
"""


def shellprocess_conf() -> str:
    """Two pre-`users` / pre-`initcpio` fixups the OFFLINE (copy-the-live-rootfs)
    install needs, run INSIDE the target chroot (dontChroot: false) after unpackfs:

    1. Delete the live rootfs's pre-existing `main` account so the `users` module
       can re-create it (see the users.conf note / module docstring). We edit the
       passwd/shadow/gshadow/group databases via `userdel`/`groupdel` rather than
       trusting one tool: `userdel main` removes the user line and its per-user
       primary group; a follow-up `groupdel` handles a lingering group. We do NOT
       pass `-r`/`--remove`: /home/main (uid 1000) must stay so users.conf
       reuseHome:true reuses it. `-f` forces removal on a freshly unpacked target.

    2. Make the target's initramfs buildable: reinstate /boot/vmlinuz-linux
       (mkarchiso emptied /boot; the kernel survives only under /usr/lib/modules)
       and replace the inherited *archiso* mkinitcpio preset with the stock `linux`
       preset (+ drop archiso.conf). Without this the later `initcpio` module's
       `mkinitcpio -p linux` fails with "'/boot/vmlinuz-linux' must be readable"
       (missing kernel) or, past that, builds an unbootable archiso-hooked initramfs
       (the exact failure seen: "Building image from preset: ... 'archiso'"). See
       `_mkinitcpio_reset_command` / STOCK_LINUX_PRESET above. NOTE: this fixup uses
       NO `$` (no shell variables / `$(...)`) -- Calamares macro-expands `$WORD` and
       would abort the whole job on an unknown one (see _mkinitcpio_reset_command).

    Command-failure policy: the user-removal commands are prefixed "-" so a rootfs
    that (for any reason) lacks the `main` account/group never aborts the install
    -- the goal is merely "main must not exist when users runs", so a no-op is
    success. The mkinitcpio fixup is NOT prefixed "-" (and uses `set -e` internally):
    reinstating the kernel and a correct preset is load-bearing -- a silent failure
    would leave /boot empty or the archiso preset in place and the install would die
    obscurely later at `initcpio`, so it should stop here with a clear failure.

    3. Remove the live-session installer artifacts (the Desktop "Az'arch Linux Installer"
       launcher + the Plasma autostart entry, from the reused /home/main and from
       /etc/skel) so the INSTALLED system has no installer icon on its Desktop and
       does not re-open Calamares at every login. This is load-bearing for the
       "installer shouldn't be on the Desktop after install" request; `rm -f` is a
       no-op on an absent path, so it never aborts.

    Ordering note: shellprocess sits after unpackfs and before both `users` and
    `initcpiocfg`/`initcpio` in settings.conf's exec sequence, so all three fixups
    land on the unpacked target before the modules that depend on them run."""
    reset_cmd = _mkinitcpio_reset_command()
    cleanup_cmd = _installer_cleanup_command()
    # Indent each multi-line command to sit under its YAML "- |" block scalar.
    reset_block = "\n".join("        " + line for line in reset_cmd.splitlines())
    cleanup_block = "\n".join("        " + line for line in cleanup_cmd.splitlines())
    return f"""\
# Post-unpackfs target fixups for the OFFLINE install (runs in the target chroot):
#   1. remove the live-ISO `main` account so the `users` module can recreate it
#      with the user-chosen password (/home/main is preserved),
#   2. make the initramfs buildable: reinstate /boot/vmlinuz-<pkgbase> (mkarchiso
#      emptied /boot) and replace the copied-in *archiso* mkinitcpio preset with the
#      stock `linux` preset (+ drop archiso.conf), so `initcpio`'s `mkinitcpio -p
#      linux` produces a bootable installed-system initramfs instead of failing, and
#   3. remove the live-session installer artifacts (Desktop launcher + autostart
#      entry) so the installed system has no installer icon and no auto-launch.
---
dontChroot: false
timeout: 60
verbose: true
script:
    - "-userdel -f {LIVE_USER}"
    - "-groupdel {LIVE_USER}"
    - |
{reset_block}
    - |
{cleanup_block}
"""
