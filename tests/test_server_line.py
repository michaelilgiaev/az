"""Tests for the headless SERVER product line.

Two guarantees: (1) the server pacstrap manifest is the full manifest minus the
GUI stack -- no X11/OpenBox/Calamares/apps, but every base/console capability
retained; (2) the desktop manifest is byte-for-byte the manifest's own package
lines, so the desktop line is unchanged by the split.
"""

from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

import compiler
import downloader
import installer
import packages_manifest as pm
import variants


# Base/console packages a server MUST keep (headless install + operation).
SERVER_MUST_KEEP = (
    "base", "linux", "linux-firmware", "mkinitcpio", "grub", "efibootmgr",
    "networkmanager", "openssh", "sudo", "gnupg", "ufw", "vim", "nano",
    "rsync", "squashfs-tools", "parted", "gptfdisk", "cryptsetup", "lvm2",
    "dosfstools", "e2fsprogs", "btrfs-progs", "ntfs-3g", "python", "git",
)

# GUI packages a server MUST NOT ship.
SERVER_MUST_DROP = (
    "xorg-server", "xorg-xinit", "openbox", "picom", "feh", "kitty",
    "calamares", "kpmcore", "qt6-base", "gtk3", "librewolf", "libreoffice-fresh",
    "vlc", "gedit", "gimp", "thunar", "xviewer", "qalculate-gtk",
    "adwaita-icon-theme", "ttf-dejavu", "xclip", "xdotool",
)


def test_desktop_manifest_is_the_full_manifest():
    assert pm.manifest_for(is_gui=True) == downloader.manifest_packages()


def test_server_manifest_drops_only_desktop_only():
    full = downloader.manifest_packages()
    server = pm.manifest_for(is_gui=False)
    dropped = set(full) - set(server)
    # exactly the DESKTOP_ONLY names that were actually present in the manifest
    assert dropped == (pm.DESKTOP_ONLY & set(full))


def test_server_keeps_console_essentials():
    server = set(pm.manifest_for(is_gui=False))
    for pkg in SERVER_MUST_KEEP:
        assert pkg in server, f"server manifest dropped essential {pkg!r}"


def test_server_drops_gui_stack():
    server = set(pm.manifest_for(is_gui=False))
    for pkg in SERVER_MUST_DROP:
        assert pkg not in server, f"server manifest leaked GUI package {pkg!r}"


def test_desktop_only_entries_are_real_manifest_packages():
    # A typo here would silently fail to filter (and would wrongly ship on server).
    manifest = set(downloader.manifest_packages())
    unknown = sorted(p for p in pm.DESKTOP_ONLY if p not in manifest)
    assert unknown == [], f"DESKTOP_ONLY names not in the manifest (typos?): {unknown}"


def test_server_manifest_preserves_order():
    # The kept packages appear in the same relative order as the source manifest.
    full = downloader.manifest_packages()
    server = pm.manifest_for(is_gui=False)
    assert server == [p for p in full if p in set(server)]


def test_manifest_text_has_trailing_newline_and_no_comments():
    txt = pm.manifest_text_for(is_gui=False)
    assert txt.endswith("\n")
    assert "#" not in txt  # package names never contain '#'; comments are stripped
    # round-trips back to the same list
    assert txt.split() == pm.manifest_for(is_gui=False)


# --- server airootfs: the GUI emits are skipped -----------------------------


def test_build_line_guards_gui_emits_behind_is_gui():
    # _build_line emits the whole desktop stack (openbox/apps/calamares/tty1-startx) ONLY
    # when is_gui. Assert the guard exists and the GUI emit calls sit under it, so a server
    # airootfs ships no X session. (Full execution needs the whole build stack; the guard is
    # the load-bearing contract.)
    src = inspect.getsource(compiler._build_line)
    assert "is_gui = line == _variants.LINE_DESKTOP" in src
    assert "if is_gui:" in src
    # the GUI-only emitters are referenced (under the guard)
    for call in ("_emit_desktop(", "_emit_apps(", "_emit_calamares("):
        assert call in src, f"{call} must still be emitted for the desktop line"
    # the pacstrap manifest is the per-line filtered one, not the verbatim file
    assert "packages_manifest.manifest_text_for(is_gui)" in src
    # the customize hook drops the app overrides on the server line
    assert "if is_gui else" in src


def test_tty1_autologin_is_universal_not_gui_gated():
    # The tty1 autologin-`main` drop-in is emitted on BOTH lines (server lands on a plain
    # console shell; desktop's bash_profile then execs startx). So the _emit_tty1_autologin
    # call must sit OUTSIDE the is_gui block -- verify by position relative to `if is_gui:`.
    src = inspect.getsource(compiler._build_line)
    autologin_at = src.index("_emit_tty1_autologin(")
    guard_at = src.index("if is_gui:")
    assert autologin_at < guard_at, "tty1 autologin must be emitted for both lines (pre-guard)"


def test_link_services_drops_only_timedate_on_server():
    # _link_services(is_gui=False) keeps every universal daemon and drops ONLY the desktop
    # timedate Flask service (its unit is desktop-emitted; enabling it on a server would
    # dangle). Behavioural: compare the enable-links written for each line.
    def links(is_gui: bool) -> set[str]:
        airootfs = Path(tempfile.mkdtemp()) / "airootfs"
        compiler._link_services(airootfs, is_gui=is_gui)
        wants = airootfs / "etc/systemd/system/multi-user.target.wants"
        return {p.name for p in wants.iterdir()}

    server, desktop = links(False), links(True)
    assert desktop - server == {"azarch-timedate.service"}
    # universal daemons present on BOTH
    for svc in ("NetworkManager.service", "org.cups.cupsd.service",
                "pkgs-setup.service", "locale-setup.service",
                "azarch-sleep-policy.service", "home-main-shared.mount"):
        assert svc in server and svc in desktop


def test_run_recomputes_offline_and_loops_lines():
    # run() builds one airootfs per DISTINCT line and recomputes the offline verdict per
    # line (so the first line warms the shared cache and later lines build offline).
    src = inspect.getsource(compiler.run)
    assert "_lines_in(build_variants)" in src
    assert "cache_is_complete()" in src
    assert "_build_line(" in src


def test_lines_in_orders_desktop_before_server():
    allv = variants.selected_variants(server=True, instant=True, ssh=True)
    assert compiler._lines_in(allv) == ("desktop", "server")
    # server-only selection still starts from desktop (base point is always desktop)
    assert compiler._lines_in(variants.selected_variants(server=True)) == ("desktop", "server")


def test_server_chroot_omits_the_desktop_openbox_cleanup():
    # REGRESSION: the chroot-setup OpenBox cleanup `cp`s /usr/local/share/azarch/
    # openbox-autostart-installed under `set -e`. That file is staged ONLY by _emit_desktop,
    # so on a server install it does not exist and the cp would abort the whole install. The
    # server chroot script must therefore NOT reference it (nor the installer .desktop it also
    # strips), while the desktop chroot script still does.
    server = installer.chroot_setup_sh(is_gui=False)
    desktop = installer.chroot_setup_sh(is_gui=True)
    assert "openbox-autostart-installed" not in server
    assert "azarch-install.desktop" not in server
    # desktop still performs the cleanup (unchanged behaviour)
    assert "openbox-autostart-installed" in desktop
    # both still reach the clean-completion message
    assert "disk installation complete" in server and "disk installation complete" in desktop


def test_build_line_threads_is_gui_into_chroot_setup():
    # _build_line must pass is_gui to chroot_setup_sh so the server gets the cleanup-free
    # variant (the bug above was that chroot-setup was emitted identically for both lines).
    src = inspect.getsource(compiler._build_line)
    assert "chroot_setup_sh(is_gui=is_gui)" in src


def test_own_packages_built_once_then_reused_across_lines():
    # The calamares/librewolf build (step 13) is line-independent: run() builds it on the
    # FIRST line and passes own_packages_ready=True to later lines so they skip the (possibly
    # multi-hour --full-compile) rebuild and just re-stage the shared repo.
    run_src = inspect.getsource(compiler.run)
    assert "own_packages_ready = False" in run_src
    assert "own_packages_ready = True" in run_src            # flipped after the first line
    line_src = inspect.getsource(compiler._build_line)
    assert "if own_packages_ready:" in line_src
    assert "build_own_packages(" in line_src                 # still built when not ready
    # the milestone + the cheap re-stage run every line regardless (step count stays stable)
    assert "_refold_own_packages_into_repo(W" in line_src
