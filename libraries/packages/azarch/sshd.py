#!/usr/bin/env python3
"""azarch guest command line interface -- `--sshd-hypervisor` (wire the guest sshd up for the hypervisor).

Installs the host's public key from ~/shared/authorized_keys (staged there by the
hypervisor) into the target user's ~/.ssh/authorized_keys, then enables and starts sshd.
Safe to run more than once. Named --sshd-hypervisor because it wires the guest sshd up for
the hypervisor's forwarded host->guest SSH port. See common.py for how modules are bundled.
"""

from __future__ import annotations

# BUNDLE_START


def sshd_hypervisor() -> int:
    """Install the host pubkey from ~/shared/authorized_keys into the TARGET user's
    ~/.ssh/authorized_keys and start sshd. Resolves the REAL login user via SUDO_USER
    (the documented invocation is `sudo azarch --sshd-hypervisor`), refuses a bare-root
    target, mounts the 9p `shared` folder, and opens the firewall before starting
    sshd."""
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
    shared = os.path.join(target_home, "shared")
    key = os.path.join(shared, "authorized_keys")
    if not _is_mountpoint(shared):
        os.makedirs(shared, exist_ok=True)
        rc = _sudo("mount", "-t", "9p", "-o",
                   "trans=virtio,version=9p2000.L,msize=104857600",
                   "shared", shared, check=False)
        if rc != 0:
            _err("azarch --sshd-hypervisor: could not mount shared folder (is the VM "
                 "running with shared_directory=true?)")
            return 1
    if not os.path.isfile(key):
        _err(f"azarch --sshd-hypervisor: {key} not found -- stage a host pubkey there "
             "first")
        return 1
    # Install the key into the TARGET user's ~/.ssh and hand ownership to them
    # (root-owned authorized_keys trips sshd StrictModes). Each privileged step is
    # FAIL-FAST, mirroring the old shell command line interface's `set -e`: if a step fails, bail with its
    # exit code and do NOT print the success line (so a failed sshd never reports
    # "enabled and started"). _sudo returns the child's exit code.
    ssh_dir = os.path.join(target_home, ".ssh")
    rc = _sudo("install", "-d", "-m", "700", "-o", target_user, "-g", target_user,
               ssh_dir, check=False)
    if rc != 0:
        return rc
    rc = _sudo("install", "-m", "600", "-o", target_user, "-g", target_user,
               key, os.path.join(ssh_dir, "authorized_keys"), check=False)
    if rc != 0:
        return rc
    print(f"Installed pubkey -> {target_home}/.ssh/authorized_keys")
    rc = _sudo("ssh-keygen", "-A", check=False)
    if rc != 0:
        return rc
    # setup-pkgs.sh sets 'ufw default deny incoming', so open :22 BEFORE starting
    # sshd (so the forwarded host->guest port is reachable the moment it listens).
    rc = _sudo("ufw", "allow", "ssh", check=False)
    if rc != 0:
        return rc
    rc = _sudo("systemctl", "enable", "--now", "sshd", check=False)
    if rc != 0:
        return rc
    print(f"sshd enabled and started -- ssh in as {target_user}.")
    return 0
