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

# The /boot files GRUB reads at boot. A SECOND shellprocess instance de-sparsifies
# these AFTER the initcpio module regenerates the initramfs (see
# _boot_desparsify_command / settings.conf's shellprocess@desparse).
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
    """Rewrite the /boot files GRUB reads so they contain NO trailing (EOF) sparse
    hole. Runs in the target chroot as the LAST step that touches /boot -- after
    `initcpio` (which generates the initramfs) and after every other /boot-writing
    step, immediately before `umount` -- so it always operates on the FINAL on-disk
    /boot state and no later step can reintroduce a hole (see settings.conf's
    ordering note).

    THE BUG this fixes (found by booting the installed disk):
        error: loader/efi/linux.c:grub_cmd_linux:551: premature end of file
               /@/boot/vmlinuz-linux
        error: ... you need to load the kernel first.
    -> GRUB drops the tail and the system will not boot.

    ROOT CAUSE: the kernel bzImage ends in a run of zero bytes, and Calamares'
    unpackfs rsyncs the live SquashFS with sparse-file handling, so /boot/vmlinuz-
    linux lands with an *implicit hole at EOF*: its last data extent ends BEFORE the
    file's i_size. GRUB (2.14) btrfs driver derives a file's readable length from
    the EXTENT tree, not i_size, and stops at the last extent -- so it returns the
    file short by exactly the trailing-hole size (observed: reads 17088512 of
    17089024, i.e. 512 bytes short). Interior holes are zero-filled correctly by
    GRUB; only a hole AT EOF truncates the read. (Verified: a full-extent file of
    the same non-4K size reads fine; only the EOF hole matters.)

    FIX: `cp --sparse=never src tmp` then `mv tmp src` rewrites the file with the
    trailing zeros as REAL data, giving a single extent that reaches i_size, which
    GRUB reads in full. Appending zero bytes is safe for a bzImage (the kernel
    header carries its own length and ignores trailing bytes) and for a cpio/zstd
    initramfs (its decoder stops at the stream's own end marker). We de-sparsify the
    fallback initramfs too (223 MB, generated by initcpio -- same risk).

    Why here and not in the earlier (pre-initcpio) shellprocess: the initramfs
    images do not exist until `initcpio` runs, and initcpio itself can write them
    sparsely, so the de-sparsify MUST run after it. The kernel is de-sparsified here
    as well (rather than in the reinstate step) so a single, well-tested step owns
    the whole "make /boot GRUB-readable" invariant.

    CRITICAL -- each `cp`/`mv` is its OWN statement, NOT chained with `&&`. Under
    `set -e` a command that is the LEFT operand of `&&` is a "tested" command whose
    failure is IGNORED (bash would not abort), so `cp ... && mv ...` would let a
    failed kernel `cp` (ENOSPC, read-only /boot, I/O error) slip through, the script
    would exit 0, and Calamares would ship the very unbootable system this step
    exists to prevent. Writing them as separate lines makes `set -e` actually fatal
    on the load-bearing kernel de-sparsify. The initramfs images are OPTIONAL, so
    each is wrapped in an `if [ -f ... ]; then ... fi` (its body still uses
    separate, set -e-covered statements) -- a preset that emitted only one image
    never aborts the install, but a real cp/mv failure on a present image does.

    Same no-`$` rule as _mkinitcpio_reset_command: Calamares macro-expands `$WORD`
    and aborts the job on an unknown one, so this is written with fixed paths only
    (no shell variables / `$(...)`). `-f` on cp/mv avoids interactive prompts."""
    def desparse_lines(path: str) -> list[str]:
        # cp then mv as TWO separate statements (see the set -e note above), so a
        # failure of either aborts under `set -e`.
        tmp = path + ".nosparse"
        return [f"cp --sparse=never -f {path} {tmp}", f"mv -f {tmp} {path}"]

    lines = ["set -e"]
    # The kernel is always present by now (reinstated pre-initcpio); de-sparsify it
    # unconditionally so GRUB can read the whole bzImage. Separate cp/mv statements
    # keep `set -e` fatal here.
    lines += desparse_lines(_BOOT_KERNEL)
    # initcpio generated these; de-sparsify both images. Guarded with `if [ -f ]`
    # (optional), but a real failure on a present image still aborts (set -e inside).
    for img in (_BOOT_INITRAMFS, _BOOT_INITRAMFS_FALLBACK):
        lines.append(f"if [ -f {img} ]; then")
        lines += [f"    {stmt}" for stmt in desparse_lines(img)]
        lines.append("fi")
    # Flush the rewritten /boot files to disk before the target is unmounted.
    # cp+mv leave the fresh, hole-free extents in the page cache; `sync` forces them
    # out so the very first real boot reads the de-sparsified data off disk, not a
    # state that could still be settling. Plain `sync` (no `$`).
    lines.append("sync")
    return "\n".join(lines)


def shellprocess_desparsify_conf() -> str:
    """Second `shellprocess` instance (shellprocess@desparse in settings.conf),
    scheduled as the LAST step that touches /boot -- after `initcpio` AND after
    `packages` (see the settings.conf ordering note), immediately before `umount`.
    It de-sparsifies the /boot kernel + initramfs so GRUB's btrfs driver can read
    them in full -- without it the install completes but the target fails to boot
    with GRUB "premature end of file /@/boot/vmlinuz-linux". See
    _boot_desparsify_command for the full root-cause note.

    NOT prefixed "-" (and uses `set -e`): making /boot GRUB-readable is load-bearing,
    so a failure here must stop the install with a clear error rather than ship an
    unbootable system."""
    cmd = _boot_desparsify_command()
    block = "\n".join("        " + line for line in cmd.splitlines())
    return f"""\
# Post-initcpio /boot fixup for the OFFLINE install (runs in the target chroot):
# de-sparsify /boot/vmlinuz-linux + the initramfs images so they carry no trailing
# (EOF) sparse hole. GRUB's btrfs driver reads a file's length from the extent tree,
# not i_size, and would otherwise drop the trailing hole and fail to boot with
# "premature end of file /@/boot/vmlinuz-linux". MUST run as the LAST step to touch
# /boot -- after `initcpio` and every other /boot-writing step, right before
# `umount`. Uses NO `$` (Calamares macro-expands $WORD and aborts on an unknown one
# -- see calamares_shellprocess.py).
---
dontChroot: false
# Generous timeout: this cp-rewrites three files, one of which (the fallback
# initramfs) is 200+ MB. On a slow target disk (spinning rust, a loaded VM's
# qcow2) three sequential copies of ~370 MB can take well over the old 120 s, and
# if Calamares KILLS the step mid-cp the `mv` leaves a truncated/sparse file -- the
# very unbootable state this step exists to prevent. 600 s leaves ample headroom
# while still bounding a genuinely hung copy.
timeout: 600
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

    Ordering note: shellprocess sits after unpackfs and before both `users` and
    `initcpiocfg`/`initcpio` in settings.conf's exec sequence, so both fixups land
    on the unpacked target before the modules that depend on them run."""
    reset_cmd = _mkinitcpio_reset_command()
    # Indent the multi-line reset command to sit under the YAML "- |" block scalar.
    reset_block = "\n".join("        " + line for line in reset_cmd.splitlines())
    return f"""\
# Post-unpackfs target fixups for the OFFLINE install (runs in the target chroot):
#   1. remove the live-ISO `main` account so the `users` module can recreate it
#      with the user-chosen password (/home/main is preserved), and
#   2. make the initramfs buildable: reinstate /boot/vmlinuz-<pkgbase> (mkarchiso
#      emptied /boot) and replace the copied-in *archiso* mkinitcpio preset with the
#      stock `linux` preset (+ drop archiso.conf), so `initcpio`'s `mkinitcpio -p
#      linux` produces a bootable installed-system initramfs instead of failing.
---
dontChroot: false
timeout: 60
verbose: true
script:
    - "-userdel -f {LIVE_USER}"
    - "-groupdel {LIVE_USER}"
    - |
{reset_block}
"""
