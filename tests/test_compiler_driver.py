"""Cross-cutting invariants for the build driver.

compiler.STEP_WEIGHTS must stay in lockstep with the number of bar.step() calls in
compiler.run() -- the source itself says "len(STEP_WEIGHTS) - 1 MUST equal the number
of bar.step() calls in run()". If they drift, the progress bar mis-weights and the
final "[ N/N ]" count is wrong. We count the calls from the actual source of run()
so adding/removing a step without updating the weights fails this test.

compiler.cache_is_complete() is the pure cache-first predicate; it reads only
paths.* and one env var, all monkeypatchable.
"""

from __future__ import annotations

import inspect

import compiler
import paths


def test_ckbcomp_asset_is_vendored_python_script():
    # Calamares' keyboard preview shells out to `ckbcomp` to render key legends;
    # Arch does not package it, so we vendor it as a modification directory module
    # (libraries/modifications/ckbcomp/, script at ckbcomp/ckbcomp.py) -- upstream software
    # modified to fit Az'arch. It is a Python 3 port of the upstream Perl ckbcomp (byte-
    # identical output, but no Perl in the tree). It must exist and be that Python script
    # (not an empty placeholder).
    src = paths.CKBCOMP_SRC
    assert src.is_file(), "libraries/modifications/ckbcomp/ckbcomp.py is missing"
    head = src.read_text(errors="ignore")[:200]
    assert head.startswith("#!/usr/bin/env python3")
    assert "ckbcomp" in head  # the script's own banner names itself


def test_run_installs_ckbcomp_into_usr_bin():
    # run() must plant the vendored ckbcomp at /usr/bin/ckbcomp (executable) so the
    # keyboard preview finds it. Assert the copy_modification_file call is present in run().
    src = inspect.getsource(compiler.run)
    assert 'copy_modification_file("ckbcomp/ckbcomp.py"' in src
    assert 'usr/bin/ckbcomp' in src


def test_emit_calamares_ships_the_window_icon_into_branding():
    # The installer's WINDOW ICON (the "Az'" tile OpenBox draws on the titlebar) is the
    # branding productIcon: a real PNG copied INTO branding/azarch/. Assert _emit_calamares
    # copies the standardized installer icon asset to the branding productIcon file, so the
    # topbar icon exists and matches the launcher icon.
    from packages.calamares import calamares
    from modifications import openbox

    src = inspect.getsource(compiler._emit_calamares)
    # The productIcon is rasterized from the standardized SVG master to a real PNG
    # (Calamares' QIcon loads a raster file directly).
    assert "render_svg_png" in src
    assert "INSTALLER_ICON_ASSET" in src
    assert "PRODUCT_ICON_FILE" in src
    # The branding.desc names that same file in productIcon.
    assert calamares.PRODUCT_ICON_FILE == "productIcon.png"
    assert openbox.INSTALLER_ICON_ASSET == "icons/azarch.svg"


# --- power management emission + enablement (Tasks 1 & 2) -------------------

def test_run_calls_emit_power():
    # run() must emit the power-management files (lid/button + PC/laptop idle sleep).
    src = inspect.getsource(compiler.run)
    assert "_emit_power(airootfs)" in src


def test_emit_power_writes_all_four_artifacts(tmp_path):
    # BEHAVIORAL: _emit_power lays down the four root-owned power files under a fresh
    # airootfs -- the static logind drop-in, the sleep-policy script (executable), its
    # service, and the udev rule. These reach the installed system via unpackfs.
    import system

    airootfs = tmp_path / "airootfs"
    compiler._emit_power(airootfs)

    dropin = airootfs / "etc/systemd/logind.conf.d/10-azarch-power.conf"
    script = airootfs / "usr/local/bin/azarch-sleep-policy"
    service = airootfs / "etc/systemd/system/azarch-sleep-policy.service"
    udev = airootfs / "etc/udev/rules.d/99-azarch-sleep-policy.rules"

    assert dropin.read_text() == system.LOGIND_POWER_DROPIN
    assert script.read_text() == system.SLEEP_POLICY_SCRIPT
    assert service.read_text() == system.SLEEP_POLICY_SERVICE
    assert udev.read_text() == system.SLEEP_POLICY_UDEV_RULE
    # The policy script must be executable (a service ExecStart on a non-exec file
    # would fail to run).
    import os
    import stat
    assert os.stat(script).st_mode & stat.S_IXUSR


def test_link_services_enables_sleep_policy(tmp_path):
    # BEHAVIORAL: _link_services must create the multi-user.target.wants symlink that
    # enables azarch-sleep-policy.service on boot (both ISOs + installed system).
    airootfs = tmp_path / "airootfs"
    (airootfs / "etc/systemd/system").mkdir(parents=True)
    compiler._link_services(airootfs)

    link = (airootfs / "etc/systemd/system/multi-user.target.wants"
            / "azarch-sleep-policy.service")
    assert link.is_symlink()
    import os
    assert os.readlink(link) == "/etc/systemd/system/azarch-sleep-policy.service"


def test_link_services_enables_spice_vdagentd(tmp_path):
    # BEHAVIORAL: _link_services must enable spice-vdagentd -- the SPICE guest agent daemon that
    # bridges the com.redhat.spice.0 channel so the session spice-vdagent can sync the guest
    # pointer with the SPICE client. This is the fix for the SPICE-guest pointer regression (no
    # hover / dropped clicks / stuck labels); without the daemon the agent has nothing to talk
    # to. Enabled on both ISOs + (via unpackfs) the installed system.
    import os
    airootfs = tmp_path / "airootfs"
    (airootfs / "etc/systemd/system").mkdir(parents=True)
    compiler._link_services(airootfs)
    link = (airootfs / "etc/systemd/system/multi-user.target.wants"
            / "spice-vdagentd.service")
    assert link.is_symlink()
    assert os.readlink(link) == "/usr/lib/systemd/system/spice-vdagentd.service"


def test_run_calls_emit_homedir():
    # run() must create the home-directory layout (folders + convenience symlinks) between
    # the desktop overlay and the app overlay, so _emit_apps's closing chown covers it.
    src = inspect.getsource(compiler.run)
    assert "_emit_homedir(airootfs, home)" in src


def test_emit_homedir_creates_layout_in_home_and_skel(tmp_path):
    # BEHAVIORAL: _emit_homedir lays down the top-level folders, the XDG trash chain and the
    # convenience symlinks in BOTH /home/main and /etc/skel (so a Calamares-created user
    # inherits the identical layout). Symlinks must be relative (valid in every home).
    import os

    from modifications import home_directory as hd

    airootfs = tmp_path / "airootfs"
    home = airootfs / "home/main"
    home.mkdir(parents=True)
    (airootfs / "etc/skel").mkdir(parents=True)

    compiler._emit_homedir(airootfs, home)

    for root in (home, airootfs / "etc/skel"):
        # 1. Every top-level directory exists and is a real dir.
        for name in hd.DIRECTORIES:
            assert (root / name).is_dir(), f"missing dir {name} under {root}"
        # 2. The XDG trash chain exists (files + info) so Trash does not dangle.
        for rel in hd.TRASH_DIRS:
            assert (root / rel).is_dir(), f"missing trash dir {rel} under {root}"
        # 3. Every convenience symlink exists, is a symlink, and has a RELATIVE target.
        for name, target in hd.LINKS:
            link = root / name
            assert link.is_symlink(), f"{name} is not a symlink under {root}"
            got = os.readlink(link)
            assert got == target, f"{name} -> {got!r}, expected {target!r}"
            assert not os.path.isabs(got), f"{name} target must be relative: {got!r}"
        # 4. The Trash symlink resolves to a real directory (the chain made it non-dangling).
        assert (root / "Trash").resolve().is_dir()


def test_brand_boot_menus_writes_all_six_boot_files(tmp_path):
    # BEHAVIORAL: _brand_boot_menus lays the rebranded systemd-boot + syslinux menus
    # over a copied releng tree. Assert the exact six files land with our content.
    import system

    W = tmp_path
    compiler._brand_boot_menus(W)

    e01 = W / "efiboot/loader/entries/01-archiso-linux.conf"
    e02 = W / "efiboot/loader/entries/02-archiso-speech-linux.conf"
    loader = W / "efiboot/loader/loader.conf"
    syssys = W / "syslinux/archiso_sys.cfg"
    syscfg = W / "syslinux/archiso_sys-linux.cfg"
    syshead = W / "syslinux/archiso_head.cfg"

    assert e01.read_text() == system.BOOT_UEFI_LINUX
    assert e02.read_text() == system.BOOT_UEFI_SPEECH
    assert loader.read_text() == system.BOOT_UEFI_LOADER
    assert syssys.read_text() == system.BOOT_BIOS_SYSLINUX_SYS
    assert syscfg.read_text() == system.BOOT_BIOS_SYSLINUX
    assert syshead.read_text() == system.BOOT_BIOS_SYSLINUX_HEAD


def test_brand_boot_menus_deletes_releng_memtest_entry(tmp_path):
    # BEHAVIORAL + the crux of the "skip the EFI options" change: the releng Memtest86+
    # entry copied by _copy_releng must be GONE afterwards, leaving only 01/02. (EFI
    # Shell / firmware are auto entries suppressed by loader.conf, tested in
    # test_configuration_system; here we prove the explicit memtest .conf is removed.)
    W = tmp_path
    entries = W / "efiboot/loader/entries"
    entries.mkdir(parents=True)
    memtest = entries / "03-archiso-memtest86+x64.conf"
    memtest.write_text("title    Memtest86+\n")  # stand in for the releng file

    compiler._brand_boot_menus(W)

    assert not memtest.exists(), "releng Memtest86+ entry must be deleted"
    remaining = sorted(p.name for p in entries.glob("*.conf"))
    assert remaining == ["01-archiso-linux.conf", "02-archiso-speech-linux.conf"]


def test_brand_boot_menus_is_idempotent_without_memtest(tmp_path):
    # The memtest deletion uses missing_ok=True so a future releng that renames/drops
    # the entry (nothing to delete) does not crash the compiler. Running against a tree
    # with no memtest entry must succeed and still write the two Az'arch entries.
    W = tmp_path
    compiler._brand_boot_menus(W)  # no pre-existing entries dir at all
    assert (W / "efiboot/loader/entries/01-archiso-linux.conf").exists()
    assert not (W / "efiboot/loader/entries/03-archiso-memtest86+x64.conf").exists()


def test_run_calls_brand_boot_menus():
    # run()'s step 4 must delegate to the helper (guards against the inline block
    # creeping back and diverging from the tested helper).
    src = inspect.getsource(compiler.run)
    assert "_brand_boot_menus(W)" in src


def test_step_weights_match_number_of_steps():
    # run() makes N literal bar.step() calls, but the final one is inside the
    # per-variant finalize loop and executes once per variant (both ISOs are built in
    # one run). So the number of EXECUTED milestones is (N - 1) + len(VARIANTS), and
    # STEP_WEIGHTS must have exactly that many real entries (+ the index-0 sentinel).
    src = inspect.getsource(compiler.run)
    n_calls = src.count("bar.step(")
    executed = (n_calls - 1) + len(compiler.VARIANTS)
    assert len(compiler.STEP_WEIGHTS) - 1 == executed, (
        f"STEP_WEIGHTS has {len(compiler.STEP_WEIGHTS)} entries "
        f"(-> {len(compiler.STEP_WEIGHTS) - 1} steps) but run() executes {executed} "
        f"milestones ({n_calls} literal bar.step() calls, the last once per "
        f"{len(compiler.VARIANTS)} variants)"
    )


def test_step_weights_leading_zero():
    # The first weight is the 0-weight "already at step 0" anchor.
    assert compiler.STEP_WEIGHTS[0] == 0


def test_step_weights_giants_are_last_four():
    # package cache, makepkg, and the TWO mkarchiso passes (one per ISO variant) --
    # the four heavy tail weights. Both ISOs are assembled in a single compiler.
    assert compiler.STEP_WEIGHTS[-4:] == [250, 120, 270, 270]


def test_cache_complete_false_when_index_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("FORCE_ONLINE", "0")
    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", tmp_path / "nope.db")
    assert compiler.cache_is_complete() is False


def test_cache_complete_force_online_overrides(monkeypatch):
    monkeypatch.setenv("FORCE_ONLINE", "1")
    # Even with everything present, FORCE_ONLINE=1 forces a re-fetch.
    assert compiler.cache_is_complete() is False


def test_cache_complete_true_when_all_present(monkeypatch, tmp_path):
    monkeypatch.setenv("FORCE_ONLINE", "0")
    repo = tmp_path / "repo"
    sync = tmp_path / "db" / "sync"
    repo.mkdir(parents=True)
    sync.mkdir(parents=True)
    idx = repo / "pacstrap-azarch-repo.db"
    idx.write_text("")
    (repo / "somepkg-1.0-1-x86_64.pkg.tar.zst").write_text("")
    # OUR OWN built packages must be present too, else the cache is not complete
    # (they are compiled by the makepkg stage, not downloaded). thunar is now one of
    # them (rebuilt from source with the symlink-resolve patch).
    (repo / "calamares-3.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "librewolf-1.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "thunar-4.20.9-2-x86_64.pkg.tar.zst").write_text("")
    (sync / "core.db").write_text("")
    # Every DOWNLOADED manifest package must also have a file in the repo (the
    # coverage clause). Point the manifest at a tiny file whose one entry is
    # present, so completeness turns only on the structural + own-package markers.
    manifest = tmp_path / "packages.x86_64"
    manifest.write_text("# header\nsomepkg\n")

    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(compiler.paths, "PKG_REPO", repo)
    monkeypatch.setattr(compiler.paths, "PKG_SYNC_DB", sync)
    monkeypatch.setattr(compiler.paths, "PACKAGES_FILE", manifest)
    monkeypatch.setattr(compiler.downloader.paths, "PACKAGES_FILE", manifest)
    assert compiler.cache_is_complete() is True


def test_cache_complete_false_when_manifest_package_missing(monkeypatch, tmp_path):
    # The 'target not found' guard: structure + synced DB + BOTH own packages are
    # present, but a package named in packages.x86_64 was never downloaded into the
    # offline repo (exactly what happens right after a new package is added to the
    # manifest). This MUST read as incomplete so the build goes ONLINE and fetches
    # the missing package -- otherwise the offline pacstrap aborts with
    # 'error: target not found: <pkg>'. Regression test for the xorg-xset failure.
    monkeypatch.setenv("FORCE_ONLINE", "0")
    repo = tmp_path / "repo"
    sync = tmp_path / "db" / "sync"
    repo.mkdir(parents=True)
    sync.mkdir(parents=True)
    idx = repo / "pacstrap-azarch-repo.db"
    idx.write_text("")
    (repo / "somepkg-1.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "calamares-3.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "librewolf-1.0-1-x86_64.pkg.tar.zst").write_text("")
    (sync / "core.db").write_text("")
    # Manifest names a second package that has NO file in the repo.
    manifest = tmp_path / "packages.x86_64"
    manifest.write_text("# header\nsomepkg\nxorg-xset\n")

    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(compiler.paths, "PKG_REPO", repo)
    monkeypatch.setattr(compiler.paths, "PKG_SYNC_DB", sync)
    monkeypatch.setattr(compiler.paths, "PACKAGES_FILE", manifest)
    monkeypatch.setattr(compiler.downloader.paths, "PACKAGES_FILE", manifest)
    assert compiler.cache_is_complete() is False


def test_cache_complete_ignores_own_packages_absent_from_repo_files(monkeypatch, tmp_path):
    # The coverage clause must EXCLUDE our own built packages the same way the
    # downloader excludes them from `pacman -Sw`: calamares/librewolf live on no
    # mirror, so their manifest entries must not be counted as "missing downloads"
    # (their presence is already enforced by the own-packages clause via the file
    # they DO get after makepkg). Here calamares is in the manifest AND present as a
    # file, librewolf is in the manifest AND present -- and a plain Arch pkg covers.
    monkeypatch.setenv("FORCE_ONLINE", "0")
    repo = tmp_path / "repo"
    sync = tmp_path / "db" / "sync"
    repo.mkdir(parents=True)
    sync.mkdir(parents=True)
    idx = repo / "pacstrap-azarch-repo.db"
    idx.write_text("")
    (repo / "somepkg-1.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "calamares-3.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "librewolf-1.0-1-x86_64.pkg.tar.zst").write_text("")
    # thunar is an own-built package too (rebuilt from source): in the manifest AND present.
    (repo / "thunar-4.20.9-2-x86_64.pkg.tar.zst").write_text("")
    (sync / "core.db").write_text("")
    manifest = tmp_path / "packages.x86_64"
    manifest.write_text("# header\nsomepkg\ncalamares\nlibrewolf\nthunar\n")

    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(compiler.paths, "PKG_REPO", repo)
    monkeypatch.setattr(compiler.paths, "PKG_SYNC_DB", sync)
    monkeypatch.setattr(compiler.paths, "PACKAGES_FILE", manifest)
    monkeypatch.setattr(compiler.downloader.paths, "PACKAGES_FILE", manifest)
    assert compiler.cache_is_complete() is True


def test_cache_complete_false_when_own_packages_absent(monkeypatch, tmp_path):
    # The deadlock guard: 800+ Arch packages, a valid index, and synced DBs are all
    # present, but calamares/librewolf (compiled, never downloaded) are NOT. This
    # MUST read as an incomplete cache so the build goes ONLINE and compiles them --
    # otherwise the offline path is chosen and makepkg refuses offline, hanging the
    # build forever with nothing to downgrade it to online.
    monkeypatch.setenv("FORCE_ONLINE", "0")
    repo = tmp_path / "repo"
    sync = tmp_path / "db" / "sync"
    repo.mkdir(parents=True)
    sync.mkdir(parents=True)
    idx = repo / "pacstrap-azarch-repo.db"
    idx.write_text("")
    (repo / "somepkg-1.0-1-x86_64.pkg.tar.zst").write_text("")
    (sync / "core.db").write_text("")
    # calamares/librewolf deliberately absent.

    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(compiler.paths, "PKG_REPO", repo)
    monkeypatch.setattr(compiler.paths, "PKG_SYNC_DB", sync)
    assert compiler.cache_is_complete() is False


def test_cache_complete_false_when_only_one_own_package_present(monkeypatch, tmp_path):
    # Half-built (calamares present, librewolf missing) is still incomplete: both
    # own packages are required, so a run that died mid-step-14 re-triggers online.
    monkeypatch.setenv("FORCE_ONLINE", "0")
    repo = tmp_path / "repo"
    sync = tmp_path / "db" / "sync"
    repo.mkdir(parents=True)
    sync.mkdir(parents=True)
    idx = repo / "pacstrap-azarch-repo.db"
    idx.write_text("")
    (repo / "somepkg-1.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "calamares-3.0-1-x86_64.pkg.tar.zst").write_text("")
    (sync / "core.db").write_text("")
    # librewolf missing.

    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(compiler.paths, "PKG_REPO", repo)
    monkeypatch.setattr(compiler.paths, "PKG_SYNC_DB", sync)
    assert compiler.cache_is_complete() is False


def test_cache_complete_false_when_no_synced_db(monkeypatch, tmp_path):
    monkeypatch.setenv("FORCE_ONLINE", "0")
    repo = tmp_path / "repo"
    sync = tmp_path / "db" / "sync"
    repo.mkdir(parents=True)
    sync.mkdir(parents=True)
    idx = repo / "pacstrap-azarch-repo.db"
    idx.write_text("")
    (repo / "somepkg-1.0-1-x86_64.pkg.tar.zst").write_text("")
    # sync dir exists but has NO .db file.

    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(compiler.paths, "PKG_REPO", repo)
    monkeypatch.setattr(compiler.paths, "PKG_SYNC_DB", sync)
    assert compiler.cache_is_complete() is False
