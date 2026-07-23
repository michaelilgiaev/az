"""Build Az'arch's OWN packages (calamares, librewolf) with makepkg and drop the
resulting *.pkg.tar.zst into the offline repo the rest of the build already uses.

Everything not in the official Arch repos is built from recipes WE author in
azarch.config.pkgbuild -- never the AUR, never an AUR helper. This module is the
runner: it emits those recipes into a scratch dir, ensures the host has the
makedepends, runs `makepkg` as an UNPRIVILEGED user (makepkg refuses root), and
copies the built packages into cache/pkgs/repo/ so the normal index-reconcile
step (packages._reconcile_index) folds them into pacstrap-azarch-repo.db next to
the Arch packages. `calamares`/`librewolf` in packages.x86_64 then resolve from
the local repo like anything else.

Tiers: BOTH calamares and librewolf are built here in every tier -- neither is
in an official Arch repo (librewolf never was; calamares was dropped from extra/
and is now AUR-only). --full-compile only changes the RECIPE, not the set:
  * librewolf -> default = repackage the verified upstream binary tarball;
                 full = build from Firefox source.
  * calamares -> always compiled from the pinned-sha256 source tarball (there is
                 no Arch binary to install anymore).
config.pkgbuild.recipe_dirs(full_compile) picks the recipe set; produced_names()
below returns the (now tier-independent) set of names built HERE.

Offline policy: makepkg needs to FETCH sources (the calamares/firefox/librewolf
tarballs + git). When the build is fully offline (BUILD_OFFLINE) we SKIP the
makepkg stage if the packages are already present in the repo, and fail loudly
if they are not -- exactly like the rest of the cache-first design.
"""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from . import emit, logstream, paths
from .config import pkgbuild as pkgbuild_cfg

ProgressCb = Callable[[int], None]

# Unprivileged user makepkg runs as (makepkg aborts as root). Created on demand
# on a native/root build; on a rootless build we already are unprivileged and
# just use the current user.
BUILDER_USER = "azarchbuilder"

# Package NAMES built by this stage. BOTH are built in EVERY tier because neither
# is in an official Arch repo: librewolf never was; calamares USED to live in
# extra/ but Arch dropped it (it is now AUR-only), so the default tier can no
# longer `pacman -S calamares` and must build it from our own recipe like the
# full tier already did. The only thing --full-compile still changes is HOW each
# is built (see produced_names / recipe_dirs), not WHICH are built.
# This set is used to (a) exclude own packages from the Arch `pacman -Sw` download
# (they exist on no mirror) and (b) know which built packages to re-add/refresh in
# the offline repo + cache.
PRODUCED = ("calamares", "librewolf")


def produced_names(full_compile: bool) -> tuple[str, ...]:
    """Names of packages the makepkg stage produces. Tier-independent now:
    calamares + librewolf are ALWAYS built here (both are AUR-only / in no Arch
    repo). --full-compile only changes the RECIPE used (source vs repackage),
    handled by recipe_dirs, not the set of names."""
    return PRODUCED


class MakepkgError(RuntimeError):
    pass


def _sudo() -> list[str]:
    return [] if paths.is_root() else ["sudo"]


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kw)


def _repo_has_all(pkg_repo: Path, names: tuple[str, ...]) -> bool:
    """True if a built package file exists for every name this tier produces."""
    for name in names:
        if not any(pkg_repo.glob(f"{name}-*.pkg.tar.zst")):
            return False
    return True


def _emit_recipes(scratch: Path, full_compile: bool) -> list[Path]:
    """Write each recipe dir (PKGBUILD + companions) from config.pkgbuild into
    scratch/. Returns the list of recipe dirs to build, in order."""
    dirs: list[Path] = []
    for dirname, files in pkgbuild_cfg.recipe_dirs(full_compile):
        d = scratch / dirname
        d.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            emit.write_text(d / filename, content)
        dirs.append(d)
    return dirs


def _ensure_builder_user() -> str:
    """Return the username makepkg should run as. On a root build, create an
    unprivileged builder; otherwise use the current (already unprivileged) user."""
    if not paths.is_root():
        return pwd.getpwuid(os.getuid()).pw_name
    try:
        pwd.getpwnam(BUILDER_USER)
    except KeyError:
        _run(["useradd", "-m", "-s", "/bin/bash", BUILDER_USER], check=True)
    # passwordless sudo for the builder is NOT granted; makepkg installs its
    # makedepends via a separate root `pacman -S` we run below, so the builder
    # only ever runs the unprivileged compile.
    return BUILDER_USER


def _collect_makedepends(dirs: list[Path]) -> list[str]:
    """Union of makedepends + depends across the recipes, so the host can build
    (makedepends) and so runtime deps are present for any check phase."""
    want: set[str] = set()
    for d in dirs:
        pb = d / "PKGBUILD"
        # Source the PKGBUILD in bash and print its dep arrays -- authoritative,
        # avoids reparsing bash arrays in Python. Bounded: a recipe should read its
        # own arrays in well under a second; a hang here (e.g. a PKGBUILD that
        # accidentally runs a network/blocking command at source time) would freeze
        # the whole stage with no output, so we cap it and move on.
        try:
            out = subprocess.run(
                ["bash", "-c", f'source "{pb}"; printf "%s\\n" "${{makedepends[@]}}" "${{depends[@]}}"'],
                capture_output=True, text=True, timeout=30,
            ).stdout
        except subprocess.TimeoutExpired:
            print(f"    [!] Reading deps from {d.name}/PKGBUILD timed out; continuing without them.")
            continue
        for tok in out.split():
            tok = tok.strip()
            if tok:
                want.add(tok)
    return sorted(want)


def _install_host_build_deps(sudo: list[str], deps: list[str], offline: bool) -> None:
    """Install makedepends on the BUILD HOST so makepkg can compile. Skipped when
    offline (assumes a warm host / already-built packages)."""
    if offline or not deps:
        return
    print(f"    [+] Installing {len(deps)} build-host dependencies for makepkg...")
    # Teed so pacman's download/install lines reach full.log in real time.
    rc = logstream.run_teed(sudo + ["pacman", "-S", "--needed", "--noconfirm", *deps])
    if rc != 0:
        # Non-fatal: makepkg will still try and fail clearly if something's truly
        # missing. Some listed deps are runtime-only and may not be needed to build.
        print("    [!] Some build-host deps failed to install; continuing (makepkg will verify).")


def _import_librewolf_key(builder: str, sudo: list[str], offline: bool) -> None:
    """Import the LibreWolf release key into the BUILDER's gpg keyring so the
    librewolf recipe's detached-signature check passes. Fails closed online: if
    the key can't be fetched, the signature check would be skipped, so we abort."""
    if offline:
        return
    key = pkgbuild_cfg.LIBREWOLF_PGP_KEY
    print(f"    [+] Importing LibreWolf signing key {key[-8:]} from a keyserver...")
    # Run gpg AS the builder (its keyring is what makepkg checks). Bounded per
    # keyserver: gpg --recv-keys over hkps can hang for minutes on an unreachable
    # or slow keyserver with ZERO output -- that was a prime cause of the stage
    # sitting silent at "own packages". A timeout turns an unreachable keyserver
    # into a fast failover to the next one instead of an invisible stall.
    def as_builder(args: list[str]) -> int:
        full = ["sudo", "-u", builder, *args] if paths.is_root() else args
        try:
            return subprocess.run(full, timeout=90).returncode
        except subprocess.TimeoutExpired:
            print(f"    [!] gpg timed out after 90s; trying the next keyserver.")
            return 1

    for ks in ("hkps://keyserver.ubuntu.com", "hkps://keys.openpgp.org"):
        print(f"    [+]   contacting {ks} ...")
        if as_builder(["gpg", "--keyserver", ks, "--recv-keys", key]) == 0:
            print(f"    [+] Imported LibreWolf signing key {key[-8:]} from {ks}.")
            return
    raise MakepkgError(
        f"Could not import the LibreWolf signing key {key} from any keyserver.\n"
        "    The signature check would be bypassed, so the build fails closed.\n"
        "    Check network/keyservers, or use --full-compile (source build, no tarball sig)."
    )


def build_own_packages(offline: bool, full_compile: bool, progress: ProgressCb,
                        phase: Callable[[str], None] = lambda _s: None) -> None:
    """Emit our recipes, build them with makepkg, and drop the packages into the
    offline repo. Idempotent: an already-built package is not rebuilt."""
    sudo = _sudo()
    pkg_repo = paths.PKG_REPO
    pkg_repo.mkdir(parents=True, exist_ok=True)
    names = produced_names(full_compile)

    # calamares is compiled from source in BOTH tiers; the tier only changes how
    # librewolf is produced (from-source vs repackage the verified upstream tarball).
    tier = ("full-compile (calamares + librewolf from source)" if full_compile
            else "default (calamares from source, librewolf repackaged)")
    print(f"[*] Building Az'arch's own packages -- tier: {tier}")
    phase(f"own packages: {tier}")
    progress(20)

    if offline:
        if not full_compile:
            # DEFAULT tier, offline: the own packages are deterministic cached
            # artifacts (calamares from a pinned source, librewolf repackaged from a
            # verified tarball). Present -> SKIP makepkg (the fast rerun the user
            # wants). Absent -> fail loudly (unchanged).
            if _repo_has_all(pkg_repo, names):
                print("    [+] Own packages already present in the offline repo -- skipping makepkg.")
                progress(1000)
                return
            raise MakepkgError(
                f"Offline build but the built package(s) {', '.join(names)} are not in the cache.\n"
                "    Wipe cache/ (or `git clean -Xdf`) so the next run rebuilds them online.\n"
                "    (An incomplete cache already forces an online run automatically; this\n"
                "    fires only when the cache LOOKS complete but the own packages are absent.)"
            )
        # FULL tier, offline: the user asked for a from-source rerun to actually
        # RE-COMPILE, not trust the cached package. Rebuild librewolf (and calamares)
        # from the sources the prior ONLINE run fetched into the makepkg scratch --
        # entirely offline. Do NOT skip, do NOT wipe the scratch (the fetched Firefox
        # tree lives there), do NOT re-fetch (the recipe's `make fetch` is gated off
        # by AZARCH_OFFLINE and makepkg is told --noextract so it reuses the tree).
        scratch = paths.CACHEDIR / "makepkg"
        if not _scratch_has_sources(scratch, full_compile=True):
            raise MakepkgError(
                "Offline --full-compile rerun but the cached makepkg source tree is\n"
                f"    missing or empty under {scratch}. The prior online run's fetched\n"
                "    Firefox/bsys6 sources are gone (e.g. cache/ was cleared). Re-run once\n"
                "    online (FORCE_ONLINE=1) to refetch, or wipe cache/ to rebuild fresh."
            )
        print("    [+] --full-compile offline: recompiling from cached sources (no network).")
        phase("own packages: offline recompile")
        _offline_full_recompile(scratch, pkg_repo, progress, phase)
        return

    phase("own packages: preparing recipes")
    print("    [+] Preparing makepkg scratch tree and emitting recipes...")
    scratch = paths.CACHEDIR / "makepkg"
    if scratch.exists():
        _run(sudo + ["rm", "-rf", str(scratch)], check=False)
    scratch.mkdir(parents=True, exist_ok=True)

    dirs = _emit_recipes(scratch, full_compile)
    print(f"    [+] Emitted {len(dirs)} recipe(s): {', '.join(d.name for d in dirs)}.")
    progress(80)

    builder = _ensure_builder_user()
    phase("own packages: collecting build deps")
    print("    [+] Reading makedepends/depends from the recipes...")
    deps = _collect_makedepends(dirs)
    phase("own packages: installing build deps")
    _install_host_build_deps(sudo, deps, offline)
    progress(200)

    phase("own packages: importing signing key")
    _import_librewolf_key(builder, sudo, offline)
    progress(260)

    # The builder must own the scratch tree to write src//pkg/ during makepkg.
    if paths.is_root():
        _run(["chown", "-R", f"{builder}:{builder}", str(scratch)], check=True)

    _build_recipe_dirs(builder, dirs, pkg_repo, progress, phase, offline=False)

    progress(1000)
    print("[✓] Az'arch's own packages built and staged into the offline repo.")


def _build_recipe_dirs(builder: str, dirs: list[Path], pkg_repo: Path,
                       progress: ProgressCb, phase: Callable[[str], None],
                       offline: bool) -> None:
    """Build each recipe dir with makepkg, copy the resulting *.pkg.tar.zst into
    the offline repo, and hand the repo back to the invoking user. Shared by the
    online build tail and the offline --full-compile recompile; only the makepkg
    invocation differs (offline adds --noextract/--nocheck + AZARCH_OFFLINE so it
    reuses the already-fetched scratch tree and never touches the network)."""
    total = len(dirs)
    for i, d in enumerate(dirs):
        name = d.name
        phase(f"makepkg: building {name}")
        print(f"[*] makepkg: building {name} ({i + 1}/{total})...")
        _makepkg_one(builder, d, offline=offline)
        # copy the freshly built package(s) into the offline repo
        built = sorted(d.glob("*.pkg.tar.zst"))
        if not built:
            raise MakepkgError(f"makepkg produced no package for {name} in {d}")
        for pkgfile in built:
            shutil.copy2(pkgfile, pkg_repo / pkgfile.name)
            print(f"    [+] {pkgfile.name} -> offline repo")
        progress(260 + (i + 1) * 700 // total)

    # hand the repo back to the invoking user (parity with packages.build_cache).
    own_uid = os.environ.get("HOST_UID") or str(os.getuid())
    own_gid = os.environ.get("HOST_GID") or str(os.getgid())
    _run(_sudo() + ["chown", "-R", f"{own_uid}:{own_gid}", str(pkg_repo)], check=False)


def _scratch_has_sources(scratch: Path, full_compile: bool) -> bool:
    """True iff every recipe dir under scratch exists with a PKGBUILD AND a
    NON-EMPTY .build tree. The .build tree (BUILDDIR in _makepkg_one) is where
    makepkg extracts $srcdir and where the librewolf recipe's `make fetch` wrote
    the Firefox source on the prior ONLINE run -- so its presence is the real
    "sources are cached, an offline recompile can succeed" signal. .src (SRCDEST)
    only ever holds the small git checkout, so it is NOT what we check. Missing or
    empty -> False -> the offline-recompile caller fails loudly instead of silently
    going online. Pure given the filesystem; unit-tested with tmp_path."""
    for dirname, _files in pkgbuild_cfg.recipe_dirs(full_compile):
        d = scratch / dirname
        if not (d / "PKGBUILD").is_file():
            return False
        build_dir = d / ".build"
        if not build_dir.is_dir() or not any(build_dir.iterdir()):
            return False
    return True


def _offline_full_recompile(scratch: Path, pkg_repo: Path, progress: ProgressCb,
                            phase: Callable[[str], None]) -> None:
    """Rebuild each recipe from its already-populated scratch dir, entirely offline.
    Unlike the online path it does NOT emit recipes, install host deps, import
    signing keys, or wipe the scratch -- it reuses exactly what the prior online run
    fetched. Only the per-dir makepkg/copy loop runs, with offline=True so makepkg
    reuses the extracted tree (--noextract) and the recipe skips `make fetch`."""
    pkg_repo.mkdir(parents=True, exist_ok=True)
    dirs = [scratch / dirname for dirname, _files
            in pkgbuild_cfg.recipe_dirs(full_compile=True)]
    builder = _ensure_builder_user()
    # The builder must own the scratch tree to write into it during makepkg.
    if paths.is_root():
        _run(["chown", "-R", f"{builder}:{builder}", str(scratch)], check=True)
    progress(260)
    _build_recipe_dirs(builder, dirs, pkg_repo, progress, phase, offline=True)
    progress(1000)
    print("[✓] Az'arch's own packages recompiled offline and staged into the repo.")


def _makepkg_one(builder: str, recipe_dir: Path, offline: bool = False) -> None:
    """Run makepkg in recipe_dir as the unprivileged builder. -f force rebuild,
    -c clean, --skippgpcheck NOT passed (sig checks must run for librewolf); -s
    would auto-install deps via sudo which the builder lacks, so deps were
    installed on the host already and we pass --nodeps=False by omitting -s and
    relying on the host having them.

    offline: an offline --full-compile RERUN. Then makepkg MUST NOT re-fetch or
    re-extract: --noextract makes it reuse the ALREADY-extracted $srcdir tree
    (the bsys6 checkout plus the Firefox source `make fetch` pulled into it last
    run) and just re-run build()+package(). Without --noextract, `makepkg -f`
    would re-extract the source=() array -- re-checking-out librewolf-bsys6 and
    DESTROYING that fetched Firefox tree -- and then build() (whose `make fetch`
    is gated off by AZARCH_OFFLINE) would have no source. --nocheck skips the
    (absent) check() phase. AZARCH_OFFLINE=1 is read by the recipe's build() to
    skip `make fetch`. On the default/online path (offline=False) none of this
    applies and the invocation is byte-identical to before."""
    # --holdver: don't let makepkg bump pkgver from VCS. --noconfirm: unattended.
    cmd = ["makepkg", "-f", "--noconfirm", "--needed", "--noprogressbar"]
    if offline:
        cmd += ["--holdver", "--noextract", "--nocheck"]
    env = dict(os.environ)
    if offline:
        env["AZARCH_OFFLINE"] = "1"  # recipe build() skips `make fetch` when set
    # Keep makepkg's build/cache under the scratch dir, not the builder's $HOME,
    # so a root build doesn't scatter files and offline reruns are clean.
    env["PKGDEST"] = str(recipe_dir)
    env["SRCDEST"] = str(recipe_dir / ".src")
    env["BUILDDIR"] = str(recipe_dir / ".build")
    src_dir = recipe_dir / ".src"
    build_dir = recipe_dir / ".build"
    src_dir.mkdir(exist_ok=True)
    build_dir.mkdir(exist_ok=True)

    if paths.is_root():
        # These dirs are created here as ROOT, AFTER build_own_packages' one-shot
        # chown of the scratch tree already ran, so they're root-owned. makepkg
        # runs as the unprivileged builder below and would abort with "You do not
        # have write permission for the directory $BUILDDIR". Chown them (and the
        # recipe dir itself, since PKGDEST is recipe_dir and makepkg writes the
        # built package there) to the builder before handing off.
        _run(["chown", "-R", f"{builder}:{builder}",
              str(recipe_dir), str(src_dir), str(build_dir)], check=True)
        # Re-exec as the builder, preserving the makepkg env vars. AZARCH_OFFLINE is
        # only present in env on the offline path, so the online envargs list is
        # unchanged (the key is simply absent).
        keys = ("PKGDEST", "SRCDEST", "BUILDDIR")
        if offline:
            keys += ("AZARCH_OFFLINE",)
        envargs = [f"{k}={env[k]}" for k in keys]
        full = ["sudo", "-u", builder, "env", *envargs, *cmd]
        # run_teed pumps the compile's stdout/stderr through the _Tee so the
        # multi-hour gcc/rustc output lands in full.log in real time instead of
        # vanishing into the inherited PTY (whose `script` capture goes to /dev/null).
        rc = logstream.run_teed(full, cwd=str(recipe_dir))
    else:
        rc = logstream.run_teed(cmd, cwd=str(recipe_dir), env=env)

    if rc != 0:
        raise MakepkgError(f"makepkg failed for {recipe_dir.name} (exit {rc})")
