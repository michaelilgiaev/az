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


# The 14 files Calamares reads, relative to /etc/calamares. Any drift here means
# a module in the sequence has no config (or an orphan config exists).
EXPECTED_FILES = {
    "settings.conf",
    "modules/partition.conf",
    "modules/unpackfs.conf",
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

def test_emit_map_has_exactly_14_files():
    m = calamares.emit_map()
    assert set(m) == EXPECTED_FILES
    assert len(m) == 14


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
