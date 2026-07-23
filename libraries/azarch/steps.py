"""The ordered build steps: assemble the archiso profile tree from the
config-as-Python modules, cache/stage the packages, and run mkarchiso.

This replaces the long body of the old compile.sh. Each `bar.step(...)` is one
milestone, named for the archiso/pacman/systemd artifact it produces. Trivial
overlay-emit steps are near-instant; the two giants (package cache, mkarchiso)
drive live sub-progress. Ownership handback and the PTY/signal machinery live in
build.py; this module is pure build logic.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import signal

from . import emit, logstream, makepkg, packages, paths
from .config import calamares, desktop, fastfetch, installer, locale, pacman, profile, system
from .progress import ProgressBar

# Weights: setup/emit steps carry real weight so the bar visibly advances through
# them (at weight 1 they were ~2% of the whole bar and looked frozen); the giants
# are still the bulk, sized from real log spans. Keep in sync with steps below:
# len(STEP_WEIGHTS) - 1 MUST equal the number of bar.step() calls in run(). The
# final THREE weights belong, in order, to: the package-cache giant, the makepkg
# stage (our own calamares/librewolf; heavy in the default tier, VERY heavy with
# --full-compile), and the mkarchiso giant.
STEP_WEIGHTS = [0] + [8] * 12 + [250, 120, 270]

# PGID of the currently-running mkarchiso child (0 = none). mkarchiso is spawned in
# its own session/process group so the signal handler can kill THAT group (and all
# its pacstrap descendants) without touching our own shell -- see build.on_signal.
_ACTIVE_CHILD_PGID = 0


def _sudo() -> list[str]:
    # `-n` (non-interactive) so a chown/unmount during Ctrl-C teardown after the
    # sudo timestamp expired fails fast instead of blocking on a password prompt.
    return [] if paths.is_root() else ["sudo", "-n"]


def kill_active_child(sudo: list[str]) -> None:
    """Kill the running mkarchiso child's process group (TERM then KILL). Root
    children (pacstrap under mkarchiso on a native run) are reaped via sudo."""
    pgid = _ACTIVE_CHILD_PGID
    if pgid <= 0:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        if sudo:
            subprocess.run(sudo + ["kill", f"-{sig}", f"-{pgid}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def run(bar: ProgressBar, offline: bool, reclaim_after_mkarchiso, full_compile: bool = False) -> Path:
    """Execute all steps; return the path to the built ISO. Raises on failure.

    full_compile: when True, Az'arch's own packages (librewolf) are compiled from
    source instead of repackaged from the verified upstream tarball. Passed to the
    makepkg stage below.
    """
    W = paths.WORKDIR
    airootfs = W / "airootfs"
    ea = airootfs / "root/azarch"  # the azarch payload dir baked into the ISO
    sudo = _sudo()

    # 1 -- Reset build workspace
    bar.step("Reset build workspace")
    _unmount_worktree(sudo)
    paths.BUILDDIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(sudo + ["rm", "-rf", str(W)], check=False)
    W.mkdir(parents=True, exist_ok=True)
    os.chdir(W)

    # 2 -- Sync host toolchain
    bar.step("Sync host toolchain")
    _check_host_deps(sudo, offline)

    # 3 -- Scaffold releng profile
    bar.step("Scaffold releng profile")
    _copy_releng(W)

    # 4 -- Brand boot menus (systemd-boot + syslinux)
    bar.step("Brand boot menus (systemd-boot, syslinux)")
    # Overwrite the releng UEFI entries in place (same filenames) rather than adding
    # differently-named ones alongside them -- otherwise the menu shows BOTH the stock
    # "Arch Linux install medium" entries AND ours, i.e. duplicated rows all reading
    # "Arch Linux". Writing over 01-archiso-linux.conf / 02-archiso-speech-linux.conf
    # replaces them with the rebranded Az'arch entries.
    emit.write_text(W / "efiboot/loader/entries/01-archiso-linux.conf", system.BOOT_UEFI_LINUX)
    emit.write_text(W / "efiboot/loader/entries/02-archiso-speech-linux.conf", system.BOOT_UEFI_SPEECH)
    emit.write_text(W / "syslinux/archiso_sys-linux.cfg", system.BOOT_BIOS_SYSLINUX)
    # Overlay the syslinux (BIOS) menu head so its `MENU TITLE` reads Az'arch instead
    # of the releng default "Arch Linux".
    emit.write_text(W / "syslinux/archiso_head.cfg", system.BOOT_BIOS_SYSLINUX_HEAD)

    # 5 -- Stage pacstrap package manifest
    bar.step("Stage pacstrap package manifest")
    emit.copy_data("packages.x86_64", W / "packages.x86_64")

    # 6 -- Provision airootfs accounts (users/groups + /home/main, chowned for the
    # autologin `main` user the getty drops straight into on the live console).
    bar.step("Provision airootfs accounts (console autologin)")
    emit.write_text(airootfs / "etc/passwd", system.PASSWD)
    emit.write_text(airootfs / "etc/shadow", system.SHADOW, mode=0o600)
    emit.write_text(airootfs / "etc/gshadow", system.GSHADOW, mode=0o600)
    emit.write_text(airootfs / "etc/group", system.GROUP)
    home = airootfs / "home/main"
    emit.mkdir(home)
    subprocess.run(sudo + ["chown", "-R", "1000:998", str(home)], check=False)

    # 7 -- Overlay branding and locale into airootfs.
    # One coherent overlay-population act: locale setup-script + service, the fastfetch
    # logo, and the os-release/hostname rebrand.
    bar.step("Overlay branding and locale")

    # locale: first-run setup script + the systemd unit that runs it.
    emit.write_exec(ea / "setup-locale.sh", locale.setup_locale_sh())
    emit.write_text(airootfs / "etc/systemd/system/locale-setup.service", system.LOCALE_SETUP_SERVICE)

    # the azarch fastfetch logo/config for the live (and installed) user.
    _emit_fastfetch(ea, home)

    # os-release rebrand:
    # Live ISO: the build pacman.conf NoExtracts usr/lib/os-release (config/pacman.py)
    # so the `filesystem` package's stock "Arch Linux" file never lands. We must NOT
    # pre-place our replacement in the airootfs overlay, though: mkarchiso copies the
    # overlay into the work root BEFORE pacstrap, and pacman's file-conflict check
    # (which runs before extraction and is NOT suppressed by NoExtract) then aborts
    # with "filesystem: usr/lib/os-release exists in filesystem". Instead we plant it
    # AFTER pacstrap via customize_airootfs.sh -- the same after-pacstrap ordering the
    # on-disk installer already uses (config/installer.py copies it into /mnt post-
    # pacstrap). The branded file is staged read-only under root/azarch/os-release and
    # the hook copies it into place inside the pacstrapped rootfs.
    emit.write_text(ea / "os-release", system.OS_RELEASE)
    emit.write_exec(airootfs / "root/customize_airootfs.sh", system.CUSTOMIZE_AIROOTFS)
    # Overlay the releng `archiso` hostname with `azarch` (prompt + fastfetch title).
    emit.write_text(airootfs / "etc/hostname", system.HOSTNAME)

    # 8 -- Overlay the Openbox live desktop + Calamares installer config.
    # The graphical live session (Manjaro-style): user configs go to BOTH the live
    # `main` home AND /etc/skel (so a Calamares-created user on the installed system
    # inherits the same desktop). The tty1 autologin override switches the releng
    # default (autologin root) to autologin `main`, whose .bash_profile execs startx.
    # The Calamares config tree lands under /etc/calamares.
    bar.step("Overlay Openbox desktop and Calamares config")
    _emit_desktop(airootfs, home)
    _emit_calamares(airootfs)
    _emit_tty1_autologin(airootfs)

    # 9 -- Stage installed-system pacman and pkgs service.
    # The package-management unit of the installed system: its /etc/pacman.conf, the
    # live-session setup-pkgs.sh, and the pkgs-setup.service that runs it.
    bar.step("Stage installed-system pacman and pkgs service")
    emit.write_text(airootfs / "etc/pacman.conf", pacman.installer_base_conf())
    emit.write_exec(ea / "setup-pkgs.sh", installer.setup_pkgs_sh())
    emit.write_text(airootfs / "etc/systemd/system/pkgs-setup.service", system.PKGS_SETUP_SERVICE)

    # 9 -- Enable systemd units and sudoers policy.
    # Activation/policy at profile finalization: the *.target.wants symlinks that enable
    # the units, plus the sudoers.d drop-ins.
    bar.step("Enable systemd units and sudoers policy")
    _link_services(airootfs)
    emit.write_text(airootfs / "etc/sudoers.d/00-rootpw", system.SUDOERS_ROOTPW, mode=0o440)
    emit.write_text(airootfs / "etc/sudoers.d/00-main", system.SUDOERS_MAIN, mode=0o440)

    # 10 -- Emit profiledef and installer payload.
    # profiledef.sh (archiso metadata at the PROFILE ROOT, not airootfs) plus the
    # first-boot script/service/conf. Calamares (auto-launched from the Openbox
    # session, step 8) is now the PRIMARY installer; the legacy bash installer is
    # still emitted to the Desktop as a terminal fallback for rescue use.
    bar.step("Emit profiledef and installer payload")
    emit.write_exec(W / "profiledef.sh", profile.profiledef_sh())
    emit.write_exec(home / "Desktop/azarch-iso-installer.sh", installer.installer_sh())
    emit.write_exec(ea / "first-boot-setup.sh", installer.first_boot_sh())
    emit.write_text(ea / "first-boot-setup.service", installer.first_boot_service())
    emit.write_text(ea / "first-boot-setup.conf", installer.first_boot_conf())

    # 11 -- Resolve build pacman.conf and mirrors.
    # Writes the pacstrap/mkarchiso build pacman.conf, injects the persistent CacheDir,
    # probes mirrors, and switches to the local file:// repo when offline. A distinct
    # pacman-prep stage that gates the cache download below.
    bar.step("Resolve build pacman.conf and mirrors")
    _write_build_pacman_conf(W, offline, bar)

    # 12 -- Warm pacman cache and stage installer payload (GIANT, weight 250).
    # pacman -Sw builds/indexes the local repo (drives bar.sub sub-progress), then the
    # on-disk installer's package manifest + pacman confs + chroot-setup.sh are staged.
    bar.step("Warm pacman cache and stage installer payload")
    packages.build_cache(W, paths.CACHEDIR, offline, bar.sub, bar.phase, full_compile)
    bar.sub_done()
    bar._arm(); bar.draw()
    # stage the installer-side payload the on-disk installer needs
    emit.copy_data("packages.x86_64", ea / "packages.x86_64")
    emit.write_text(ea / "pacman-base-conf/pacman.conf", pacman.installer_base_conf())
    emit.write_text(ea / "pacstrap-azarch-conf/pacman.conf", pacman.installer_pacstrap_conf())
    emit.write_exec(ea / "chroot-setup.sh", installer.chroot_setup_sh())

    # 13 -- Build Az'arch's OWN packages and fold them into the offline repo
    # (GIANT-ish, weight 120; MUCH heavier under --full-compile). BOTH calamares
    # and librewolf are built here in EVERY tier -- neither is in an Arch repo
    # (librewolf never was; calamares was dropped from extra/, now AUR-only, so
    # step 12 can no longer fetch it). Default tier: calamares from source
    # (sha256-verified) + librewolf by repackaging the verified upstream binary
    # tarball. --full-compile: calamares from source + librewolf from Firefox
    # source. Whatever is built is dropped into cache/pkgs/repo/, then we
    # RE-reconcile the index and RE-stage the repo into airootfs so mkarchiso's
    # pacstrap (and the on-disk installer) can install them.
    bar.step("Build Az'arch's own packages (calamares, librewolf)")
    makepkg.build_own_packages(offline, full_compile, bar.sub, bar.phase)
    bar.sub_done()
    bar._arm(); bar.draw()
    _refold_own_packages_into_repo(W, full_compile)

    # 14 -- Assemble ISO (GIANT, weight 270).
    # mkarchiso: pacstrap into airootfs, mksquashfs, checksum, build the .iso
    # (drives bar.sub sub-progress via _drive_mkarchiso_progress).
    bar.step("Assemble ISO (mkarchiso)")
    iso = _run_mkarchiso(sudo, W, bar, reclaim_after_mkarchiso)
    return iso


# --- helpers ---------------------------------------------------------------

def _emit_desktop(airootfs: Path, home: Path) -> None:
    """Emit the Openbox live-session files. Each PLAN entry has an absolute dest
    (either under /home/main for the live user or an absolute system path). User
    files are ALSO copied into /etc/skel so a Calamares-created user on the
    installed system inherits the same desktop (Manjaro-style). The /home/main
    tree is chowned 1000:998 by step 6 / the post-emit chown below."""
    skel = airootfs / "etc/skel"
    for entry in desktop.emit_plan():
        content = entry["builder"]()
        dest_abs = entry["dest"]          # e.g. "/home/main/.xinitrc" or "/usr/local/bin/..."
        mode = entry["mode"]
        # airootfs-relative destination (strip leading '/').
        emit.write_text(airootfs / dest_abs.lstrip("/"), content, mode=mode)
        # Mirror HOME-relative user files into /etc/skel for installed-system users.
        if entry["owner"] == "home" and dest_abs.startswith(desktop.HOME + "/"):
            rel = dest_abs[len(desktop.HOME) + 1:]   # path under the home dir
            emit.write_text(skel / rel, content, mode=mode)
    # re-assert ownership of the live user's tree (new files were added under it).
    subprocess.run(_sudo() + ["chown", "-R", "1000:998", str(home)], check=False)


def _emit_calamares(airootfs: Path) -> None:
    """Write the whole Calamares config tree under /etc/calamares."""
    base = airootfs / "etc/calamares"
    for rel, content in calamares.emit_map().items():
        emit.write_text(base / rel, content)


def _emit_tty1_autologin(airootfs: Path) -> None:
    """Override the releng getty@tty1 autologin so it logs in `main` (not root).
    The graphical session runs X as the unprivileged live user; `main`'s
    .bash_profile then execs startx. Root autologin would run the whole desktop
    as root, which Calamares and Qt both dislike."""
    dropin = airootfs / "etc/systemd/system/getty@tty1.service.d/autologin.conf"
    emit.write_text(dropin, system.GETTY_TTY1_AUTOLOGIN)


def _refresh_own_in_pacstrap_cache(full_compile: bool = False) -> None:
    """Refresh the packages the makepkg stage BUILT (calamares and librewolf, both
    tiers) IN the persistent pacstrap CacheDir (cache/pacman-pkg) so mkarchiso's
    pacstrap always reads the freshly-rebuilt bytes from cache -- never a stale
    copy, and never a file:// re-fetch. The downloaded Arch packages are immutable
    per version and handled by the normal cache path, so they are deliberately NOT
    touched here.

    Two failure modes this closes, both caused by makepkg NOT being reproducible
    bit-for-bit (a rebuild of calamares/librewolf yields a byte-different
    *.pkg.tar.zst under the SAME versioned filename, so its checksum in
    pacstrap-azarch-repo.db changes each build):

      1. Stale-checksum abort. pacstrap consults its CacheDir BEFORE the file://
         repo. A same-named file left by a PRIOR build fails pacstrap's checksum
         check ("invalid or corrupted package"); on /dev/null stdin it can't answer
         the "delete it? [Y/n]" prompt and aborts the whole ISO build.

      2. file:// max-file-size abort. Simply DELETING the stale copy (an earlier
         fix) forced pacstrap to re-fetch from the file:// repo -- but pacman caps
         a file:// transfer at the DB-recorded size and rejects a package that hits
         exactly that ceiling ("Exceeded the maximum allowed file size"), which the
         138 MB librewolf package does. Observed exactly this.

    Overwriting the cached copy in place with the current repo bytes gives pacstrap
    a VALID cache hit: the checksum matches (correct content) and no download
    happens (so the size cap never applies). The downloaded Arch packages are
    untouched -- they're immutable for a given version, so their cached copy always
    matches."""
    cache = paths.PACSTRAP_CACHE
    repo = paths.PKG_REPO
    if not cache.is_dir():
        return
    from .makepkg import produced_names
    PRODUCED = produced_names(full_compile)          # this tier: which to REFRESH (copy in)
    # Every name the makepkg stage can EVER produce. Both tiers build the same set
    # (calamares + librewolf) now, so this union equals PRODUCED -- it is kept as a
    # union so that if the tiers ever diverge again, cleanup still spans BOTH sets.
    # It must: a byte-different rebuild under the SAME version-rel filename left in
    # this CacheDir by a prior run would fail pacstrap's checksum check, and with
    # stdin on /dev/null pacstrap cannot answer the delete prompt -- the ISO build
    # aborts. (Filename equality means a name-only staleness check would MISS it; we
    # compare CONTENT below.)
    ALL_OWN = tuple(sorted(set(produced_names(True)) | set(produced_names(False))))
    import hashlib

    def _sha(p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    sudo = _sudo()
    # Cleanup pass (over the UNION of tiers). For every own-name, drop any cached copy
    # that does not byte-match the copy currently in the repo -- whether it is a
    # superseded VERSION (different filename) or a same-version file with different
    # BYTES (a non-reproducible makepkg rebuild yields new bytes under the same
    # versioned filename). A repo copy with matching bytes
    # is left for the refresh pass. A cached file whose name isn't in the repo at all
    # (name fully retired) is dropped too. This gives pacstrap either a valid cache hit
    # or a clean miss (it then reads the correct file from the file:// repo), never a
    # checksum-mismatch abort.
    for name in ALL_OWN:
        repo_by_name = {p.name: p for p in repo.glob(f"{name}-*.pkg.tar.zst")}
        for cached in cache.glob(f"{name}-*.pkg.tar.zst"):
            repo_copy = repo_by_name.get(cached.name)
            if repo_copy is not None and _sha(cached) == _sha(repo_copy):
                continue  # correct bytes already cached -> keep
            subprocess.run(sudo + ["rm", "-f", str(cached), str(cached) + ".sig"],
                           check=False)
    # Refresh pass (this tier's built packages only): mirror each current repo copy of a
    # TIER-BUILT package into the cache when absent (the cleanup above removed any stale
    # one). Only makepkg-built packages need their bytes forced in place -- downloaded
    # Arch packages (default-tier calamares) are re-fetched from the file:// repo on the
    # clean miss the cleanup produced, so we do NOT copy them here (that would also hit
    # the file:// max-file-size cap that motivated in-place refresh for big librewolf).
    for name in PRODUCED:
        for repo_copy in repo.glob(f"{name}-*.pkg.tar.zst"):
            cached = cache / repo_copy.name
            if cached.is_file():
                continue  # cleanup kept it only if bytes already matched -> valid hit
            print(f"    [+] Refreshing {repo_copy.name} in pacstrap cache "
                  f"(rebuilt; syncing bytes so pacstrap gets a valid cache hit).")
            subprocess.run(sudo + ["cp", "-f", str(repo_copy), str(cached)], check=False)
            # keep a matching .sig alongside if the repo has one. The offline file://
            # repo runs SigLevel = Never (config/pacman.py) so pacstrap does not verify
            # it -- this copy is a harmless belt-and-braces, not load-bearing.
            sig = repo_copy.with_suffix(repo_copy.suffix + ".sig")
            if sig.is_file():
                subprocess.run(sudo + ["cp", "-f", str(sig), str(cache / sig.name)], check=False)


def _refold_own_packages_into_repo(W: Path, full_compile: bool = False) -> None:
    """After makepkg drops our built package(s) into cache/pkgs/repo/, re-reconcile
    the local repo index so those packages are in pacstrap-azarch-repo.db, then
    RE-stage the repo + db into the airootfs payload dir. build_cache already
    staged the Arch packages there; this overlays our built package(s) on top so
    mkarchiso's pacstrap and the on-disk installer resolve them from the same
    offline repo. full_compile decides which packages count as OUR built ones
    (default: librewolf only; full: calamares + librewolf)."""
    pkg_repo = paths.PKG_REPO
    pkg_db = paths.PKG_DB
    # Re-run the incremental index reconcile (delta: only the 2 new packages added).
    packages._reconcile_index(pkg_repo, lambda _p: None)
    # FORCE re-add of our OWN packages so the DB checksum tracks the just-rebuilt
    # file. _reconcile_index keys the delta by name-ver-rel: a rebuilt own package
    # keeps its version (e.g. librewolf-153.0.1-1) but makepkg is NOT reproducible,
    # so the *bytes* (hence the SHA256/CSIZE the .db records) change every build.
    # The delta sees the key already indexed and SKIPS it, leaving the DB pinned to
    # a PRIOR build's checksum while the repo file is the current one. pacstrap then
    # validates the current file against the stale DB checksum and aborts with
    # "invalid or corrupted package (checksum)" (observed exactly this on librewolf).
    # repo-add (no -n) overwrites the same-version entry, refreshing SHA256+CSIZE to
    # match the file on disk. Idempotent and cheap (2 packages).
    packages._readd_own_packages(pkg_repo, full_compile)
    # A prior build may have cached an OLDER byte-image of our built packages in the
    # persistent pacstrap CacheDir. Refresh them IN PLACE with the freshly-rebuilt
    # bytes so mkarchiso's pacstrap gets a valid cache hit -- avoiding both the
    # checksum-mismatch abort AND the file:// max-file-size abort a delete-and-
    # refetch would trigger on the 138 MB librewolf package.
    _refresh_own_in_pacstrap_cache(full_compile)
    # Re-stage into the airootfs payload the on-disk installer copies from.
    ea = W / "airootfs" / "root/azarch"
    final_db = ea / "pacstrap-azarch-db"
    final_cache = ea / "pacstrap-azarch-repo"
    final_db.mkdir(parents=True, exist_ok=True)
    final_cache.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cp", "-r", f"{pkg_db}/.", f"{final_db}/"], check=False)
    subprocess.run(["cp", "-r", f"{pkg_repo}/.", f"{final_cache}/"], check=False)


def _unmount_worktree(sudo) -> None:
    aw = paths.AIROOTFS
    if not aw.is_dir():
        return
    for m in ("proc", "sys", "dev", "run"):
        p = aw / m
        if subprocess.run(["mountpoint", "-q", str(p)]).returncode == 0:
            subprocess.run(sudo + ["umount", "-lf", str(p)], check=False)
    subprocess.run(sudo + ["umount", "-R", str(aw)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _check_host_deps(sudo, offline: bool) -> None:
    host_pkgs = ["archiso", "git", "base-devel", "go"]
    if subprocess.run(["pacman", "-Qq", *host_pkgs],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        print("    [+] Build-host dependencies already present, skipping sync (offline).")
        return
    if offline:
        sys.stderr.write(
            "[x] Missing build-host dependencies but the package cache is complete, so\n"
            "    this run must stay fully offline. Install them yourself:\n"
            f"    {'sudo ' if sudo else ''}pacman -Sy --needed {' '.join(host_pkgs)}\n"
            "    or re-run with FORCE_ONLINE=1 (or after 'git clean -Xdf').\n"
        )
        raise SystemExit(1)
    print("    [+] Installing missing build-host dependencies...")
    # Teed so the install's output reaches full.log live. Preserve the old
    # check=True raise-on-failure: run_teed returns the exit code, so raise here.
    cmd = sudo + ["pacman", "-Sy", "--noconfirm", "--needed", *host_pkgs]
    rc = logstream.run_teed(cmd)
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


def _copy_releng(W: Path) -> None:
    src = Path("/usr/share/archiso/configs/releng")
    if not src.is_dir():
        raise SystemExit(f"[x] archiso releng profile not found at {src}; is archiso installed?")
    emit.copy_tree(src, W)


def _emit_fastfetch(ea: Path, home: Path) -> None:
    """Write the azarch fastfetch config + Az' logo for the live user, and stage
    a copy under root/azarch/fastfetch so the on-disk installer can replant it
    into the installed user's ~/.config/fastfetch."""
    cfg = home / ".config/fastfetch"
    emit.write_text(cfg / "config.jsonc", fastfetch.config_jsonc())
    emit.write_text(cfg / fastfetch.LOGO_FILENAME, fastfetch.logo_txt())
    # staged copy for the installer to plant on the installed system
    staged = ea / "fastfetch"
    emit.write_text(staged / "config.jsonc", fastfetch.config_jsonc())
    emit.write_text(staged / fastfetch.LOGO_FILENAME, fastfetch.logo_txt())


def _link_services(airootfs: Path) -> None:
    # Graphical live medium WITHOUT a display manager: the tty1 autologin (overridden
    # to `main`) drops into a login shell whose ~/.bash_profile execs startx -> Openbox
    # -> Calamares. So there is deliberately NO display-manager unit and NO
    # graphical.target.wants here; we only enable the multi-user daemons and the two
    # azarch oneshots. X is started from the shell, not by systemd.
    base = airootfs / "etc/systemd/system"
    emit.mkdir(base / "multi-user.target.wants")
    for svc in ("NetworkManager.service", "bluetooth.service", "org.cups.cupsd.service"):
        emit.link(f"/usr/lib/systemd/system/{svc}", base / f"multi-user.target.wants/{svc}")
    emit.link("/etc/systemd/system/locale-setup.service", base / "multi-user.target.wants/locale-setup.service")
    emit.link("/etc/systemd/system/pkgs-setup.service", base / "multi-user.target.wants/pkgs-setup.service")


def _switch_offline(W: Path, conf: str, localrepo: Path) -> None:
    """Drop stale partial downloads, rewrite to the local file:// repo, write it,
    and assert the rewrite actually landed (parity with the old bash guards)."""
    # A file:// directory listing must not trip over a zero-byte *.part left by an
    # interrupted -Sw; drop them first (harmless if none exist).
    for part in localrepo.glob("*.part"):
        part.unlink(missing_ok=True)
    conf = pacman.switch_to_local_repo(conf, str(localrepo))
    emit.write_text(W / "pacman.conf", conf)
    if "[pacstrap-azarch-repo]" not in conf:
        sys.stderr.write(
            "    [!] Offline conf rewrite did not inject the local repo -- check config/pacman.py.\n"
        )


def _write_build_pacman_conf(W: Path, offline: bool, bar: ProgressBar) -> None:
    """Write the profile pacman.conf mkarchiso's pacstrap uses. Injects the
    persistent CacheDir, and (offline) rewrites to the local file:// repo."""
    paths.PACSTRAP_CACHE.mkdir(parents=True, exist_ok=True)
    conf = pacman.build_profile_conf(cachedir=str(paths.PACSTRAP_CACHE) + "/")
    localrepo = paths.PKG_REPO
    if offline:
        print(f"    [+] Complete cache present -- building OFFLINE from {localrepo} (no mirror).")
        _switch_offline(W, conf, localrepo)
    else:
        _probe_and_maybe_switch(W, conf, localrepo, bar)


def _probe_and_maybe_switch(W: Path, conf: str, localrepo: Path, bar: ProgressBar) -> None:
    sudo = _sudo()
    probe = W / ".netprobe-db"
    subprocess.run(["rm", "-rf", str(probe)], check=False)
    (probe / "sync").mkdir(parents=True, exist_ok=True)
    # write the network-repo conf first so the probe uses the exact mirror set.
    emit.write_text(W / "pacman.conf", conf)
    ok = subprocess.run(
        sudo + ["pacman", "-Sy", "--config", str(W / "pacman.conf"), "--dbpath", str(probe),
                "--cachedir", str(probe), "--disable-sandbox", "--noconfirm"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if ok:
        print("    [+] Mirrors reachable -- building online (new packages will be fetched).")
        # Online build still needs the LOCAL repo for Az'arch's own packages
        # (calamares, librewolf) -- they exist on no mirror. Append it alongside
        # the network repos so pacstrap resolves Arch pkgs from mirrors and ours
        # from file://. The packages themselves are dropped in by the makepkg step
        # (13) before mkarchiso (14) runs.
        conf = pacman.append_local_repo(conf, str(localrepo))
        emit.write_text(W / "pacman.conf", conf)
    elif paths.LOCALREPO_INDEX.exists():
        print(f"    [!] Mirrors unreachable -- building OFFLINE from {localrepo}.")
        _switch_offline(W, conf, localrepo)
    else:
        sys.stderr.write(
            f"    [!] Mirrors unreachable and no local repo cached at {localrepo} --\n"
            "        run once online to populate the cache, then offline rebuilds work.\n"
        )
    subprocess.run(["rm", "-rf", str(probe)], check=False)


def _run_mkarchiso(sudo, W: Path, bar: ProgressBar, reclaim_after) -> Path:
    # temp dir cleanup (matches the old "Cleaning up temp directory" step)
    subprocess.run(["rm", "-rf", str(W / ".temp")], check=False)
    env = dict(os.environ)
    # Fixes sporadic "xz uncompress failed with error code 9" (kept from old build).
    env["MKSQUASHFS_OPTIONS"] = "-processors 4"
    # Binary pipe on purpose: _drive_mkarchiso_progress wraps it in a TextIOWrapper
    # with newline="" so it can split on BOTH \r and \n (pacman redraws with \r).
    # text=True here would hand us a pre-decoded stream that TextIOWrapper rejects.
    # start_new_session=True puts mkarchiso (and its pacstrap children) in their OWN
    # process group so a Ctrl-C can group-kill THEM without hitting our shell.
    global _ACTIVE_CHILD_PGID
    # stdin from /dev/null: pacstrap under mkarchiso hits the `xorg` package group and
    # prints "Enter a selection (default=all):" on stdin. With no input it stalls for a
    # minute before defaulting; feeding EOF makes it take default=all immediately
    # instead of hanging.
    proc = subprocess.Popen(
        sudo + ["mkarchiso", "-v", "-w", str(W / "work"), "-o", str(paths.BUILDDIR), str(W)],
        env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
    )
    _ACTIVE_CHILD_PGID = proc.pid  # PID == PGID for a session leader
    try:
        _drive_mkarchiso_progress(proc, bar)
        rc = proc.wait()
    finally:
        _ACTIVE_CHILD_PGID = 0
    bar.sub_done()
    # immediate reclaim: unmount, then hand the work tree back while sudo is fresh.
    _unmount_worktree(sudo)
    reclaim_after()
    if rc != 0:
        raise SystemExit(f"[x] mkarchiso failed (exit {rc})")
    isos = sorted(paths.BUILDDIR.glob("*.iso"))
    if not isos:
        raise SystemExit("[x] ISO build failed: no .iso found in output/")
    return isos[0]


# pacman phase -> (base, span) sub-band within 20..820 for live mkarchiso progress.
_PACMAN_BANDS = {
    "checking keys in keyring": (20, 90),
    "checking package integrity": (110, 70),
    "loading package files": (180, 20),
    "checking for file conflicts": (200, 20),
    "checking available disk space": (220, 20),
    "installing": (240, 580),
    "upgrading": (240, 580),
    "reinstalling": (240, 580),
    "downgrading": (240, 580),
}


def _drive_mkarchiso_progress(proc, bar: ProgressBar) -> None:
    """Parse mkarchiso/pacstrap live output and drive the bar. pacman redraws its
    progress with carriage returns (not newlines), so we split on BOTH \\r and \\n
    to see each (N/M) frame live.

    Each line goes out two ways in ONE call via the stdout tee's write_split: a
    width-CLIPPED copy to the terminal (so a long line does not wrap and desync the
    pinned bar's scroll region) and the FULL untruncated line to full.log. A prior
    change wrote the clipped copy through plain stdout.write, which fed the SAME
    truncated text to the log too -- silently cutting the tail off every wide
    mkarchiso line in full.log. write_split keeps the two independent so the log is
    complete while the terminal stays clip-safe."""
    import io
    import re

    frame = re.compile(
        r"\(\s*(\d+)/(\d+)\)\s+(" + "|".join(re.escape(k) for k in _PACMAN_BANDS) + r")"
    )
    inpac = False
    reader = io.TextIOWrapper(proc.stdout, encoding="utf-8", errors="replace", newline="")
    buf = ""

    # Heartbeat: pacman/mksquashfs suppress their (N/M) progress frames when their
    # output is not a TTY (it is a pipe here), so whole phases -- pacstrap install and
    # the minute-long SquashFS pack -- produce many log lines but no parseable frame,
    # and the bar froze between milestone jumps. Between two milestones we creep toward
    # (but never reach) the next milestone, one notch per output line, so the bar keeps
    # visibly moving even with no frames. `hb` holds (floor, ceil) for the live phase.
    hb = {"floor": 0, "ceil": 0, "at": 0}

    def creep() -> None:
        # asymptotic: close ~1/16 of the remaining gap to the ceiling per line.
        room = hb["ceil"] - max(hb["at"], hb["floor"])
        if room > 0:
            hb["at"] = max(hb["at"], hb["floor"]) + max(1, room // 16)
            bar.sub(hb["at"])

    def phase_span(floor: int, ceil: int) -> None:
        hb["floor"], hb["ceil"], hb["at"] = floor, ceil, floor

    def emit_line(line: str) -> None:
        nonlocal inpac
        if not line:
            return
        # Terminal gets the width-clipped line (no wrap -> the pinned bar stays put);
        # full.log gets the FULL line. write_split does both in one write via the tee.
        # If stdout is not the tee (e.g. logging not installed), fall back to a plain
        # clipped write so the terminal still behaves.
        writer = getattr(sys.stdout, "write_split", None)
        if writer is not None:
            writer(bar._clip(line) + "\n", line + "\n")
        else:
            sys.stdout.write(bar._clip(line) + "\n")
        if "Installing packages to" in line:
            inpac = True
            bar.sub(20)
            bar.phase("pacstrap: installing packages into airootfs")
            phase_span(20, 810)   # creep across the install phase, stop short of 820
        elif "Done! Packages installed" in line:
            inpac = False
            bar.sub(820)
            bar.phase("pacstrap done, running customize hooks")
            phase_span(840, 930)  # next visible work is SquashFS; creep toward it
        elif "Creating SquashFS image" in line:
            inpac = False
            bar.sub(840)
            bar.phase("mksquashfs: compressing root filesystem (slow)")
            phase_span(840, 925)  # the long silent pack: creep so the minute animates
        elif "Creating checksum file" in line:
            bar.sub(930)
            bar.phase("writing SquashFS checksum")
            phase_span(930, 958)
        elif "Creating ISO image" in line:
            bar.sub(960)
            bar.phase("xorriso: writing bootable ISO image")
            phase_span(960, 995)
        elif inpac and (m := frame.search(line)):
            n, mm, ph = int(m.group(1)), int(m.group(2)), m.group(3)
            base, span = _PACMAN_BANDS[ph]
            if mm > 0:
                bar.sub(base + n * span // mm)
        else:
            # no milestone, no frame -- keep the bar alive within the current phase.
            creep()

    while True:
        ch = reader.read(1)
        if not ch:
            break
        if ch in ("\n", "\r"):
            emit_line(buf)
            buf = ""
        else:
            buf += ch
    emit_line(buf)
