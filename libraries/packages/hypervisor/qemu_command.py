"""qemu_command.py - the pure QEMU command-line assembler.

build_qemu_argv() takes already-resolved inputs (the system disk path, the
display/gpu args, the installer-ISO args, and the forwarded SSH port) and returns
the full argv list. It is PURE: no process launch, no filesystem mutation. That
purity is what lets the command be pinned in tests without a real host.

virtual_machine.do_run decides the host-dependent inputs (render node, whether an
ISO is attached) and keeps the checks + launch; this module just assembles. The
audio, shared-folder (virtio-9p), networking, and USB blocks are gated on the
config here so the whole command lives in one place.

Extracted from virtual_machine.py to keep that module under the 750-line limit
once the richer usb/shared/network handling landed.
"""

from __future__ import annotations

import os
import sys

# Flat app, dual-mode sibling import (see configuration.py for the full rationale): use a
# package-relative import when loaded as packages.hypervisor.qemu_command (tests / -m), and
# a sys.path bootstrap + bare import when loaded flat by absolute path (via the launcher).
if __package__:
    from .configuration import Config
else:  # loaded flat (run by absolute path via the launcher) -- no parent package
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from configuration import Config  # noqa: E402  (after the sys.path bootstrap above)


def _audio_args(cfg: Config) -> list[str]:
    """PipeWire duplex audio when audio=on; nothing when off."""
    if cfg.audio != "on":
        return []
    return [
        "-audiodev", "pipewire,id=snd0",
        "-device", "ich9-intel-hda,id=hda",
        "-device", "hda-duplex,bus=hda.0,audiodev=snd0",
    ]


def _shared_args(cfg: Config) -> list[str]:
    """virtio-9p export of the host share dir, or nothing when shared is off.

    cfg.shared_path resolves the union type: True -> the working ./shared dir, a
    string -> that host path, False -> '' (disabled)."""
    path = cfg.shared_path
    if not path:
        return []
    return [
        "-fsdev", f"local,id=fsdev0,path={path},security_model=none",
        "-device", "virtio-9p-pci,fsdev=fsdev0,mount_tag=shared",
    ]


def _net_args(cfg: Config, port: "int | None") -> list[str]:
    """Guest networking from cfg.network:
      * user       -> QEMU user-mode NAT (+ optional guest :22 hostfwd).
      * none       -> no NIC at all.
      * <iface>    -> bridge a virtio NIC onto that host interface (needs the
                      iface to be a bridge / qemu-bridge-helper; wifi usually
                      cannot be bridged).
    """
    net = cfg.hcfg.network
    if net == "none":
        return []
    if net == "user":
        netdev = "user,id=net0"
        if port is not None:
            netdev += f",hostfwd=tcp::{port}-:22"
        return ["-netdev", netdev, "-device", "virtio-net-pci,netdev=net0"]
    # a named host interface -> bridged. hostfwd does not apply to a bridge.
    return ["-netdev", f"bridge,id=net0,br={net}",
            "-device", "virtio-net-pci,netdev=net0"]


def _usb_args(cfg: Config) -> list[str]:
    """Pass each configured USB device through to the guest via usb-host.

    cfg.usb is a list of absolute host device paths (e.g. /dev/bus/usb/003/004).
    Empty list -> no controller, no devices. One xHCI controller carries all of
    them."""
    devices = cfg.hcfg.usb
    if not devices:
        return []
    args = ["-device", "qemu-xhci,id=xhci"]
    for i, path in enumerate(devices):
        args += ["-device",
                 f"usb-host,hostdevice={path},id=usbhost{i},bus=xhci.0"]
    return args


def build_qemu_argv(cfg: Config, *, disk: str, gpu_args: list[str],
                    iso_args: list[str], port: "int | None") -> list[str]:
    """Assemble the full QEMU command line as an argv list. PURE."""
    return [
        "qemu-system-x86_64",
        "-name", f"{cfg.vm},process={cfg.proc}",
        "-nodefaults",
        "-machine", "q35,accel=kvm,vmport=off",
        "-cpu", "host",
        "-smp", f"{cfg.cpus},sockets=1,cores={cfg.cpus},threads=1",
        "-m", cfg.ram,
        "-drive", f"if=pflash,format=raw,unit=0,readonly=on,file={cfg.code}",
        "-drive", f"if=pflash,format=raw,unit=1,file={cfg.vars}",
        "-drive", f"if=none,id=disk0,file={disk},format=qcow2,cache=writeback,discard=unmap,aio=threads",
        "-device", "virtio-blk-pci,drive=disk0,bootindex=1",
        *iso_args,
        *gpu_args,
        "-spice", f"unix=on,addr={cfg.spice_sock},disable-ticketing=on,gl=off,streaming-video=off,playback-compression=off",
        "-device", "virtio-serial-pci",
        "-chardev", "spicevmc,id=vdagent,name=vdagent",
        "-device", "virtserialport,chardev=vdagent,name=com.redhat.spice.0",
        *_shared_args(cfg),
        *_net_args(cfg, port),
        "-device", "virtio-keyboard-pci",
        "-device", "virtio-tablet-pci",
        "-object", "rng-random,filename=/dev/urandom,id=rng0",
        "-device", "virtio-rng-pci,rng=rng0",
        *_usb_args(cfg),
        *_audio_args(cfg),
        "-rtc", "base=utc,driftfix=slew",
        "-global", "kvm-pit.lost_tick_policy=discard",
    ]
