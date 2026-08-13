"""The Az'arch bare-`azarch` TERMINAL UI (C port) -- build wiring.

Running `azarch` with no arguments opens a full-screen settings UI for the three things a
fresh machine needs tuned -- Theme, Wallpaper, Network. It used to be Python/curses (in
packages/azarch/tui.py) but felt laggy, so it was rewritten in C driving the terminal with
raw ANSI + termios: instant redraws, coloured (the Az'arch logo cyan), everything centred,
WASD/HJKL/arrow navigation, live status, and kitty-graphics previews (the hovered wallpaper;
the theme rendered as LibreWolf + Dolphin mock-ups).

This module is the BUILD WIRING (the same shape as application_menu.py): it COMPILES the C
sources here into a single binary, azarch-tui, and installs it under TUI_LIB_DIR. The
Python `azarch` CLI's tui.py execs that binary for the no-argument case; the binary shells
back to the `azarch` subcommands for every action, so the behaviour is still the tested CLI.

Layers:
  * SOURCE tree -- libraries/packages/azarch_tui/ (paths.AZARCH_TUI_DIR). The C sources live
    DIRECTLY here next to this build-wiring module:
      main.c     raw termios + the input loop + running the apply actions (main())
      render.c   the centred, coloured ANSI renderer
      model.c    the screen/menu tree + the live status probes
      preview.c  the hovered-row previews (kitty icat wallpaper; ANSI theme mock-ups)
      tui.h / render.h / preview.h   the headers
      Makefile   builds azarch-tui (+ `make test`)
  * BUILD wiring -- THIS module compiles those into the binary and installs it to
    TUI_BIN_SYSTEM_PATH. compiler.py calls build_tui() during the desktop emit.

Build host requirements: just a C compiler (gcc) -- no ncurses, no GTK (the UI is pure libc
+ raw ANSI, and previews shell out to kitty's `kitten icat` at RUNTIME, so there is no
compile-time kitty dependency). The live system carries the compiled binary; it compiles
nothing itself. kitty is already in the ISO manifest, so previews work on the guest.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import paths


# --- Installed system paths (root-owned) ------------------------------------
# Where the UI lands in the live/installed rootfs. Kept under /usr/local/lib (like the
# application-menu daemon) rather than directly on PATH: the bin entry point is the Python
# `azarch` script, which execs this binary for the no-argument case.
TUI_LIB_DIR = "/usr/local/lib/azarch-tui"
# The compiled binary the `azarch` CLI execs. MUST match packages/azarch/tui.py TUI_BIN
# (a test pins the two together so the launcher and the build cannot drift).
TUI_BIN_SYSTEM_PATH = f"{TUI_LIB_DIR}/azarch-tui"

# The binary name the Makefile produces.
TUI_BIN_NAME = "azarch-tui"

# Host BUILD dependency: just the C compiler. Listed for compiler._check_host_deps /
# the Dockerfile (gcc is already pulled in for the application-menu build, so this is
# effectively already satisfied; kept explicit for clarity + a slimmer host).
TUI_BUILD_DEPS = ["gcc"]


def _csrc_files() -> list[Path]:
    """Every C source/header/Makefile in the package dir (the build inputs).

    The build copies exactly these into a scratch dir so `make` has a clean tree and the
    repo is never polluted with object files or the binary."""
    d = paths.AZARCH_TUI_DIR
    names = sorted(
        p.name
        for p in d.iterdir()
        if p.is_file() and (p.suffix in (".c", ".h") or p.name == "Makefile")
    )
    return [d / n for n in names]


def build_tui(dest: Path, *, make: str = "make") -> Path:
    """Compile the C terminal UI and install the binary at `dest`.

    Builds in a throwaway temp dir populated with a copy of the C sources (NOT in the repo,
    so no .o/binary ever lands in version control), then copies the produced binary to
    `dest` with mode 0755. Raises CalledProcessError if the build fails -- a broken UI MUST
    fail the ISO build loudly rather than ship a missing binary. Returns the destination
    path. Mirrors application_menu.build_daemon()."""
    dest = Path(dest)
    with tempfile.TemporaryDirectory(prefix="azarch-tui-build-") as tmp:
        build_dir = Path(tmp)
        for src in _csrc_files():
            shutil.copy2(src, build_dir / src.name)
        subprocess.run([make, TUI_BIN_NAME], cwd=build_dir, check=True)
        built = build_dir / TUI_BIN_NAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, dest)
        dest.chmod(0o755)
    return dest
