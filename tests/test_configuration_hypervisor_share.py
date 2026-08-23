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
