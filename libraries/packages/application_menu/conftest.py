#!/usr/bin/env python3
"""Pytest fixtures for the Az'arch application-menu unit tests (test_menu.py).

These modules are imported as FLAT siblings (menu.py does `import actions`,
`import apps`, ...), so this conftest lives next to them and simply guarantees
that dir is importable; pytest's rootdir-insertion plus the sibling layout make
`import actions` / `import apps` / `import usage` resolve when the suite is run
from this directory:

    cd libraries/packages/application_menu/libraries
    xvfb-run -a python -m pytest test_menu.py

(The Tk-based UI tests need an X display, hence xvfb-run.)

Fixtures provided:
  * ``tmp``              -- a throwaway directory (str), for the usage-store /
                           .desktop-parsing tests that write scratch files.
  * ``monkeypatch_launch`` -- replaces ``actions.launch`` with a recorder so the
                           UI launch test can assert what argv was launched
                           WITHOUT spawning a real process. Exposes ``.calls``
                           (a list of the argv lists passed to launch).
  * ``monkeypatch_actions`` -- replaces the power actions (suspend/lock/reboot/
                           poweroff) with recorders so the power-row test can
                           assert which fired WITHOUT suspending the test host.
                           Exposes ``.calls`` (a list of action-name strings).
"""

from __future__ import annotations

import os
import sys

import pytest

# Make the flat sibling modules (actions, apps, usage, menu, ...) importable even
# when pytest is invoked from the repo root rather than this directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class _Recorder:
    """A tiny call recorder used by the monkeypatch fixtures. ``calls`` collects
    one entry per invocation (argv list for launch; action name for power)."""

    def __init__(self) -> None:
        self.calls: list = []


@pytest.fixture
def tmp(tmp_path) -> str:
    """A scratch directory as a plain string path (the tests use os.path.join and
    open() on it). Backed by pytest's per-test tmp_path so it is auto-cleaned."""
    return str(tmp_path)


@pytest.fixture
def monkeypatch_launch(monkeypatch) -> _Recorder:
    """Replace ``actions.launch`` with a recorder. The UI selection/launch test
    reads ``.calls[-1]`` to assert the launched argv (e.g. ["kitty"]) without
    ever spawning a process."""
    import actions

    rec = _Recorder()

    def _fake_launch(argv) -> None:
        rec.calls.append(list(argv))

    monkeypatch.setattr(actions, "launch", _fake_launch)
    return rec


@pytest.fixture
def monkeypatch_actions(monkeypatch) -> _Recorder:
    """Replace the power/session actions with recorders so the power-row test can
    assert which action fired (``"suspend"`` in ``.calls``) without actually
    suspending / rebooting / powering off the test machine."""
    import actions

    rec = _Recorder()

    for name in ("suspend", "lock_session", "reboot", "poweroff"):
        def _make(action_name):
            def _fake() -> None:
                rec.calls.append(action_name)
            return _fake

        monkeypatch.setattr(actions, name, _make(name))
    return rec
