"""Tests for the headless product line.

Two guarantees: (1) the headless pacstrap manifest is the full manifest minus the
GUI stack -- no X11/OpenBox/Calamares/apps, but every base/console capability AND
the whole GPU/compute driver stack retained; (2) the headed manifest is
byte-for-byte the manifest's own package lines, so the headed line is unchanged by
the split.
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


# Base/console packages the headless line MUST keep (headless install + operation).
HEADLESS_MUST_KEEP = (
    "base", "linux", "linux-firmware", "mkinitcpio", "grub", "efibootmgr",
    "networkmanager", "openssh", "sudo", "gnupg", "ufw", "vim", "nano",
    "rsync", "squashfs-tools", "parted", "gptfdisk", "cryptsetup", "lvm2",
    "dosfstools", "e2fsprogs", "btrfs-progs", "ntfs-3g", "python", "git",
)

# The GPU / COMPUTE driver stack MUST STAY on headless (Decision 2: a headless box may
# be an AI/compute server needing CUDA/ROCm/Vulkan-compute even with no display).
HEADLESS_MUST_KEEP_GPU = (
    "mesa", "dkms", "nvidia-open-dkms", "nvidia-utils", "cuda", "opencl-nvidia",
    "vulkan-icd-loader", "vulkan-radeon", "vulkan-intel", "rocm-opencl-runtime",
    "rocm-hip-runtime", "intel-compute-runtime", "xf86-video-amdgpu", "clinfo",
)

# GUI packages the headless line MUST NOT ship.
HEADLESS_MUST_DROP = (
    "xorg-server", "xorg-xinit", "openbox", "picom", "feh", "kitty",
    "calamares", "kpmcore", "qt6-base", "gtk3", "librewolf", "libreoffice-fresh",
    "vlc", "gedit", "gimp", "thunar", "xviewer", "qalculate-gtk",
    "adwaita-icon-theme", "ttf-dejavu", "xclip", "xdotool", "spice-vdagent",
)


def test_headed_manifest_is_the_full_manifest():
    assert pm.manifest_for(is_gui=True) == downloader.manifest_packages()


def test_headless_manifest_drops_only_the_excluded_set():
    full = downloader.manifest_packages()
    headless = pm.manifest_for(is_gui=False)
    dropped = set(full) - set(headless)
    # exactly the HEADLESS_EXCLUDED names that were actually present in the manifest
    assert dropped == (pm.HEADLESS_EXCLUDED & set(full))


def test_headless_keeps_console_essentials():
    headless = set(pm.manifest_for(is_gui=False))
    for pkg in HEADLESS_MUST_KEEP:
        assert pkg in headless, f"headless manifest dropped essential {pkg!r}"


def test_headless_keeps_the_gpu_compute_stack():
    # Decision 2: the ENTIRE GPU/compute driver block stays on headless.
    headless = set(pm.manifest_for(is_gui=False))
    manifest = set(downloader.manifest_packages())
    for pkg in HEADLESS_MUST_KEEP_GPU:
        # only assert on GPU packages the manifest actually ships
        if pkg in manifest:
            assert pkg in headless, f"headless manifest dropped GPU/compute {pkg!r}"
        # and none of them may be in the exclusion set
        assert pkg not in pm.HEADLESS_EXCLUDED, f"{pkg!r} must NOT be excluded on headless"


def test_headless_drops_gui_stack():
    headless = set(pm.manifest_for(is_gui=False))
    for pkg in HEADLESS_MUST_DROP:
        assert pkg not in headless, f"headless manifest leaked GUI package {pkg!r}"


def test_excluded_entries_are_real_manifest_packages():
    # A typo here would silently fail to filter (and would wrongly ship on headless).
    manifest = set(downloader.manifest_packages())
    unknown = sorted(p for p in pm.HEADLESS_EXCLUDED if p not in manifest)
    assert unknown == [], f"HEADLESS_EXCLUDED names not in the manifest (typos?): {unknown}"


def test_legacy_desktop_only_alias_still_points_at_the_exclusion_set():
    assert pm.DESKTOP_ONLY is pm.HEADLESS_EXCLUDED


def test_headless_manifest_preserves_order():
    # The kept packages appear in the same relative order as the source manifest.
    full = downloader.manifest_packages()
    headless = pm.manifest_for(is_gui=False)
    assert headless == [p for p in full if p in set(headless)]


def test_manifest_text_has_trailing_newline_and_no_comments():
    txt = pm.manifest_text_for(is_gui=False)
    assert txt.endswith("\n")
    assert "#" not in txt  # package names never contain '#'; comments are stripped
    # round-trips back to the same list
    assert txt.split() == pm.manifest_for(is_gui=False)


# --- headless airootfs: the GUI emits are skipped ---------------------------


def test_build_line_guards_gui_emits_behind_is_gui():
    # _build_line emits the whole desktop stack (openbox/apps/calamares/tty1-startx) ONLY
    # when is_gui. Assert the guard exists and the GUI emit calls sit under it, so a headless
    # airootfs ships no X session. (Full execution needs the whole build stack; the guard is
    # the load-bearing contract.)
    src = inspect.getsource(compiler._build_line)
    assert "is_gui = line == _variants.LINE_HEADED" in src
    assert "if is_gui:" in src
    # the GUI-only emitters are referenced (under the guard)
    for call in ("_emit_desktop(", "_emit_apps(", "_emit_calamares("):
        assert call in src, f"{call} must still be emitted for the headed line"
    # the pacstrap manifest is the per-line filtered one, not the verbatim file
    assert "packages_manifest.manifest_text_for(is_gui)" in src
    # the customize hook drops the app overrides on the headless line
    assert "if is_gui else" in src


def test_tty1_autologin_is_universal_not_gui_gated():
    # The tty1 autologin-`main` drop-in is emitted on BOTH lines (headless lands on a plain
    # console shell; headed's bash_profile then execs startx). So the _emit_tty1_autologin
    # call must sit OUTSIDE the is_gui block -- verify by position relative to `if is_gui:`.
    src = inspect.getsource(compiler._build_line)
    autologin_at = src.index("_emit_tty1_autologin(")
    guard_at = src.index("if is_gui:")
    assert autologin_at < guard_at, "tty1 autologin must be emitted for both lines (pre-guard)"


def test_link_services_drops_gui_only_units_on_headless():
    # _link_services(is_gui=False) keeps every universal daemon and drops ONLY the GUI-only
    # units (the timedate Flask service and the SPICE guest-agent daemon), whose packages the
    # headless line excludes -- enabling them there would dangle. Behavioural: compare the
    # enable-links written for each line.
    def links(is_gui: bool) -> set[str]:
        airootfs = Path(tempfile.mkdtemp()) / "airootfs"
        compiler._link_services(airootfs, is_gui=is_gui)
        wants = airootfs / "etc/systemd/system/multi-user.target.wants"
        return {p.name for p in wants.iterdir()}

    headless, headed = links(False), links(True)
    assert headed - headless == {"azarch-timedate.service", "spice-vdagentd.service"}
    # universal daemons present on BOTH
    for svc in ("NetworkManager.service", "org.cups.cupsd.service",
                "pkgs-setup.service", "locale-setup.service",
                "azarch-sleep-policy.service", "home-main-shared.mount"):
        assert svc in headless and svc in headed


def test_run_recomputes_offline_and_loops_lines():
    # run() builds one airootfs per DISTINCT line and recomputes the offline verdict per
    # line (so the first line warms the shared cache and later lines build offline).
    src = inspect.getsource(compiler.run)
    assert "_lines_in(build_variants)" in src
    assert "cache_is_complete()" in src
    assert "_build_line(" in src


def test_lines_in_orders_headed_before_headless():
    allv = variants.selected_variants(headless=True, instant=True, ssh=True)
    assert compiler._lines_in(allv) == ("headed", "headless")
    # headless-only selection still starts from headed (base point is always headed)
    assert compiler._lines_in(variants.selected_variants(headless=True)) == ("headed", "headless")


def test_headless_chroot_omits_the_openbox_cleanup():
    # REGRESSION: the chroot-setup OpenBox cleanup `cp`s /usr/local/share/azarch/
    # openbox-autostart-installed under `set -e`. That file is staged ONLY by _emit_desktop,
    # so on a headless install it does not exist and the cp would abort the whole install. The
    # headless chroot script must therefore NOT reference it (nor the installer .desktop it also
    # strips), while the headed chroot script still does.
    headless = installer.chroot_setup_sh(is_gui=False)
    headed = installer.chroot_setup_sh(is_gui=True)
    assert "openbox-autostart-installed" not in headless
    assert "azarch-install.desktop" not in headless
    # headed still performs the cleanup (unchanged behaviour)
    assert "openbox-autostart-installed" in headed
    # both still reach the clean-completion message
    assert "disk installation complete" in headless and "disk installation complete" in headed


def test_build_line_threads_is_gui_into_chroot_setup():
    # _build_line must pass is_gui to chroot_setup_sh so the headless line gets the cleanup-free
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
