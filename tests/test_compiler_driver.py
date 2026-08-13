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
    # Arch does not package it, so we vendor it as a flat modification module
    # (libraries/modifications/ckbcomp.py) -- an upstream tool modified to fit Az'arch. It
    # is a Python 3 port of the upstream Perl ckbcomp (byte-identical output, but no
    # Perl in the tree). It must exist and be that Python script (not an empty
    # placeholder).
    src = paths.CKBCOMP_SRC
    assert src.is_file(), "libraries/modifications/ckbcomp.py is missing"
    head = src.read_text(errors="ignore")[:200]
    assert head.startswith("#!/usr/bin/env python3")
    assert "ckbcomp" in head  # the script's own banner names itself


def test_run_installs_ckbcomp_into_usr_bin():
    # run() must plant the vendored ckbcomp at /usr/bin/ckbcomp (executable) so the
    # keyboard preview finds it. Assert the copy_modification_file call is present in run().
    src = inspect.getsource(compiler.run)
    assert 'copy_modification_file("ckbcomp.py"' in src
    assert 'usr/bin/ckbcomp' in src


def test_emit_calamares_ships_the_window_icon_into_branding():
    # The installer's WINDOW ICON (the "Az'" tile OpenBox draws on the titlebar) is the
    # branding productIcon: a real PNG copied INTO branding/azarch/. Assert _emit_calamares
    # copies the standardized installer icon asset to the branding productIcon file, so the
    # topbar icon exists and matches the launcher icon.
    from modifications.calamares import calamares
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
    # (they are compiled by the makepkg stage, not downloaded).
    (repo / "calamares-3.0-1-x86_64.pkg.tar.zst").write_text("")
    (repo / "librewolf-1.0-1-x86_64.pkg.tar.zst").write_text("")
    (sync / "core.db").write_text("")

    monkeypatch.setattr(compiler.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(compiler.paths, "PKG_REPO", repo)
    monkeypatch.setattr(compiler.paths, "PKG_SYNC_DB", sync)
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
