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

from azarch import build, steps


def test_step_weights_match_number_of_steps():
    src = inspect.getsource(steps.run)
    n_calls = src.count("bar.step(")
    assert len(steps.STEP_WEIGHTS) - 1 == n_calls, (
        f"STEP_WEIGHTS has {len(steps.STEP_WEIGHTS)} entries "
        f"(-> {len(steps.STEP_WEIGHTS) - 1} steps) but run() makes {n_calls} bar.step() calls"
    )


def test_step_weights_leading_zero():
    # The first weight is the 0-weight "already at step 0" anchor.
    assert steps.STEP_WEIGHTS[0] == 0


def test_step_weights_giants_are_last_three():
    # package cache, makepkg, mkarchiso -- the three heavy tail weights.
    assert steps.STEP_WEIGHTS[-3:] == [250, 120, 270]


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
