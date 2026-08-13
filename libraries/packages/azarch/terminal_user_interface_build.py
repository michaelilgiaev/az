"""The bare-`azarch` TERMINAL UI (C) -- build wiring, inside the `azarch` package.

Running `azarch` with no arguments opens a full-screen settings UI for the three things a
fresh machine needs tuned -- Theme, Wallpaper, Network. It is C driving the terminal with
raw ANSI + termios (no ncurses/GTK), so redraws are instant: coloured (the Az'arch logo
cyan), everything centred, WASD/HJKL/arrow navigation, live status, and kitty-graphics
previews (the hovered wallpaper; the theme rendered as real LibreWolf + Dolphin screenshots).

WHY IT LIVES HERE. It used to be a SEPARATE package (packages/azarch_terminal_user_interface/) with its own
Python wrapper, but the command line interface it drives is the `azarch` package -- and there is only ONE
program, `azarch`, in C for speed. So the C sources (main.c/render.c/model.c/preview.c +
headers + Makefile) now live DIRECTLY in packages/azarch/ next to the Python command line interface, and THIS
module is the build wiring that compiles them into the `azarch` binary and installs it.
There is no `azarch_terminal_user_interface` package anymore.

Layers:
  * SOURCE tree -- libraries/packages/azarch/ (paths.AZARCH_COMMAND_LINE_INTERFACE_DIR). The C sources:
      main.c     raw termios + the input loop + running the apply actions (main())
      render.c   the centred, coloured ANSI renderer
      model.c    the screen/menu tree + the live status probes
      preview.c  the hovered-row previews (kitty icat wallpaper; kitty icat theme shots)
      terminal_user_interface.h / render.h / preview.h   the headers
      Makefile   builds azarch (+ `make test`)
    They sit alongside the Python command line interface modules (command_line_interface.py, theme.py, ...). _csrc_files() picks up
    ONLY the C inputs (.c/.h/Makefile), never the .py files, so the two coexist cleanly.
  * BUILD wiring -- THIS module compiles those into the binary and installs it to
    TERMINAL_USER_INTERFACE_BIN_SYSTEM_PATH. compiler.py calls build_terminal_user_interface() during the desktop emit.

The theme previews are REAL screenshots shipped from assets/previews/ (see PREVIEW_ASSETS)
to a fixed system dir; preview.c places them with kitty's `kitten icat` at RUNTIME. Swapping
the images (same filenames) needs no code change.

Build host requirements: just a C compiler (gcc) -- no ncurses, no GTK. The live system
carries the compiled binary; it compiles nothing itself. kitty is already in the ISO
manifest, so previews work on the guest.
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
TERMINAL_USER_INTERFACE_LIB_DIR = "/usr/local/lib/azarch"
# The compiled binary the `azarch` command line interface execs. MUST match packages/azarch/terminal_user_interface.py TERMINAL_USER_INTERFACE_BIN
# (a test pins the two together so the launcher and the build cannot drift).
TERMINAL_USER_INTERFACE_BIN_SYSTEM_PATH = f"{TERMINAL_USER_INTERFACE_LIB_DIR}/azarch"

# The compiled UI reads its theme-preview screenshots from here at RUNTIME (kitty icat).
# Kept as a sibling data dir of the binary so it travels with it. MUST match preview.c's
# AZ_PREVIEW_DIR (a test pins the two together).
TERMINAL_USER_INTERFACE_PREVIEW_SYSTEM_DIR = f"{TERMINAL_USER_INTERFACE_LIB_DIR}/previews"

# The binary name the Makefile produces.
TERMINAL_USER_INTERFACE_BIN_NAME = "azarch"

# The theme-preview screenshots shipped verbatim from assets/previews/ to
# TERMINAL_USER_INTERFACE_PREVIEW_SYSTEM_DIR. The names are the CONTRACT preview.c hard-codes: LibreWolf on the
# timedate home page + Dolphin, each in a dark and a white variant. They ship UNMODIFIED
# (kitty scales them into the reserved rectangle at draw time); replacing them with the same
# filenames needs no code change. Relative to assets/.
PREVIEW_ASSETS = (
    "previews/timedate_dark.png",
    "previews/timedate_white.png",
    "previews/files_dark.png",
    "previews/files_white.png",
)

# Host BUILD dependency: just the C compiler. Listed for compiler._check_host_deps /
# the Dockerfile (gcc is already pulled in for the application-menu build, so this is
# effectively already satisfied; kept explicit for clarity + a slimmer host).
TERMINAL_USER_INTERFACE_BUILD_DEPS = ["gcc"]


def _csrc_files() -> list[Path]:
    """Every C source/header + the Makefile in the azarch package dir (the build inputs).

    The `azarch` package dir holds BOTH the Python command line interface modules and the C UI sources; this
    returns ONLY the C inputs (.c/.h and the Makefile), never the .py files, so the build
    copies exactly the C tree into a scratch dir and `make` sees a clean, Python-free tree."""
    d = paths.AZARCH_COMMAND_LINE_INTERFACE_DIR
    names = sorted(
        p.name
        for p in d.iterdir()
        if p.is_file() and (p.suffix in (".c", ".h") or p.name == "Makefile")
    )
    return [d / n for n in names]


def build_terminal_user_interface(dest: Path, *, make: str = "make") -> Path:
    """Compile the C terminal UI and install the binary at `dest`.

    Builds in a throwaway temp dir populated with a copy of the C sources (NOT in the repo,
    so no .o/binary ever lands in version control), then copies the produced binary to
    `dest` with mode 0755. Raises CalledProcessError if the build fails -- a broken UI MUST
    fail the ISO build loudly rather than ship a missing binary. Returns the destination
    path. Mirrors application_menu.build_daemon()."""
    dest = Path(dest)
    with tempfile.TemporaryDirectory(prefix="azarch-build-") as tmp:
        build_dir = Path(tmp)
        for src in _csrc_files():
            shutil.copy2(src, build_dir / src.name)
        subprocess.run([make, TERMINAL_USER_INTERFACE_BIN_NAME], cwd=build_dir, check=True)
        built = build_dir / TERMINAL_USER_INTERFACE_BIN_NAME
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, dest)
        dest.chmod(0o755)
    return dest


def install_previews(dest_dir: Path) -> list[Path]:
    """Copy the theme-preview screenshots verbatim into `dest_dir` (the airootfs preview dir).

    The images ship UNMODIFIED under their contract filenames (PREVIEW_ASSETS); preview.c
    reads them by name at runtime and scales them with kitty at draw time. Returns the list
    of written paths. Root-owned system dir; the OFFLINE Calamares install rsyncs it onto
    the installed system with no separate step."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for rel in PREVIEW_ASSETS:
        out = dest_dir / Path(rel).name
        shutil.copy2(paths.ASSETSDIR / rel, out)
        out.chmod(0o644)
        written.append(out)
    return written
