"""azarch.config.system -- the security-sensitive user/group databases, sudoers,
OS branding, boot menus, and systemd units baked into the live ISO.

These are pure Python string constants, but they are the ones where a silent
byte drift is genuinely dangerous. A non-empty root password field would lock
out the passwordless autologin; a wrong gid in one of passwd/group/gshadow would
desync the user's primary group; flipping ID=arch to anything else would make
pacman and every AUR helper stop treating the system as Arch; dropping the empty
first `ExecStart=` reset line would make systemd refuse the getty drop-in; losing
the `%INSTALL_DIR%`/`%ARCHISO_UUID%` archiso placeholders would produce an
unbootable ISO because mkarchiso would have nothing to substitute. Nothing in the
build catches any of these -- the ISO just boots wrong. These tests pin the exact
bytes so such a drift fails here instead of at boot.
"""

from __future__ import annotations

from azarch.config import system


# --- passwd / shadow / group / gshadow: the user database -------------------

def test_passwd_exact():
    # Byte-exact: root uid/gid 0 with bash, main uid 1000 primary gid 998.
    assert system.PASSWD == (
        "root:x:0:0:root:/root:/usr/bin/bash\n"
        "main:x:1000:998::/home/main:/usr/bin/bash\n"
    )


def test_passwd_lines_have_seven_colon_fields():
    # /etc/passwd is 7 colon-separated fields; a miscount corrupts the DB.
    for line in system.PASSWD.splitlines():
        assert len(line.split(":")) == 7, line


def test_shadow_passwords_empty():
    # Blank password field (index 1) == no password == the passwordless live login.
    # A non-empty hash here would silently lock out autologin.
    for line in system.SHADOW.splitlines():
        assert line.split(":")[1] == "", line


def test_gid_coupling_autologin_matches_passwd_primary_gid():
    # main's primary gid in PASSWD (field 4) must equal the `autologin` gid in GROUP.
    # If these drift, the live user is no longer in its intended primary group.
    gids = {}
    for line in system.GROUP.splitlines():
        fields = line.split(":")
        gids[fields[0]] = fields[2]
    assert gids["autologin"] == "998"

    main_line = next(l for l in system.PASSWD.splitlines() if l.startswith("main:"))
    assert main_line.split(":")[3] == gids["autologin"]


def test_group_names_match_gshadow():
    # group and gshadow must describe the SAME set of groups or shadow-group tools
    # complain / entries are ignored.
    group_names = {l.split(":")[0] for l in system.GROUP.splitlines()}
    gshadow_names = {l.split(":")[0] for l in system.GSHADOW.splitlines()}
    assert group_names == {"root", "autologin", "main"}
    assert group_names == gshadow_names


# --- sudoers + hostname: short byte-exact files -----------------------------

def test_short_files_exact():
    # These four are mode-sensitive (0440 sudoers) and must be byte-faithful:
    # a stray space in the sudoers rule invalidates the whole file (sudo refuses).
    assert system.SUDOERS_MAIN == "main ALL=(ALL) NOPASSWD: ALL\n"
    assert system.SUDOERS_ROOTPW == "Defaults rootpw\n"
    assert system.HOSTNAME == "azarch\n"


# --- os-release: the branding that must NOT change ID -----------------------

def _parse_os_release():
    d = {}
    for line in system.OS_RELEASE.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            d[key] = val.strip('"')
    return d


def test_os_release_id_stays_arch():
    # ID=arch is load-bearing: pacman/AUR helpers key on it. Only the human strings
    # (NAME/PRETTY_NAME) carry the Az'arch brand.
    d = _parse_os_release()
    assert d["ID"] == "arch"
    assert d["ID_LIKE"] == "arch"
    assert d["NAME"] == "Az'arch Linux"
    assert d["PRETTY_NAME"] == "Az'arch Linux"
    assert d["BUILD_ID"] == "rolling"


# --- customize_airootfs: the post-pacstrap os-release planting hook ----------

def test_customize_airootfs_copies_os_release():
    s = system.CUSTOMIZE_AIROOTFS
    assert s.startswith("#!/usr/bin/env bash")
    assert "cp /root/azarch/os-release /usr/lib/os-release" in s
    assert "chmod 0644 /usr/lib/os-release" in s


# --- getty autologin drop-in ------------------------------------------------

def test_getty_autologin_reset_first():
    # systemd requires an empty `ExecStart=` line FIRST to clear the unit default
    # before a drop-in sets its own; the second line does the actual autologin.
    exec_lines = [
        l for l in system.GETTY_TTY1_AUTOLOGIN.splitlines()
        if l.startswith("ExecStart=")
    ]
    assert exec_lines[0] == "ExecStart="
    assert "--autologin main" in exec_lines[1]
    assert "agetty" in exec_lines[1]


# --- boot menu entries: placeholders + accessibility split ------------------

def test_boot_entries_placeholders_survive():
    # mkarchiso substitutes %INSTALL_DIR% and %ARCHISO_UUID%; if either is lost the
    # entry points at a nonexistent path and the ISO won't boot.
    for const in (
        system.BOOT_UEFI_LINUX,
        system.BOOT_UEFI_SPEECH,
        system.BOOT_BIOS_SYSLINUX,
    ):
        assert "%INSTALL_DIR%" in const
        assert "%ARCHISO_UUID%" in const


def test_accessibility_only_in_speech_entries():
    # The plain entry must NOT carry accessibility=on; the speech entry must.
    assert "accessibility=on" not in system.BOOT_UEFI_LINUX
    assert "accessibility=on" in system.BOOT_UEFI_SPEECH
    # BIOS combined block: exactly one accessibility entry (the ^speech LABEL).
    assert system.BOOT_BIOS_SYSLINUX.count("accessibility=on") == 1


def test_bios_syslinux_has_two_boot_labels():
    # Two actual boot targets: `LABEL arch64` and `LABEL arch64speech`. Count lines
    # that START with `LABEL ` (a bare .count('LABEL ') would also catch the two
    # `MENU LABEL ` display lines -- the substring appears 4x in the block).
    label_lines = [
        l for l in system.BOOT_BIOS_SYSLINUX.splitlines() if l.startswith("LABEL ")
    ]
    assert len(label_lines) == 2
    # And the substring really does appear 4 times (2 LABEL + 2 MENU LABEL) --
    # documents why the ^-anchored count above is the right check.
    assert system.BOOT_BIOS_SYSLINUX.count("LABEL ") == 4


def test_syslinux_head_rebranded():
    # The releng head.cfg says `MENU TITLE Arch Linux`; ours overlays the brand.
    assert "MENU TITLE Az'arch Linux" in system.BOOT_BIOS_SYSLINUX_HEAD
    assert "MENU TITLE Arch Linux" not in system.BOOT_BIOS_SYSLINUX_HEAD


# --- systemd units: the two must diverge on purpose -------------------------

def test_locale_service_waits_for_network_online():
    # The locale detector needs actual connectivity (IP geolocation), so it orders
    # AFTER and WANTS network-online.target, and stays active (yes) after exit.
    s = system.LOCALE_SETUP_SERVICE
    assert "After=network-online.target" in s
    assert "Wants=network-online.target" in s
    assert "RemainAfterExit=yes" in s


def test_pkgs_service_diverges_from_locale():
    # The pkgs unit deliberately uses the weaker network.target (no -online), guards
    # on the script existing, and uses the `true` spelling of RemainAfterExit.
    s = system.PKGS_SETUP_SERVICE
    assert "After=network.target" in s
    assert "network-online" not in s
    assert "ConditionPathExists=/root/azarch/setup-pkgs.sh" in s
    assert "RemainAfterExit=true" in s
