"""modifications.installer -- the on-disk install pipeline scripts.

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

import installer


# --- every generator produces bash / configuration text ---------------------------

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


# --- grub auto-boot first option (Task 4, shell-installer path) -------------

def test_chroot_setup_configures_grub_auto_boot():
    # The shell installer must set the same auto-boot-first-entry policy the
    # Calamares path does, BEFORE grub-mkconfig reads /etc/default/grub.
    s = installer.chroot_setup_sh()
    assert "set_grub_default GRUB_DEFAULT 0" in s        # first entry
    assert "set_grub_default GRUB_TIMEOUT 0" in s        # no wait
    assert "set_grub_default GRUB_TIMEOUT_STYLE hidden" in s
    # It must run before grub-mkconfig regenerates grub.cfg, or the change is unused.
    assert s.index("set_grub_default GRUB_TIMEOUT 0") < s.index("grub-mkconfig -o /boot/grub/grub.cfg")


def test_chroot_setup_grub_default_helper_is_idempotent(tmp_path):
    # BEHAVIORAL: the set_grub_default helper must (a) REWRITE an existing key
    # (commented or not) and (b) APPEND a missing key, leaving each set exactly once.
    # Extract the helper definition + its three invocations from the emitted script
    # (a contiguous block: `set_grub_default() { ... }` immediately followed by the
    # three `set_grub_default ...` calls) and run it against a stock-like grub file.
    import re
    import subprocess

    s = installer.chroot_setup_sh()
    start = s.index("set_grub_default() {")
    end = s.index("\n\ngrub-mkconfig -o /boot/grub/grub.cfg")
    block = s[start:end]                       # def + the three calls
    assert "set_grub_default GRUB_TIMEOUT_STYLE hidden" in block

    grub = tmp_path / "grub"
    # Stock-ish: GRUB_DEFAULT present (non-zero, to prove rewrite), GRUB_TIMEOUT
    # present, GRUB_TIMEOUT_STYLE COMMENTED (to prove the commented branch), plus an
    # unrelated line that must be preserved.
    grub.write_text(
        "GRUB_DEFAULT=saved\n"
        "GRUB_TIMEOUT=5\n"
        "#GRUB_TIMEOUT_STYLE=menu\n"
        'GRUB_CMDLINE_LINUX_DEFAULT="quiet"\n'
    )
    sandboxed = block.replace("/etc/default/grub", str(grub))
    # Run TWICE to prove idempotency (a second pass must not duplicate any line).
    res = subprocess.run(["bash", "-c", "set -e\n" + sandboxed + "\n" + sandboxed],
                         capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    out = grub.read_text()
    # Exactly one of each key, all carrying the auto-boot values.
    assert len(re.findall(r"(?m)^GRUB_DEFAULT=", out)) == 1
    assert len(re.findall(r"(?m)^GRUB_TIMEOUT=", out)) == 1
    assert len(re.findall(r"(?m)^GRUB_TIMEOUT_STYLE=", out)) == 1
    assert "GRUB_DEFAULT=0" in out
    assert "GRUB_TIMEOUT=0" in out
    assert "GRUB_TIMEOUT_STYLE=hidden" in out
    # The old saved/5/commented values must be gone.
    assert "GRUB_DEFAULT=saved" not in out
    assert "GRUB_TIMEOUT=5" not in out
    # The unrelated line is preserved.
    assert 'GRUB_CMDLINE_LINUX_DEFAULT="quiet"' in out


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
    # Default-DENY inbound (silent drop -- no ICMP advertising the box), default-allow
    # outbound. Swapping these silently either firewalls off the machine's own traffic or
    # opens it to the world. The timedate port (49154) is explicitly denied so the local
    # home page stays reachable only by the machine itself.
    s = installer.setup_pkgs_sh()
    assert "sudo ufw enable" in s
    assert "sudo ufw default deny incoming" in s
    assert "sudo ufw default allow outgoing" in s
    assert "sudo ufw deny 49154" in s
    # The old 'reject' policy must not linger (the spec asks for Deny).
    assert "reject incoming" not in s


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
