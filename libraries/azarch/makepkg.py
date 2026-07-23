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

from . import emit, paths
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
        # avoids reparsing bash arrays in Python.
        out = subprocess.run(
            ["bash", "-c", f'source "{pb}"; printf "%s\\n" "${{makedepends[@]}}" "${{depends[@]}}"'],
            capture_output=True, text=True,
        ).stdout
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
    r = _run(sudo + ["pacman", "-S", "--needed", "--noconfirm", *deps])
    if r.returncode != 0:
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
    # Run gpg AS the builder (its keyring is what makepkg checks).
    def as_builder(args: list[str]) -> subprocess.CompletedProcess:
        if paths.is_root():
            return _run(["sudo", "-u", builder, *args])
        return _run(args)

    for ks in ("hkps://keyserver.ubuntu.com", "hkps://keys.openpgp.org"):
        r = as_builder(["gpg", "--keyserver", ks, "--recv-keys", key])
        if r.returncode == 0:
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
        if _repo_has_all(pkg_repo, names):
            print("    [+] Own packages already present in the offline repo -- skipping makepkg.")
            progress(1000)
            return
        raise MakepkgError(
            f"Offline build but the built package(s) {', '.join(names)} are not in the cache.\n"
            "    Rebuild once online (FORCE_ONLINE=1) or wipe cache/ so they get built."
        )

    scratch = paths.CACHEDIR / "makepkg"
    if scratch.exists():
        _run(sudo + ["rm", "-rf", str(scratch)], check=False)
    scratch.mkdir(parents=True, exist_ok=True)

    dirs = _emit_recipes(scratch, full_compile)
    progress(80)

    builder = _ensure_builder_user()
    deps = _collect_makedepends(dirs)
    _install_host_build_deps(sudo, deps, offline)
    progress(200)

    _import_librewolf_key(builder, sudo, offline)
    progress(260)

    # The builder must own the scratch tree to write src//pkg/ during makepkg.
    if paths.is_root():
        _run(["chown", "-R", f"{builder}:{builder}", str(scratch)], check=True)

    total = len(dirs)
    for i, d in enumerate(dirs):
        name = d.name
        phase(f"makepkg: building {name}")
        print(f"[*] makepkg: building {name} ({i + 1}/{total})...")
        _makepkg_one(builder, d)
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
    _run(sudo + ["chown", "-R", f"{own_uid}:{own_gid}", str(pkg_repo)], check=False)
    progress(1000)
    print("[✓] Az'arch's own packages built and staged into the offline repo.")


def _makepkg_one(builder: str, recipe_dir: Path) -> None:
    """Run makepkg in recipe_dir as the unprivileged builder. -f force rebuild,
    -c clean, --skippgpcheck NOT passed (sig checks must run for librewolf); -s
    would auto-install deps via sudo which the builder lacks, so deps were
    installed on the host already and we pass --nodeps=False by omitting -s and
    relying on the host having them."""
    # --holdver: don't let makepkg bump pkgver from VCS. --noconfirm: unattended.
    cmd = ["makepkg", "-f", "--noconfirm", "--needed", "--noprogressbar"]
    env = dict(os.environ)
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
        # Re-exec as the builder, preserving the makepkg env vars.
        envargs = [f"{k}={env[k]}" for k in ("PKGDEST", "SRCDEST", "BUILDDIR")]
        full = ["sudo", "-u", builder, "env", *envargs, *cmd]
        r = subprocess.run(full, cwd=str(recipe_dir))
    else:
        r = subprocess.run(cmd, cwd=str(recipe_dir), env=env)

    if r.returncode != 0:
        raise MakepkgError(f"makepkg failed for {recipe_dir.name} (exit {r.returncode})")
