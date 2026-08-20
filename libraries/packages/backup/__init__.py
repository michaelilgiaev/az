"""backup -- Az'arch's home-directory backup (the `backup` command).

Step one of the backup system (it will grow step by step). `backup` gathers the
top-level folders in the current user's HOME -- skipping the ``Ignore`` directory
and hidden dot files, keeping symlinks AS links (and recording where they point) --
and writes them into one timestamped, GPG-encrypted archive back in the home dir:
``~/backup_YYYY-MM-DD_HH-MM.tar.gz.gpg``.

This package holds the whole thing in one flat directory (like packages/passwords):

Entry point:
    backup                          the `backup` command (the archiver)

Also here (not part of the runtime import graph):
    packaging                       ISO build wiring (install paths, launcher, emit_plan)

The app is a SINGLE self-contained module (backup.py, Python standard library only:
tarfile + gpg via subprocess); packaging.py ships it to /usr/local/lib/azarch-backup/
and installs the /usr/local/bin/backup launcher. This ``__init__.py`` makes the same
directory importable as the ``packages.backup`` package for the test suite.
"""

from __future__ import annotations
