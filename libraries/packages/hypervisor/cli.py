"""cli.py - argument parsing, usage text, and the dispatch entry point.

This file only parses args and calls into virtual_machine.py; all the real logic
lives in the other modules.
"""

from __future__ import annotations

import os
import sys

# The app is a flat directory installed to LIB_DIR; this is the ENTRY the launcher execs.
# Dual-mode sibling import (see configuration.py for the full rationale): when run FLAT by
# absolute path (the launcher does NOT cd -- the caller's CWD is preserved so
# `Config.from_cwd()` resolves the VM against the directory the user is in) __package__ is
# empty, so we bootstrap sys.path and import the bare siblings; when imported by the test
# suite as packages.hypervisor.cli, __package__ is set, so we use package-relative imports
# (one HypervisorError class, shared with the tests). Mirrors packages/backup/backup.py.
if __package__:
    from . import virtual_machine as vm
    from .checks import HypervisorError
    from .configuration import Config, DEFAULT_SSH_FORWARD_PORT
else:  # loaded flat (run by absolute path via the launcher) -- no parent package
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import virtual_machine as vm  # noqa: E402  (after the sys.path bootstrap above)
    from checks import HypervisorError  # noqa: E402
    from configuration import Config, DEFAULT_SSH_FORWARD_PORT  # noqa: E402


def usage(cfg: Config) -> str:
    return f"""\
hypervisor - run a QEMU/KVM VM from the current directory.

Each directory is its own independent VM (name derived from folder: '{cfg.vm}').
Files created here: {cfg.vm}.qcow2 (disk), OVMF_VARS.4m.fd (UEFI NVRAM),
shared/ (host<->guest folder), hypervisor.cfg (settings).

USAGE:
  hypervisor install <file.iso> [--shared] [--ssh[=PORT]] [--share-host-gpu]
                             Create disk + UEFI NVRAM + hypervisor.cfg (does NOT
                             boot). The ISO argument is REQUIRED. Flags set the
                             matching hypervisor.cfg toggles on.
  hypervisor run <file.qcow2> [--iso <file.iso>]
                             Boot the named disk (REQUIRED). --iso attaches an
                             installer ISO for repair or first-time install. An
                             EMPTY disk auto-attaches the dir's single ISO.
  hypervisor share [--offline]
                             Print commands to mount the host ./shared folder
                             inside the guest. --offline edits the powered-off
                             disk directly (Btrfs @/@home layout only).
  hypervisor status          Show VM name, files, running state, SSH port, toggles.
  hypervisor stop            Power this VM off.
  hypervisor help            This text.

hypervisor.cfg keys (all settings live here -- edit freely; a running VM applies
edits live where it can, and reverts a file with an invalid value):
  share_host_gpu                  guest uses the host GPU (shared, not passthrough);
                                  false = generic software-rendered GPU
  network                         user (NAT) | none | a host interface to bridge
                                  (list interfaces: ip -br addr)
  shared                          false | empty (this dir) | an absolute host path
                                  to share into the guest via virtio-9p
  ssh                             forward the guest's SSH port to the host
  ssh_guest_to_host_port_forward  host port that maps to guest :22 (default {DEFAULT_SSH_FORWARD_PORT})
  usb                             empty | absolute device path(s) to pass through
                                  (find them: lsusb, lsblk -o NAME,TRAN,MOUNTPOINT)
  fullscreen                      borderless exclusive fullscreen
  ask_before_quitting_hypervisor  prompt before closing the viewer window
  ram                             MiB of guest RAM, e.g. 16384 (host: free -h)
  cpus                            vCPU count, do not exceed nproc (host: lscpu)
  disk_size                       qcow2 disk size (e.g. 200G)
  audio                           on | off (on = PipeWire; confirm: pactl info)

ENV OVERRIDES (override hypervisor.cfg at runtime, not persisted):
  NETWORK  DISK_SIZE  RAM  CPUS  AUDIO  SSHPORT  SHARED  USB
  SHARE_HOST_GPU=1  SSH=1  FULLSCREEN=1  ASK_QUIT=1  FORCE=1  YES=1  VENUS=1  DRYRUN=1

EXAMPLE:
  cd ~/Hypervisors/azarch
  hypervisor install azarch-2026.07.23-x86_64.iso --ssh
  hypervisor run azarch.qcow2 --iso azarch-2026.07.23-x86_64.iso"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "help"
    rest = argv[1:]

    try:
        cfg = Config.from_cwd()

        if cmd == "install":
            vm.do_install(cfg, *_parse_install_args(rest))
        elif cmd == "run":
            _dispatch_run(cfg, rest)
        elif cmd == "share":
            vm.do_share(cfg, rest[0] if rest else "")
        elif cmd == "status":
            vm.do_status(cfg)
        elif cmd == "stop":
            vm.do_stop(cfg)
        elif cmd in ("help", "-h", "--help"):
            print(usage(cfg))
        else:
            print(f"hypervisor: unknown subcommand: {cmd}\n", file=sys.stderr)
            print(usage(cfg), file=sys.stderr)
            return 2
    except HypervisorError as exc:
        print(f"hypervisor: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


def _parse_install_args(rest: list[str]) -> tuple:
    """Return (iso_arg, shared, ssh, share_host_gpu, ssh_port) from install args.

    ssh_port is '' unless the user wrote --ssh=PORT or '--ssh PORT'; an empty
    string means "use the hypervisor.cfg default". (USB passthrough has no install
    flag -- it is a device-path list edited in hypervisor.cfg after install.)
    """
    iso_arg = ""
    shared = False
    ssh = False
    share_host_gpu = False
    ssh_port = ""
    i = 0
    while i < len(rest):
        token = rest[i]
        if token == "--shared":
            shared = True
        elif token == "--share-host-gpu":
            share_host_gpu = True
        elif token == "--ssh":
            ssh = True
            # optional space-separated port: '--ssh 2222'
            if i + 1 < len(rest) and rest[i + 1].isdigit():
                ssh_port = rest[i + 1]
                i += 1
        elif token.startswith("--ssh="):
            ssh = True
            ssh_port = token.split("=", 1)[1]
        elif token.startswith("--"):
            print(f"hypervisor install: unknown flag: {token}", file=sys.stderr)
        elif not iso_arg:
            iso_arg = token
        i += 1
    return iso_arg, shared, ssh, share_host_gpu, ssh_port


def _dispatch_run(cfg: Config, rest: list[str]) -> None:
    positional = [t for t in rest if not t.startswith("--")]
    disk_arg = positional[0] if positional else ""
    disk = cfg.resolve_run_disk(disk_arg)
    cfg = cfg.__class__(**{**cfg.__dict__, "disk": disk})

    iso_arg = _flag_value(rest, "--iso")
    if "--iso" in rest or iso_arg:
        iso = cfg.resolve_iso(iso_arg) if iso_arg else cfg.resolve_iso(os.environ.get("ISO", ""))
        vm.do_run(cfg, install_iso=iso)
    else:
        vm.do_run(cfg)


def _flag_value(rest: list[str], flag: str) -> str:
    """Value after `flag` (space-separated) or in `flag=value` form; '' if none."""
    for i, tok in enumerate(rest):
        if tok == flag and i + 1 < len(rest) and not rest[i + 1].startswith("--"):
            return rest[i + 1]
        if tok.startswith(flag + "="):
            return tok.split("=", 1)[1]
    return ""


# cli.py IS the entry the /usr/local/bin/hypervisor launcher execs directly (see
# packaging.py), so it must run main() when executed as a script -- the source relied on
# __main__.py for this, but the launcher targets cli.py. Mirrors packages/backup/backup.py.
if __name__ == "__main__":
    sys.exit(main())
