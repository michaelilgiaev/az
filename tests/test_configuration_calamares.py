"""azarch.configuration.calamares -- the Calamares 3.4.2 installer configuration tree.

Every builder here returns the verbatim YAML text of one file Calamares reads at
runtime. Python never parses these strings, so a wrong filename, a clobbered exec
name, a camelCase key where the schema wants snake_case, or a key the schema
rejects (additionalProperties:false) produces a configuration that TYPE-CHECKS fine in
Python but makes Calamares abort at startup with "Initialization Failed" or
silently ignore a setting. Nothing in the build catches it -- the ISO builds,
boots, and only dies when a user clicks Install. These tests are the only place
those literal contracts are checked, so they parse the emitted YAML and assert
the exact keys/values/filenames the shipped Calamares schemas require.
"""

from __future__ import annotations

import re

import yaml

from azarch.configuration import calamares


# The files Calamares reads, relative to /etc/calamares. Any drift here means
# a module in the sequence has no configuration (or an orphan configuration exists).
EXPECTED_FILES = {
    "settings.conf",
    "modules/partition.conf",
    "modules/unpackfs.conf",
    "modules/shellprocess.conf",
    "modules/shellprocess-desparse.conf",
    "modules/users.conf",
    "modules/packages.conf",
    "modules/mount.conf",
    "modules/fstab.conf",
    "modules/locale.conf",
    "modules/keyboard.conf",
    "modules/initcpiocfg.conf",
    "modules/luksbootkeyfile.conf",
    "modules/services-systemd.conf",
    "modules/grubcfg.conf",
    "modules/bootloader.conf",
    "modules/finished.conf",
    "branding/azarch/branding.desc",
    "branding/azarch/show.qml",
}


def _settings_exec_list() -> list:
    """Return the ordered `exec` module names from settings.conf."""
    doc = yaml.safe_load(calamares.settings_conf())
    for phase in doc["sequence"]:
        if "exec" in phase:
            return phase["exec"]
    raise AssertionError("no exec phase in settings.conf sequence")


def _settings_show_list() -> list:
    """Return the union of all `show` module names from settings.conf."""
    doc = yaml.safe_load(calamares.settings_conf())
    names: list = []
    for phase in doc["sequence"]:
        if "show" in phase:
            names.extend(phase["show"])
    return names


# --- emit_map shape ---------------------------------------------------------

def test_emit_map_has_exactly_expected_files():
    m = calamares.emit_map()
    assert set(m) == EXPECTED_FILES
    assert len(m) == len(EXPECTED_FILES) == 19


def test_emit_map_values_are_nonempty_strings():
    # An import-time f-string ValueError or an accidental None return would show
    # up here before it ever reached disk.
    for rel, content in calamares.emit_map().items():
        assert isinstance(content, str) and content.strip(), rel


# --- the fatal filename guard ----------------------------------------------

def test_services_filename_is_services_systemd():
    m = calamares.emit_map()
    assert "modules/services-systemd.conf" in m
    assert "modules/services.conf" not in m


def test_services_conf_wired_to_right_path():
    # The services-systemd.conf slot must carry services_conf()'s text, not some
    # other module's, or NetworkManager is never enabled on the installed system.
    assert calamares.emit_map()["modules/services-systemd.conf"] == calamares.services_conf()


def test_services_conf_schema_only_units():
    doc = yaml.safe_load(calamares.services_conf())
    assert set(doc) == {"units"}
    names = {u["name"] for u in doc["units"]}
    assert names == {"NetworkManager", "bluetooth", "cups"}
    nm = next(u for u in doc["units"] if u["name"] == "NetworkManager")
    assert nm["mandatory"] is True


# --- settings.conf sequence -------------------------------------------------

def test_settings_sequence_uses_services_systemd():
    execs = _settings_exec_list()
    assert "services-systemd" in execs
    assert "services" not in execs


def test_settings_exec_ordering_constraints():
    execs = _settings_exec_list()
    # partition must format before anything is mounted or unpacked onto it.
    assert execs.index("partition") < execs.index("mount") < execs.index("unpackfs")
    # initcpiocfg writes HOOKS, initcpio regenerates the initramfs, then the
    # bootloader is installed -- get this wrong and a LUKS/btrfs root is unbootable.
    assert execs.index("initcpiocfg") < execs.index("initcpio") < execs.index("bootloader")
    assert execs.index("grubcfg") < execs.index("bootloader")


def test_luksbootkeyfile_runs_before_fstab_and_initcpiocfg():
    # The double-password fix: luksbootkeyfile creates /crypto_keyfile.bin +
    # luksAddKey. It MUST run before fstab (which points crypttab at the keyfile
    # only if it exists) and before initcpiocfg (which adds the keyfile to
    # mkinitcpio FILES= only if it exists). It also must run after unpackfs (the
    # target root must exist to write the keyfile onto).
    execs = _settings_exec_list()
    assert "luksbootkeyfile" in execs
    assert execs.index("unpackfs") < execs.index("luksbootkeyfile")
    assert execs.index("luksbootkeyfile") < execs.index("fstab")
    assert execs.index("luksbootkeyfile") < execs.index("initcpiocfg")


def test_luksbootkeyfile_conf_schema():
    # The module's only valid key is luks2Hash. Az'arch uses LUKS1 so it is inert,
    # but it must parse and carry a recognized value.
    doc = yaml.safe_load(calamares.luksbootkeyfile_conf())
    assert set(doc) == {"luks2Hash"}
    assert doc["luks2Hash"] in ("default", "pbkdf2", "argon2i", "argon2id")


def _instance_config_stems() -> dict:
    """Map a custom-instance configuration STEM (e.g. 'shellprocess-desparse') to the
    `module@id` token it is used as in the sequence (e.g. 'shellprocess@desparse'),
    read from settings.conf's `instances:` block. Lets the orphan check recognise a
    per-instance configuration file whose name does not equal any bare module name."""
    doc = yaml.safe_load(calamares.settings_conf())
    out = {}
    for inst in doc.get("instances", []):
        stem = inst["configuration"][:-len(".conf")] if inst["configuration"].endswith(".conf") \
            else inst["configuration"]
        out[stem] = f"{inst['module']}@{inst['id']}"
    return out


def test_configured_modules_referenced_in_sequence():
    # Every modules/<x>.conf we emit must name a module (or a declared instance)
    # that actually appears in the settings.conf sequence (show or exec). An orphan
    # configuration is dead weight; a missing one means a configured module never runs.
    seq_names = set(_settings_exec_list()) | set(_settings_show_list())
    inst = _instance_config_stems()
    for rel in calamares.emit_map():
        if rel.startswith("modules/") and rel.endswith(".conf"):
            stem = rel[len("modules/"):-len(".conf")]
            # A per-instance configuration (shellprocess-desparse.conf) is referenced via
            # its module@id token (shellprocess@desparse); a plain configuration via its
            # bare module name.
            if stem in inst:
                assert inst[stem] in seq_names, inst[stem]
            else:
                assert stem in seq_names, stem


# --- partition.conf ---------------------------------------------------------

def test_partition_filesystem_key_spelling():
    d = yaml.safe_load(calamares.partition_conf())
    # Calamares 3.4.x uses defaultFileSystemType; the old defaultFileSystem is a
    # dead key that leaves the default silently wrong.
    assert d["defaultFileSystemType"] == "btrfs"
    assert "defaultFileSystem" not in d
    assert d["availableFileSystemTypes"][0] == "btrfs"
    # luks1, NOT luks2: /boot is on the encrypted btrfs root, so GRUB must unlock
    # the container, and GRUB <= 2.12 cannot open LUKS2 + Argon2id (cryptsetup's
    # luks2 default). luks1 is PBKDF2 and GRUB-openable. This + the luksbootkeyfile
    # module is the "password twice" fix; a drift back to luks2 would break the
    # GRUB unlock. (Matches upstream Calamares' own default.)
    assert d["luksGeneration"] == "luks1"


def test_partition_btrfs_subvolumes():
    d = yaml.safe_load(calamares.partition_conf())
    pairs = {(s["mountPoint"], s["subvolume"]) for s in d["btrfsSubvolumes"]}
    assert ("/", "/@") in pairs
    assert ("/home", "/@home") in pairs


def test_partition_supplies_efi_system_partition():
    # The ESP mount point lives HERE (bootloader.conf reads it from globalstorage),
    # so partition.conf must be the one that sets it.
    d = yaml.safe_load(calamares.partition_conf())
    assert d["efiSystemPartition"] == "/boot/efi"


# --- mount.conf -------------------------------------------------------------

def _extra_mount_points(doc) -> set:
    return {m["mountPoint"] for m in doc["extraMounts"]}


def test_mount_binds_the_standard_pseudo_filesystems():
    # proc/sys/dev/run must all be mounted into the target chroot so the
    # bootloader + initcpio jobs (which run chrooted) can see the running kernel's
    # interfaces. A missing one silently breaks a chrooted command.
    d = yaml.safe_load(calamares.mount_conf())
    pts = _extra_mount_points(d)
    assert {"/proc", "/sys", "/dev", "/run"} <= pts


def test_mount_includes_efivarfs_for_uefi_grub_install():
    # THE bootloader-install fix. grub-install (UEFI) shells out to efibootmgr to
    # register the NVRAM boot entry, and efibootmgr needs efivarfs mounted RW at
    # /sys/firmware/efi/efivars INSIDE the target chroot. A fresh sysfs mount does
    # NOT carry the efivarfs submount, so without an explicit entry grub-install
    # dies with "EFI variables are not supported on this system" /
    # "efibootmgr failed to register the boot entry" and Calamares aborts at the
    # bootloader step. This asserts the explicit efivarfs extraMount exists.
    d = yaml.safe_load(calamares.mount_conf())
    efivars = [m for m in d["extraMounts"]
               if m.get("mountPoint") == "/sys/firmware/efi/efivars"]
    assert efivars, "mount.conf must mount efivarfs for UEFI grub-install"
    entry = efivars[0]
    assert entry["fs"] == "efivarfs"
    assert entry["device"] == "efivarfs"


def test_mount_efivarfs_is_efi_only():
    # The entry MUST carry `efi: true` so Calamares' mount module drops it on a
    # legacy-BIOS install (where /sys/firmware/efi does not exist). Without this
    # flag a BIOS install still boots fine but logs a spurious "Cannot mount
    # efivarfs" warning; with it the efivarfs mount is a clean no-op off UEFI.
    # (Calamares sorts extraMounts lexically by mountPoint at runtime, so list
    # ORDER is irrelevant -- /sys sorts before /sys/firmware/... regardless and
    # the mountpoint dir is created on demand; the efi flag is the real contract.)
    d = yaml.safe_load(calamares.mount_conf())
    entry = next(m for m in d["extraMounts"]
                 if m.get("mountPoint") == "/sys/firmware/efi/efivars")
    assert entry.get("efi") is True


# --- unpackfs.conf ----------------------------------------------------------

def test_unpackfs_source_and_sourcefs():
    d = yaml.safe_load(calamares.unpackfs_conf())
    entry = d["unpack"][0]
    assert entry["source"] == calamares.ARCHISO_SFS
    assert entry["sourcefs"] == "squashfs"
    assert entry["destination"] == ""
    # Proves the f-string actually interpolated the constant into the text.
    assert calamares.ARCHISO_SFS in calamares.unpackfs_conf()


def test_archiso_sfs_path_literal():
    assert calamares.ARCHISO_SFS == "/run/archiso/bootmnt/arch/x86_64/airootfs.sfs"


# --- shellprocess.conf (the "user already exists" + archiso-preset fixes) ----

def test_shellprocess_runs_between_unpackfs_and_its_dependents():
    # The whole point: both fixups run AFTER the target exists (unpackfs) but
    # BEFORE the modules that depend on them -- `users` (account recreation) and
    # `initcpiocfg`/`initcpio` (mkinitcpio -P). Order is load-bearing.
    execs = _settings_exec_list()
    assert "shellprocess" in execs
    assert execs.index("unpackfs") < execs.index("shellprocess") < execs.index("users")
    assert execs.index("shellprocess") < execs.index("initcpiocfg") < execs.index("initcpio")


def test_shellprocess_conf_schema_and_chroot():
    d = yaml.safe_load(calamares.shellprocess_conf())
    # Runs INSIDE the target chroot so it edits the target's databases/config.
    assert d["dontChroot"] is False
    # script is a list of command strings (the shellprocess CommandList form).
    assert isinstance(d["script"], list)
    assert all(isinstance(c, str) for c in d["script"])


def _userdel_commands(script: list) -> list:
    """The two account-removal commands (userdel/groupdel), which are the ones
    prefixed '-' to be non-fatal. The mkinitcpio-reset command is separate."""
    return [c for c in script if "userdel" in c or "groupdel" in c]


def test_shellprocess_deletes_the_live_user_non_fatally():
    d = yaml.safe_load(calamares.shellprocess_conf())
    script = d["script"]
    # It must delete the `main` account (userdel), and the account-removal commands
    # are prefixed "-" so a rootfs lacking the account/group never aborts install.
    assert calamares.LIVE_USER == "main"
    assert f"-userdel -f {calamares.LIVE_USER}" in script
    assert f"-groupdel {calamares.LIVE_USER}" in script
    removal = _userdel_commands(script)
    assert len(removal) == 2
    for cmd in removal:
        assert cmd.startswith("-"), cmd
    # It must NOT remove the home directory (reuseHome relies on /home/main staying).
    joined = "\n".join(removal)
    assert "--remove" not in joined
    assert "userdel -r" not in joined
    assert "-r " not in joined


# --- shellprocess.conf: the archiso mkinitcpio fix (kernel + preset) --------

def _mkinitcpio_reset_command(script: list) -> str:
    """The single script command that fixes the target's initramfs setup (the one
    that writes linux.preset). Exactly one such command must exist."""
    matches = [c for c in script if "linux.preset" in c]
    assert len(matches) == 1, matches
    return matches[0]


def test_shellprocess_reinstates_the_kernel_image():
    # mkarchiso empties the rootfs /boot before squashing, so the unpacked target
    # has NO /boot/vmlinuz-linux -- the kernel survives only at
    # /usr/lib/modules/<kver>/vmlinuz. Calamares' initcpio step (`mkinitcpio -p
    # linux`) would fail "'/boot/vmlinuz-linux' must be readable" without this. The
    # command must replicate the linux package's install hook: copy
    # modules/<kver>/vmlinuz -> /boot/vmlinuz-linux. `find ... -exec install` (NOT a
    # glob passed to `install`, which would treat a second kernel as a target dir and
    # abort under set -e) is version-agnostic and recreates /boot with mode 644.
    d = yaml.safe_load(calamares.shellprocess_conf())
    cmd = _mkinitcpio_reset_command(d["script"])
    assert (
        "find /usr/lib/modules -maxdepth 2 -name vmlinuz "
        "-exec install -Dm644 {} /boot/vmlinuz-linux \\;"
    ) in cmd
    # find -exec exits 0 even on no match, so set -e alone would miss a missing
    # kernel; a `test -r` guard re-arms the hard failure the old glob provided.
    assert "test -r /boot/vmlinuz-linux" in cmd


def test_shellprocess_uses_no_shell_variables():
    # LOAD-BEARING: Calamares runs each shellprocess command through a
    # KWordMacroExpander (escape char '$') BEFORE the shell sees it. Any bare
    # `$WORD` that is not a Calamares variable makes the ENTIRE job abort with
    # "Missing variables" -- nothing runs, including the userdel/groupdel. And the
    # only literal-`$` escape ('$$') yields a shell-escaped `\\$` (a literal, not an
    # expansion), so shell variables / `$(...)` are unusable here. Assert NO '$'
    # appears in any emitted script command.
    d = yaml.safe_load(calamares.shellprocess_conf())
    for cmd in d["script"]:
        assert "$" not in cmd, cmd


def test_shellprocess_replaces_archiso_preset_with_stock():
    d = yaml.safe_load(calamares.shellprocess_conf())
    cmd = _mkinitcpio_reset_command(d["script"])
    # Writes the stock `linux` preset to the canonical path...
    assert "/etc/mkinitcpio.d/linux.preset" in cmd
    # ...whose defining feature is the default+fallback PRESETS (NOT archiso).
    assert "PRESETS=('default' 'fallback')" in cmd
    assert "default_image=\"/boot/initramfs-linux.img\"" in cmd
    assert "fallback_image=\"/boot/initramfs-linux-fallback.img\"" in cmd
    # The archiso preset name must be gone from what we write (that name is exactly
    # what makes `mkinitcpio -P` fail on the copied-in live rootfs).
    assert "archiso'" not in cmd  # PRESETS=('archiso') fragment
    # And it removes the archiso conf.d drop-in whose HOOKS would otherwise win.
    assert "rm -f /etc/mkinitcpio.conf.d/archiso.conf" in cmd


def test_shellprocess_mkinitcpio_command_is_fatal_on_failure():
    # The mkinitcpio fixup is deliberately NOT prefixed "-" and uses `set -e`:
    # reinstating the kernel + writing a correct preset is load-bearing (a silent
    # failure would leave /boot empty or the archiso preset in place, and the
    # install would die obscurely later at `initcpio`).
    d = yaml.safe_load(calamares.shellprocess_conf())
    cmd = _mkinitcpio_reset_command(d["script"])
    assert not cmd.startswith("-")
    assert cmd.startswith("set -e")


def test_stock_preset_constant_is_a_valid_default_fallback_preset():
    # The reused constant is the source of truth for the written preset.
    preset = calamares.STOCK_LINUX_PRESET
    assert "PRESETS=('default' 'fallback')" in preset
    assert 'ALL_kver="/boot/vmlinuz-linux"' in preset
    # No archiso-specific keys leak into the installed-system preset.
    assert "archiso" not in preset


# --- shellprocess@desparse (make /boot GRUB-readable) -----------------------

def _desparse_cmd() -> str:
    d = yaml.safe_load(calamares.shellprocess_desparsify_conf())
    # Single block-scalar command in the script list.
    assert len(d["script"]) == 1
    return d["script"][0]


def test_desparse_conf_schema_and_chroot():
    d = yaml.safe_load(calamares.shellprocess_desparsify_conf())
    # Runs INSIDE the target chroot (paths like /boot/vmlinuz-linux are target-abs).
    assert d["dontChroot"] is False
    assert "script" in d


def test_desparse_rewrites_boot_files_hole_free():
    # THE boot fix: cp --sparse=never eliminates the trailing EOF hole that makes
    # GRUB's btrfs driver read the kernel/initramfs short ("premature end of file").
    cmd = _desparse_cmd()
    assert "--sparse=never" in cmd
    # It must touch the kernel AND both initramfs images GRUB loads.
    assert "/boot/vmlinuz-linux" in cmd
    assert "/boot/initramfs-linux.img" in cmd
    assert "/boot/initramfs-linux-fallback.img" in cmd


def test_desparse_kernel_is_unconditional_initramfs_guarded():
    # The kernel always exists by now (reinstated pre-initcpio) -> de-sparsified
    # unconditionally (no `if`/`test` guard). The initramfs images are guarded with
    # `if [ -f ... ]` so a preset emitting only one image never aborts the install.
    cmd = calamares._boot_desparsify_command()
    lines = cmd.splitlines()
    # The kernel cp/mv lines are NOT inside an `if` guard (they sit at top level,
    # right after `set -e`, before the first `if`).
    first_if = next(i for i, l in enumerate(lines) if l.startswith("if "))
    kernel_lines = [l for l in lines[:first_if] if "/boot/vmlinuz-linux" in l]
    assert kernel_lines, "kernel must be de-sparsified before the first guard"
    assert not any(l.strip().startswith(("if ", "test ")) for l in kernel_lines)
    # Both initramfs rewrites ARE guarded with `if [ -f ... ]`.
    for img in ("/boot/initramfs-linux.img", "/boot/initramfs-linux-fallback.img"):
        assert f"if [ -f {img} ]; then" in cmd


def test_desparse_cp_and_mv_are_separate_statements_not_and_chains():
    # REGRESSION GUARD (the exact adversarial finding): `cp ... && mv ...` would let
    # a failed kernel `cp` slip past `set -e` (a command left of `&&` is a "tested"
    # command whose failure is ignored), so the script would exit 0 and Calamares
    # would ship an UNBOOTABLE system. The cp and mv MUST be separate statements.
    cmd = calamares._boot_desparsify_command()
    assert "&&" not in cmd, "cp/mv must not be && -chained (defeats set -e)"


def test_desparse_uses_no_shell_variables():
    # Same Calamares macro-expander constraint as the other shellprocess: a bare
    # `$WORD` aborts the whole job. Assert NO '$' in the emitted command.
    assert "$" not in _desparse_cmd()


def test_desparse_is_fatal_on_failure():
    # Making /boot GRUB-readable is load-bearing: NOT prefixed "-", uses `set -e`.
    cmd = calamares._boot_desparsify_command()
    assert not cmd.startswith("-")
    assert cmd.startswith("set -e")


def test_desparse_actually_aborts_when_kernel_cp_fails(tmp_path):
    # BEHAVIORAL proof of the fatal-on-failure contract (not just a string check):
    # run the emitted command with the kernel source ABSENT but an initramfs image
    # PRESENT. The kernel `cp` must fail and, under set -e, abort the WHOLE script
    # with a non-zero exit -- even though the later (present) initramfs step would
    # succeed. The old `&&`-chained form exited 0 here (the bug).
    import subprocess
    cmd = calamares._boot_desparsify_command()
    # Rebase the absolute /boot/... paths into a sandbox so the test touches no real
    # system files. The kernel source is deliberately NOT created (cp will fail);
    # one initramfs image IS created (its guarded step would otherwise succeed).
    boot = tmp_path / "boot"
    boot.mkdir()
    (boot / "initramfs-linux.img").write_bytes(b"present")
    sandboxed = cmd.replace("/boot/", f"{boot}/")
    rc = subprocess.run(["bash", "-c", sandboxed], capture_output=True).returncode
    assert rc != 0, "a failed kernel cp must abort the install (set -e), not exit 0"


def test_desparse_actually_removes_trailing_hole_on_disk(tmp_path):
    # THE regression guard the project was missing (this boot bug has now hit TWICE):
    # every other desparse test checks the COMMAND STRING; none proved the command
    # actually yields a hole-free file. Here we reproduce the exact pre-desparse
    # state -- a kernel + initramfs with a TRAILING EOF SPARSE HOLE, as unpackfs'
    # rsync --sparse leaves them -- run the REAL emitted command, and assert the
    # result carries NO trailing hole (allocated blocks cover the whole file). A file
    # with a hole at EOF is precisely what makes GRUB's btrfs driver read the kernel
    # short ("premature end of file /@/boot/vmlinuz-linux"); if a future edit weakens
    # the desparse (drops --sparse=never, re-&&-chains cp/mv, etc.) the file stays
    # sparse and THIS test fails -- catching the regression before an ISO ships.
    import os
    import subprocess

    boot = tmp_path / "boot"
    boot.mkdir()

    def make_sparse(name: str, data_bytes: int, hole_bytes: int) -> None:
        # Write `data_bytes` of real data, then extend the file by `hole_bytes` via
        # truncate -> a genuine sparse hole at EOF (last data extent ends before
        # i_size), the exact shape rsync --sparse produces for a zero-padded bzImage.
        # The hole is 1 MiB+ so the FS reliably leaves it unallocated (a sub-block
        # hole is not portably sparse -- tail allocation/delalloc can back it).
        p = boot / name
        with open(p, "wb") as fh:
            fh.write(b"\xa5" * data_bytes)
            fh.truncate(data_bytes + hole_bytes)

    make_sparse("vmlinuz-linux", 5_000_000, 4 * 1024 * 1024)
    make_sparse("initramfs-linux.img", 3_000_000, 2 * 1024 * 1024)
    make_sparse("initramfs-linux-fallback.img", 7_000_000, 8 * 1024 * 1024)

    # If the test filesystem refuses to make ANY of them sparse (rare -- some tmpfs/
    # overlay setups), there is nothing to de-sparsify and the on-disk assertion is
    # meaningless here; skip rather than assert a false pass/fail.
    if not any(
        os.stat(boot / n).st_blocks * 512 < os.stat(boot / n).st_size
        for n in ("vmlinuz-linux", "initramfs-linux.img", "initramfs-linux-fallback.img")
    ):
        import pytest as _pytest
        _pytest.skip("test filesystem does not create sparse files; on-disk check N/A")

    cmd = calamares._boot_desparsify_command().replace("/boot/", f"{boot}/")
    res = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
    assert res.returncode == 0, f"desparse command failed: {res.stderr}"

    # Every /boot file GRUB reads must now be hole-free: allocated blocks >= size.
    for name in ("vmlinuz-linux", "initramfs-linux.img", "initramfs-linux-fallback.img"):
        st = os.stat(boot / name)
        assert st.st_blocks * 512 >= st.st_size, (
            f"{name} still has a trailing hole after desparse "
            f"(allocated {st.st_blocks * 512} < size {st.st_size}) -- GRUB would "
            f"read it short and fail to boot"
        )
    # No leftover .nosparse temp files (mv must have renamed them into place).
    assert not list(boot.glob("*.nosparse")), "desparse left a .nosparse temp behind"


def test_desparse_preserves_file_contents(tmp_path):
    # De-sparsifying must not change the bytes GRUB/the kernel see: cp --sparse=never
    # rewrites the trailing zeros as real data but the logical content is identical.
    # (A bzImage carries its own length and ignores trailing zeros; an initramfs
    # decoder stops at its own end marker -- so real-zeros vs a hole is equivalent.)
    import hashlib
    import os
    import subprocess

    boot = tmp_path / "boot"
    boot.mkdir()
    body = b"AZ" * 100_000
    for name in ("vmlinuz-linux", "initramfs-linux.img", "initramfs-linux-fallback.img"):
        with open(boot / name, "wb") as fh:
            fh.write(body)
            fh.truncate(len(body) + 777)   # trailing hole
    want = hashlib.sha256(body + b"\x00" * 777).hexdigest()

    cmd = calamares._boot_desparsify_command().replace("/boot/", f"{boot}/")
    assert subprocess.run(["bash", "-c", cmd]).returncode == 0
    for name in ("vmlinuz-linux", "initramfs-linux.img", "initramfs-linux-fallback.img"):
        got = hashlib.sha256((boot / name).read_bytes()).hexdigest()
        assert got == want, f"{name} content changed across desparse"


def test_desparse_timeout_is_generous_for_large_initramfs():
    # REGRESSION GUARD: the fallback initramfs is 200+ MB; three sequential cp copies
    # on a slow target disk can exceed a tight timeout, and if Calamares KILLS the
    # step mid-cp the mv leaves a truncated/sparse file -> the exact unbootable state.
    # The timeout must be comfortably large (>= 300 s).
    d = yaml.safe_load(calamares.shellprocess_desparsify_conf())
    assert int(d["timeout"]) >= 300, "desparse timeout too tight for a 200MB+ initramfs cp"


def test_desparse_syncs_before_bootloader():
    # The rewritten /boot files must be flushed to disk before bootloader/grub-install
    # reads them, so a trailing `sync` is part of the command.
    assert calamares._boot_desparsify_command().rstrip().endswith("sync")


def test_desparse_runs_after_initcpio_before_bootloader():
    # It MUST run after initcpio (which writes the initramfs) and before grubcfg/
    # bootloader (which point grub.cfg at the /boot files). Wrong order => the very
    # boot failure this fixes.
    execs = _settings_exec_list()
    assert "shellprocess@desparse" in execs
    i = execs.index("shellprocess@desparse")
    assert execs.index("initcpio") < i
    assert i < execs.index("grubcfg")
    assert i < execs.index("bootloader")


def test_desparse_declared_as_shellprocess_instance():
    # The second instance must be declared so Calamares loads
    # shellprocess-desparse.conf for the `shellprocess@desparse` sequence entry.
    doc = yaml.safe_load(calamares.settings_conf())
    insts = {i["id"]: i for i in doc.get("instances", [])}
    assert "desparse" in insts
    assert insts["desparse"]["module"] == "shellprocess"
    assert insts["desparse"]["configuration"] == "shellprocess-desparse.conf"


def test_desparse_conf_wired_to_right_path():
    # The emitted file name must match the instance's configuration: reference.
    assert (calamares.emit_map()["modules/shellprocess-desparse.conf"]
            == calamares.shellprocess_desparsify_conf())


# --- users.conf (reuse the surviving /home/main) ----------------------------

def test_users_reuse_home_true():
    # After shellprocess removes the account, /home/main (uid 1000) remains on the
    # target; reuseHome makes useradd -m reuse it instead of erroring/wiping.
    d = yaml.safe_load(calamares.users_conf())
    assert d["reuseHome"] is True
    # The live user must NOT be autologin on the installed system.
    assert d["doAutologin"] is False


# --- locale.conf timezone default -------------------------------------------

def test_locale_conf_defaults_to_asia_jerusalem():
    d = yaml.safe_load(calamares.locale_conf())
    assert d["region"] == "Asia"
    assert d["zone"] == "Jerusalem"


# --- keyboard.conf: no auto-resolve (the Hebrew-preselect fix) --------------

def test_keyboard_conf_disables_layout_guess():
    # THE fix for the installer auto-resolving the keyboard to Hebrew from the
    # Asia/Jerusalem region default: guessLayout MUST be false so the module keeps
    # the live system's current layout ("us", set by setup-locale.sh) instead of
    # deriving one from the locale/timezone. (Verified against Calamares 3.4.2
    # keyboard Config.cpp: guessLocaleKeyboardLayout() early-returns when false.)
    d = yaml.safe_load(calamares.keyboard_conf())
    assert d["guessLayout"] is False


def test_keyboard_conf_uses_plain_xorg_not_locale1():
    # Az'arch is Openbox/X11 and setup-locale.sh already wrote
    # /etc/X11/xorg.conf.d/00-keyboard.conf with "us"; managing that file directly
    # (useLocale1 false) is what lets the module read "us" as the current layout.
    d = yaml.safe_load(calamares.keyboard_conf())
    assert d["useLocale1"] is False
    assert d["xOrgConfFileName"] == "/etc/X11/xorg.conf.d/00-keyboard.conf"


def test_keyboard_conf_no_kde_gnome_integration():
    # Openbox/X11 -- no KWin/GNOME keyboard integration to configure.
    d = yaml.safe_load(calamares.keyboard_conf())
    assert d["configure"] == {"kwin": False, "gnome": False}


def test_keyboard_in_show_and_configured():
    # keyboard is a UI page (show) and now carries a real configuration (not defaults).
    assert "keyboard" in _settings_show_list()
    assert calamares.emit_map()["modules/keyboard.conf"] == calamares.keyboard_conf()


# --- grubcfg.conf -----------------------------------------------------------

def test_grubcfg_snake_case_key():
    d = yaml.safe_load(calamares.grubcfg_conf())
    # keep_distributor is snake_case; the camelCase variant is silently ignored,
    # so the GRUB_DISTRIBUTOR string would be dropped.
    assert "keep_distributor" in d
    assert "keepDistributor" not in d
    assert d["keep_distributor"] is True


def test_grubcfg_defaults_and_kernel_params():
    d = yaml.safe_load(calamares.grubcfg_conf())
    assert d["kernel_params"] == ["quiet"]
    assert d["defaults"]["GRUB_TIMEOUT"] == 5
    assert d["defaults"]["GRUB_DEFAULT"] == "saved"


# --- packages.conf ----------------------------------------------------------

def test_packages_conf_uses_try_remove():
    d = yaml.safe_load(calamares.packages_conf())
    ops = d["operations"]
    # try_remove (not remove) so an absent live-only package does not fail install.
    assert ops == [{"try_remove": ["calamares"]}]
    for op in ops:
        assert "remove" not in op


def test_packages_backend_is_pacman_no_network():
    d = yaml.safe_load(calamares.packages_conf())
    assert d["backend"] == "pacman"
    assert d["update_db"] is False
    assert d["update_system"] is False


# --- fstab.conf -------------------------------------------------------------

def test_fstab_only_allowed_keys():
    # Schema is additionalProperties:false with exactly these two keys.
    d = yaml.safe_load(calamares.fstab_conf())
    assert set(d) == {"crypttabOptions", "tmpOptions"}


# --- bootloader.conf --------------------------------------------------------

def test_bootloader_no_schema_rejected_keys():
    # bootloader schema is additionalProperties:false: these derived keys would
    # fail validation and abort the install.
    d = yaml.safe_load(calamares.bootloader_conf())
    assert "kernel" not in d
    assert "img" not in d
    assert "fallback" not in d
    # The ESP key belongs to partition.conf, not here.
    assert "efiSystemPartition" not in d


def test_bootloader_grub_identity():
    d = yaml.safe_load(calamares.bootloader_conf())
    assert d["efiBootLoader"] == "grub"
    assert d["efiBootloaderId"] == "azarch"


# --- finished.conf (Restart-now option on the Finish page) ------------------

def test_finished_offers_restart_now():
    # Without this configuration the Finish page shows only "Done" and cannot reboot into
    # the new system. user-unchecked shows a "Restart now" checkbox, default off.
    d = yaml.safe_load(calamares.finished_conf())
    assert d["restartNowMode"] == "user-unchecked"
    # Reboot command must ignore inhibitors so it actually restarts.
    assert d["restartNowCommand"] == "systemctl -i reboot"


def test_finished_conf_schema_only_valid_keys():
    # finished schema is additionalProperties:false -- an unknown key aborts
    # Calamares at startup. Assert we only use documented keys.
    d = yaml.safe_load(calamares.finished_conf())
    valid = {"restartNowEnabled", "restartNowChecked", "restartNowCommand",
             "restartNowMode", "notifyOnFinished"}
    assert set(d) <= valid
    # finished is in the sequence's show phase, so its configuration is not an orphan.
    assert "finished" in _settings_show_list()


# --- branding.desc ----------------------------------------------------------

def test_branding_style_keys_capitalized():
    d = yaml.safe_load(calamares.branding_desc())
    style = d["style"]
    # Lowercase style keys are silently ignored, so the accent never applies.
    for key in style:
        assert key[0].isupper(), key


def test_branding_images_all_empty():
    d = yaml.safe_load(calamares.branding_desc())
    images = d["images"]
    # No PNGs shipped; empty strings make Calamares fall back to its default
    # pixmap instead of logging "does not exist".
    assert set(images) == {"productLogo", "productIcon", "productWelcome"}
    for val in images.values():
        assert val == ""


def test_branding_component_and_product_strings():
    d = yaml.safe_load(calamares.branding_desc())
    assert d["componentName"] == "azarch"
    assert d["strings"]["productName"] == "Az'arch Linux"
    assert d["strings"]["bootloaderEntryName"] == "Az'arch"


# --- module identity constants ---------------------------------------------

def test_module_identity_constants():
    assert calamares.BRANDING == "azarch"
    assert calamares.PRODUCT == "Az'arch Linux"
    # The branding paths in emit_map interpolate BRANDING.
    m = calamares.emit_map()
    assert f"branding/{calamares.BRANDING}/branding.desc" in m
    assert f"branding/{calamares.BRANDING}/show.qml" in m


# --- every YAML file parses -------------------------------------------------

def test_every_yaml_value_parses():
    # The .qml slide is not YAML; everything else must load without raising, or
    # Calamares would fail to read it at runtime.
    for rel, content in calamares.emit_map().items():
        if rel.endswith(".qml"):
            continue
        parsed = yaml.safe_load(content)
        assert isinstance(parsed, dict), rel


def test_qml_slide_carries_product_name():
    qml = calamares.branding_show_qml()
    # The apostrophe in "Az'arch" must survive into the QML string literal and the
    # escaped newline must stay escaped (raw \\n in the emitted text).
    assert "Installing Az'arch Linux" in qml
    assert "goToNextSlide()" in qml
