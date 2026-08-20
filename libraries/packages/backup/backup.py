#!/usr/bin/env python3
"""The `backup` command -- Az'arch's home-directory backup.

This is step one of the backup system (it will grow, step by step). Running
`backup`:

  * Scans your HOME directory (``~`` -- whatever the current user's home is; it is
    resolved live, never a hard-coded path) and gathers every TOP-LEVEL directory in it.
  * SKIPS the ``Ignore`` directory (a home-dir dumping ground for things you never
    want backed up) and SKIPS every dot file / dot directory (``.bashrc``,
    ``.config``, ``.ssh`` ...): those are hidden config, out of scope for now.
  * Preserves SYMLINKS as links -- it never follows them into their target -- and
    records where each one points, so a restore can recreate the exact same link.
  * Rolls the whole selection into ONE timestamped, GPG-encrypted archive written
    back into your home directory:  ``~/backup_YYYY-MM-DD_HH-MM.tar.gz.gpg``.

WHY tar + gpg (no rar). The archive is a gzip-compressed tar piped straight into
``gpg --symmetric`` (AES256). tar stores symlinks AS links by default (never
dereferenced), which is exactly the "save the symlink and where it points"
requirement, and both ``tar`` and ``gpg`` (gnupg) are in the Az'arch manifest --
no proprietary ``rar`` dependency. The passphrase you enter is the archive's only
key; it is never written anywhere.

This is intentionally small and self-contained (Python standard library only). The
cloud upload / rotation / GitHub / QEMU machinery from the original prototype in
``data/backup.py`` is deliberately NOT here yet -- we are building this up one step
at a time, and step one is just "make the encrypted archive of the right files".
"""

import os
import subprocess
import sys
import tarfile
import threading
import time
from datetime import datetime
from getpass import getpass


# The one directory in HOME we never back up (a deliberate dumping ground). Matched
# by exact top-level name, case-sensitively -- only ``~/Ignore`` is skipped, not a
# nested ``Foo/Ignore``.
IGNORE_DIR_NAME = "Ignore"

# __pycache__ / compiled Python are never worth archiving; dropped everywhere in the
# tree (the top-level dot-file rule already hides most clutter, but these can sit
# inside a backed-up project dir).
_ALWAYS_SKIP_NAMES = {"__pycache__"}
_ALWAYS_SKIP_SUFFIXES = (".pyc", ".pyo")


def home_dir():
    """The current user's home directory -- ``~`` expanded. Never a hard-coded path:
    a user may have named their account anything, so we resolve it live (``$HOME``,
    falling back to the password database) every run."""
    return os.path.expanduser("~")


def _is_hidden(name):
    """A dot file / dot directory (hidden config we skip at the top level)."""
    return name.startswith(".")


def select_entries(home):
    """Return the sorted top-level entries in ``home`` to back up.

    The selection rule (the PROMPT's spec):
      * every top-level entry in HOME is a candidate,
      * EXCEPT the ``Ignore`` directory,
      * EXCEPT dot files / dot directories (hidden config),
      * and symlinks ARE included (kept as links; tar records their target).

    Returns bare NAMES (relative to ``home``); the archiver adds them with
    ``arcname`` so the archive is rooted at the home dir, not at ``/``."""
    entries = []
    for name in os.listdir(home):
        if name == IGNORE_DIR_NAME:
            continue
        if _is_hidden(name):
            continue
        entries.append(name)
    return sorted(entries)


def _tar_filter(tarinfo):
    """Per-entry filter for ``tarfile.add(recursive=True)``.

    Drops __pycache__ dirs and ``.pyc``/``.pyo`` files anywhere in the tree.
    Everything else is kept verbatim -- crucially, tarfile does NOT dereference
    symlinks here (``TarInfo`` for a link has ``type == SYMTYPE`` and carries its
    ``linkname``), so a symlink is stored AS a link together with where it points.
    Returning ``None`` excludes the entry."""
    base = os.path.basename(tarinfo.name)
    if base in _ALWAYS_SKIP_NAMES:
        return None
    if tarinfo.name.endswith(_ALWAYS_SKIP_SUFFIXES):
        return None
    return tarinfo


def _count_symlinks(home, entries):
    """How many symlinks are in the selection (for the summary line). Walks without
    following links so it counts the links themselves, not their targets."""
    count = 0
    for name in entries:
        path = os.path.join(home, name)
        if os.path.islink(path):
            count += 1
            continue
        for root, dirs, files in os.walk(path, followlinks=False):
            dirs[:] = [d for d in dirs if d not in _ALWAYS_SKIP_NAMES]
            for entry in dirs + files:
                if os.path.islink(os.path.join(root, entry)):
                    count += 1
    return count


def prompt_passphrase():
    """Ask for the archive passphrase twice and return it once the two match.

    The passphrase is the archive's only key and is never stored. An empty
    passphrase is rejected (gpg would refuse it and it defeats the encryption)."""
    while True:
        first = getpass("Encryption passphrase: ")
        if not first:
            print("Passphrase cannot be empty.")
            continue
        second = getpass("Confirm passphrase: ")
        if first == second:
            return first
        print("Passphrases do not match. Try again.")


def build_archive(home, entries, out_path, passphrase):
    """Write the gzip-tar of ``entries`` (under ``home``) through gpg to ``out_path``.

    The tar stream is produced in-process and piped to ``gpg --symmetric`` so the
    plaintext archive never touches disk -- only the encrypted ``.tar.gz.gpg`` is
    written. The passphrase is handed to gpg on a private pipe (``--passphrase-fd``),
    never on the command line (where it would show up in the process list).

    Returns True on success. On failure the partial output is removed and False is
    returned."""
    # gpg reads the passphrase from a dedicated fd (passphrase-fd), so it is never
    # visible in `ps` -- unlike handing it as a command-line argument. --batch/--yes
    # keep it non-interactive and overwrite a stale archive from the same minute.
    read_fd, write_fd = os.pipe()
    gpg_cmd = [
        "gpg", "--symmetric", "--cipher-algo", "AES256",
        "--batch", "--yes", "--passphrase-fd", str(read_fd),
        "-o", out_path,
    ]
    # Spawn gpg FIRST (so it is already draining the read end), THEN write the
    # passphrase from a short-lived thread and close the write end. Writing before
    # the child existed could block if the passphrase ever exceeded the pipe buffer
    # (nothing would be reading yet); doing it from a thread after Popen can never
    # deadlock the archiving below.
    proc = subprocess.Popen(gpg_cmd, stdin=subprocess.PIPE, pass_fds=(read_fd,))
    os.close(read_fd)  # the child owns the read end now

    def _feed_passphrase():
        try:
            os.write(write_fd, (passphrase + "\n").encode("utf-8"))
        finally:
            os.close(write_fd)

    pass_thread = threading.Thread(target=_feed_passphrase, daemon=True)
    pass_thread.start()

    try:
        with tarfile.open(fileobj=proc.stdin, mode="w:gz") as tar:
            for name in entries:
                path = os.path.join(home, name)
                # arcname=name roots the archive at the home dir (paths are
                # "Documents/...", not "/home/<user>/Documents/..."). recursive=True
                # walks dirs; the filter drops pycache and keeps symlinks as links.
                tar.add(path, arcname=name, recursive=True, filter=_tar_filter)
                print(f"  added {name}")
    except (OSError, tarfile.TarError) as error:
        proc.stdin.close()
        proc.wait()
        pass_thread.join()
        _cleanup_partial(out_path)
        print(f"Archive failed: {error}")
        return False

    proc.stdin.close()
    returncode = proc.wait()
    pass_thread.join()
    if returncode != 0:
        _cleanup_partial(out_path)
        print(f"gpg failed (exit {returncode}).")
        return False
    return True


def _cleanup_partial(out_path):
    """Remove a half-written archive so a failed run never leaves a corrupt file."""
    try:
        os.remove(out_path)
    except OSError:
        pass


def _fmt_size(num_bytes):
    for unit, scale in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if num_bytes >= scale:
            return f"{num_bytes / scale:.2f} {unit}"
    return f"{num_bytes} B"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print("Usage: backup\n\n"
              "Create an encrypted archive of your home directory's top-level\n"
              "folders (skipping the 'Ignore' folder and hidden dot files, keeping\n"
              "symlinks as links) at ~/backup_<date>.tar.gz.gpg.")
        return 0

    if not _which("gpg"):
        print("Error: 'gpg' not found. Install it with: sudo pacman -S gnupg")
        return 1

    home = home_dir()
    entries = select_entries(home)
    if not entries:
        print(f"Nothing to back up in {home} "
              f"(everything is hidden or in '{IGNORE_DIR_NAME}').")
        return 0

    symlinks = _count_symlinks(home, entries)
    print(f"Backing up {len(entries)} item(s) from {home}"
          + (f" ({symlinks} symlink(s), kept as links)" if symlinks else "")
          + f", skipping '{IGNORE_DIR_NAME}' and dot files.\n")

    passphrase = prompt_passphrase()
    print()

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    out_path = os.path.join(home, f"backup_{stamp}.tar.gz.gpg")

    start = time.time()
    ok = build_archive(home, entries, out_path, passphrase)
    if not ok:
        return 1

    size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
    print(f"\nDone in {int(time.time() - start)}s -> {out_path} ({_fmt_size(size)})")
    return 0


def _which(name):
    """Tiny shutil.which shim (kept dependency-light)."""
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


if __name__ == "__main__":
    sys.exit(main())
