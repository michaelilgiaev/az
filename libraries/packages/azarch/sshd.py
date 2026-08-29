#!/usr/bin/env python3
"""azarch guest command line interface -- `--sshd-hypervisor` (wire the guest sshd up for the hypervisor).

Installs the host's public key from ~/shared/authorized_keys (staged there by the
hypervisor) into the target user's ~/.ssh/authorized_keys, then enables and starts sshd.
Safe to run more than once. Named --sshd-hypervisor because it wires the guest sshd up for
the hypervisor's forwarded host->guest SSH port. See common.py for how modules are bundled.
"""

from __future__ import annotations

# BUNDLE_START

# The ssh-variant hardening drop-in (written to /etc/ssh/sshd_config.d/ by the bring-up).
# `PermitEmptyPasswords no` is OpenSSH's default; pinning it explicitly makes the ssh
# variant's posture intentional and drift-proof (data/PROMPT.md DECISION 2: never allow a
# blank-password login). A drop-in leaves the stock sshd_config untouched.
SSHD_HARDENING_CONF = (
    "# Az'arch ssh-variant hardening -- written by `azarch --sshd-hypervisor`.\n"
    "# Refuse empty-password logins (the shipped default, pinned so it cannot drift).\n"
    "PermitEmptyPasswords no\n"
)


def _install_hypervisor_pubkey(target_user: str, target_home: str) -> None:
    """BEST-EFFORT: if the virtiofs `shared` folder carries a host pubkey, install it into
    the TARGET user's ~/.ssh/authorized_keys so the hypervisor can log in by KEY.

    This is the HYPERVISOR nicety and is deliberately NON-FATAL: under QEMU/virtiofs the
    host stages ~/shared/authorized_keys and we install it; on BARE-METAL (an installed ssh
    variant) there is no virtiofs share, so we simply skip it and rely on PASSWORD auth (the
    operator's --ssh password, baked into /etc/shadow). Enabling sshd itself must NOT
    depend on this -- otherwise the installed ssh desktop would never start sshd. Any
    failure here is reported and swallowed; the caller proceeds to bring sshd up regardless.

    A root-owned authorized_keys trips sshd StrictModes, so the dir + key are chowned to
    the target user (install -o/-g target_user)."""
    shared = os.path.join(target_home, "shared")
    key = os.path.join(shared, "authorized_keys")
    if not _is_mountpoint(shared):
        # Try to mount the virtiofs share; if it is not there (bare metal, or the
        # home-main-shared.mount unit already covers it), give up quietly. This is a
        # FALLBACK: normally the systemd .mount unit has already mounted ~/shared, but
        # mounting here too makes the pubkey install work even before that unit runs.
        os.makedirs(shared, exist_ok=True)
        rc = _sudo("mount", "-t", "virtiofs", "shared", shared, check=False)
        if rc != 0:
            print("azarch --sshd-hypervisor: no virtiofs shared folder; skipping "
                  "host-key install (password login still works).")
            return
    if not os.path.isfile(key):
        print(f"azarch --sshd-hypervisor: {key} not found; skipping host-key install "
              "(password login still works).")
        return
    ssh_dir = os.path.join(target_home, ".ssh")
    rc = _sudo("install", "-d", "-m", "700", "-o", target_user, "-g", target_user,
               ssh_dir, check=False)
    if rc != 0:
        _err("azarch --sshd-hypervisor: could not create ~/.ssh; skipping host-key "
             "install (password login still works).")
        return
    rc = _sudo("install", "-m", "600", "-o", target_user, "-g", target_user,
               key, os.path.join(ssh_dir, "authorized_keys"), check=False)
    if rc != 0:
        _err("azarch --sshd-hypervisor: could not install the host pubkey; skipping "
             "(password login still works).")
        return
    print(f"Installed pubkey -> {target_home}/.ssh/authorized_keys")


def sshd_hypervisor() -> int:
    """Bring the ssh server up: (best-effort) install the hypervisor host pubkey, generate
    host keys, OPEN port 22/tcp, then enable+start sshd. Resolves the REAL login user via
    SUDO_USER (the documented invocation is `sudo azarch --sshd-hypervisor`) and refuses a
    bare-root target.

    Works in BOTH environments: under the hypervisor it also installs the host pubkey from
    the virtiofs share (key login); on bare metal (an installed ssh desktop) it skips the pubkey
    step and relies on PASSWORD login (the --ssh password in /etc/shadow). Only the pubkey
    step is optional -- host-key generation, the firewall open, and enabling sshd are
    FAIL-FAST (a failure bails with that step's code and does NOT print the success line, so
    a dead sshd never reports "enabled and started")."""
    target_user = os.environ.get("SUDO_USER") or _current_user()
    if target_user == "root":
        _err("azarch --sshd-hypervisor: run as a normal user via sudo (got root); "
             "cannot stage a login key for root")
        return 1
    try:
        import pwd
        target_home = pwd.getpwnam(target_user).pw_dir
    except KeyError:
        target_home = ""
    if not target_home:
        _err(f"azarch --sshd-hypervisor: could not resolve home for user {target_user}")
        return 1
    # Host pubkey install is BEST-EFFORT (hypervisor only); never blocks bringing sshd up.
    _install_hypervisor_pubkey(target_user, target_home)
    # From here the steps are FAIL-FAST: a failure bails with its exit code and does NOT
    # print the success line (so a failed sshd never reports "enabled and started").
    rc = _sudo("ssh-keygen", "-A", check=False)
    if rc != 0:
        return rc
    # setup-pkgs.sh sets 'ufw default deny incoming', so open :22 BEFORE starting
    # sshd (so the forwarded host->guest port is reachable the moment it listens).
    # 22/tcp explicitly (ssh is tcp): the user's firewall spec is "port 22 configured to
    # allow tcp", and an explicit proto is unambiguous where the `ssh` service alias could
    # in principle also add udp on some ufw app profiles.
    rc = _sudo("ufw", "allow", "22/tcp", check=False)
    if rc != 0:
        return rc
    # HARDEN the ssh variant (data/PROMPT.md DECISION 2): drop a config snippet that
    # refuses empty-password logins, so even if some account ever ended up with a blank
    # shadow field, sshd would reject it. `PermitEmptyPasswords no` is already OpenSSH's
    # default, but writing it explicitly makes the posture intentional and drift-proof (a
    # future default change cannot silently weaken us). A sshd_config.d drop-in is the
    # non-destructive way to set it (leaves the stock sshd_config untouched).
    _sudo_write("/etc/ssh/sshd_config.d/10-azarch-hardening.conf", SSHD_HARDENING_CONF)
    rc = _sudo("systemctl", "enable", "--now", "sshd", check=False)
    if rc != 0:
        return rc
    print(f"sshd enabled and started -- ssh in as {target_user}.")
    return 0


def sshd_stop() -> int:
    """Stop AND disable sshd, then CLOSE port 22 in the firewall -- the inverse of the
    `--sshd-hypervisor` bring-up. Used by `azarch network ssh stop` and the TUI's SSH
    Server screen so a user can turn ssh back off from one place.

    Disabling the service (not just stopping it) is deliberate: `stop` alone would let
    sshd come back at the next boot. We also `ufw delete allow 22/tcp` so the open port
    does not outlive the running service (an open :22 with nothing listening is still an
    advertised attack surface). Each step is best-effort (check=False) and the worst rc is
    returned, so a missing ufw rule does not mask a failed systemctl."""
    rc = _sudo("systemctl", "disable", "--now", "sshd", check=False)
    # Remove the allow rule so the port is not left open with no service behind it. A
    # non-existent rule makes ufw exit non-zero, which is fine here (nothing to close).
    _sudo("ufw", "delete", "allow", "22/tcp", check=False)
    if rc != 0:
        _err("azarch: could not stop sshd (systemctl disable --now sshd failed).")
        return rc
    print("sshd stopped and disabled; port 22 closed in the firewall.")
    return 0


def sshd_is_active() -> bool:
    """True if the sshd service is currently active. Pure read (no root)."""
    return subprocess.run(["systemctl", "is-active", "--quiet", "sshd"],
                          check=False).returncode == 0


def sshd_status() -> int:
    """Print whether sshd is active and whether port 22 is allowed through the firewall --
    a one-shot read for `azarch network ssh status` and the TUI status line. Returns 0 if
    sshd is active, 1 otherwise, so a caller/probe can branch on the exit code."""
    active = sshd_is_active()
    print(f"sshd: {'active' if active else 'inactive'}")
    # Report the firewall posture for :22 too (read-only via a non-interactive sudo; if
    # that needs a password we simply omit the line rather than prompt from a status read).
    r = subprocess.run(["sudo", "-n", "ufw", "status"],
                       capture_output=True, text=True, check=False)
    if r.returncode == 0:
        allowed = any("22" in ln and "ALLOW" in ln.upper() for ln in r.stdout.splitlines())
        print(f"firewall: port 22 {'allowed' if allowed else 'not allowed'}")
    return 0 if active else 1
