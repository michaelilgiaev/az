"""azarch.config.installer -- the on-disk install pipeline scripts.

These generators emit the real .sh/.conf/.service files the ISO ships. They are
pure string producers, but the strings are load-bearing in three brittle ways:

  1. Cross-file token contracts. `first_boot_conf()` writes the literal line
     `First_Boot=TRUE`; `first_boot_sh()` greps for `^First_Boot=TRUE` and
     `sed`s it to `First_Boot=FALSE`. If either side's spelling drifts, the
     first-boot-once mechanism silently never runs (or never disables itself)
     -- nothing in Python catches a mismatched grep token.

  2. Brace escaping. `chroot_setup_sh()` is an f-string, so every literal `{`/`}`
     that must survive into bash (the `find ... -exec chmod {} \\;` calls) is
     doubled as `{{`/`}}` in the source. A single missed doubling raises
     ValueError at import; a stray leftover `{{` ships broken bash. We assert the
     emitted text has singular braces and no `{{`/`}}` residue.

  3. Path / argv agreement. The UEFI vs BIOS grub-install target flags, the
     fdisk keystroke strings (`+1G` for the UEFI ESP, `+1M` for the BIOS boot
     partition), the nvme `p1`/`p2` vs plain `1`/`2` partition-suffix branches,
     and the first-boot service `ExecStart=` path all have to match the paths the
     installer copies files to. A wrong path fails only on real hardware.

Everything here is pure: no network, no subprocess, no filesystem writes. The one
seam we isolate is `_detect_and_apply_locale_block`, imported into the installer
module namespace, so monkeypatching `installer._detect_and_apply_locale_block`
lets us prove the locale block is spliced into `chroot_setup_sh()` at the right
spot without depending on the locale module's exact content.
"""

from __future__ import annotations

from azarch.config import installer


# --- every generator produces bash / config text ---------------------------

def test_each_generator_returns_bash():
    # A broken f-string (bad brace, missing interpolation) raises ValueError at
    # call time, and an accidental `return` of None ships an empty file. This
    # single sweep catches both across every public generator.
    shell_generators = (
        installer.installer_sh,
        installer.chroot_setup_sh,
        installer.setup_pkgs_sh,
        installer.first_boot_sh,
    )
    for gen in shell_generators:
        out = gen()
        assert isinstance(out, str) and out
        assert out.splitlines()[0] == "#!/bin/bash", gen.__name__


def test_conf_and_service_headers():
    conf = installer.first_boot_conf()
    service = installer.first_boot_service()
    assert isinstance(conf, str) and conf
    assert conf.splitlines()[0] == "# Set to TRUE to enable first boot shell script."
    assert isinstance(service, str) and service
    assert service.splitlines()[0] == "[Unit]"


# --- cross-file First_Boot token contract ----------------------------------

def test_first_boot_conf_token_is_a_full_line():
    # The conf carries the exact token the .sh side greps for. It must be a
    # standalone line so `grep -q '^First_Boot=TRUE'` anchors on it.
    conf = installer.first_boot_conf()
    assert "First_Boot=TRUE" in conf.splitlines()


def test_first_boot_sh_greps_and_flips_the_same_token():
    # The whole first-boot-once mechanism is this handshake: grep the TRUE token,
    # then sed it to FALSE so the second boot skips. Both anchored on ^.
    sh = installer.first_boot_sh()
    assert "grep -q '^First_Boot=TRUE'" in sh
    assert "sed -i 's/^First_Boot=TRUE/First_Boot=FALSE/'" in sh


# --- brace escaping in the f-string chroot script --------------------------

def test_chroot_setup_braces_emitted_singly():
    # The `find ... -exec chmod {} \;` calls need literal single braces in the
    # emitted bash. In the source these are doubled ({{}}) for the f-string; a
    # missed doubling would either raise at call time or leak `{{`/`}}`.
    s = installer.chroot_setup_sh()
    assert "find /home/main -type f -exec chmod 666 {} \\;" in s
    assert "find /home/main -type d -exec chmod 777 {} \\;" in s
    assert "find /home/main -type f -exec chmod +x {} \\;" in s


def test_chroot_setup_has_no_leftover_double_braces():
    s = installer.chroot_setup_sh()
    assert "{{" not in s
    assert "}}" not in s


# --- grub-install: both firmware branches present --------------------------

def test_grub_install_both_branches():
    # UEFI and BIOS installs take different grub-install targets. Both must be
    # present; a dropped branch bricks half the install base.
    s = installer.chroot_setup_sh()
    assert (
        "grub-install --target=x86_64-efi --bootloader-id=grub_uefi "
        "--recheck --efi-directory=/boot/EFI" in s
    )
    assert 'grub-install --target=i386-pc "$disk"' in s


# --- installer_sh: ANSI codes, fdisk keystrokes, partition suffixes --------

def test_installer_sh_ansi_escape_sequences():
    # The color codes are emitted as the two-char bash escape backslash-033
    # (LIGHT_BLUE, RED, RESET). These reach the terminal as ESC at runtime; in
    # the file they are the literal backslash-zero-three-three text.
    s = installer.installer_sh()
    assert "LIGHT_BLUE='\\033[1;34m'" in s
    assert "RED='\\033[1;31m'" in s
    assert "RESET='\\033[0m'" in s
    # three color variables -> three backslash-033 occurrences.
    assert s.count("\\033") == 3


def test_installer_sh_fdisk_keystrokes_uefi_and_bios():
    # UEFI carves a +1G EFI system partition; BIOS carves a +1M BIOS-boot
    # partition. The exact fdisk keystroke pipelines differ; both must ship.
    s = installer.installer_sh()
    assert '+1G' in s
    assert '+1M' in s
    assert 'echo -e "g\\nn\\n\\n\\n+1G\\nt\\n1\\nn\\n\\n\\n\\nw" | fdisk "$largest_disk"' in s
    assert 'echo -e "g\\nn\\n\\n\\n+1M\\nt\\n4\\nn\\n\\n\\n\\nw" | fdisk "$largest_disk"' in s


def test_installer_sh_nvme_vs_sata_partition_suffix():
    # nvme devices name partitions <disk>p1/p2; sata/scsi name them <disk>1/2.
    # Both branches must exist or one disk class gets the wrong device node.
    s = installer.installer_sh()
    assert 'part1="${largest_disk}p1"' in s
    assert 'part2="${largest_disk}p2"' in s
    assert 'part1="${largest_disk}1"' in s
    assert 'part2="${largest_disk}2"' in s


def test_installer_sh_pacstrap_sed_matches_manifest_parsing():
    # The on-disk installer must pacstrap the SAME package set mkarchiso built
    # from, so it strips comments/blanks from packages.x86_64 with the identical
    # sed program. A drift here installs a different set than the live medium.
    s = installer.installer_sh()
    assert (
        "pacstrap /mnt $(sed '/^[[:blank:]]*#.*/d;s/#.*//;/^[[:blank:]]*$/d' "
        "/root/azarch/packages.x86_64)" in s
    )


# --- setup_pkgs: firewall direction ----------------------------------------

def test_setup_pkgs_firewall_direction():
    # Default-reject inbound, default-allow outbound. Swapping these silently
    # either firewalls off the machine's own traffic or opens it to the world.
    s = installer.setup_pkgs_sh()
    assert "sudo ufw default reject incoming" in s
    assert "sudo ufw default allow outgoing" in s


# --- first-boot systemd unit -----------------------------------------------

def test_first_boot_service_execstart_and_type():
    # The unit's ExecStart must point at the exact path installer_sh copies the
    # script to, and it must be a oneshot wanted by multi-user.target or it
    # never runs at boot.
    s = installer.first_boot_service()
    assert "ExecStart=/home/main/.config/first-boot/first-boot-setup.sh" in s
    assert "Type=oneshot" in s
    assert "[Install]" in s
    assert "WantedBy=multi-user.target" in s


def test_first_boot_service_execstart_path_matches_installer_copy():
    # Cross-file: the path the service execs must be a path installer_sh actually
    # populates. Assert the same absolute script path appears on both sides.
    script = "/home/main/.config/first-boot/first-boot-setup.sh"
    assert f"ExecStart={script}" in installer.first_boot_service()
    assert script in installer.installer_sh()


# --- locale block splice (single-seam isolation) ---------------------------

def test_locale_block_spliced_between_shebang_and_pacman_key(monkeypatch):
    # chroot_setup_sh() interpolates _detect_and_apply_locale_block() by the name
    # bound in the installer module namespace, so replacing that name changes the
    # emitted script. We prove the block lands after the shebang and before the
    # keyring init -- the ordering the chroot depends on.
    monkeypatch.setattr(
        installer, "_detect_and_apply_locale_block", lambda: "SENTINEL_LOCALE_MARKER"
    )
    s = installer.chroot_setup_sh()
    assert "SENTINEL_LOCALE_MARKER" in s
    assert s.index("#!/bin/bash") < s.index("SENTINEL_LOCALE_MARKER")
    assert s.index("SENTINEL_LOCALE_MARKER") < s.index("pacman-key --init")
