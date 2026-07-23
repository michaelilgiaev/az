"""Real-time, resumable package cache -- the port of the old cache-pkgs.sh.

Downloads (or reuses) the ~1200 packages that get baked into the ISO's offline
install repo, reconciles a local repo index incrementally, and stages the result
into the airootfs. Progress is reported via a callback so the build's bar moves.

pacman -Sw --cachedir <persistent> makes caching incremental & resumable: only
missing packages are fetched, finished ones are durable immediately, and a
re-run skips what's present. The repo index (.db) is likewise persistent and
reconciled by DELTA (only new/changed packages re-indexed), so a warm re-run is
near-instant.

Cache-first: when BUILD_OFFLINE=1 (a complete cache exists) BOTH the -Sy DB sync
and the -Sw download are skipped -- no server is contacted at all.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import paths
from .config import pacman as pacman_cfg

ProgressCb = Callable[[int], None]


class PackageError(RuntimeError):
    pass


def _sudo() -> list[str]:
    return [] if paths.is_root() else ["sudo"]


def _run(cmd: list[str], *, check: bool = True, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, **kw)


def _vercmp(a: str, b: str) -> int:
    out = subprocess.run(["vercmp", a, b], capture_output=True, text=True).stdout.strip()
    try:
        return int(out)
    except ValueError:
        return 0


def _split_pkg(basename: str) -> tuple[str, str, str]:
    """basename -> (db_key, name, verrel). db_key = name-ver-rel (arch+suffix
    stripped) -- exactly the entry-dir name repo-add stores."""
    key = basename.rsplit("-", 1)[0]  # drop -<arch>.pkg.tar.zst tail piece
    # key is name-ver-rel; verrel is last field, name-ver before it.
    nv, rel = key.rsplit("-", 1)
    name, ver = nv.rsplit("-", 1)
    return key, name, f"{ver}-{rel}"


def _write_download_conf(dest: Path) -> Path:
    dest.write_text(pacman_cfg.download_conf() + "\n", encoding="utf-8")
    return dest


def build_cache(workdir: Path, cachedir: Path, offline: bool, progress: ProgressCb,
                phase: Callable[[str], None] = lambda _s: None,
                full_compile: bool = False) -> None:
    """Sync/download (unless offline), reconcile the index, and stage the cache.

    workdir      : the disposable profile tree (holds the transient sync DB + gpg dir)
    cachedir     : the persistent cache root (survives builds)
    offline      : BUILD_OFFLINE -- skip all network when the cache is complete
    progress     : called with a permille (0..1000) as milestones are reached
    phase        : called with a short sub-phase label to narrate the bar (optional)
    full_compile : the build tier. It NO LONGER changes which packages the
                   makepkg stage produces -- calamares AND librewolf are built
                   here in every tier (neither is in an Arch repo), so both are
                   always EXCLUDED from the Arch `pacman -Sw` download (they exist
                   on no mirror). The flag only changes librewolf's recipe.
                   See makepkg.produced_names().
    """
    sudo = _sudo()
    pkg_repo = cachedir / "pkgs" / "repo"
    pkg_db = cachedir / "pkgs" / "db"
    final_db = workdir / "airootfs/root/azarch/pacstrap-azarch-db"
    final_cache = workdir / "airootfs/root/azarch/pacstrap-azarch-repo"
    gpgdir = workdir / ".pkgs-gnupg"
    dlconf = _write_download_conf(workdir / ".cache-pkgs-pacman.conf")

    pkg_repo.mkdir(parents=True, exist_ok=True)
    (pkg_db / "sync").mkdir(parents=True, exist_ok=True)
    if gpgdir.exists():
        subprocess.run(["rm", "-rf", str(gpgdir)], check=False)
    gpgdir.mkdir(parents=True, exist_ok=True)

    # clear a stale db lock from a killed prior run (may be root-owned).
    _run(sudo + ["rm", "-f", str(pkg_db / "db.lck")], check=False)

    if offline:
        print("[*] Complete cache present -- skipping DB sync and download (fully offline).")
        phase("cache complete, using offline packages")
        if not any((pkg_db / "sync").iterdir()):
            raise PackageError(
                "BUILD_OFFLINE set but no cached sync DB -- wipe cache/ and rebuild online."
            )
        progress(20)
    else:
        _sync_and_download(sudo, dlconf, gpgdir, pkg_db, pkg_repo, progress, phase, full_compile)

    # hand the cache subtree back so the later unprivileged steps here can read it.
    own_uid = os.environ.get("HOST_UID") or str(os.getuid())
    own_gid = os.environ.get("HOST_GID") or str(os.getgid())
    _run(sudo + ["chown", "-R", f"{own_uid}:{own_gid}", str(pkg_repo), str(pkg_db)], check=False)

    print("[*] Reconciling local repository index with the cache...")
    phase("reconciling local repo index")
    progress(440)
    _reconcile_index(pkg_repo, progress)

    print("[*] Staging cached packages into the ISO working tree...")
    phase("staging cache into ISO tree")
    progress(880)
    final_db.mkdir(parents=True, exist_ok=True)
    final_cache.mkdir(parents=True, exist_ok=True)
    _run(["cp", "-r", f"{pkg_db}/.", f"{final_db}/"])
    _run(["cp", "-r", f"{pkg_repo}/.", f"{final_cache}/"])
    if not any(final_cache.iterdir()):
        raise PackageError("Package cache is empty after staging.")

    subprocess.run(["rm", "-rf", str(gpgdir)], check=False)
    progress(1000)
    print("[✓] Package cache is complete and staged (offline-ready, resumable).")


def _sync_and_download(sudo, dlconf, gpgdir, pkg_db, pkg_repo, progress, phase=lambda _s: None,
                       full_compile: bool = False) -> None:
    phase("syncing package databases")
    print("[*] Syncing package databases...")
    r = subprocess.run(
        sudo + ["pacman", "-Sy", "--config", str(dlconf), "--gpgdir", str(gpgdir),
                "--dbpath", str(pkg_db), "--cachedir", str(pkg_repo), "--noconfirm"],
        check=False,
    )
    if r.returncode != 0:
        if any((pkg_db / "sync").iterdir()):
            print("    [+] DB sync failed but a cached DB exists -- continuing offline.")
        else:
            raise PackageError("Could not sync package databases and no cached DB to fall back on.")

    print("[*] Preparing package list...")
    # Parse the manifest the SAME way mkarchiso does (and the on-disk installer):
    # drop full-line and trailing `# ...` comments and blank lines, keeping only
    # package names. packages.x86_64 carries a header + a Stock/Az'arch delimiter,
    # so a bare .split() would feed those comment words to `pacman -Sw` as bogus
    # targets and fail the cache download. (Package names never contain '#'.)
    pkgs = [tok for line in paths.PACKAGES_FILE.read_text().splitlines()
            if (tok := line.split("#", 1)[0].strip())]
    # EXCLUDE the packages the makepkg stage builds ITSELF: they exist on no Arch
    # mirror, so `pacman -Sw` would abort with "target not found". They are built by
    # the makepkg stage (steps.py step 13) and folded into the same offline repo
    # right AFTER this download, then indexed alongside everything else.
    #   Both tiers -> calamares AND librewolf are built here, so both are excluded.
    #                 (calamares was in extra/ once, but Arch dropped it -- if it is
    #                 NOT excluded, `pacman -Sw calamares` fails with "target not
    #                 found" and the whole download aborts. This is that bug's fix.)
    from .makepkg import produced_names
    own = set(produced_names(full_compile))
    pkgs = [p for p in pkgs if p not in own]

    print("[*] Downloading missing packages into the persistent cache (resumable)...")
    phase(f"downloading {len(pkgs)} packages into cache")
    progress(20)
    r = subprocess.run(
        sudo + ["pacman", "-Sw", "--config", str(dlconf), "--gpgdir", str(gpgdir),
                "--noconfirm", "--cachedir", str(pkg_repo), "--dbpath", str(pkg_db)] + pkgs,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if r.returncode != 0:
        raise PackageError("package download")
    progress(440)


def _readd_own_packages(pkg_repo: Path, full_compile: bool = False) -> None:
    """Force `repo-add` of the packages the makepkg stage BUILT so their DB entry's
    SHA256/CSIZE match the file currently on disk.

    _reconcile_index keys its delta by name-ver-rel and SKIPS a package whose key
    is already indexed. A makepkg-built package (calamares and librewolf, both
    tiers) keeps its version across rebuilds, but makepkg is not reproducible
    bit-for-bit, so the rebuilt file's checksum changes while its key does not --
    the delta skips it and the DB keeps a stale checksum. pacstrap then rejects
    the current file as corrupted. repo-add (WITHOUT -n) overwrites an existing
    same-version entry, so this simply refreshes SHA256+CSIZE to the on-disk
    bytes. Only OUR built packages need it; the downloaded Arch packages are
    immutable per version, so their DB entry from the download is always correct
    and must NOT be forced here."""
    from .makepkg import produced_names
    db = pkg_repo / "pacstrap-azarch-repo.db.tar.gz"
    files: list[str] = []
    for name in produced_names(full_compile):
        files += [str(p) for p in sorted(pkg_repo.glob(f"{name}-*.pkg.tar.zst"))]
    if not files:
        return
    r = subprocess.run(["repo-add", "-q", str(db)] + files,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        raise PackageError("repo-add (own-package refresh)")


def _reconcile_index(pkg_repo: Path, progress: ProgressCb) -> None:
    """Incrementally reconcile pacstrap-azarch-repo.db with the .pkg files on disk.
    Only new/changed packages are added; stale names removed; duplicate older
    versions pruned. Byte-for-byte equivalent to a full rebuild's db."""
    db = pkg_repo / "pacstrap-azarch-repo.db.tar.gz"
    pkgfiles = sorted(pkg_repo.glob("*.pkg.tar.zst"))
    if not pkgfiles:
        raise PackageError("no packages in cache to index")

    have_key: dict[str, str] = {}       # db_key -> basename on disk
    have_name: dict[str, int] = {}
    file_of_name: dict[str, Path] = {}
    ver_of_name: dict[str, str] = {}
    key_of_name: dict[str, str] = {}
    superseded: list[Path] = []

    for f in pkgfiles:
        b = f.name
        key, name, verrel = _split_pkg(b)
        if name in ver_of_name:
            if _vercmp(verrel, ver_of_name[name]) > 0:
                superseded.append(file_of_name[name])
                have_key.pop(key_of_name[name], None)
            else:
                superseded.append(f)
                continue
        have_key[key] = b
        have_name[name] = 1
        file_of_name[name] = f
        ver_of_name[name] = verrel
        key_of_name[name] = key

    usable = db.is_file() and subprocess.run(
        ["bsdtar", "-tf", str(db)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0

    if not usable:
        _seed_fresh_index(pkg_repo, db, have_key, progress)
    else:
        _delta_index(pkg_repo, db, have_key, have_name)

    if superseded:
        print(f"    [-] Removing {len(superseded)} superseded package file(s) from cache.")
        for f in superseded:
            f.unlink(missing_ok=True)


def _seed_fresh_index(pkg_repo, db, have_key, progress) -> None:
    add = [str(pkg_repo / bn) for bn in have_key.values()]
    print(f"    [+] No usable index -- building fresh from {len(add)} package(s) (one-time).")
    for old in pkg_repo.glob("pacstrap-azarch-repo.db*"):
        old.unlink(missing_ok=True)
    for old in pkg_repo.glob("pacstrap-azarch-repo.files*"):
        old.unlink(missing_ok=True)
    tot, chunk = len(add), 50
    for i in range(0, tot, chunk):
        r = subprocess.run(["repo-add", "-q", str(db)] + add[i:i + chunk],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if r.returncode != 0:
            raise PackageError("repo-add (fresh)")
        n = min(i + chunk, tot)
        print(f"    [+] Indexing {n}/{tot} packages...")
        # map the seed onto the index band 440..880
        progress(440 + (n * 440 // tot if tot else 440))


def _delta_index(pkg_repo, db, have_key, have_name) -> None:
    db_key: dict[str, int] = {}
    db_name: dict[str, int] = {}
    out = subprocess.run(["bsdtar", "-tf", str(db)], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.endswith("/desc"):
            ekey = line[:-5]
            db_key[ekey] = 1
            # name = ekey minus the trailing -ver-rel (two fields)
            db_name[ekey.rsplit("-", 2)[0]] = 1

    add = [str(pkg_repo / bn) for k, bn in have_key.items() if k not in db_key]
    rm = [n for n in db_name if n not in have_name]

    if rm:
        print(f"    [-] Dropping {len(rm)} stale entr(y/ies) from the index.")
        if subprocess.run(["repo-remove", "-q", str(db)] + rm).returncode != 0:
            raise PackageError("repo-remove")
    if add:
        print(f"    [+] Indexing {len(add)} new/updated package(s).")
        if subprocess.run(["repo-add", "-q", str(db)] + add).returncode != 0:
            raise PackageError("repo-add (delta)")
    if not rm and not add:
        print("    [=] Index already up to date -- nothing to re-index.")
