"""azarch.config.profile -- profiledef.sh (the archiso profile mkarchiso sources).

The file_permissions map is load-bearing: archiso NORMALIZES overlay file modes
when it packs the squashfs, so any path that must stay executable in the live ISO
MUST have an explicit entry here. The azarch-install launcher losing its 0755
entry is called out in the source as "THIS is what breaks the live installer" --
so it gets a dedicated regression test.
"""

from __future__ import annotations

import re

from azarch.config import profile


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
