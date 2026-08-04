"""azarch.configuration.system -- the security-sensitive user/group databases, sudoers,
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

from azarch.configuration import system


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


def test_customize_airootfs_sets_default_plasma_wallpaper():
    # The regeneration-proof wallpaper mechanism: rewrite the org.kde.image plugin's
    # Image default (owned by plasma-workspace) to the Az'arch wallpaper. Must target
    # the stable main.xml path and be guarded so an absent Plasma / parse surprise
    # never aborts the mkarchiso build.
    s = system.CUSTOMIZE_AIROOTFS
    assert "/usr/share/plasma/wallpapers/org.kde.image/contents/config/main.xml" in s
    # The default points at the "years" KPackage DIRECTORY (== desktop.WALLPAPER_PACKAGE_DIR),
    # NOT its inner image file (a file path makes Plasma add a duplicate resolution-
    # labelled tile) and NOT a standalone /usr/share/azarch/wallpaper.png.
    from azarch.configuration import desktop
    assert f'WALLPAPER="{desktop.WALLPAPER_PACKAGE_DIR}"' in s
    assert "/usr/share/azarch/wallpaper.png" not in s
    # Must NOT reference the inner png for the Plasma default (the duplicate-tile bug).
    assert 'WALLPAPER="/usr/share/wallpapers/years/contents/images' not in s
    # non-fatal + only runs when the xml file and the wallpaper DIRECTORY both exist
    assert "|| true" in s
    assert 'if [ -f "$IMG_MAIN_XML" ] && [ -d "$WALLPAPER" ]; then' in s


def test_customize_airootfs_removes_notifications_applet_entirely():
    # The user wants NO notifications on the distro. The plasmoid .so is deleted so
    # plasmashell cannot load/auto-discover it into any tray. Guarded with `|| true`.
    s = system.CUSTOMIZE_AIROOTFS
    assert (
        "rm -f /usr/lib/qt6/plugins/plasma/applets/org.kde.plasma.notifications.so"
        in s
    )
    assert "rm -rf /usr/share/plasma/plasmoids/org.kde.plasma.notifications" in s


def test_customize_airootfs_wallpaper_python_is_valid():
    # The embedded Python rewriter must at least compile -- a SyntaxError would only
    # surface at build time inside the chroot, aborting mkarchiso. Extract the
    # heredoc body and compile it.
    s = system.CUSTOMIZE_AIROOTFS
    body = s.split("<<'PYEOF' || true\n", 1)[1].split("\nPYEOF", 1)[0]
    compile(body, "<customize_airootfs embedded python>", "exec")


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
    # The live locale oneshot orders AFTER and WANTS network-online.target and
    # stays active (yes) after exit. The setup itself is now STATIC (no IP-geo
    # since auto-resolve was removed), so this ordering is currently harmless
    # rather than required; it is kept for the deferred `azarch --resolve-*`
    # network resolver (issue #46) that reuses this unit's timing.
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


# --- Power management: lid / power button (static logind drop-in) -----------

def _parse_ini(text: str) -> dict:
    """Parse a simple [Section] key=value INI (logind drop-in) into
    {section: {key: value}}. Good enough for the small drop-ins here."""
    out: dict = {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            out.setdefault(section, {})
        elif "=" in line and section is not None:
            k, v = line.split("=", 1)
            out[section][k.strip()] = v.strip()
    return out


def test_logind_power_dropin_lid_does_nothing():
    # The user asked: closing the lid does NOTHING. All three lid keys must be
    # ignore -- otherwise logind still suspends on lid-close when on battery/docked.
    d = _parse_ini(system.LOGIND_POWER_DROPIN)
    login = d["Login"]
    assert login["HandleLidSwitch"] == "ignore"
    assert login["HandleLidSwitchExternalPower"] == "ignore"
    assert login["HandleLidSwitchDocked"] == "ignore"


def test_logind_power_dropin_power_button_shuts_down():
    # The user asked: the power button SHUTS DOWN.
    d = _parse_ini(system.LOGIND_POWER_DROPIN)
    assert d["Login"]["HandlePowerKey"] == "poweroff"


def test_logind_power_dropin_is_login_section():
    # logind drop-ins are read from the [Login] group; a wrong header makes every
    # key silently ignored.
    d = _parse_ini(system.LOGIND_POWER_DROPIN)
    assert set(d) == {"Login"}


# --- Power management: PC-vs-laptop idle-sleep policy (dynamic) --------------

def test_sleep_policy_idle_is_fifteen_minutes():
    # 15 minutes == 900 seconds, per the request.
    assert system.SLEEP_POLICY_IDLE_SECONDS == 900


def test_sleep_policy_dropin_path_is_separate_from_static():
    # The dynamic idle drop-in must be a DIFFERENT file from the static lid/button
    # one (10-*), so the two never clobber each other; 20-* sorts after 10-*.
    assert system.SLEEP_POLICY_DROPIN_PATH == "/etc/systemd/logind.conf.d/20-azarch-sleep.conf"


def test_sleep_policy_script_is_bash_with_battery_and_ac_detection():
    s = system.SLEEP_POLICY_SCRIPT
    assert s.startswith("#!/bin/bash")
    # Reads sysfs power_supply to detect battery presence and AC state.
    assert "/sys/class/power_supply" in s
    assert 'has_battery' in s
    assert 'on_ac' in s
    assert '"Battery"' in s
    assert '"Mains"' in s


def test_sleep_policy_script_encodes_the_three_cases():
    # The decision table: only "laptop AND unplugged" -> suspend; everything else
    # (PC, or laptop on AC) -> ignore (never sleep).
    s = system.SLEEP_POLICY_SCRIPT
    assert 'action="ignore"' in s            # default: never sleep
    assert 'if has_battery && ! on_ac; then' in s
    assert 'action="suspend"' in s           # the one sleeping case
    # It writes IdleAction/IdleActionSec into the drop-in and reloads logind live.
    assert "IdleAction=$action" in s
    assert "IdleActionSec=$secs" in s
    assert system.SLEEP_POLICY_DROPIN_PATH in s
    assert "systemctl reload systemd-logind" in s


def test_sleep_policy_script_uses_the_idle_seconds_constant():
    # The 15-minute value in the script must come from the constant (single source).
    s = system.SLEEP_POLICY_SCRIPT
    assert f"IDLE_SECS={system.SLEEP_POLICY_IDLE_SECONDS}" in s


def test_sleep_policy_service_is_oneshot_after_logind():
    s = system.SLEEP_POLICY_SERVICE
    assert "Type=oneshot" in s
    assert "ExecStart=/usr/local/bin/azarch-sleep-policy" in s
    # Ordered after logind so the boot-time reload lands on a running logind.
    assert "After=systemd-logind.service" in s
    assert "WantedBy=multi-user.target" in s


def test_sleep_policy_udev_rule_retriggers_on_ac_change():
    # The rule must re-run the policy service ONLY on AC-adapter (Mains) change --
    # not on every battery-level tick.
    r = system.SLEEP_POLICY_UDEV_RULE
    assert 'SUBSYSTEM=="power_supply"' in r
    assert 'ENV{POWER_SUPPLY_TYPE}=="Mains"' in r
    assert 'ACTION=="change"' in r


def test_sleep_policy_udev_rule_uses_restart_not_systemd_wants():
    # REGRESSION GUARD (adversary-found bug): SYSTEMD_WANTS added on a `change` event
    # is IGNORED for an already-active .device unit (systemd only acts on Wants= at
    # first activation), so the oneshot would run once at boot and NEVER re-arm on
    # plug/unplug. The rule must instead `systemctl restart` the oneshot (runs it
    # unconditionally every time) with --no-block (never stall udev).
    r = system.SLEEP_POLICY_UDEV_RULE
    assert 'RUN+="/usr/bin/systemctl --no-block restart azarch-sleep-policy.service"' in r
    # The broken mechanism must be gone.
    assert "SYSTEMD_WANTS" not in r
    # `restart` (not `start`) so a oneshot in inactive/dead state is re-run each time.
    assert "restart" in r
    assert "--no-block" in r

