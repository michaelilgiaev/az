"""azarch.config.calamares -- the Calamares 3.4.2 installer config tree.

Every builder here returns the verbatim YAML text of one file Calamares reads at
runtime. Python never parses these strings, so a wrong filename, a clobbered exec
name, a camelCase key where the schema wants snake_case, or a key the schema
rejects (additionalProperties:false) produces a config that TYPE-CHECKS fine in
Python but makes Calamares abort at startup with "Initialization Failed" or
silently ignore a setting. Nothing in the build catches it -- the ISO builds,
boots, and only dies when a user clicks Install. These tests are the only place
those literal contracts are checked, so they parse the emitted YAML and assert
the exact keys/values/filenames the shipped Calamares schemas require.
"""

from __future__ import annotations

import re

import yaml

from azarch.config import calamares


# The 15 files Calamares reads, relative to /etc/calamares. Any drift here means
# a module in the sequence has no config (or an orphan config exists).
EXPECTED_FILES = {
    "settings.conf",
    "modules/partition.conf",
    "modules/unpackfs.conf",
    "modules/shellprocess.conf",
    "modules/users.conf",
    "modules/packages.conf",
    "modules/mount.conf",
    "modules/fstab.conf",
    "modules/locale.conf",
    "modules/initcpiocfg.conf",
    "modules/services-systemd.conf",
    "modules/grubcfg.conf",
    "modules/bootloader.conf",
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

def test_emit_map_has_exactly_15_files():
    m = calamares.emit_map()
    assert set(m) == EXPECTED_FILES
    assert len(m) == 15


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


def test_configured_modules_referenced_in_sequence():
    # Every modules/<x>.conf we emit must name a module that actually appears in
    # the settings.conf sequence (show or exec). An orphan config is dead weight;
    # a missing one means a configured module never runs.
    seq_names = set(_settings_exec_list()) | set(_settings_show_list())
    for rel in calamares.emit_map():
        if rel.startswith("modules/") and rel.endswith(".conf"):
            stem = rel[len("modules/"):-len(".conf")]
            assert stem in seq_names, stem


# --- partition.conf ---------------------------------------------------------

def test_partition_filesystem_key_spelling():
    d = yaml.safe_load(calamares.partition_conf())
    # Calamares 3.4.x uses defaultFileSystemType; the old defaultFileSystem is a
    # dead key that leaves the default silently wrong.
    assert d["defaultFileSystemType"] == "btrfs"
    assert "defaultFileSystem" not in d
    assert d["availableFileSystemTypes"][0] == "btrfs"
    assert d["luksGeneration"] == "luks2"


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
    # /usr/lib/modules/<kver>/vmlinuz. mkinitcpio -P would fail "'/boot/vmlinuz-linux'
    # must be readable" without this. The command must replicate the linux package's
    # install hook: copy modules/<kver>/vmlinuz -> /boot/vmlinuz-linux. A shell GLOB
    # (version-agnostic; no hardcoded kernel version a bump would break) selects the
    # single installed kernel, and `install -Dm644` recreates /boot with mode 644.
    d = yaml.safe_load(calamares.shellprocess_conf())
    cmd = _mkinitcpio_reset_command(d["script"])
    assert "install -Dm644 /usr/lib/modules/*/vmlinuz /boot/vmlinuz-linux" in cmd


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
