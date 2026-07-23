"""Build entrypoint: `python3 -m azarch.build`.

Invoked by the thin compile.sh shim AFTER it has set up the PTY (via util-linux
`script`) and primed sudo. This module owns the high-level flow:

  * resolve the cache-first offline policy (BUILD_OFFLINE)
  * start the sudo keepalive + continuous ownership reclaim
  * run the ordered steps (steps.run) with a live progress bar
  * on ANY exit (success / error / Ctrl-C) restore the terminal, unmount the work
    tree, and hand cache/ output/ logs/ back to the host user -- so nothing is
    ever left root-owned and locked.

The heavy PTY/signal nuance the old bash script needed (re-exec on a PTY, group
kills of root children) is split: the PTY + sudo prime stay in compile.sh; here
we handle SIGINT/SIGTERM by terminating the child process group and running the
same teardown.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading

from . import estimate, logstream, makepkg, paths, steps
from .ownership import Ownership
from .progress import ProgressBar


def _sudo() -> list[str]:
    return [] if paths.is_root() else ["sudo", "-n"]


def cache_is_complete() -> bool:
    """The cache-first verdict: a COMPLETE cache => build with zero server contact.
    Complete = local repo index symlink + at least one indexed pkg + synced DBs +
    OUR OWN built packages (calamares, librewolf) actually present.
    FORCE_ONLINE=1 overrides (re-fetch without wiping).

    The own-packages clause is load-bearing: a cache can hold all 800+ downloaded
    Arch packages, a valid index, and synced DBs yet still LACK calamares/librewolf
    (they are compiled by the makepkg stage, not downloaded -- so a fresh cache, or
    one warmed by an earlier run that died before step 14, never has them). Without
    this clause cache_is_complete() returned True, the build took the OFFLINE path,
    and makepkg.build_own_packages then refused offline because the packages it was
    supposed to produce were absent -- a permanent deadlock (offline can't build
    them; nothing ever downgrades to online to build them). Treating their absence
    as an incomplete cache makes the build go ONLINE, compile them, drop them into
    cache/pkgs/repo/, and be genuinely offline-complete on the next run."""
    if os.environ.get("FORCE_ONLINE", "0") == "1":
        return False
    if not paths.LOCALREPO_INDEX.exists():
        return False
    if not any(paths.PKG_REPO.glob("*.pkg.tar.zst")):
        return False
    if not paths.PKG_SYNC_DB.is_dir() or not any(paths.PKG_SYNC_DB.glob("*.db")):
        return False
    # produced_names is tier-independent (both own packages are always built), so
    # full_compile=False is correct regardless of the eventual --full-compile flag.
    if not makepkg._repo_has_all(paths.PKG_REPO, makepkg.produced_names(full_compile=False)):
        return False
    # NOTE: a COMPLETE cache makes the build go offline for BOTH tiers, but the two
    # tiers then diverge inside makepkg.build_own_packages: the default tier trusts
    # the cached own packages and SKIPS makepkg, while a --full-compile offline rerun
    # RE-COMPILES librewolf from the source fetched into the makepkg scratch by the
    # prior online run (no network). So "offline" here means "no server contact",
    # not "no compile" -- the recompile stays entirely local.
    return True


class SudoKeepalive:
    """Keep the sudo timestamp warm across the long build so the trap/immediate
    `sudo -n chown` still works past sudo's short timeout. No-op when root."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if paths.is_root():
            return

        def loop() -> None:
            while not self._stop.wait(60):
                if subprocess.run(["sudo", "-n", "-v"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
                    return

        self._thread = threading.Thread(target=loop, name="sudo-keepalive", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def _stale_cache_notice(offline: bool) -> None:
    if not offline:
        return
    idx = paths.LOCALREPO_INDEX_TAR
    try:
        if idx.exists() and paths.PACKAGES_FILE.stat().st_mtime > idx.stat().st_mtime:
            sys.stderr.write(
                "[!] packages.x86_64 is newer than the cached package index. If you ADDED\n"
                "    packages, this offline build won't have them and pacstrap may fail with\n"
                "    'target not found'. Re-run with FORCE_ONLINE=1 (or 'git clean -Xdf').\n"
            )
    except OSError:
        pass


def main() -> int:
    paths.LOGDIR.mkdir(parents=True, exist_ok=True)

    # --estimate* (six variants): predict how long a build would take on this
    # machine -- COMPUTE (compiling on this CPU/RAM) and/or NETWORK (downloading
    # the components over this connection) -- then exit. Pure query: no workspace
    # reset, no sudo, no build, and NOT routed through the build-log tee (it is a
    # query, not a build, so its output belongs on the terminal, not logs/full.log
    # -- this branch returns before logstream.install() below). The network modes
    # DO open a client socket for a few-second bandwidth probe, but that needs no
    # privilege and writes no build file. compile.sh routes any --estimate* arg
    # here without a PTY or sudo prime.
    if estimate.parse_estimate_flag(sys.argv[1:]) is not None:
        return estimate.run(sys.argv[1:])

    paths.CACHEDIR.mkdir(parents=True, exist_ok=True)

    # Python owns full.log from here on: route stdout/stderr through a tee that
    # mirrors every print/stderr line into the log in real time. `script` in
    # compile.sh now only provides the PTY (its capture goes to /dev/null), so the
    # progress bar -- which paints to the RAW terminal only -- never reaches the log.
    logstream.install()

    # --full-compile: build Az'arch's own packages entirely from source (incl. the
    # multi-hour LibreWolf/Firefox compile) rather than repackaging the verified
    # upstream LibreWolf tarball. Default is the fast repackage tier.
    full_compile = "--full-compile" in sys.argv[1:]
    if full_compile:
        print("[*] --full-compile: Az'arch's own packages will be built ENTIRELY from source.")
        print("    This includes a LibreWolf/Firefox compile that can take 1.5-3+ hours.")

    offline = cache_is_complete()
    _stale_cache_notice(offline)

    bar = ProgressBar(steps.STEP_WEIGHTS)
    own = Ownership(_sudo())
    keep = SudoKeepalive()

    # SAFEGUARD 1: startup reclaim (recovers a tree left by a SIGKILL'd prior run).
    own.reclaim_full()
    keep.start()
    own.start_continuous()

    _torn_down = threading.Event()

    def teardown() -> None:
        # Re-entrancy guard: signal + normal/error exit paths must not double-run
        # the chown/unmount (mirrors the old _HANDED_BACK / _KILLED flags).
        if _torn_down.is_set():
            return
        _torn_down.set()
        keep.stop()
        own.stop_continuous()
        steps.kill_active_child(_sudo())  # kill mkarchiso's OWN group, not ours
        steps._unmount_worktree(_sudo())
        bar.cleanup()
        own.reclaim_full()  # SAFEGUARD final

    def on_signal(signum, _frame) -> None:
        # Kill ONLY the mkarchiso child's process group (it is spawned in its own
        # session, see steps._run_mkarchiso), never our own group -- signalling our
        # own group would re-enter this handler and could interrupt teardown
        # mid-chown, leaving cache/build root-owned (the exact old-bash hazard).
        teardown()
        os._exit(130)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    bar.init()
    try:
        iso = steps.run(bar, offline, full_compile=full_compile,
                        reclaim_after_mkarchiso=own.reclaim_full)
    except SystemExit as e:
        teardown()
        msg = str(e)
        if msg and not msg.isdigit():
            sys.stderr.write(msg + "\n")
        return e.code if isinstance(e.code, int) else 1
    except Exception as e:
        teardown()
        sys.stderr.write(f"[x] Build failed: {e}\n")
        return 1

    bar.subfrac = 1000
    bar.finalize()
    iso_size = subprocess.run(["du", "-h", str(iso)], capture_output=True, text=True).stdout.split("\t")[0]
    iso_path = f"output/{iso.name}" if paths.in_docker() else str(iso)
    line = f"\n[ {bar.total_steps}/{bar.total_steps} ] [OK] ISO built successfully: {iso_path}"
    if iso_size:
        line += f" ({iso_size})"
    print(line)
    with paths.STEPS_LOG.open("a") as f:
        f.write(line + "\n")
    if paths.in_docker():
        print(f"           The ISO is at {iso_path} on your host (NOT build/output/).")

    teardown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
