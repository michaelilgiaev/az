"""The compiler: assemble the archiso profile tree from the configuration-as-Python
modules, cache/stage the packages, run mkarchiso -- AND drive the whole build.

This is what the user means by "the compiler": the ordered steps that compile the
ISO. Each `bar.step(...)` is one milestone, named for the archiso/pacman/systemd
artifact it produces. Trivial overlay-emit steps are near-instant; the two giants
(package cache, mkarchiso) drive live sub-progress.

It is also the ENTRY POINT: `python3 -m compiler`. The thin compile.sh shim sets
up the PTY (via util-linux `script`) and primes sudo, then hands off here. The
high-level driver folded in below (formerly compiler.py) owns:

  * resolve the cache-first offline policy (cache_is_complete)
  * start the sudo keepalive + continuous ownership reclaim
  * run the ordered steps (run) with a live progress bar
  * on ANY exit (success / error / Ctrl-C) restore the terminal, unmount the work
    tree, and hand cache/ output/ logs/ back to the host user -- so nothing is
    ever left root-owned and locked.

The PTY/signal split: the PTY + sudo prime stay in compile.sh; here we handle
SIGINT/SIGTERM by terminating the child process group and running the teardown.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import signal

import downloader
import emit
import estimate
import logstream
import makepkg
import paths
from ownership import Ownership
from progress import ProgressBar
from packages.application_menu import application_menu
from packages.azarch import terminal_user_interface_build
from packages.azarch import default_applications
# timedate (the Flask home page) was folded into the librewolf package (LibreWolf lands on it),
# so its build wiring is imported from there now.
from packages.librewolf import timedate
from packages.passwords import packaging as passwords
from packages.backup import packaging as backup
from packages.hypervisor import packaging as hypervisor
from packages.calamares import calamares
from packages.calamares import locale
# The packages tree is DISCOVERABLE: `packages` is a namespace package (its directory has NO
# __init__.py), each package is a SUB-directory with an __init__.py, and
# package_discovery.with_emit_plan() finds every one exposing an emit_plan() (skipping any
# directory without an __init__.py, and the packages.x86_64 manifest file). The per-application
# tweaks below are collected that way in _emit_apps -- so adding packages/<newapp>/__init__.py
# with an emit_plan() ships it with no edit here, and removing one never leaves a dangling import.
import package_discovery
# The packages the compiler drives BY NAME (they expose more than emit_plan(), feed the desktop
# step, or hold vendored data/scripts), so they stay explicit imports:
#   openbox      -- the whole live desktop: many constants + emit_plan (feeds _emit_desktop)
#   librewolf    -- the browser-policy override (feeds _emit_desktop, not the app loop)
#   gedit        -- notepad-mode: emit_plan (app loop) PLUS the compiled libpeas plugin build
#   fastfetch    -- the branded logo/config (no emit_plan; config_jsonc()/logo_txt())
from packages import openbox
from packages import fastfetch
from packages import librewolf
from packages import gedit
# The home-directory LAYOUT data (dirs/links/trash; no emit_plan) was folded into the thunar
# package (Thunar's sidebar is built from the same list), so _emit_homedir reads it from there.
from packages.thunar import home_directory
# The per-application tweaks that expose ONLY emit_plan() (kitty, vlc, libreoffice, gimp, thunar,
# xviewer) are NOT imported by name -- _emit_apps discovers them. (thunar folds in the ~/Templates
# "Create Document" set from its templates submodule, so there is no standalone templates package.)
# The packages the
# compiler already drives explicitly (the desktop pair openbox/librewolf, plus application_menu,
# passwords, calamares, and the azarch guest command line interface) are excluded from that
# discovery so they are not emitted twice. See _EXPLICIT_PACKAGES below.
_DESKTOP_MODIFICATIONS = ("openbox", "librewolf")
# Every package the compiler emits BY NAME (so package_discovery.with_emit_plan() must skip them
# in the auto-discovered app loop). The desktop pair is emitted in _emit_desktop; application_menu
# and passwords have their own emit_plan() driven directly; calamares and azarch are not app-loop
# packages at all. Keeping this list here means a newly-dropped packages/<app>/ is auto-emitted
# unless it is added here on purpose.
_EXPLICIT_PACKAGES = ("openbox", "librewolf", "application_menu", "window_switcher", "passwords", "backup", "hypervisor", "calamares", "azarch")
import installer
import network_profile
import packages_manifest
import pacman
import profile
import system
import variants as _variants

# Weights: setup/emit steps carry real weight so the bar visibly advances through them
# (at weight 1 they were ~2% of the whole bar and looked frozen); the giants are still
# the bulk, sized from real log spans. The bar is now sized DYNAMICALLY from the selected
# variants (see weights_for), because the number of milestones depends on how many PRODUCT
# LINES and how many ISO passes are built:
#
#   * prelude (run once):  reset workspace + sync toolchain          -> 2 light steps
#   * per product LINE:    scaffold, boot-brand, manifest, accounts, -> 9 light steps
#                          branding, desktop, pacman-svc, units,
#                          installer-payload
#                          + warm cache (GIANT 250) + build own pkgs (GIANT 120)
#   * per ISO variant:     one mkarchiso pass                        -> GIANT 270 each
#
# The invariant compiler tests assert is exactly this composition, so it holds for any
# 1..8 selection. LIGHT/CACHE/MAKEPKG/MKARCHISO name the individual weights.
_LIGHT = 8
_CACHE_GIANT = 250
_MAKEPKG_GIANT = 120
_MKARCHISO_GIANT = 270
_PRELUDE_LIGHT_STEPS = 2      # reset workspace + sync toolchain (once)
# The light bar.step() calls inside _build_line (all weight _LIGHT): scaffold releng,
# brand boot, stage manifest, provision accounts, overlay branding, overlay desktop,
# stage pacman+pkgs service, enable units, emit installer payload, resolve pacman.conf.
# The two GIANT per-line steps (cache warm, own-package build) and the per-variant
# mkarchiso pass are counted separately in weights_for.
_PER_LINE_LIGHT_STEPS = 10


def _lines_in(build_variants: tuple) -> tuple[str, ...]:
    """The DISTINCT product lines present in the selected variants, in first-seen
    (variants.selected_variants) order -- headed before headless. One airootfs is built
    per line, and the bar is sized per line, so both weights_for and run() use this."""
    seen: list[str] = []
    for v in build_variants:
        if v.line not in seen:
            seen.append(v.line)
    return tuple(seen)


def weights_for(build_variants: tuple) -> list[int]:
    """The ProgressBar weight list for a given selection of variants.Variant. Index 0
    is the unused sentinel; then the prelude's light steps, then per DISTINCT LINE its
    light steps + the two cache/makepkg giants, then one mkarchiso giant per variant.
    len(result) - 1 == the number of bar.step() calls the build executes."""
    if not build_variants:
        build_variants = (_variants.Variant(),)
    n_lines = len(_lines_in(build_variants))
    n_variants = len(build_variants)
    weights = [0]
    weights += [_LIGHT] * _PRELUDE_LIGHT_STEPS
    for _ in range(n_lines):
        weights += [_LIGHT] * _PER_LINE_LIGHT_STEPS
        weights += [_CACHE_GIANT, _MAKEPKG_GIANT]
    weights += [_MKARCHISO_GIANT] * n_variants
    return weights


# Back-compat: the historical module constants. Tests and older call sites read
# compiler.VARIANTS (the two legacy keys) and compiler.STEP_WEIGHTS (the default single-
# line, single-headed-ISO build). The live build sizes its own bar via weights_for on the
# actually-selected variants; these defaults describe the no-flags build (one headed ISO).
VARIANTS = ("base", "sshd")
STEP_WEIGHTS = weights_for((_variants.Variant(),))

# PGID of the currently-running mkarchiso child (0 = none). mkarchiso is spawned in
# its own session/process group so the signal handler can kill THAT group (and all
# its pacstrap descendants) without touching our own shell -- see on_signal below.
_ACTIVE_CHILD_PGID = 0


def _sudo() -> list[str]:
    # `-n` (non-interactive) so a chown/unmount during Ctrl-C teardown after the
    # sudo timestamp expired fails fast instead of blocking on a password prompt.
    return [] if paths.is_root() else ["sudo", "-n"]


# --- Method A: the --ssh=<PASSWORD> opt-in for the sshd ISO ------------------
# The sshd ISO is OPT-IN: it is built ONLY when `--ssh="<PASSWORD>"` is supplied with
# a non-empty string, and that password becomes the `main` login credential (hashed
# into that variant's /etc/shadow). No flag / empty string -> no sshd ISO. This is the
# security posture from data/PROMPT.md DECISION 2: no default password is ever shipped;
# the SSH variant's credential must come from the operator at build time.

def parse_ssh_flag(argv: list[str]) -> str | None:
    """Pull the `--ssh=<PASSWORD>` value out of argv, or None if absent/empty.

    Mirrors the codebase's existing value-flag precedent (command_line_interface.py
    parses --server=/--ssh= via split("=", 1)[1]) so a password containing '=' is not
    truncated. An empty value (`--ssh=`) returns None: the flag "demands a string or it
    doesn't work" -- a blank string opts OUT of the sshd ISO rather than shipping a
    blank password.
    """
    for token in argv:
        if token.startswith("--ssh="):
            value = token.split("=", 1)[1]
            return value or None
    return None


def ssh_flag_present(argv: list[str]) -> bool:
    """True if the operator wrote the `--ssh` flag AT ALL -- bare (`--ssh`), empty
    (`--ssh=`, `--ssh=""`), or with a value (`--ssh=pw`).

    This is the OTHER half of three-state detection: parse_ssh_flag() reports the VALUE
    (None when blank/absent), and this reports PRESENCE. Together they let main() tell
    "operator asked for the ssh ISO but forgot the password" (present, no value -> HARD
    STOP with an explanation) apart from "operator never mentioned ssh" (absent -> build
    the base ISO only, which is correct). A token like `--sshfoo` is NOT the flag."""
    return any(t == "--ssh" or t.startswith("--ssh=") for t in argv)


def check_ssh_flag(argv: list[str]) -> str | None:
    """Validate the --ssh flag combination, returning an ERROR MESSAGE to abort on, or
    None to proceed.

    The rule the user asked for: the flag "demands a string or it doesn't work". So a
    PRESENT-but-blank flag (`--ssh`, `--ssh=`) is a hard error -- it must stop the build
    and EXPLAIN why, rather than silently building the base ISO only (the reported bug:
    `--ssh` with no password produced no ssh ISO AND no explanation). An ABSENT flag is
    fine (base-only). A flag WITH a value is fine (the ssh ISO builds).

    Pure (argv in, message out) so main() can print+exit on it and tests can assert it."""
    if ssh_flag_present(argv) and parse_ssh_flag(argv) is None:
        return (
            'The --ssh flag needs a password: --ssh="<PASSWORD>". You passed --ssh with '
            "no value, so there is nothing to set as the ssh ISO's login password. "
            "No default password is ever shipped, so the ssh ISO was NOT built and "
            "nothing was changed. Re-run with a real password, e.g. "
            'compile.sh --ssh="mysecret", or drop --ssh entirely to build just the base '
            "headed ISO (ssh disabled)."
        )
    return None


def ssh_password_hash(password: str) -> str:
    """Hash a build-time --ssh password into a sha-512 crypt hash ($6$...) for shadow.

    Never store or ship the plaintext: the image carries only this hash. Uses
    `openssl passwd -6`, present on every host that runs mkarchiso (openssl is a hard
    dependency of the archiso/pacman toolchain). Python's own crypt module is gone as
    of 3.13, so openssl is the single, portable source of a sha-512 crypt hash. A blank
    password is rejected -- the flag must resolve to a real credential before shadow.
    """
    if not password:
        raise ValueError("ssh_password_hash: refusing to hash an empty password")
    try:
        out = subprocess.run(
            ["openssl", "passwd", "-6", "-stdin"],
            input=password, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError(
            "ssh_password_hash: `openssl passwd -6` failed -- openssl is required to "
            f"hash the --ssh password ({e})."
        ) from e
    if not out.startswith("$6$"):
        raise RuntimeError(
            f"ssh_password_hash: openssl produced an unexpected hash (not $6$): {out!r}"
        )
    return out


# --- The --password / --user opt-in (a login password WITHOUT sshd) ----------
# --password sets `main` (or --user)'s login password the SAME way --ssh does (hashed
# into that ISO's /etc/shadow) but does NOT enable sshd. --ssh and --password are
# MUTUALLY EXCLUSIVE: if the operator wants ssh, they set the password via --ssh.

def parse_password_flag(argv: list[str]) -> str | None:
    """The `--password=<PW>` value, or None if absent/empty. Mirrors parse_ssh_flag:
    split('=', 1) so a '=' in the password is kept; a blank value opts out."""
    for token in argv:
        if token.startswith("--password="):
            return token.split("=", 1)[1] or None
    return None


def password_flag_present(argv: list[str]) -> bool:
    """True if `--password` appears at all (bare, empty, or with a value)."""
    return any(t == "--password" or t.startswith("--password=") for t in argv)


def check_password_flag(argv: list[str]) -> str | None:
    """Blank/bare --password is a hard error (it demands a string), mirroring --ssh."""
    if password_flag_present(argv) and parse_password_flag(argv) is None:
        return (
            'The --password flag needs a value: --password="<PASSWORD>". You passed '
            "--password with no value, so there is nothing to set as the login password. "
            "No default password is ever shipped, so nothing was changed. Re-run with a "
            'real password, e.g. compile.sh --password="mysecret", or drop --password to '
            "build the base (locked) ISO."
        )
    return None


def check_ssh_password_conflict(argv: list[str]) -> str | None:
    """--ssh and --password together is a hard error: they set the same credential two
    different ways. If the operator wants ssh, the password goes on --ssh."""
    if ssh_flag_present(argv) and password_flag_present(argv):
        return (
            "--ssh and --password conflict: both set the login password, but --ssh ALSO "
            'enables sshd. Pick one -- use --ssh="<PW>" if you want remote SSH (it sets '
            'the password too), or --password="<PW>" for a local login password with sshd '
            "OFF. No ISO was built."
        )
    return None


def parse_user_flag(argv: list[str]) -> str:
    """The login user name for --password/--ssh: the `--user=` value, or "main"."""
    for token in argv:
        if token.startswith("--user="):
            return token.split("=", 1)[1] or "main"
    return "main"


def user_without_password_warning(argv: list[str]) -> str | None:
    """A WARNING when --user is given without --ssh/--password: the name only takes effect
    together with a password flag (the live account stays `main`, locked, otherwise)."""
    present = any(t == "--user" or t.startswith("--user=") for t in argv)
    if present and not ssh_flag_present(argv) and not password_flag_present(argv):
        return ("--user only takes effect with a password flag (--ssh or --password); "
                "with neither, the live account stays `main` and locked. Add --password "
                'or --ssh to set a login for the chosen user.')
    return None


# --- The --static-ip / --gateway / --dns opt-in (deterministic server IP) -----
# When set, the compiler bakes a NetworkManager static keyfile into the airootfs so a
# deployed machine has a fixed IPv4 (see network_profile). --gateway/--dns refine it.

def _value_flag(argv: list[str], name: str) -> str | None:
    for token in argv:
        if token.startswith(name + "="):
            return token.split("=", 1)[1] or None
    return None


def parse_static_ip_flag(argv: list[str]) -> str | None:
    """The `--static-ip=<CIDR>` value (e.g. 192.168.1.50/24), or None."""
    return _value_flag(argv, "--static-ip")


def parse_gateway_flag(argv: list[str]) -> str | None:
    """The `--gateway=<IP>` value, or None."""
    return _value_flag(argv, "--gateway")


def parse_dns_flag(argv: list[str]) -> str | None:
    """The `--dns=<IP[,IP...]>` value (comma list), or None."""
    return _value_flag(argv, "--dns")


def check_static_ip_flag(argv: list[str]) -> str | None:
    """Validate --static-ip's CIDR, returning an ERROR MESSAGE or None. Absent is fine."""
    cidr = parse_static_ip_flag(argv)
    if cidr is None:
        return None
    if not network_profile.is_valid_cidr(cidr):
        return (
            f'--static-ip="{cidr}" is not a valid IPv4 CIDR. Use A.B.C.D/NN, e.g. '
            '--static-ip="192.168.1.50/24". No ISO was built.'
        )
    return None


def gateway_dns_without_static_ip_warning(argv: list[str]) -> str | None:
    """WARNING when --gateway/--dns are given without --static-ip (they are ignored)."""
    has_gw = any(t == "--gateway" or t.startswith("--gateway=") for t in argv)
    has_dns = any(t == "--dns" or t.startswith("--dns=") for t in argv)
    if (has_gw or has_dns) and parse_static_ip_flag(argv) is None:
        return ("--gateway/--dns only apply with --static-ip, which was not given, so they "
                'will be ignored. Add --static-ip="<CIDR>" to set a static address.')
    return None


# --- The --encrypt opt-in (encrypt the INSTANT auto-install's target disk) ----
# Encryption reuses the ONE password (--ssh/--password); there is no separate encryption
# password. --encrypt is only meaningful for instant variants (unattended); interactive
# installs choose encryption at install time.

def wants_encrypt(argv: list[str]) -> bool:
    """True if --encrypt was requested (encrypt the instant install's disk)."""
    return _presence_flag(argv, "--encrypt")


def check_encrypt_flag(argv: list[str]) -> str | None:
    """--encrypt without a password (--ssh/--password) is a hard error: there is no
    passphrase to encrypt with, and no default is ever shipped."""
    if wants_encrypt(argv) and not ssh_flag_present(argv) and not password_flag_present(argv):
        return (
            "--encrypt needs a password to use as the disk passphrase, but neither --ssh "
            'nor --password was given. Add --password="<PW>" (or --ssh="<PW>") so the '
            "encrypted install has a passphrase. No ISO was built."
        )
    return None


# --- The --type / --instant / --timezone axis flags -------------------------
# The build matrix has three orthogonal axes; the build is the Cartesian product of what
# was requested (variants.selected_variants). A bare compile.sh still builds exactly one
# ISO (azarch-headed), and --ssh keeps its existing meaning.
#   --type=<headed|headless|all|both>  which product LINE(s): headed (default) | headless |
#                      all/both (both).
#   --instant          ALSO build the instant (auto-install) variants.
#   --ssh="<PASSWORD>"  ALSO build the ssh variants (existing flag, unchanged).
#   --timezone="<TZ>"   the instant-install timezone (default Asia/Jerusalem; validated).

def _presence_flag(argv: list[str], name: str) -> bool:
    """True if a bare presence flag (e.g. --instant, --encrypt) appears in argv, in either
    the bare (`--instant`) or value (`--instant=anything`) spelling. These axes are on/off,
    so any spelling means 'on'."""
    return any(t == name or t.startswith(name + "=") for t in argv)


_TYPE_VALUES = ("headed", "headless", "all", "both")


def parse_type_flag(argv: list[str]) -> str:
    """The product-line selection: the `--type=<headed|headless|all|both>` value,
    normalized (both -> all), or "headed" when the flag is absent or blank.
    `all`/`both` mean 'build BOTH lines'. split('=', 1) so a value is never truncated;
    a blank value falls back to the default."""
    for token in argv:
        if token.startswith("--type="):
            value = token.split("=", 1)[1]
            if not value:
                return "headed"
            return "all" if value == "both" else value
    return "headed"


def check_type_flag(argv: list[str]) -> str | None:
    """Validate --type, returning an ERROR MESSAGE to abort on, or None to proceed.
    Absent/blank is fine (defaults to headed). A value outside headed|headless|all|both
    is a hard error."""
    for token in argv:
        if token.startswith("--type="):
            value = token.split("=", 1)[1]
            if value and value not in _TYPE_VALUES:
                return (
                    f'--type="{value}" is not a valid product line. Use one of: '
                    '--type="headed" (default, the GUI line), --type="headless" '
                    '(console-only), or --type="all" (both; --type="both" is an alias). '
                    "No ISO was built."
                )
    return None


def type_wants_headless(type_value: str) -> bool:
    """True when the selected --type builds the headless line (headless or all)."""
    return type_value in ("headless", "all")


def wants_instant(argv: list[str]) -> bool:
    """True if the instant variants were requested (--instant)."""
    return _presence_flag(argv, "--instant")


DEFAULT_INSTANT_TIMEZONE = "Asia/Jerusalem"


def parse_timezone_flag(argv: list[str]) -> str:
    """The instant-install timezone: the `--timezone=<TZ>` value, or the
    Asia/Jerusalem default when the flag is absent or blank. split('=', 1) so a zone with
    no '=' is taken verbatim; a blank value falls back to the default."""
    for token in argv:
        if token.startswith("--timezone="):
            return token.split("=", 1)[1] or DEFAULT_INSTANT_TIMEZONE
    return DEFAULT_INSTANT_TIMEZONE


def check_timezone_flag(argv: list[str]) -> str | None:
    """Validate --timezone against the build host's zoneinfo DB, returning an ERROR MESSAGE
    to abort on, or None to proceed. A --timezone naming a zone with no
    /usr/share/zoneinfo/<TZ> file is a hard error (the installer validates the same way at
    runtime, so catching it at compile time fails fast instead of shipping an instant ISO
    that aborts mid-install). Absent/blank --timezone is fine (the default is always valid).
    Pure enough to unit-test: it only stats the host zoneinfo tree."""
    from pathlib import Path as _Path
    present = any(t == "--timezone" or t.startswith("--timezone=") for t in argv)
    if not present:
        return None
    tz = parse_timezone_flag(argv)
    if not _Path(f"/usr/share/zoneinfo/{tz}").is_file():
        return (
            f'--timezone="{tz}" is not a known timezone on this build host (no '
            f"/usr/share/zoneinfo/{tz}). Use e.g. --timezone=\"Europe/London\" or "
            '--timezone="America/New_York"; see /usr/share/zoneinfo for the full list. '
            "No ISO was built."
        )
    return None


def timezone_without_instant_warning(argv: list[str]) -> str | None:
    """A WARNING (not an error) when --timezone is given without --instant: the timezone
    only affects the instant auto-install, so it is silently unused otherwise -- most likely
    the operator forgot --instant. Returns the warning text, or None when there is nothing to
    warn about."""
    present = any(t == "--timezone" or t.startswith("--timezone=") for t in argv)
    if present and not wants_instant(argv):
        return ("--timezone only affects the instant auto-install, but --instant was not "
                "requested, so it will be ignored. Add --instant to build the instant "
                "variants.")
    return None


def _variants_for(ssh_hash: str | None) -> tuple[str, ...]:
    """LEGACY helper (kept for the sshd-variant tests): the two headed variant KEYS a
    build produces given only the ssh hash -- base always, sshd only with a hash. The live
    build now selects variants via variants.selected_variants (three axes), so run() no
    longer calls this; it remains as the documented base-always / ssh-opt-in contract."""
    if ssh_hash:
        return VARIANTS
    return ("base",)


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


def run(bar: ProgressBar, offline: bool, reclaim_after_mkarchiso,
        full_compile: bool = False, ssh_password_hash: str | None = None,
        build_variants: tuple = (), timezone: str = "Asia/Jerusalem",
        login_user: str = "main", login_password: str | None = None,
        encrypt: bool = False, static_ip_text: str | None = None) -> list[Path]:
    """Execute all steps; return the paths of the built ISOs. Raises on failure.

    full_compile: when True, Az'arch's own packages (librewolf) are compiled from
    source instead of repackaged from the verified upstream tarball. Passed to the
    makepkg stage below.

    ssh_password_hash: the operator's --ssh password ALREADY HASHED (sha-512 crypt),
    or None. It is the credential the `ssh` variants bake into `main`'s /etc/shadow
    (DECISION 2: no default password is ever shipped -- it comes from the operator at
    build time). None means no ssh variant was requested.

    build_variants: the variants.Variant tuple this build produces (from
    variants.selected_variants, decided by the --type/--instant/--ssh flags). It
    ALWAYS contains the headed base point; it may add the headless line and the
    instant/ssh flavours. Empty -> default to the single headed base point.

    timezone: the instant-install timezone baked into the instant autorun (compile
    --timezone, default Asia/Jerusalem; validated on the build host).

    Structure: the build groups the selected variants BY LINE (headed, headless). The
    two lines need DIFFERENT airootfs contents -- the headless line strips the whole GUI
    stack (packages AND emitted session files) -- so they cannot share one squashfs.
    Each line therefore gets its own full profile build (cheap overlay emits) plus one
    mkarchiso pass per selected sub-variant of that line. The genuinely expensive,
    line-independent work -- the package cache warm and the own-package (calamares/
    librewolf) build -- lands in the persistent cache OUTSIDE the work tree, so the
    first line pays for it and every later line/pass reuses it for free (each line
    recomputes `offline`, which flips to True once the cache is warm). Within a line
    the tiny per-variant differences (profiledef iso_name, /etc/shadow, the sshd and
    instant enable-links) are cheap overlays applied just before each pass."""
    if not build_variants:
        build_variants = (_variants.Variant(),)  # headed base point
    sudo = _sudo()

    # 0 -- One-time workspace reset + host-toolchain check, BEFORE the line loop, so
    # they run exactly once no matter how many lines/variants are selected (they are
    # line-independent, and the toolchain check is the single point a missing dep is
    # reported). Each line's own profile build re-scaffolds the releng tree into W.
    bar.step("Reset build workspace")
    _unmount_worktree(sudo)
    paths.BUILDDIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(sudo + ["rm", "-rf", str(paths.WORKDIR)], check=False)
    paths.WORKDIR.mkdir(parents=True, exist_ok=True)

    bar.step("Sync host toolchain")
    _check_host_deps(sudo, offline)

    # Build each selected LINE in turn (headed first, per selected_variants order),
    # each producing one ISO per its selected sub-variants. Recompute `offline` per
    # line: after the first line warms the cache, later lines build fully offline.
    #
    # own_packages_ready: the calamares/librewolf build (step 13) is line-independent --
    # the packages land in the shared repo. The FIRST line builds them; every later line
    # just RE-STAGES the already-built repo into its airootfs instead of rebuilding. This
    # matters for `--full-compile` + a second line: without this, `build_own_packages`
    # offline+full-compile would RE-COMPILE librewolf from source (a multi-hour job) again
    # for the headless line. Passing own_packages_ready=True after the first line skips that.
    isos: list[Path] = []
    own_packages_ready = False
    for line in _lines_in(build_variants):
        line_variants = tuple(v for v in build_variants if v.line == line)
        line_offline = cache_is_complete()
        isos += _build_line(
            bar, line, line_variants, line_offline, reclaim_after_mkarchiso,
            full_compile=full_compile, ssh_password_hash=ssh_password_hash,
            timezone=timezone, own_packages_ready=own_packages_ready,
            login_user=login_user, login_password=login_password,
            encrypt=encrypt, static_ip_text=static_ip_text,
        )
        own_packages_ready = True  # built (or confirmed present) by the first line
    return isos


def _build_line(bar: ProgressBar, line: str, line_variants: tuple, offline: bool,
                reclaim_after_mkarchiso, *, full_compile: bool,
                ssh_password_hash: str | None, timezone: str,
                own_packages_ready: bool = False, login_user: str = "main",
                login_password: str | None = None, encrypt: bool = False,
                static_ip_text: str | None = None) -> list[Path]:
    """Build ONE product line's profile tree and assemble its ISO(s).

    line: "headed" or "headless". is_gui below drives every difference between the two:
    the headed line ships the full manifest + the OpenBox/Calamares/apps session
    emits; the headless line ships the console subset of the manifest and NONE of the
    GUI emits (its live console is a plain login shell, and it installs via the
    headless CLI installer). Everything else -- accounts, branding/locale, the
    installed-system pacman + pkgs service, systemd units, power policy, the installer
    payload, the cache warm, and the own-package build -- is identical across lines.

    own_packages_ready: True when a prior line already built calamares/librewolf into the
    shared repo, so this line skips the (possibly multi-hour under --full-compile) rebuild
    and only re-stages the repo. False on the first line, which does the real build.

    Returns the ISO paths this line produced (one per variant in line_variants)."""
    is_gui = line == _variants.LINE_HEADED
    W = paths.WORKDIR
    airootfs = W / "airootfs"
    ea = airootfs / "root/azarch"  # the azarch payload dir baked into the ISO
    sudo = _sudo()

    # Reset the profile tree for THIS line (the prior line's tree, if any, is wiped so
    # a headed overlay never bleeds into the headless ISO). The persistent package repo
    # + cache live outside W, so this reset is cheap and loses nothing expensive.
    _unmount_worktree(sudo)
    subprocess.run(sudo + ["rm", "-rf", str(W)], check=False)
    W.mkdir(parents=True, exist_ok=True)

    # 3 -- Scaffold releng profile
    bar.step(f"[{line}] Scaffold releng profile")
    _copy_releng(W)

    # 4 -- Brand boot menus (systemd-boot + syslinux)
    bar.step(f"[{line}] Brand boot menus (systemd-boot, syslinux)")
    _brand_boot_menus(W)

    # 5 -- Stage pacstrap package manifest (FILTERED per line: the full manifest for
    # the headed line, the console subset -- manifest minus the GUI stack -- for the
    # headless line). The offline cache still holds the full superset (warmed below), so a
    # headless pacstrap just installs fewer of the cached packages. See packages_manifest.
    bar.step(f"[{line}] Stage pacstrap package manifest")
    emit.write_text(W / "packages.x86_64", packages_manifest.manifest_text_for(is_gui))

    # 6 -- Provision airootfs accounts (users/groups + /home/main, chowned for the
    # autologin `main` user the getty drops straight into on the live console).
    bar.step(f"[{line}] Provision airootfs accounts (console autologin)")
    emit.write_text(airootfs / "etc/passwd", system.PASSWD)
    # Shadow ships LOCKED by default (both accounts, DECISION 1): no password login is
    # possible on the base ISO, autologin still works. The ssh variants rewrite `main`'s
    # field to the operator's hash per-pass in _apply_variant, so this shared write is
    # the safe locked baseline every variant starts from.
    emit.write_text(airootfs / "etc/shadow", system.shadow_for(None), mode=0o600)
    emit.write_text(airootfs / "etc/gshadow", system.GSHADOW, mode=0o600)
    emit.write_text(airootfs / "etc/group", system.GROUP)
    home = airootfs / "home/main"
    emit.mkdir(home)
    subprocess.run(sudo + ["chown", "-R", "1000:998", str(home)], check=False)

    # 7 -- Overlay branding and locale into airootfs.
    # One coherent overlay-population act: locale setup-script + service, the fastfetch
    # logo, and the os-release/hostname rebrand.
    bar.step(f"[{line}] Overlay branding and locale")

    # locale: first-run setup script + the systemd unit that runs it.
    emit.write_exec(ea / "setup-locale.sh", locale.setup_locale_sh())
    emit.write_text(airootfs / "etc/systemd/system/locale-setup.service", system.LOCALE_SETUP_SERVICE)

    # the azarch fastfetch logo/config for the live (and installed) user.
    _emit_fastfetch(ea, home)

    # os-release rebrand:
    # Live ISO: the build pacman.conf NoExtracts usr/lib/os-release (libraries/pacman.py)
    # so the `filesystem` package's stock "Arch Linux" file never lands. We must NOT
    # pre-place our replacement in the airootfs overlay, though: mkarchiso copies the
    # overlay into the work root BEFORE pacstrap, and pacman's file-conflict check
    # (which runs before extraction and is NOT suppressed by NoExtract) then aborts
    # with "filesystem: usr/lib/os-release exists in filesystem". Instead we plant it
    # AFTER pacstrap via customize_airootfs.sh -- the same after-pacstrap ordering the
    # on-disk installer already uses (libraries/installer.py copies it into /mnt post-
    # pacstrap). The branded file is staged read-only under root/azarch/os-release and
    # the hook copies it into place inside the pacstrapped rootfs.
    emit.write_text(ea / "os-release", system.OS_RELEASE)
    # The customize hook. On the HEADED line it also carries the per-app override
    # plant/remove lines (kitty icon SVG, the stale cat PNGs, the gedit/thunar/xviewer
    # .desktop files, ...) -- those `install`/`rm` lines target GUI PACKAGE paths and copy
    # bodies _emit_apps stages under root/azarch/apps/. The HEADLESS line ships none of those
    # packages and runs no _emit_apps, so it gets the branding-only hook (appending the app
    # overrides there would `install` from absent staged bodies onto absent package files).
    hook = system.CUSTOMIZE_AIROOTFS + (pacman.app_override_cp_sh() if is_gui else "")
    emit.write_exec(airootfs / "root/customize_airootfs.sh", hook)
    # Overlay the releng `archiso` hostname with `azarch` (prompt + fastfetch title).
    emit.write_text(airootfs / "etc/hostname", system.HOSTNAME)

    # 8 -- Overlay the live session.
    # The tty1 autologin override (releng autologins ROOT; we autologin `main` on BOTH
    # lines) is UNIVERSAL: on the headed line `main`'s ~/.bash_profile (emitted just below)
    # execs startx into OpenBox; on the headless line there is no such bash_profile, so `main`
    # simply lands on a plain console login shell -- the correct headless behaviour, and
    # consistent with the identity re-point the installer runs (which expects an
    # `--autologin main` drop-in to rewrite after a rename). Everything ELSE here is the
    # graphical stack (OpenBox/X11 session, the per-app tweaks, the home-dir layout, the
    # Calamares GUI installer + its vendored ckbcomp) and is HEADED-ONLY: the headless line has no
    # X and installs via the headless CLI installer staged in step 10.
    bar.step(f"[{line}] Overlay live session and installer configuration")
    _emit_tty1_autologin(airootfs)   # autologin `main` to tty1 on both lines
    if is_gui:
        _emit_desktop(airootfs, home)
        _emit_homedir(airootfs, home)
        _emit_apps(airootfs, home, ea)
        _emit_calamares(airootfs)
        # ckbcomp: Calamares' keyboard page renders its on-screen key legends by shelling
        # out to `ckbcomp`; without it the preview draws BLANK keys. It is a self-contained
        # Python 3 port vendored in the calamares package, copied verbatim into /usr/bin.
        # Desktop-only (it exists solely for the Calamares GUI).
        emit.copy_data("calamares/ckbcomp.py", airootfs / "usr/bin/ckbcomp", mode=0o755)

    # 9 -- Stage installed-system pacman and pkgs service.
    # The package-management unit of the installed system: its /etc/pacman.conf, the
    # live-session setup-pkgs.sh, and the pkgs-setup.service that runs it. Universal.
    bar.step(f"[{line}] Stage installed-system pacman and pkgs service")
    emit.write_text(airootfs / "etc/pacman.conf", pacman.installer_base_conf())
    emit.write_exec(ea / "setup-pkgs.sh", installer.setup_pkgs_sh())
    emit.write_text(airootfs / "etc/systemd/system/pkgs-setup.service", system.PKGS_SETUP_SERVICE)

    # 9b -- Enable systemd units and sudoers policy. Universal daemons (NetworkManager,
    # CUPS, spice-vdagentd, locale/pkgs oneshots, sleep policy, virtiofs share) + the
    # sudoers.d drop-ins + power management. The headed-only timedate Flask service is
    # enabled inside _link_services only when is_gui (its unit is emitted by _emit_desktop,
    # which the headless line skips). The sshd-hypervisor and instant auto-setup units are
    # per-variant (finalize loop), not here.
    bar.step(f"[{line}] Enable systemd units and sudoers policy")
    _link_services(airootfs, is_gui=is_gui)
    emit.write_text(airootfs / "etc/sudoers.d/00-rootpw", system.SUDOERS_ROOTPW, mode=0o440)
    emit.write_text(airootfs / "etc/sudoers.d/00-main", system.SUDOERS_MAIN, mode=0o440)
    emit.write_text(airootfs / "etc/sudoers.d/00-secure-path", system.SUDOERS_SECURE_PATH, mode=0o440)
    _emit_power(airootfs)
    # The virtiofs shared-folder .mount unit + its mountpoint, enabled on every variant.
    _emit_shared_mount(airootfs)

    # Static IPv4: bake ONE NetworkManager keyfile so a deployed machine has a fixed
    # address (the rootfs clone / Calamares unpackfs carries it onto the install). 0600,
    # root-owned (NetworkManager refuses world-readable keyfiles).
    if static_ip_text is not None:
        emit.write_text(airootfs / network_profile.CONNECTION_PATH.lstrip("/"),
                        static_ip_text, mode=0o600)

    # 10 -- Emit installer payload.
    # The first-boot script/service/conf + the scripted (terminal/SSH/instant) installer.
    # profiledef.sh is written per-variant in the finalize loop (its iso_name differs).
    # The CLI installer (azarch-install-cli.sh) is the ONLY installer on the headless line
    # and the SSH/instant installer on both lines. The instant autorun script is staged
    # here too (per line: its ssh flag follows whether any ssh variant of this line is
    # built; the actual enable happens per-variant). Universal.
    bar.step(f"[{line}] Emit installer payload")
    emit.write_exec(ea / "first-boot-setup.sh", installer.first_boot_sh())
    emit.write_text(ea / "first-boot-setup.service", installer.first_boot_service())
    emit.write_text(ea / "first-boot-setup.conf", installer.first_boot_conf())
    emit.write_exec(ea / "azarch-install-cli.sh", installer.installer_sh())

    # 11 -- Resolve build pacman.conf and mirrors (uses the FULL manifest's repo).
    bar.step(f"[{line}] Resolve build pacman.conf and mirrors")
    _write_build_pacman_conf(W, offline, bar)

    # 12 -- Warm pacman cache and stage installer payload (GIANT, weight 250).
    # Warms the FULL manifest superset (line-independent) into the persistent cache, so
    # the headless line's smaller pacstrap still resolves from it and later lines reuse it.
    bar.step(f"[{line}] Warm pacman cache and stage installer payload")
    downloader.build_cache(W, paths.CACHEDIR, offline, bar.sub, bar.phase, full_compile)
    bar.sub_done()
    bar._arm(); bar.draw()
    # stage the installer-side payload the on-disk installer needs (the FILTERED manifest
    # for this line, so the installed headless system's own pacstrap manifest is console-only).
    emit.write_text(ea / "packages.x86_64", packages_manifest.manifest_text_for(is_gui))
    emit.write_text(ea / "pacman-base-conf/pacman.conf", pacman.installer_base_conf())
    emit.write_text(ea / "pacstrap-azarch-conf/pacman.conf", pacman.installer_pacstrap_conf())
    emit.write_exec(ea / "chroot-setup.sh", installer.chroot_setup_sh(is_gui=is_gui))

    # 13 -- Build Az'arch's OWN packages and fold them into the offline repo (GIANT-ish,
    # weight 120; MUCH heavier under --full-compile). calamares + librewolf are built in
    # every tier; whatever is built is dropped into cache/pkgs/repo/ and re-staged into
    # airootfs. This is line-INDEPENDENT (the built packages land in the shared repo); on
    # the headless line they simply are not in that line's pacstrap manifest, so they are
    # built-but-not-installed (harmless -- the repo is a superset).
    #
    # own_packages_ready: only the FIRST line actually BUILDS them; a later line skips the
    # build (they are already in the shared repo) and just RE-STAGES the repo into its own
    # airootfs. Without this skip, `--full-compile` on a second line would re-run the
    # multi-hour librewolf-from-source compile (build_own_packages offline+full-compile
    # RE-COMPILES by design). The milestone (and the cheap re-stage) still run per line, so
    # the step count stays one-per-line and every line's airootfs gets the repo.
    bar.step(f"[{line}] Build packages (calamares, librewolf)")
    if own_packages_ready:
        print("    [+] Own packages already built this run -- re-staging the shared repo "
              "for this line (no rebuild).")
        bar.sub(1000)
    else:
        makepkg.build_own_packages(offline, full_compile, bar.sub, bar.phase)
    bar.sub_done()
    bar._arm(); bar.draw()
    _refold_own_packages_into_repo(W, full_compile)

    # 14 -- Assemble this line's ISO(s): one mkarchiso pass per selected sub-variant
    # (weight 270 each). Every step above is variant-independent within the line, so we
    # overlay each variant's tiny differences (profiledef iso_name, /etc/shadow, the sshd
    # + instant enable-links) onto the shared airootfs and run one pass per variant.
    # mkarchiso re-copies the airootfs overlay into its work tree at the start of each
    # pass, so toggling the shadow / enable-symlinks between passes is reflected per ISO.
    line_isos: list[Path] = []
    for variant in line_variants:
        _apply_variant(W, airootfs, variant,
                       ssh_password_hash=ssh_password_hash, timezone=timezone,
                       login_user=login_user, login_password=login_password,
                       encrypt=encrypt)
        bar.step(f"Assemble {variant.iso_name} ISO (mkarchiso)")
        line_isos.append(_run_mkarchiso(sudo, W, bar, reclaim_after_mkarchiso,
                                        iso_name=variant.iso_name))
    return line_isos


# --- helpers ---------------------------------------------------------------

def _apply_variant(W: Path, airootfs: Path, variant,
                   ssh_password_hash: str | None = None,
                   timezone: str = "Asia/Jerusalem",
                   login_user: str = "main", login_password: str | None = None,
                   encrypt: bool = False) -> None:
    """Overlay the per-variant differences onto the shared (per-line) profile tree just
    before its mkarchiso pass. Accepts a variants.Variant (or a legacy "base"/"sshd"
    key, coerced) and toggles the two flavour axes -- ssh and instant -- independently.
    Four things differ between the variants of a line, all rewritten EVERY pass so a
    preceding variant's state never bleeds into the next one on the shared airootfs:

      1. profiledef iso_name -- drives the artifact filename (azarch-<line>[-instant]
         [-ssh]-<ver>.iso). Rewritten at the profile root.
      2. /etc/shadow -- ssh variants replace `main`'s field with the operator's
         build-time hash (remote login with the --ssh password); non-ssh variants ship
         the base LOCKED shadow (relocked here even if a prior ssh pass left a hash).
      3. the sshd-hypervisor auto-setup service + enable-link -- emitted+enabled ONLY on
         ssh variants (that ISO auto-runs `azarch --sshd-hypervisor` at boot); removed
         otherwise.
      4. the instant auto-install service + enable-link -- emitted+enabled ONLY on
         instant variants. Its script (installer.instant_install_sh) pre-seeds the
         AZ_INSTALL_* environment for the largest-non-USB-disk unattended install with
         user `main`, the given timezone, and either the cloned ssh password (ssh
         variants) or a LOCKED `!*` account (non-ssh). Removed on non-instant variants.

    ssh_password_hash is REQUIRED (a sha-512 crypt hash) for an ssh variant: an ssh ISO
    must never ship the base locked shadow -- that would be an sshd nobody can log in to,
    silently hiding that the credential was dropped."""
    v = _variants.coerce(variant)
    emit.write_exec(W / "profiledef.sh", profile.profiledef_sh(v))

    # 2 -- /etc/shadow.
    if v.ssh:
        if not ssh_password_hash:
            raise ValueError(
                "_apply_variant: an ssh variant requires an --ssh password hash; "
                "refusing to build an ssh ISO with the base (locked) shadow."
            )
        emit.write_text(airootfs / "etc/shadow",
                        system.shadow_for(ssh_password_hash), mode=0o600)
    else:
        emit.write_text(airootfs / "etc/shadow", system.shadow_for(None), mode=0o600)

    wants = airootfs / "etc/systemd/system/multi-user.target.wants"

    # 3 -- sshd-hypervisor auto-setup (ssh variants only).
    sshd_svc = airootfs / "etc/systemd/system/sshd-hypervisor-setup.service"
    sshd_link = wants / "sshd-hypervisor-setup.service"
    if v.ssh:
        emit.write_text(sshd_svc, system.SSHD_HYPERVISOR_SETUP_SERVICE)
        emit.link("/etc/systemd/system/sshd-hypervisor-setup.service", sshd_link)
    else:
        sshd_link.unlink(missing_ok=True)
        sshd_svc.unlink(missing_ok=True)

    # 4 -- instant auto-install (instant variants only).
    inst_svc = airootfs / "etc/systemd/system/azarch-instant-install.service"
    inst_link = wants / "azarch-instant-install.service"
    inst_script = airootfs / "root/azarch/azarch-instant-install.sh"
    if v.instant:
        # The script's password posture follows THIS variant's ssh flag: ssh -> keep the
        # cloned --ssh password; non-ssh -> lock the installed account (`!*`).
        # When --encrypt is set the target disk is LUKS-formatted with the ONE password.
        # For an ssh variant that password was already cloned into the account, so LUKS
        # reads it from AZ_INSTALL_PASSWORD only for the NON-ssh case (account stays locked,
        # but LUKS still needs the secret) -- hence passphrase is threaded only then.
        passphrase = login_password if (encrypt and not v.ssh) else None
        emit.write_exec(inst_script,
                        installer.instant_install_sh(timezone, ssh=v.ssh,
                                                     encrypt=encrypt, user=login_user,
                                                     passphrase=passphrase))
        emit.write_text(inst_svc, system.INSTANT_INSTALL_SERVICE)
        emit.link("/etc/systemd/system/azarch-instant-install.service", inst_link)
    else:
        inst_link.unlink(missing_ok=True)
        inst_svc.unlink(missing_ok=True)
        inst_script.unlink(missing_ok=True)


def _emit_desktop(airootfs: Path, home: Path) -> None:
    """Emit the OpenBox live-session files. Each PLAN entry has an absolute dest
    (either under /home/main for the live user -- e.g. ~/.config/openbox/* -- or an
    absolute system path). User files are ALSO copied into /etc/skel so a
    Calamares-created user on the installed system inherits the same desktop
    (Manjaro-style). The /home/main tree is chowned 1000:998 by step 6 / the post-emit
    chown below."""
    skel = airootfs / "etc/skel"
    # OpenBox live-session files + the LibreWolf browser-policy override. Both use the
    # same builder/dest/mode/owner plan shape and the same home-file + /etc/skel mirror
    # rule, so they iterate through one loop. The LibreWolf entry drops
    # librewolf.overrides.cfg at the PROFILE path LibreWolf's AutoConfig loader actually
    # reads (~/.config/librewolf/librewolf/...); shipping it under /opt did nothing (the
    # loader never looks there). See packages/librewolf.emit_plan().
    for entry in openbox.emit_plan() + librewolf.emit_plan():
        content = entry["builder"]()
        dest_abs = entry["dest"]          # e.g. "/home/main/.xinitrc" or "/usr/local/bin/..."
        mode = entry["mode"]
        # airootfs-relative destination (strip leading '/').
        emit.write_text(airootfs / dest_abs.lstrip("/"), content, mode=mode)
        # Mirror HOME-relative user files into /etc/skel for installed-system users.
        if entry["owner"] == "home" and dest_abs.startswith(openbox.HOME + "/"):
            rel = dest_abs[len(openbox.HOME) + 1:]   # path under the home dir
            emit.write_text(skel / rel, content, mode=mode)
    # Installer launcher icon ("Az'" app tile), standardized as the scalable vector
    # assets/icons/azarch.svg. Ship the SVG to the hicolor SCALABLE apps dir (the vector
    # master, like kitty.svg) AND rasterize it to PNGs at /usr/share/pixmaps and the
    # hicolor 256x256 apps dir, so the Desktop/menu/autostart .desktop files
    # (Icon=azarch-installer) resolve it regardless of which path/size the icon loader
    # consults, with no theme-cache rebuild needed. Root-owned system paths.
    emit.copy_asset(openbox.INSTALLER_ICON_ASSET,
                    airootfs / openbox.INSTALLER_ICON_SCALABLE.lstrip("/"), mode=0o644)
    for icon_dest in (openbox.INSTALLER_ICON_PIXMAP, openbox.INSTALLER_ICON_HICOLOR):
        emit.render_svg_png(openbox.INSTALLER_ICON_ASSET,
                            airootfs / icon_dest.lstrip("/"),
                            openbox.INSTALLER_ICON_PNG_SIZE, mode=0o644)
    # The two Az'arch wallpaper images ("years", "decades") under /usr/share/wallpapers.
    # Each ships as contents/images/<res>.png (+ a screenshot.png thumbnail and an inert
    # metadata.json kept for self-description). feh paints the "years" image as the X
    # root pixmap from the OpenBox autostart / ~/.xinitrc (KDE Plasma and its wallpaper
    # grid are gone). Root-owned under /usr/share/wallpapers.
    for pkg in openbox.WALLPAPER_PACKAGES:
        pkg_root = airootfs / openbox.WALLPAPERS_SYSTEM_DIR.lstrip("/") / pkg["id"]
        emit.write_text(pkg_root / "metadata.json",
                        openbox.wallpaper_metadata_json(pkg["id"]), mode=0o644)
        img = pkg_root / "contents" / "images" / f"{openbox.WALLPAPER_IMAGE_RES}.png"
        emit.copy_asset(pkg["asset"], img, mode=0o644)
        # screenshot.png = a thumbnail (reuse the full image).
        emit.copy_asset(pkg["asset"], pkg_root / "contents" / "screenshot.png", mode=0o644)
    # Az'arch application menu (OUR menu -- the whole shell now that Plasma is gone: a
    # centered GTK3 launcher opened by the Super key). The menu is a COMPILED C program:
    # build_daemon() runs `make` against a private copy of the C sources and installs the
    # resulting binary; emit_plan() then drops the two generated TEXT artifacts (the
    # pure-Python launcher installed as the bin entry point, and the .desktop). The
    # OpenBox session (openbox.py) starts the daemon binary from its autostart and binds
    # the Super key to the launcher.
    # Root-owned system paths -> the OFFLINE Calamares install rsyncs them onto the
    # installed system with no separate step.
    application_menu.build_daemon(
        airootfs / application_menu.MENU_DAEMON_BIN_SYSTEM_PATH.lstrip("/")
    )
    for entry in application_menu.emit_plan():
        emit.write_text(
            airootfs / entry["dest"].lstrip("/"),
            entry["builder"](),
            mode=entry["mode"],
        )
    # The Az'arch window switcher (alt-tab): a SECOND compiled C/GTK3 daemon, OUR
    # replacement for OpenBox's built-in NextWindow list (a horizontal, Windows-like
    # overlay of LIVE window thumbnails). build_daemon() stages this package AND
    # application_menu (four reused translation units) into a scratch tree and installs the
    # binary; emit_plan() ships the pure-Python launcher (the bin entry point A-Tab runs).
    # OpenBox autostart starts the daemon + picom, and rc.xml binds A-Tab/A-S-Tab to the
    # launcher (see packages/openbox).
    from packages.window_switcher import window_switcher as window_switcher_pkg
    window_switcher_pkg.build_daemon(
        airootfs / window_switcher_pkg.SWITCHER_DAEMON_BIN_SYSTEM_PATH.lstrip("/")
    )
    for entry in window_switcher_pkg.emit_plan():
        emit.write_text(
            airootfs / entry["dest"].lstrip("/"),
            entry["builder"](),
            mode=entry["mode"],
        )
    # The bare-`azarch` TERMINAL UI (OUR C settings UI: Theme / Wallpaper / Network, opened
    # by running `azarch` with no arguments). It is part of the `azarch` package now (one
    # program, C for speed); like the menu it is a COMPILED C program: build_terminal_user_interface() runs
    # `make` against a private copy of the package's C sources and installs the resulting
    # binary under /usr/local/lib/azarch. The `azarch` command line interface (installed by openbox.PLAN
    # below) execs this binary for the no-argument case. Then install_previews() ships the
    # theme-preview screenshots (verbatim) into the sibling previews dir the UI reads at
    # runtime with kitty. Root-owned; the OFFLINE Calamares install rsyncs both onto the
    # installed system with no separate step.
    terminal_user_interface_build.build_terminal_user_interface(
        airootfs / terminal_user_interface_build.TERMINAL_USER_INTERFACE_BIN_SYSTEM_PATH.lstrip("/")
    )
    terminal_user_interface_build.install_previews(
        airootfs / terminal_user_interface_build.TERMINAL_USER_INTERFACE_PREVIEW_SYSTEM_DIR.lstrip("/")
    )
    # The media OSD indicator (bottom-middle cyan volume/brightness bar). Like the terminal UI it
    # is a COMPILED C program (on_screen_display.c -> azarch-osd), built from the SAME Makefile and installed
    # next to the UI binary. `azarch volume/brightness` launches it; it draws a single, no-flicker
    # Xlib window (so it links X11/Xrandr/Xft, on the build host per the UI build deps). Root-
    # owned; the OFFLINE Calamares install rsyncs it onto the installed system with no extra step.
    terminal_user_interface_build.build_osd(
        airootfs / terminal_user_interface_build.OSD_BIN_SYSTEM_PATH.lstrip("/")
    )
    # Az'arch timedate (OUR Flask Time + Calendar home page -- the site LibreWolf lands
    # on at localhost:49154). A pure-Python app: emit_plan() copies the app sources
    # (applications.py/page.py), the launcher, and the azarch-timedate.service unit to their fixed
    # root-owned system paths. The service ENABLE-symlink is added in _link_services (like
    # the other azarch units); the OFFLINE Calamares install rsyncs all of it onto the
    # installed system so the home page also runs at boot there. Its runtime dep
    # (python-flask) is in the manifest. See packages/librewolf/timedate.py.
    for entry in timedate.emit_plan():
        emit.write_text(
            airootfs / entry["dest"].lstrip("/"),
            entry["builder"](),
            mode=entry["mode"],
        )
    # Az'arch passwords (OUR encrypted GPG/AES256 terminal password manager -- the
    # `passwords` command). A pure-Python app like timedate, and now ONE FLAT directory (no
    # pwlib/ sub-library): emit_plan() writes the entry script, the optional plaintext
    # importer, every working module, and the /usr/local/bin/passwords launcher to their
    # fixed root-owned system paths -- one single-file entry each, so the whole flat app is
    # expressed by the plan alone (no separate directory copy). No systemd service -- it is
    # an interactive command, not a boot service. Its runtime deps (gnupg for gpg, xclip for
    # the clipboard) are in the manifest. The OFFLINE Calamares install rsyncs all of it
    # onto the installed system, so `passwords` works there too, unlocking a store at
    # ~/Vault/passwords.txt.gpg. See packages/passwords/packaging.py.
    for entry in passwords.emit_plan():
        emit.write_text(
            airootfs / entry["dest"].lstrip("/"),
            entry["builder"](),
            mode=entry["mode"],
        )
    # Az'arch backup (OUR home-directory backup -- the `backup` command). A pure-Python
    # app like passwords and a single flat directory: emit_plan() writes the entry
    # script (and any future module) plus the /usr/local/bin/backup launcher to their
    # fixed root-owned system paths -- one single-file entry each, so the whole flat app
    # is expressed by the plan alone (no separate directory copy). No systemd service --
    # it is an interactive command. Its runtime dep (gnupg for gpg) is already in the
    # manifest. The OFFLINE Calamares install rsyncs it onto the installed system, so
    # `backup` works there too, writing ~/backup_<date>.tar.gz.gpg. See
    # packages/backup/packaging.py.
    for entry in backup.emit_plan():
        emit.write_text(
            airootfs / entry["dest"].lstrip("/"),
            entry["builder"](),
            mode=entry["mode"],
        )
    # Az'arch hypervisor (OUR per-directory QEMU/KVM VM runner -- the `hypervisor`
    # command). A pure-Python app like backup and a single flat directory: emit_plan()
    # writes the entry script (command_line_interface.py) and every working module plus the
    # /usr/local/bin/hypervisor launcher to their fixed root-owned system paths -- one
    # single-file entry each, so the whole flat app is expressed by the plan alone (no
    # separate directory copy). No systemd service -- it is an interactive command. Its
    # runtime deps (qemu-full, edk2-ovmf, virt-viewer) are in the manifest. The launcher
    # deliberately does NOT cd (unlike passwords): `hypervisor` derives the VM identity
    # from the caller's CWD, which the launcher must preserve. The OFFLINE Calamares
    # install rsyncs it onto the installed system, so `hypervisor` works there too. See
    # packages/hypervisor/packaging.py.
    for entry in hypervisor.emit_plan():
        emit.write_text(
            airootfs / entry["dest"].lstrip("/"),
            entry["builder"](),
            mode=entry["mode"],
        )
    # re-assert ownership of the live user's tree (new files were added under it).
    subprocess.run(_sudo() + ["chown", "-R", "1000:998", str(home)], check=False)


def _emit_apps(airootfs: Path, home: Path, ea: Path) -> None:
    """Overlay the per-application tweaks (kitty/vlc/gedit), each a self-contained
    package module exposing emit_plan() in the same builder/dest/mode/owner shape as
    openbox/librewolf. Several extras beyond the plain write loop, all driven by keys on
    the plan entries so this stays declarative:

      * owner "home" files are ALSO mirrored into /etc/skel (like _emit_desktop), so a
        Calamares-created user inherits them; owner "root" files are system-wide.
      * entries with "asset": <rel> COPY assets/<rel> verbatim to dest (kitty's scalable
        icon SVG, whose single source of truth is the repo asset).
      * entries with "render": {"asset","size"} RASTERIZE that SVG asset to a square PNG
        at dest (kitty's in-window titlebar icon kitty.app.png).
      * entries with "remove": True are DELETED from the airootfs rather than written
        (kitty removes the two PNG icons that would otherwise outrank our SVG).
      * entries with "compile_schemas": True trigger a glib-compile-schemas pass after
        emit (gedit's gschema override is inert until the schemas are recompiled).

    The gedit notepad-mode libgedit plugin (a compiled C .so that removes the New Tab
    action, strips the headerbar buttons and makes Ctrl+W quit -- the only route on the
    gedit-technology fork, which dropped Python plugins) is BUILT and installed here too,
    right after the plan loop.

    The /home/main subtree is re-chowned 1000:998 at the end (new user files were added).
    All of this lands in the airootfs overlay, so the OFFLINE Calamares install carries it
    onto the installed system with no separate installer step."""
    skel = airootfs / "etc/skel"
    apps_stage = ea / "apps"                            # staged bodies for the customize hook
    need_compile_schemas = False

    # Package-owned system paths we REPLACE/SUPPRESS cannot go in the airootfs overlay:
    # pacstrap's file-conflict check would abort (see libraries/pacman.py). They are
    # NoExtract'd and planted post-pacstrap instead. Map override target -> staged basename
    # (None == suppress-only, no body to stage). A replacement entry writes its body under
    # root/azarch/apps/<basename> (the hook installs it); a suppress-only entry is dropped
    # here entirely (NoExtract keeps the package file out -- no overlay action needed).
    _override_basename = {target: basename
                          for basename, target, _remove in pacman.ISO_APP_OVERRIDES}

    def _skel_mirror(entry: dict, dest_abs: str) -> Path | None:
        """If entry is a HOME file, return its /etc/skel mirror path (else None)."""
        if entry["owner"] == "home" and dest_abs.startswith(openbox.HOME + "/"):
            return skel / dest_abs[len(openbox.HOME) + 1:]
        return None

    # The per-application tweaks are DISCOVERED, not hard-coded: every package exposing an
    # emit_plan() (kitty icon | vlc vlcrc | gedit .desktop + gschema | libreoffice
    # registrymodifications.xcu | gimp gimprc | thunar thunarrc/xfconf/gtk.css/bookmarks/uca.xml
    # + icon + the ~/Templates "Create Document" set | xviewer icon | ... plus any newly-added
    # packages/<app>/__init__.py) contributes its entries here, EXCEPT the ones the compiler
    # drives by name (_EXPLICIT_PACKAGES: the desktop pair openbox/librewolf, application_menu,
    # passwords, calamares, azarch). default_applications (a packages.azarch module, the XDG
    # mimeapps + preferred terminal) is appended explicitly since it is not an app-loop package.
    # Each entry is handled the same declarative way below regardless of which package produced
    # it, so the set can grow/shrink freely.
    app_mods = package_discovery.with_emit_plan(exclude=_EXPLICIT_PACKAGES)
    app_plan: list[dict] = []
    for name in sorted(app_mods):
        app_plan += app_mods[name].emit_plan()
    app_plan += default_applications.emit_plan()
    for entry in app_plan:
        dest_abs = entry["dest"]                       # absolute path on the target
        # Package-owned override path? Redirect its body to the post-pacstrap staging dir
        # (or drop it if suppress-only) instead of writing into the conflicting overlay.
        if dest_abs in _override_basename:
            basename = _override_basename[dest_abs]
            if basename is None:                       # suppress-only (kitty cat PNGs)
                continue                               # NoExtract handles it; nothing to write
            target = apps_stage / basename             # plant body for app_override_cp_sh()
            skel_dest = None                           # system file -- never skel-mirrored
        else:
            target = airootfs / dest_abs.lstrip("/")
            # Removal entries with no override mapping: unlink instead of writing. (Kept for
            # completeness; the kitty PNG removals are handled via the override map above.)
            if entry.get("remove"):
                target.unlink(missing_ok=True)
                continue
            skel_dest = _skel_mirror(entry, dest_abs)
        # Asset-copy entries (e.g. kitty's scalable icon SVG): copy the repo asset verbatim.
        if entry.get("asset"):
            emit.copy_asset(entry["asset"], target, mode=entry["mode"])
            if skel_dest is not None:
                emit.copy_asset(entry["asset"], skel_dest, mode=entry["mode"])
            continue
        # Render entries (e.g. kitty's titlebar kitty.app.png): rasterize the SVG asset.
        if entry.get("render"):
            r = entry["render"]
            emit.render_svg_png(r["asset"], target, r["size"], mode=entry["mode"])
            if skel_dest is not None:
                emit.render_svg_png(r["asset"], skel_dest, r["size"], mode=entry["mode"])
            continue
        # Binary-content entries (e.g. thunar's compiled gettext .mo catalog): the builder
        # returns raw bytes written verbatim (no newline normalization). System locale
        # catalogs are root-owned, so skel_dest is None for them; the mirror is handled
        # generically in case a HOME binary is ever added.
        if entry.get("bytes_builder"):
            data = entry["bytes_builder"]()
            emit.write_bytes(target, data, mode=entry["mode"])
            if skel_dest is not None:
                emit.write_bytes(skel_dest, data, mode=entry["mode"])
            continue
        content = entry["builder"]()
        emit.write_text(target, content, mode=entry["mode"])
        # Mirror HOME-relative user files into /etc/skel for installed-system users
        # (same rule as _emit_desktop). System (root) files are not skel-mirrored.
        if skel_dest is not None:
            emit.write_text(skel_dest, content, mode=entry["mode"])
        if entry.get("compile_schemas"):
            need_compile_schemas = True
    # Compile + install the gedit notepad-mode libpeas plugin (.so). This is the only
    # mechanism on the gedit-technology fork that can remove the New Tab action, strip the
    # headerbar buttons and make Ctrl+W exit (config/CSS/GSettings/accels cannot; Python
    # plugins were dropped in gedit 49.0). Built from C like the application-menu daemon;
    # the .plugin metadata that pairs with it is emitted by the plan loop above, and the
    # gschema override's active-plugins enables it. Root-owned system path.
    gedit.build_plugin(airootfs / gedit.GEDIT_PLUGIN_SO_DEST.lstrip("/"))
    # gedit's glib schema override is inert until the machine-readable gschemas.compiled
    # is regenerated. On the ISO the actual recompile happens LATER and for free: glib2 (a
    # gedit dependency) ships /usr/share/libalpm/hooks/glib-compile-schemas.hook, which
    # runs PostTransaction whenever a *.gschema.* file changes -- and by then our override
    # has been copied in AND gedit's base schema is installed, so the hook compiles both
    # together. This explicit pass is therefore a harmless no-op at profile-emit time
    # (gedit's base schema is not installed yet, so glib-compile-schemas prints "No schema
    # files found: doing nothing"); we keep it as belt-and-braces (and because the
    # live-apply path, which drops the override onto an already-installed system, DOES need
    # it). Use the command the gedit modification defines (single source of truth).
    if need_compile_schemas:
        schemas_dir = airootfs / gedit.GLIB_SCHEMAS_DIR.lstrip("/")
        subprocess.run(_sudo() + ["glib-compile-schemas", str(schemas_dir)], check=False)
    # re-assert ownership of the live user's tree (new home files were added under it).
    subprocess.run(_sudo() + ["chown", "-R", "1000:998", str(home)], check=False)


def _emit_homedir(airootfs: Path, home: Path) -> None:
    """Create the home-directory LAYOUT -- the top-level folders and convenience symlinks
    that packages.thunar.home_directory defines as the single source of truth (and that
    Thunar's sidebar mirrors). Unlike the emit_plan() modules this emits no file CONTENT:
    directories and symlinks are not text, so it walks home_directory's plain data with
    emit.mkdir()/emit.link() rather than a builder loop.

    Everything is created in BOTH the live user's /home/main AND /etc/skel, so a
    Calamares-created user on the installed system inherits the identical layout. Symlink
    targets are RELATIVE (home_directory keeps them that way on purpose) so each link is
    valid in every home it lands in -- an absolute /home/main/... target would dangle under
    /etc/skel and in a copied-out /home/<newuser>. The XDG trash chain
    (.local/share/Trash/{files,info}) is created BEFORE the "Trash" symlink so it resolves
    to a real directory instead of dangling.

    Runs before _emit_apps's closing `chown -R 1000:998`, so the new dirs/links in
    /home/main are swept into the live user's ownership with the rest of the tree; /etc/skel
    stays root-owned (skel is copied, not owned, by Calamares)."""
    skel = airootfs / "etc/skel"
    # The live user's /home/main (the passed `home`, == airootfs/home/main) AND /etc/skel.
    roots = (home, skel)
    for root in roots:
        # 1. The top-level directories (Desktop, Downloads, ... Videos).
        for name in home_directory.DIRECTORIES:
            emit.mkdir(root / name)
        # 1b. Extra non-sidebar directories (~/Templates for the Thunar Create Document set).
        for name in home_directory.EXTRA_DIRECTORIES:
            emit.mkdir(root / name)
        # 2. The XDG trash chain -- created BEFORE the Trash symlink so it does not dangle.
        for rel in home_directory.TRASH_DIRS:
            emit.mkdir(root / rel)
        # 3. The convenience symlinks (Trash/Cache/Config/Bashrc/Local). RELATIVE targets,
        #    verbatim from home_directory.LINKS, so they resolve against the link's own
        #    directory in every home. emit.link replaces any pre-existing entry.
        for name, target in home_directory.LINKS:
            emit.link(target, root / name)
        # (No ".home-directory" symlink: the "Home Directory" sidebar bookmark it used to back
        #  was deleted at the user's request -- see thunar/home_directory.py and thunar/sidebar.py.)


def _emit_calamares(airootfs: Path) -> None:
    """Write the whole Calamares configuration tree under /etc/calamares."""
    base = airootfs / "etc/calamares"
    for rel, content in calamares.emit_map().items():
        emit.write_text(base / rel, content)
    # The Calamares WINDOW ICON: rasterize the standardized "Az'" vector app tile to a REAL
    # PNG inside the branding component dir (branding/azarch/productIcon.png). branding.desc
    # names it by that branding-relative filename in `productIcon`, so Calamares resolves it
    # to an absolute path and QIcon() loads it as the window icon -- which OpenBox draws on
    # the titlebar (rc.xml titleLayout's `N`). Calamares wants a real raster FILE here (a
    # PNG QIcon loads directly -- see calamares.py PRODUCT_ICON_FILE), so we rasterize the
    # SVG rather than shipping the vector. Same source asset as the .desktop launcher icon
    # (packages/openbox.INSTALLER_ICON_ASSET), so the topbar icon matches the launcher.
    emit.render_svg_png(
        openbox.INSTALLER_ICON_ASSET,
        base / "branding" / calamares.BRANDING / calamares.PRODUCT_ICON_FILE,
        openbox.INSTALLER_ICON_PNG_SIZE,
        mode=0o644,
    )


def _emit_power(airootfs: Path) -> None:
    """Emit the power-management files (lid/power-button + PC-vs-laptop idle sleep).

    Four root-owned artifacts, all under /etc or /usr/local/bin, so the OFFLINE
    Calamares install (unpackfs rsyncs the live rootfs) carries them onto the
    installed system unchanged -- and they also govern the live ISO:

      1. STATIC logind drop-in (10-azarch-power.conf): lid does nothing, power
         button powers off. A plain /etc file, effective immediately at boot.
      2. The azarch-sleep-policy script (/usr/local/bin, 0755): decides PC vs laptop
         (battery present?) and AC state at RUNTIME and writes the idle-sleep
         drop-in (20-azarch-sleep.conf), then reloads logind.
      3. Its systemd service (azarch-sleep-policy.service): runs the script at boot;
         the enable-symlink is added in _link_services.
      4. Its udev rule: re-runs the service on AC-adapter plug/unplug so the
         15-minute idle timer arms/disarms live.

    The dynamic 20-*.conf is NOT emitted here -- the script generates it on the
    running system (its value depends on live hardware state, so baking a fixed one
    would be wrong)."""
    emit.write_text(
        airootfs / "etc/systemd/logind.conf.d/10-azarch-power.conf",
        system.LOGIND_POWER_DROPIN,
    )
    emit.write_exec(
        airootfs / "usr/local/bin/azarch-sleep-policy", system.SLEEP_POLICY_SCRIPT
    )
    emit.write_text(
        airootfs / "etc/systemd/system/azarch-sleep-policy.service",
        system.SLEEP_POLICY_SERVICE,
    )
    emit.write_text(
        airootfs / "etc/udev/rules.d/99-azarch-sleep-policy.rules",
        system.SLEEP_POLICY_UDEV_RULE,
    )


def _emit_shared_mount(airootfs: Path) -> None:
    """Write the virtiofs shared-folder .mount unit and create its mountpoint.

    The hypervisor exports the host ./shared folder over virtiofs (mount tag
    "shared"); this unit mounts it at /home/main/shared on boot for BOTH variants,
    so --shared works on the headed variant too (it no longer rides on the ssh
    bring-up). The mountpoint dir must exist for systemd to mount onto it; it is
    owned by `main` (uid 1000) via the closing chown in _emit_provision/_emit_apps
    that covers all of /home/main. The enable-link is added in _link_services."""
    emit.write_text(
        airootfs / "etc/systemd/system/home-main-shared.mount",
        system.HOME_MAIN_SHARED_MOUNT,
    )
    emit.mkdir(airootfs / "home/main/shared")


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
    from makepkg import produced_names
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
            # repo runs SigLevel = Never (libraries/pacman.py) so pacstrap does not verify
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
    downloader._reconcile_index(pkg_repo, lambda _p: None)
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
    downloader._readd_own_packages(pkg_repo, full_compile)
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
    # archiso/git/base-devel/go are the base build toolchain; the application-menu build
    # deps (gtk3 + pkgconf + gcc) are appended because _emit_desktop COMPILES the C/GTK3
    # menu daemon (application_menu.build_daemon) later in this run -- without the GTK3
    # dev stack present here, that `make` dies with "gtk/gtk.h: No such file or directory"
    # and aborts the whole build. Listing them here also means the "already present"
    # early-return below cannot skip a host that is missing only the GTK3 dev stack.
    # + the gedit notepad-mode plugin build deps (the `gedit` pkg-config module -> the
    # gedit/GTK3/libpeas dev headers): _emit_apps COMPILES that libpeas plugin later in
    # this run, so the dev stack must be present here or `make` dies on a missing header.
    # + the bare-`azarch` C terminal UI build dep (just gcc): _emit_desktop COMPILES that
    # UI (terminal_user_interface_build.build_terminal_user_interface) later in this run. It is pure libc (no ncurses/GTK), so gcc
    # -- already pulled in by base-devel / the menu deps -- is all it needs; listed for
    # completeness so the dependency intent is explicit.
    host_pkgs = (["archiso", "git", "base-devel", "go"]
                 + application_menu.MENU_BUILD_DEPS + gedit.GEDIT_PLUGIN_BUILD_DEPS
                 + terminal_user_interface_build.TERMINAL_USER_INTERFACE_BUILD_DEPS)
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
    # Teed so the install's output reaches compile-full.log live. Preserve the old
    # check=True raise-on-failure: run_teed returns the exit code, so raise here.
    cmd = sudo + ["pacman", "-Sy", "--noconfirm", "--needed", *host_pkgs]
    rc = logstream.run_teed(cmd)
    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd)


# Releng-inherited multi-user.target.wants enable-links Az'arch must NOT ship enabled.
# The stock archiso `releng` profile enables sshd on the official Arch ISO by shipping
# airootfs/etc/systemd/system/multi-user.target.wants/sshd.service. _copy_releng copies
# releng verbatim (symlinks preserved), so that link survives onto BOTH Az'arch variants
# unless stripped -- which is exactly why the DEFAULT headed ISO was booting with sshd active
# on :22 (`systemctl status sshd` -> enabled; running). ssh must be OFF on the base ISO and
# ON only on the ssh variant, where it is enabled at boot by sshd-hypervisor-setup.service
# (see _apply_variant / packages/azarch/sshd.py), NOT by this inherited stock want. So we
# delete the releng sshd want here, before any overlay; the ssh variant re-enables sshd
# through its own mechanism, leaving the stock want permanently stripped.
_RELENG_WANTS_TO_STRIP = ("sshd.service",)


def _strip_releng_wants(W: Path) -> None:
    """Remove releng-inherited multi-user.target.wants links Az'arch must not ship enabled
    (currently the stock sshd.service want -- ssh is opt-in per variant, never a releng
    default). Best-effort per name so a future releng that drops one is a no-op, not a break."""
    wants = W / "airootfs/etc/systemd/system/multi-user.target.wants"
    for name in _RELENG_WANTS_TO_STRIP:
        (wants / name).unlink(missing_ok=True)


def _copy_releng(W: Path) -> None:
    src = Path("/usr/share/archiso/configs/releng")
    if not src.is_dir():
        raise SystemExit(f"[x] archiso releng profile not found at {src}; is archiso installed?")
    emit.copy_tree(src, W)
    # Strip releng's inherited sshd enable-link so the DEFAULT headed ISO ships sshd DISABLED
    # (the ssh variant re-enables it per-variant). Without this the base ISO listens on :22.
    _strip_releng_wants(W)


def _brand_boot_menus(W: Path) -> None:
    """Rebrand the copied releng boot menus (systemd-boot UEFI + syslinux BIOS) and
    SKIP the first-boot menu -- boot straight into the default Az'arch entry.

    Runs right after _copy_releng, over the releng files it laid down. The releng
    profile is systemd-boot-only for UEFI (profiledef bootmodes list no `*.grub.*`),
    so the systemd-boot loader here IS the first-boot menu the screenshot shows.

    SKIP: the loader.conf `timeout 0` (UEFI) and archiso_sys.cfg `TIMEOUT 1` (BIOS)
    make the default entry boot immediately with no menu drawn. The menu is still
    reachable by holding a key during boot -- so it is a skip, not a removal -- and
    the branding/trim below is what it shows IF forced open.

    UEFI entries: overwrite 01/02 IN PLACE (same filenames) rather than adding
    differently-named ones alongside -- otherwise the menu shows BOTH the stock
    "Arch Linux install medium" rows AND ours (duplicated rows all reading "Arch
    Linux"). Overwriting rebrands them to Az'arch.

    The extra UEFI rows beside 01/02 -- gone so a forced-open menu is clean too -- go
    via the loader.conf override + one deletion:
      * "EFI Shell"          -- systemd-boot AUTO-discovers the shellx64.efi mkarchiso
                                plants on the ESP; `auto-entries no` hides that (and
                                systemd-boot's own self-entry).
      * "Reboot Into Firmware Interface" -- systemd-boot AUTO-generates it; `auto-firmware
                                no` hides it (still reachable with the `f` key).
      * "Memtest86+"         -- NOT auto-discovered; it is the EXPLICIT releng entry
                                03-archiso-memtest86+x64.conf, so auto-entries can't hide
                                it -- we DELETE the .conf. `auto-entries no` leaves our
                                explicit 01/02 untouched. missing_ok: a future releng may
                                rename/drop it.
    """
    emit.write_text(W / "efiboot/loader/entries/01-archiso-linux.conf", system.BOOT_UEFI_LINUX)
    emit.write_text(W / "efiboot/loader/entries/02-archiso-speech-linux.conf", system.BOOT_UEFI_SPEECH)
    emit.write_text(W / "efiboot/loader/loader.conf", system.BOOT_UEFI_LOADER)
    (W / "efiboot/loader/entries/03-archiso-memtest86+x64.conf").unlink(missing_ok=True)
    # syslinux (BIOS): overlay the top-level archiso_sys.cfg (TIMEOUT 1 -> skip menu),
    # rebrand the two boot labels, and rebrand the menu head's `MENU TITLE` (releng
    # ships "Arch Linux"). BIOS syslinux has no auto-discovered extras to trim.
    emit.write_text(W / "syslinux/archiso_sys.cfg", system.BOOT_BIOS_SYSLINUX_SYS)
    emit.write_text(W / "syslinux/archiso_sys-linux.cfg", system.BOOT_BIOS_SYSLINUX)
    emit.write_text(W / "syslinux/archiso_head.cfg", system.BOOT_BIOS_SYSLINUX_HEAD)


def _emit_fastfetch(ea: Path, home: Path) -> None:
    """Write the azarch fastfetch configuration + Az' logo for the live user, and stage
    a copy under root/azarch/fastfetch so the on-disk installer can replant it
    into the installed user's ~/.config/fastfetch."""
    cfg = home / ".config/fastfetch"
    emit.write_text(cfg / "config.jsonc", fastfetch.config_jsonc())
    emit.write_text(cfg / fastfetch.LOGO_FILENAME, fastfetch.logo_txt())
    # staged copy for the installer to plant on the installed system
    staged = ea / "fastfetch"
    emit.write_text(staged / "config.jsonc", fastfetch.config_jsonc())
    emit.write_text(staged / fastfetch.LOGO_FILENAME, fastfetch.logo_txt())


def _link_services(airootfs: Path, is_gui: bool = True) -> None:
    # Graphical live medium WITHOUT a display manager: the tty1 autologin (overridden
    # to `main`) drops into a login shell whose ~/.bash_profile execs startx ->
    # openbox-session -> (autostart) Calamares. So there is deliberately NO
    # display-manager unit and NO graphical.target.wants here; we only enable the
    # multi-user daemons and the azarch oneshots. X is started from the shell, not by
    # systemd.
    #
    # is_gui gates the desktop-only enable-links (the timedate Flask home page and the
    # SPICE guest agent daemon): their units come from GUI-only packages the headless line
    # skips, so linking them on the headless line would leave a dangling want to a
    # non-existent unit. Every other link here is universal (base console daemons +
    # oneshots). The per-variant sshd + instant enable-links are added in _apply_variant,
    # just before each variant's mkarchiso pass.
    base = airootfs / "etc/systemd/system"
    emit.mkdir(base / "multi-user.target.wants")
    # bluetooth.service is DELIBERATELY NOT enabled here: Bluetooth is OFF by default on
    # Az'arch. `azarch network bluetooth on` enables + starts it (and rfkill-unblocks the
    # radio) on demand; leaving it out of multi-user.target.wants keeps the radio down at
    # boot. NetworkManager (the network stack) and CUPS (printing) stay auto-enabled on
    # BOTH lines.
    for svc in ("NetworkManager.service", "org.cups.cupsd.service"):
        emit.link(f"/usr/lib/systemd/system/{svc}", base / f"multi-user.target.wants/{svc}")
    # spice-vdagentd is the SPICE guest agent's system daemon: it bridges the
    # com.redhat.spice.0 virtio channel so the session spice-vdagent can sync the guest
    # pointer/clipboard/resolution with the SPICE client. Enabling it fixes the SPICE-guest
    # pointer regression (no hover / dropped clicks / stuck labels) -- see the spice-vdagent
    # note in packages.x86_64 and the autostart line in packages/openbox. HEADED LINE ONLY:
    # spice-vdagent is a GUI-session package excluded from the headless pacstrap
    # (packages_manifest.HEADLESS_EXCLUDED), so enabling its daemon on the headless line
    # would dangle. Harmless on non-SPICE headed systems (the daemon idles with no channel).
    if is_gui:
        emit.link("/usr/lib/systemd/system/spice-vdagentd.service",
                  base / "multi-user.target.wants/spice-vdagentd.service")
    emit.link("/etc/systemd/system/locale-setup.service", base / "multi-user.target.wants/locale-setup.service")
    emit.link("/etc/systemd/system/pkgs-setup.service", base / "multi-user.target.wants/pkgs-setup.service")
    # PC-vs-laptop idle-sleep policy oneshot: enabled on BOTH ISOs (and, via unpackfs,
    # the installed system). Runs azarch-sleep-policy at boot to write the idle
    # drop-in for the detected chassis/AC state; the udev rule re-runs it on plug/
    # unplug. See _emit_power / libraries/system.py.
    emit.link("/etc/systemd/system/azarch-sleep-policy.service",
              base / "multi-user.target.wants/azarch-sleep-policy.service")
    # Az'arch timedate home page service: the Flask Time + Calendar site (localhost:49154)
    # LibreWolf lands on. HEADED LINE ONLY -- its unit is emitted by _emit_desktop (which
    # the headless line skips), and a headless machine has no browser to land on it. Enabling
    # it on the headless line would leave a dangling want to a unit that was never written.
    if is_gui:
        emit.link(timedate.SERVICE_SYSTEM_PATH,
                  base / f"multi-user.target.wants/{timedate.SERVICE_NAME}")
    # The virtiofs shared-folder auto-mount: enabled on BOTH ISOs (and, via unpackfs,
    # the installed system) so the host ./shared folder appears at /home/main/shared
    # on boot regardless of --ssh. This is the fix for the headed-variant coupling;
    # the unit body + mountpoint come from _emit_shared_mount. A .mount enable-link is
    # a symlink named after the unit, same mechanism as the .service links above.
    emit.link("/etc/systemd/system/home-main-shared.mount",
              base / "multi-user.target.wants/home-main-shared.mount")


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
            "    [!] Offline conf rewrite did not inject the local repo -- check libraries/pacman.py.\n"
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


def _run_mkarchiso(sudo, W: Path, bar: ProgressBar, reclaim_after, iso_name: str = "azarch-headed") -> Path:
    # temp dir cleanup (matches the old "Cleaning up temp directory" step)
    subprocess.run(["rm", "-rf", str(W / ".temp")], check=False)
    # Reset the mkarchiso work tree BEFORE every pass. This is load-bearing for the
    # two-variant build: mkarchiso guards each build step with a `_run_once` sentinel
    # file (work/base.<fn>, work/iso.<fn>) and REFUSES to remove a pre-existing work
    # dir. If the sshd pass reused the base pass's work/, every step -- airootfs build,
    # squashfs, and the final ISO write -- would be skipped as "already done", and
    # azarch-sshd-*.iso would never be written (mkarchiso even reuses the base ISO's
    # name slot). Wiping work/ first makes each variant a genuine fresh mkarchiso pass.
    # Unmount any proc/sys/dev/run mkarchiso bind-mounted under the old airootfs before
    # rm, or rm -rf would recurse into live mounts. The base pass's rm is a near-no-op
    # (step 1 already reset W); the sshd pass's rm clears the base pass's sentinels.
    _unmount_worktree(sudo)
    subprocess.run(sudo + ["rm", "-rf", str(W / "work")], check=False)
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
    # Select the ISO THIS build produced. output/ may hold BOTH variants
    # (azarch-*.iso AND azarch-sshd-*.iso) when both have been built, so we must not
    # just take the first *.iso. mkarchiso names artifacts <iso_name>-<version>-<arch>
    # where <version> is YYYY.MM.DD (always starts with a DIGIT). Anchoring the glob
    # with a digit right after "{iso_name}-" makes the BASE selection exact: "azarch-"
    # followed by a digit matches azarch-2026...iso but NOT azarch-sshd-...iso ("s" is
    # not a digit) -- so the base pass can never accidentally pick up the sshd ISO,
    # regardless of build order or mtimes.
    isos = sorted(paths.BUILDDIR.glob(f"{iso_name}-[0-9]*.iso"))
    if not isos:
        # Fall back to any .iso so a naming surprise still surfaces the artifact.
        isos = sorted(paths.BUILDDIR.glob("*.iso"))
    if not isos:
        raise SystemExit("[x] ISO build failed: no .iso found in output/")
    # Newest matching ISO (this run's), in case an older same-variant ISO lingers.
    return max(isos, key=lambda p: p.stat().st_mtime)


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
    pinned bar's scroll region) and the FULL untruncated line to compile-full.log. A prior
    change wrote the clipped copy through plain stdout.write, which fed the SAME
    truncated text to the log too -- silently cutting the tail off every wide
    mkarchiso line in compile-full.log. write_split keeps the two independent so the log is
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
        # compile-full.log gets the FULL line. write_split does both in one write via the tee.
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


# --- driver / entry point --------------------------------------------------
# Folded in from the old compiler.py: `python3 -m compiler` runs main() below. The
# thin compile.sh shim sets up the PTY + primes sudo, then hands off here; this
# section owns the offline decision, the sudo keepalive + ownership reclaim, the
# progress bar, the SIGINT/SIGTERM teardown, and the final ISO report.


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
    # Manifest-coverage clause (same spirit as the own-packages clause above): the
    # offline repo must hold a package file for EVERY downloadable package the
    # manifest names. A cache can pass all the structural markers yet still lack a
    # package that was ADDED to packages.x86_64 after the cache was last warmed
    # (e.g. xorg-xset) -- and an offline pacstrap then dies with "target not found:
    # <pkg>". Treating any such gap as incomplete forces this run ONLINE to fetch
    # exactly the missing packages; the next run is then genuinely offline-complete.
    # The exclusion set (our own built packages) is tier-independent, so
    # full_compile=False matches the produced_names call above.
    if downloader.missing_from_repo(paths.PKG_REPO, full_compile=False):
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
    # When we are going ONLINE despite an otherwise-warm cache, say WHY: name the
    # manifest packages the offline repo is missing (the coverage clause in
    # cache_is_complete demoted this run to online precisely because these have no
    # file in cache/pkgs/repo/). Without this, adding a package to packages.x86_64
    # would silently trigger a fresh download with no explanation. Best-effort:
    # never let diagnostics abort the build.
    if offline:
        return
    try:
        if not any(paths.PKG_REPO.glob("*.pkg.tar.zst")):
            return  # no cache at all -- a normal cold build, nothing "stale".
        missing = downloader.missing_from_repo(paths.PKG_REPO, full_compile=False)
        if missing:
            shown = ", ".join(missing[:12]) + (", ..." if len(missing) > 12 else "")
            sys.stderr.write(
                f"[!] {len(missing)} manifest package(s) are not in the offline cache "
                f"and will be downloaded: {shown}\n"
                "    (packages.x86_64 gained entries since the cache was last warmed.)\n"
            )
    except OSError:
        pass


def main() -> int:
    paths.LOGDIR.mkdir(parents=True, exist_ok=True)

    # --estimate* (six variants): predict how long a build would take on this
    # machine -- COMPUTE (compiling on this CPU/RAM) and/or NETWORK (downloading
    # the components over this connection) -- then exit. Pure query: no workspace
    # reset, no sudo, no build, and NOT routed through the build-log tee (it is a
    # query, not a build, so its output belongs on the terminal, not logs/compile-full.log
    # -- this branch returns before logstream.install() below). The network modes
    # DO open a client socket for a few-second bandwidth probe, but that needs no
    # privilege and writes no build file. compile.sh routes any --estimate* arg
    # here without a PTY or sudo prime.
    if estimate.parse_estimate_flag(sys.argv[1:]) is not None:
        return estimate.run(sys.argv[1:])

    # HARD STOPS (side-effect-free, before any workspace/cache setup). Each returns an
    # error message to print + exit 2 on; None means proceed. A bare/empty --ssh or
    # --password, an --ssh+--password conflict, --encrypt without a password, a bad --type,
    # a malformed --static-ip, or an unknown --timezone all abort cleanly here.
    for err in (
        check_type_flag(sys.argv[1:]),
        check_ssh_flag(sys.argv[1:]),
        check_password_flag(sys.argv[1:]),
        check_ssh_password_conflict(sys.argv[1:]),
        check_encrypt_flag(sys.argv[1:]),
        check_static_ip_flag(sys.argv[1:]),
        check_timezone_flag(sys.argv[1:]),
    ):
        if err:
            sys.stderr.write("[x] " + err + "\n")
            return 2

    paths.CACHEDIR.mkdir(parents=True, exist_ok=True)

    # Python owns compile-full.log from here on: route stdout/stderr through a tee that
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

    # ONE login password from EITHER --ssh (also enables sshd + the ssh variants) OR
    # --password (sshd off); they are mutually exclusive (checked above). It is hashed HERE
    # (sha-512 crypt) and threaded into run(); the plaintext stays in this process EXCEPT for
    # a non-ssh encrypted instant, where the LUKS passphrase needs it (threaded as
    # login_password and written only into that ISO's root-owned instant script).
    ssh_password = parse_ssh_flag(sys.argv[1:])
    login_password = ssh_password if ssh_password else parse_password_flag(sys.argv[1:])
    login_hash = ssh_password_hash(login_password) if login_password else None
    login_user = parse_user_flag(sys.argv[1:])

    # The headed line is ALWAYS built; --type adds the headless line, --instant adds the
    # auto-install variants, --ssh adds the ssh variants (the Cartesian product via
    # variants.selected_variants). --encrypt encrypts the instant install's disk.
    type_value = parse_type_flag(sys.argv[1:])
    headless = type_wants_headless(type_value)
    instant = wants_instant(sys.argv[1:])
    encrypt = wants_encrypt(sys.argv[1:])
    timezone = parse_timezone_flag(sys.argv[1:])
    build_variants = _variants.selected_variants(
        headless=headless, instant=instant, ssh=bool(ssh_password),
    )

    # Static IP: build the NetworkManager keyfile text once (baked into every line's
    # airootfs in run()). --gateway/--dns refine it; both validated/warn'd above.
    static_ip = parse_static_ip_flag(sys.argv[1:])
    static_ip_text = None
    if static_ip:
        static_ip_text = network_profile.nmconnection_text(
            static_ip, gateway=parse_gateway_flag(sys.argv[1:]),
            dns=parse_dns_flag(sys.argv[1:]),
        )

    # Warnings (non-fatal): a flag that will be silently ignored in this configuration.
    for warn in (
        timezone_without_instant_warning(sys.argv[1:]),
        user_without_password_warning(sys.argv[1:]),
        gateway_dns_without_static_ip_warning(sys.argv[1:]),
    ):
        if warn:
            print("[!] " + warn)

    # Announce exactly what will be built (name every ISO), so the operator sees the matrix
    # the flags expanded to before the long build starts.
    noun = "ISO" if len(build_variants) == 1 else "ISOs"
    print(f"[*] Building {len(build_variants)} {noun}:")
    for v in build_variants:
        notes = []
        if v.ssh:
            notes.append(f"ssh: `{login_user}` gets the --ssh password, sshd on :22")
        if v.instant:
            enc = ", ENCRYPTED disk" if encrypt else ""
            notes.append(f"instant: auto-install to the largest disk, tz {timezone}{enc}")
        suffix = ("  (" + "; ".join(notes) + ")") if notes else ""
        print(f"      - {v.iso_name}-<ver>-x86_64.iso{suffix}")
    if not login_hash:
        print('    (pass --ssh="<PW>" for ssh; --password="<PW>" for a local login; '
              '--type=headless|all for the headless line; --instant for auto-install.)')

    offline = cache_is_complete()
    _stale_cache_notice(offline)

    bar = ProgressBar(weights_for(build_variants))
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
        kill_active_child(_sudo())  # kill mkarchiso's OWN group, not ours
        _unmount_worktree(_sudo())
        bar.cleanup()
        own.reclaim_full()  # SAFEGUARD final

    def on_signal(signum, _frame) -> None:
        # Kill ONLY the mkarchiso child's process group (it is spawned in its own
        # session, see _run_mkarchiso), never our own group -- signalling our
        # own group would re-enter this handler and could interrupt teardown
        # mid-chown, leaving cache/build root-owned (the exact old-bash hazard).
        teardown()
        os._exit(130)

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    bar.init()
    try:
        isos = run(bar, offline, full_compile=full_compile,
                   ssh_password_hash=login_hash,
                   login_user=login_user, login_password=login_password,
                   encrypt=encrypt, static_ip_text=static_ip_text,
                   build_variants=build_variants, timezone=timezone,
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
    # Report each ISO actually built with its size. The count is conditional now: the
    # base ISO always, plus the sshd ISO only when --ssh was supplied (isos is ordered
    # base first -- see _variants_for). Pluralize honestly so we never claim two ISOs
    # when only one was built.
    noun = "ISO" if len(isos) == 1 else "ISOs"
    lines = [f"\n[ {bar.total_steps}/{bar.total_steps} ] [OK] {len(isos)} {noun} built successfully:"]
    for iso in isos:
        iso_size = subprocess.run(["du", "-h", str(iso)], capture_output=True, text=True).stdout.split("\t")[0]
        iso_path = f"output/{iso.name}" if paths.in_docker() else str(iso)
        entry = f"           - {iso_path}"
        if iso_size:
            entry += f" ({iso_size})"
        lines.append(entry)
    if paths.in_docker():
        lines.append("           The ISOs are in output/ on your host (NOT build/output/).")
    report = "\n".join(lines)
    print(report)
    with paths.STEPS_LOG.open("a") as f:
        f.write(report + "\n")

    teardown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
