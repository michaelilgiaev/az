"""modifications.profile -- profiledef.sh (the archiso profile mkarchiso sources).

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
    from packages.timedate import timedate
    launcher = timedate.LAUNCHER_SYSTEM_PATH
    assert launcher == "/usr/local/bin/azarch-timedate"
    assert profile.FILE_PERMISSIONS[launcher] == "0:0:755"
    assert f'["{launcher}"]="0:0:755"' in profile.profiledef_sh()


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
