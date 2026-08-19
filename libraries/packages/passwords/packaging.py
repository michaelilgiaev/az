"""Az'arch passwords -- build wiring for the `passwords` command.

`passwords` is an encrypted (GPG AES256) terminal password manager: the master
password is the GPG passphrase (never stored), the store is a single .gpg file at
~/Vault/passwords.txt.gpg, and running `passwords` unlocks it, decrypts it to a
session plaintext for the search/select curses UI, then re-encrypts on quit only if
something changed and always deletes the session plaintext. See pwlib/ and the module
docstrings there for the app itself; THIS module is only the ISO build wiring.

Mirrors packages/timedate/timedate.py: our OWN package, so the sources live directly in
this dir next to the build wiring, and compiler.py iterates emit_plan() to place the
artifacts into the airootfs (root-owned system paths -- the OFFLINE Calamares install
rsyncs the live rootfs, so they carry onto the installed system with no separate
installer step). Like timedate this is a PURE-PYTHON app (nothing to compile).

Unlike timedate, the app is a PACKAGE (a pwlib/ dir), not a handful of flat modules, so
the layout is two parts:
  * emit_plan() places the three TOP-LEVEL single files -- the entry script, the one-time
    setup script, and the /usr/local/bin/passwords launcher.
  * the pwlib/ package tree is copied wholesale by compiler.py via emit.copy_tree() right
    after the emit_plan loop (the emit_plan builder/dest/mode contract is one-file-per-
    entry and cannot express a directory). PWLIB_SRC_DIR / PWLIB_SYSTEM_DIR name the two
    ends of that copy.

Layers:
  * SOURCE tree -- libraries/packages/passwords/ (paths.PASSWORDS_DIR):
      passwords.py                    the `passwords` entry script (the UI driver)
      encrypt_passwords_text_tile.py  one-time setup: encrypt the plaintext + record paths
      pwlib/                          the working package (config/crypto/model/tui/...)
      packaging.py                    THIS module -- install paths, launcher, emit_plan()
  * INSTALLED layout (root-owned):
      /usr/local/lib/azarch-passwords/passwords.py                   the entry script
      /usr/local/lib/azarch-passwords/encrypt_passwords_text_tile.py the setup script
      /usr/local/lib/azarch-passwords/pwlib/                         the package
      /usr/local/bin/passwords                        the launcher (execs passwords.py)

Runtime dependencies (system binaries the app shells out to): `gpg` (gnupg) for
encrypt/decrypt and `xclip` for the clipboard -- BOTH are named in the manifest
(packages.x86_64 AZ'ARCH ADDITIONS). python is already there; everything else the app
uses is Python standard library (curses, subprocess, ctypes, json, re). No systemd
service: `passwords` is an interactive command, launched on demand, not a boot service.
"""

from __future__ import annotations

import paths

# --- Installed system paths (root-owned) ------------------------------------
# Where the app lands in the live/installed rootfs. Under /usr/local (our stuff), so the
# OFFLINE install's unpackfs rsync carries it to the target unchanged. Mirrors
# timedate.LIB_DIR.
LIB_DIR = "/usr/local/lib/azarch-passwords"
# The entry script the launcher execs. It does `sys.path.insert(0, <its own dir>)` then
# `from pwlib import ...`, so it must land in LIB_DIR beside pwlib/.
ENTRY_SYSTEM_PATH = f"{LIB_DIR}/passwords.py"
# The one-time setup script (`encrypt_passwords_text_tile.py`): encrypts a plaintext file
# into the ~/Vault store and records the paths. Ships beside the entry script; the entry
# script's "no store yet" message tells the user to run it from here.
SETUP_SYSTEM_PATH = f"{LIB_DIR}/encrypt_passwords_text_tile.py"
# The bin entry point on PATH -- the actual `passwords` command. A tiny wrapper that execs
# the system python on the entry script from LIB_DIR (so `import pwlib` resolves).
LAUNCHER_SYSTEM_PATH = "/usr/local/bin/passwords"

# The pwlib/ package: source dir (in the repo) and install dir (in the airootfs). Copied
# as a whole tree by compiler.py (emit_plan cannot express a directory). The install dir
# MUST be LIB_DIR/pwlib so the entry + setup scripts' `from pwlib import ...` resolves.
PWLIB_DIR_NAME = "pwlib"
PWLIB_SRC_DIR = paths.PASSWORDS_DIR / PWLIB_DIR_NAME
PWLIB_SYSTEM_DIR = f"{LIB_DIR}/{PWLIB_DIR_NAME}"

# --- Source files (in the repo) ---------------------------------------------
_SRC_ENTRY = "passwords.py"
_SRC_SETUP = "encrypt_passwords_text_tile.py"


def _read_source(name: str) -> str:
    """Read one of the app's top-level Python sources from the passwords package dir."""
    return (paths.PASSWORDS_DIR / name).read_text(encoding="utf-8")


def entry_py() -> str:
    """The `passwords` entry script (passwords.py), verbatim from the source tree.
    Installed to ENTRY_SYSTEM_PATH; the launcher execs it. It inserts its own dir on
    sys.path and imports pwlib, so pwlib/ must be installed beside it in LIB_DIR."""
    return _read_source(_SRC_ENTRY)


def setup_py() -> str:
    """The one-time setup script (encrypt_passwords_text_tile.py), verbatim from the
    source tree. Installed to SETUP_SYSTEM_PATH beside the entry script; it encrypts the
    plaintext into ~/Vault/passwords.txt.gpg and records the paths."""
    return _read_source(_SRC_SETUP)


def launcher_sh() -> str:
    """A tiny launcher installed on PATH as the `passwords` command.

    It cd's into LIB_DIR (so the entry script's `from pwlib import ...` resolves without
    installing pwlib as a site package) and execs the system python on passwords.py,
    forwarding any arguments (so `passwords -h` reaches the script). `exec` so the python
    process replaces the shell (clean signals -- the app installs SIGTERM/SIGHUP handlers
    to shred the session plaintext, and exec lets them fire on the python process itself).
    `"$@"` is quoted so arguments with spaces survive."""
    return f"""\
#!/bin/sh
# passwords -- launch the Az'arch encrypted password manager.
# Generated by packages/passwords/packaging.py (edit the Python, not this file).
cd '{LIB_DIR}' || exit 1
exec python -u passwords.py "$@"
"""


# --- Emit plan --------------------------------------------------------------
# Declarative map (builder -> dest -> mode), mirroring timedate.PLAN so compiler.py
# iterates it the same way. All absolute SYSTEM paths (root-owned): the OFFLINE Calamares
# install rsyncs the live rootfs, so these carry onto the installed system unchanged. The
# pwlib/ package tree is copied separately in compiler._emit_desktop (emit.copy_tree),
# right after this plan is emitted. No systemd service (interactive command).
_EXEC = 0o755
_CONF = 0o644

PLAN = [
    {"builder": entry_py, "dest": ENTRY_SYSTEM_PATH, "mode": _CONF},
    {"builder": setup_py, "dest": SETUP_SYSTEM_PATH, "mode": _CONF},
    {"builder": launcher_sh, "dest": LAUNCHER_SYSTEM_PATH, "mode": _EXEC},
]


def emit_plan() -> list[dict]:
    """Return the PLAN (builder/dest/mode) for compiler.py to emit into the airootfs.
    Kept as a function to mirror timedate.emit_plan()/openbox.emit_plan(). The pwlib/
    package tree is copied separately (emit.copy_tree) since the plan is one-file-per-entry.

    Returns FRESH dict copies (not the module-level PLAN entries) so a caller that mutates
    a returned entry cannot corrupt module state -- compiler.py may call this more than
    once per build."""
    return [dict(entry) for entry in PLAN]
