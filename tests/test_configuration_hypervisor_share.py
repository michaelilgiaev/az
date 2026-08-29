"""do_share_offline -- the powered-off-disk editor's guard.

This path has no host-independent happy route (it needs qemu-nbd, sudo, a real
Btrfs guest), but its FIRST action is a precondition: the disk for this directory
must exist. That guard is pure and must fail CLEANLY (HypervisorError -> the
'hypervisor: ...' exit-1 path), never crash. A prior refactor that made
resolve_run_disk() require an argument left this call site stale and turned the
missing-disk case into an uncaught TypeError; this pins it shut.
"""

from __future__ import annotations

import pytest

from hypervisor_helpers import make_cfg

from packages.hypervisor import virtual_machine as vm
from packages.hypervisor.checks import HypervisorError


def test_share_offline_missing_disk_raises_cleanly(tmp_path):
    cfg = make_cfg(str(tmp_path))  # no testvm.qcow2 on disk
    with pytest.raises(HypervisorError):
        vm.do_share_offline(cfg)


def test_guest_fstab_line_is_virtiofs_not_9p():
    # The baked-in guest mount uses virtiofs (mount tag "shared"), NOT 9p. virtiofs
    # needs no trans=/version= options and no modules-load entry (the driver is
    # in-tree in modern kernels), so the line is a plain virtiofs fstab entry.
    line = vm._guest_fstab_line("main")
    fields = line.split()
    assert fields[0] == "shared"                 # source == the virtiofs mount tag
    assert fields[1] == "/home/main/shared"      # target
    assert fields[2] == "virtiofs"               # fstype
    assert "nofail" in fields[3].split(",")      # never blocks boot if absent
    assert "9p" not in line and "trans=virtio" not in line
