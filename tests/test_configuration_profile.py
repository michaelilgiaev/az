"""profile.py -- profiledef.sh (the archiso profile mkarchiso sources).

The file_permissions map is load-bearing: archiso NORMALIZES overlay file modes
when it packs the squashfs, so any path that must stay executable in the live ISO
MUST have an explicit entry here. The azarch-install launcher losing its 0755
entry is called out in the source as "THIS is what breaks the live installer" --
so it gets a dedicated regression test.
"""

from __future__ import annotations

import re

import profile


def test_profiledef_is_a_bash_script():
    sh = profile.profiledef_sh()
    assert sh.startswith("#!/usr/bin/env bash")


def test_iso_identity_fields_present():
    sh = profile.profiledef_sh()
    assert f'iso_name="{profile.ISO_NAME}"' in sh
    assert f'install_dir="{profile.INSTALL_DIR}"' in sh
    assert 'arch="x86_64"' in sh
    assert "airootfs_image_type=\"squashfs\"" in sh


def test_all_bootmodes_are_quoted_in_the_array():
    sh = profile.profiledef_sh()
    for mode in profile.BOOTMODES:
        assert f"'{mode}'" in sh


def test_every_file_permission_entry_is_emitted():
    sh = profile.profiledef_sh()
    for path, mode in profile.FILE_PERMISSIONS.items():
        assert f'["{path}"]="{mode}"' in sh


def test_calamares_launcher_stays_executable():
    # Regression guard for the exact bug in the source comment: if this entry is
    # dropped or its mode drifts from 755, the autostart's `[ -x ... ]` guard is
    # false and Calamares never launches on the live ISO.
    assert profile.FILE_PERMISSIONS["/usr/local/bin/azarch-install"] == "0:0:755"
    assert '["/usr/local/bin/azarch-install"]="0:0:755"' in profile.profiledef_sh()


def test_ckbcomp_stays_executable():
    # The vendored ckbcomp (Python port) must keep its exec bit through archiso's mode
    # normalization, or Calamares cannot run it and the keyboard preview is blank.
    assert profile.FILE_PERMISSIONS["/usr/bin/ckbcomp"] == "0:0:755"
    assert '["/usr/bin/ckbcomp"]="0:0:755"' in profile.profiledef_sh()


def test_headless_profile_omits_headed_only_permissions():
    # THE HEADLESS-BUILD FIX: the headless line ships no GUI, so it never plants Calamares'
    # vendored ckbcomp (nor the OpenBox/desktop launchers). archiso's file_permissions
    # pass chmods every listed path and FAILS the whole build ("Failed to set permissions
    # on .../usr/bin/ckbcomp. Outside of valid path.") if a path is absent from the
    # airootfs. So the headless profiledef must NOT list any headed-only path.
    from variants import Variant

    headless = Variant(line="headless")
    sh = profile.profiledef_sh(headless)
    # The exact path that broke the headless ISO must be gone from the headless profile...
    assert '["/usr/bin/ckbcomp"]' not in sh
    # ...along with every other headed-only launcher/daemon (a representative sample).
    for gone in (
        "/usr/bin/ckbcomp",
        "/usr/local/bin/azarch-install",
        "/usr/local/bin/azarch-application-menu",
        "/usr/local/bin/azarch-timedate",
        "/usr/local/bin/passwords",
        "/home/main/.config/openbox/autostart",
        "/home/main/Desktop/azarch-install.desktop",
    ):
        assert f'["{gone}"]' not in sh, gone
    # But the universal, non-GUI entries the headless line DOES plant stay pinned.
    assert '["/etc/shadow"]="0:0:400"' in sh
    assert '["/etc/sudoers.d/00-main"]="0:0:440"' in sh
    assert '["/usr/local/bin/choose-mirror"]="0:0:755"' in sh
    assert '["/root/azarch/setup-locale.sh"]="0:0:755"' in sh


def test_permissions_for_headless_line_string_drops_headed_only():
    # Footgun guard: permissions_for must key off the LINE, not fall back to headed.
    # variants.coerce("headless") now maps the bare line name to Variant(line="headless")
    # (is_gui=False). Before that hardening it slipped through from_legacy_key's
    # unknown-key default to the headed base point (is_gui=True), so permissions_for
    # returned the FULL headed map (with ckbcomp) and would resurrect the exact
    # headless-build abort. The headless profile must omit ckbcomp whether it is asked for
    # via Variant(line="headless") OR the string "headless".
    perms = profile.permissions_for("headless")
    assert "/usr/bin/ckbcomp" not in perms
    assert "/usr/local/bin/azarch-install" not in perms
    # ...and the universal entries still survive.
    assert perms["/etc/shadow"] == "0:0:400"
    assert perms["/usr/local/bin/choose-mirror"] == "0:0:755"


def test_headed_profile_keeps_headed_only_permissions():
    # The headed line is unchanged by the headless split: every headed-only path it
    # actually plants must still be pinned (a regression guard so the split does not
    # accidentally strip the GUI line too). No-arg profiledef_sh() defaults to headed.
    from variants import Variant

    headed = Variant(line="headed")
    sh = profile.profiledef_sh(headed)
    for present in (
        "/usr/bin/ckbcomp",
        "/usr/local/bin/azarch-install",
        "/usr/local/bin/azarch-application-menu",
        "/usr/local/bin/passwords",
        "/home/main/.config/openbox/autostart",
    ):
        assert f'["{present}"]="' in sh, present
    # The no-arg default and the explicit headed variant agree.
    assert sh == profile.profiledef_sh()


def test_application_menu_launcher_stays_executable():
    # Regression guard for the "panel icon does nothing" bug: the menu launcher the
    # org.kde.plasma.icon backing .desktop Exec's must keep its 0755 through archiso's
    # squashfs mode normalization. Without this pin it ships 0644 (non-executable), so
    # clicking the icon runs a non-executable file and the menu never opens. The path
    # must match application_menu.MENU_LAUNCHER_SYSTEM_PATH (the Exec target).
    from packages.application_menu import application_menu
    launcher = application_menu.MENU_LAUNCHER_SYSTEM_PATH
    assert launcher == "/usr/local/bin/azarch-application-menu"
    assert profile.FILE_PERMISSIONS[launcher] == "0:0:755"
    assert f'["{launcher}"]="0:0:755"' in profile.profiledef_sh()


def test_timedate_launcher_stays_executable():
    # Regression guard for the "home page lands on a dead port" bug (hit on the built
    # ISO): azarch-timedate.service ExecStart's this launcher, but archiso's squashfs
    # normalizes the overlay mode to 0644 unless the path is pinned here -- and a 0644
    # launcher makes systemd fail the unit with status=203/EXEC (Permission denied), so
    # nothing listens on 49154 and LibreWolf's home/new tab shows a dead page. The path
    # must match timedate.LAUNCHER_SYSTEM_PATH (the ExecStart target).
    from packages.librewolf import timedate
    launcher = timedate.LAUNCHER_SYSTEM_PATH
    assert launcher == "/usr/local/bin/azarch-timedate"
    assert profile.FILE_PERMISSIONS[launcher] == "0:0:755"
    assert f'["{launcher}"]="0:0:755"' in profile.profiledef_sh()


def test_passwords_launcher_stays_executable():
    # Regression guard for "typing `passwords` says Permission denied": the `passwords`
    # command (the encrypted terminal password manager) is /usr/local/bin/passwords, but
    # archiso's squashfs normalizes the overlay mode to 0644 unless the path is pinned
    # here -- and a 0644 launcher cannot be exec'd by the shell, so the command fails on
    # BOTH the live ISO and the installed system (the whole feature is dead). The path
    # must match packaging.LAUNCHER_SYSTEM_PATH (the command the user types).
    from packages.passwords import packaging as passwords
    launcher = passwords.LAUNCHER_SYSTEM_PATH
    assert launcher == "/usr/local/bin/passwords"
    assert profile.FILE_PERMISSIONS[launcher] == "0:0:755"
    assert f'["{launcher}"]="0:0:755"' in profile.profiledef_sh()


def test_window_switcher_launcher_stays_executable():
    # Regression guard for "Alt+Tab pops an OpenBox 'Permission denied' dialog": the
    # window-switcher launcher is /usr/local/bin/azarch-window-switcher, run by OpenBox's
    # A-Tab/A-S-Tab <action name="Execute">. archiso's squashfs normalizes the overlay mode
    # to 0644 unless the path is pinned here -- and a 0644 launcher makes OpenBox's /bin/sh
    # -c fail with "Permission denied", which OpenBox surfaces as an error popup instead of
    # the overlay. The path must match window_switcher.SWITCHER_LAUNCHER_SYSTEM_PATH (the
    # rc.xml Execute target).
    from packages.window_switcher import window_switcher
    launcher = window_switcher.SWITCHER_LAUNCHER_SYSTEM_PATH
    assert launcher == "/usr/local/bin/azarch-window-switcher"
    assert profile.FILE_PERMISSIONS[launcher] == "0:0:755"
    assert f'["{launcher}"]="0:0:755"' in profile.profiledef_sh()


def test_window_switcher_daemon_stays_executable():
    # Same archiso mode-normalization as the menu daemon: the COMPILED switcher daemon is
    # started from the OpenBox autostart, whose `[ -x ... ]` guard skips a non-executable
    # binary -- so a 0644 daemon is never pre-built and the first Alt+Tab starts nothing.
    # The path must match window_switcher.SWITCHER_DAEMON_BIN_SYSTEM_PATH (the autostart
    # target).
    from packages.window_switcher import window_switcher
    daemon = window_switcher.SWITCHER_DAEMON_BIN_SYSTEM_PATH
    assert daemon == "/usr/local/lib/azarch-window-switcher/azarch-window-switcher-daemon"
    assert profile.FILE_PERMISSIONS[daemon] == "0:0:755"
    assert f'["{daemon}"]="0:0:755"' in profile.profiledef_sh()


def test_desktop_installer_launcher_stays_executable():
    # THE WARNING-BADGE FIX: KDE paints an "emblem-important" warning badge over a
    # Desktop .desktop launcher (and prompts on first launch) unless it is executable
    # (KDesktopFile::isAuthorizedDesktopFile). compiler.py emits it 0755, but archiso
    # normalizes overlay modes to 0644 in the squashfs unless pinned here -- which is
    # exactly why the badge appeared. Pin both the live-user copy (uid 1000:998) and
    # the /etc/skel copy (root-owned) to 0755 so the shipped launcher is trusted.
    assert (
        profile.FILE_PERMISSIONS["/home/main/Desktop/azarch-install.desktop"]
        == "1000:998:755"
    )
    assert (
        profile.FILE_PERMISSIONS["/etc/skel/Desktop/azarch-install.desktop"]
        == "0:0:755"
    )
    sh = profile.profiledef_sh()
    assert '["/home/main/Desktop/azarch-install.desktop"]="1000:998:755"' in sh
    assert '["/etc/skel/Desktop/azarch-install.desktop"]="0:0:755"' in sh


def test_openbox_autostart_stays_executable():
    # The OpenBox session autostart (~/.config/openbox/autostart) is run by
    # openbox-session and carries a shebang; desktop.PLAN emits it 0o755. archiso
    # normalizes home files to 0644 in the squashfs unless pinned here, so without
    # these pins the shipped autostart would be non-executable. Both the live-user copy
    # and the /etc/skel copy must be 0755. (The old Plasma org.kde.plasma.icon backing
    # .desktop pins were removed -- there is no panel applet under OpenBox.)
    live = "/home/main/.config/openbox/autostart"
    skel = "/etc/skel/.config/openbox/autostart"
    assert profile.FILE_PERMISSIONS[live] == "1000:998:755"
    assert profile.FILE_PERMISSIONS[skel] == "0:0:755"
    sh = profile.profiledef_sh()
    assert f'["{live}"]="1000:998:755"' in sh
    assert f'["{skel}"]="0:0:755"' in sh
    # The stale Plasma plasma_icons backing-file pins must be GONE.
    assert not any("plasma_icons" in p for p in profile.FILE_PERMISSIONS)


def test_secrets_locked_down():
    # shadow/gshadow/sudoers must not ship world-readable.
    assert profile.FILE_PERMISSIONS["/etc/shadow"] == "0:0:400"
    assert profile.FILE_PERMISSIONS["/etc/gshadow"] == "0:0:400"
    assert profile.FILE_PERMISSIONS["/etc/sudoers.d/00-main"] == "0:0:440"


def test_file_permission_modes_are_well_formed():
    # Every value is owner:group:octal.
    for mode in profile.FILE_PERMISSIONS.values():
        assert re.fullmatch(r"\d+:\d+:[0-7]{3,4}", mode), mode


def test_zstd_squashfs_workaround_present():
    # The xz-error-code-9 workaround pins zstd; losing it resurrects the sporadic
    # "xz uncompress failed" build failure.
    sh = profile.profiledef_sh()
    assert "'-comp' 'zstd'" in sh
