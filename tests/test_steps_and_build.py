"""Cross-cutting invariants for the build driver.

steps.STEP_WEIGHTS must stay in lockstep with the number of bar.step() calls in
steps.run() -- the source itself says "len(STEP_WEIGHTS) - 1 MUST equal the number
of bar.step() calls in run()". If they drift, the progress bar mis-weights and the
final "[ N/N ]" count is wrong. We count the calls from the actual source of run()
so adding/removing a step without updating the weights fails this test.

build.cache_is_complete() is the pure cache-first predicate; it reads only
paths.* and one env var, all monkeypatchable.
"""

from __future__ import annotations

import inspect

from azarch import build, paths, steps


def test_ckbcomp_asset_is_vendored_python_script():
    # Calamares' keyboard preview shells out to `ckbcomp` to render key legends;
    # Arch does not package it, so we vendor it inside the azarch package
    # (libraries/azarch/ckbcomp). It is a Python 3 port of the upstream Perl ckbcomp
    # (byte-identical output, but no Perl in the tree). It must exist and be that
    # Python script (not an empty placeholder).
    src = paths.CKBCOMP_SRC
    assert src.is_file(), "libraries/azarch/ckbcomp is missing"
    head = src.read_text(errors="ignore")[:200]
    assert head.startswith("#!/usr/bin/env python3")
    assert "ckbcomp" in head  # the script's own banner names itself


def test_run_installs_ckbcomp_into_usr_bin():
    # run() must plant the vendored ckbcomp at /usr/bin/ckbcomp (executable) so the
    # keyboard preview finds it. Assert the copy_pkg_file call is present in run().
    src = inspect.getsource(steps.run)
    assert 'copy_pkg_file("ckbcomp"' in src
    assert 'usr/bin/ckbcomp' in src


# --- power management emission + enablement (Tasks 1 & 2) -------------------

def test_run_calls_emit_power():
    # run() must emit the power-management files (lid/button + PC/laptop idle sleep).
    src = inspect.getsource(steps.run)
    assert "_emit_power(airootfs)" in src


def test_emit_power_writes_all_four_artifacts(tmp_path):
    # BEHAVIORAL: _emit_power lays down the four root-owned power files under a fresh
    # airootfs -- the static logind drop-in, the sleep-policy script (executable), its
    # service, and the udev rule. These reach the installed system via unpackfs.
    from azarch.configuration import system

    airootfs = tmp_path / "airootfs"
    steps._emit_power(airootfs)

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
    steps._link_services(airootfs)

    link = (airootfs / "etc/systemd/system/multi-user.target.wants"
            / "azarch-sleep-policy.service")
    assert link.is_symlink()
    import os
    assert os.readlink(link) == "/etc/systemd/system/azarch-sleep-policy.service"


def test_step_weights_match_number_of_steps():
    # run() makes N literal bar.step() calls, but the final one is inside the
    # per-variant finalize loop and executes once per variant (both ISOs are built in
    # one run). So the number of EXECUTED milestones is (N - 1) + len(VARIANTS), and
    # STEP_WEIGHTS must have exactly that many real entries (+ the index-0 sentinel).
    src = inspect.getsource(steps.run)
    n_calls = src.count("bar.step(")
    executed = (n_calls - 1) + len(steps.VARIANTS)
    assert len(steps.STEP_WEIGHTS) - 1 == executed, (
        f"STEP_WEIGHTS has {len(steps.STEP_WEIGHTS)} entries "
        f"(-> {len(steps.STEP_WEIGHTS) - 1} steps) but run() executes {executed} "
        f"milestones ({n_calls} literal bar.step() calls, the last once per "
        f"{len(steps.VARIANTS)} variants)"
    )


def test_step_weights_leading_zero():
    # The first weight is the 0-weight "already at step 0" anchor.
    assert steps.STEP_WEIGHTS[0] == 0


def test_step_weights_giants_are_last_four():
    # package cache, makepkg, and the TWO mkarchiso passes (one per ISO variant) --
    # the four heavy tail weights. Both ISOs are assembled in a single build.
    assert steps.STEP_WEIGHTS[-4:] == [250, 120, 270, 270]


def test_cache_complete_false_when_index_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("FORCE_ONLINE", "0")
    monkeypatch.setattr(build.paths, "LOCALREPO_INDEX", tmp_path / "nope.db")
    assert build.cache_is_complete() is False


def test_cache_complete_force_online_overrides(monkeypatch):
    monkeypatch.setenv("FORCE_ONLINE", "1")
    # Even with everything present, FORCE_ONLINE=1 forces a re-fetch.
    assert build.cache_is_complete() is False


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

    monkeypatch.setattr(build.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(build.paths, "PKG_REPO", repo)
    monkeypatch.setattr(build.paths, "PKG_SYNC_DB", sync)
    assert build.cache_is_complete() is True


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

    monkeypatch.setattr(build.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(build.paths, "PKG_REPO", repo)
    monkeypatch.setattr(build.paths, "PKG_SYNC_DB", sync)
    assert build.cache_is_complete() is False


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

    monkeypatch.setattr(build.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(build.paths, "PKG_REPO", repo)
    monkeypatch.setattr(build.paths, "PKG_SYNC_DB", sync)
    assert build.cache_is_complete() is False


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

    monkeypatch.setattr(build.paths, "LOCALREPO_INDEX", idx)
    monkeypatch.setattr(build.paths, "PKG_REPO", repo)
    monkeypatch.setattr(build.paths, "PKG_SYNC_DB", sync)
    assert build.cache_is_complete() is False
