"""fastfetch configuration + the azarch "Az'" ASCII logo.

fastfetch ships in the ISO's package list; this module provides the two files
that make `fastfetch` render the azarch brand instead of the stock Arch logo:

  logo_txt()     the "Az'" ASCII art, read verbatim from the repo asset
                 assets/ascii/azarch_fastfetch.ansi. That file is ALREADY
                 colored with the azarch cyan->blue gradient (real ANSI truecolor
                 escapes baked in per row), so the configuration below uses
                 `type: "file-raw"`, which prints the file byte-for-byte with no
                 post-processing. (The older `type: "file"` + $N-placeholder path
                 was dropped: it required a separate uncolored art plus a color
                 map, and the hand-rolled art it used was a crude reverse-engineer
                 of the logo. The .ansi asset is the good hand-tuned art.)
  config_jsonc() ~/.config/fastfetch/config.jsonc pointing fastfetch at the logo
                 file by ABSOLUTE path, and carrying a custom "Edition" line that
                 names the running product line (HEADED vs HEADLESS). The label is
                 baked in per line at build time (config_jsonc(is_gui=...)), so it is
                 correct both live and on the installed system with no runtime probe.

Both land in the user's ~/.config/fastfetch/ on the live ISO and, via the
installer copy path (the verbatim rootfs clone), on the installed system.
"""

from __future__ import annotations

import paths

# The "Az'" logo lives as a real asset in the repo (git-tracked, survives
# `git clean -Xdf`): a rounded capital A with a hollow counter and a lowercase z,
# 40 cols x 18 rows, pre-colored with the cyan->blue gradient sampled from
# assets/azarch_logo.png. We read it verbatim rather than embedding a copy here so
# the art has a single source of truth (the .ansi file you can open and eyeball).
_LOGO_ASSET = paths.ASSETSDIR / "ascii" / "azarch_fastfetch.ansi"

# The bare filename the art is written to inside ~/.config/fastfetch/. The configuration's
# `source` is the absolute path to this; compiler.py / the installer write the file
# there. Kept as a constant so the two stay in lockstep.
LOGO_FILENAME = "azarch.ansi"
LOGO_PATH = f"/home/main/.config/fastfetch/{LOGO_FILENAME}"

# The two product lines' human labels, printed as the fastfetch "Edition" line (see
# config_jsonc). The graphical line is HEADED; the console/compute line is HEADLESS.
EDITION_HEADED = "Az'arch Headed"
EDITION_HEADLESS = "Az'arch Headless"


def edition_label(is_gui: bool) -> str:
    """The edition string fastfetch prints for a line: HEADED for the graphical line,
    HEADLESS for the console/compute line. Baked into the config at build time (the config
    is emitted per line), so it stays correct live AND on the installed system (which is a
    verbatim clone of the live rootfs) with no runtime detection needed."""
    return EDITION_HEADED if is_gui else EDITION_HEADLESS


def logo_txt() -> str:
    """The pre-colored Az' art, verbatim from the repo asset."""
    return _LOGO_ASSET.read_text(encoding="utf-8")


def config_jsonc(is_gui: bool = True) -> str:
    """fastfetch configuration: print the pre-colored Az' art verbatim.

    is_gui: True for the HEADED (graphical) line, False for the HEADLESS
    (console/compute) line. The ONLY difference between the two configs is the value of
    the custom "Edition" module line -- "Az'arch Headed" vs "Az'arch Headless" -- so
    `fastfetch` states which edition is running. It is baked in here at build time
    (config_jsonc is emitted once per line), which keeps it identical on the live medium
    and on the installed system: the installer clones the live rootfs verbatim, carrying
    this ~/.config/fastfetch/config.jsonc onto the target unchanged. Default True keeps a
    bare config_jsonc() (any existing caller) producing the headed edition's config.

    `source` MUST be an absolute path. fastfetch resolves a RELATIVE source
    against the CURRENT WORKING DIRECTORY -- not the configuration dir -- so a bare
    filename only works if you happen to run fastfetch from ~/.config/fastfetch/.
    Run it from ~ (the normal case) and fastfetch fails to read the file and
    SILENTLY falls back to the auto-detected Arch logo -- exactly the bug that
    showed the stock Arch logo. We hard-code the absolute path (rather than "~/...")
    to avoid any ambiguity about tilde expansion in the source field: the live ISO
    user and the installed user are both `main` with home /home/main, so the
    literal path is correct in both.

    `type: "file-raw"` prints the file byte-for-byte -- no $N replacement, no
    re-coloring -- because the .ansi art already carries its own truecolor escapes.
    """
    return f"""\
{{
    "$schema": "https://github.com/fastfetch-cli/fastfetch/raw/dev/doc/json_schema.json",
    "logo": {{
        "type": "file-raw",
        "source": "{LOGO_PATH}",
        "padding": {{
            "top": 1,
            "left": 2
        }}
    }},
    "modules": [
        "title",
        "separator",
        "os",
        {{
            "type": "custom",
            "key": "Edition",
            "format": "{edition_label(is_gui)}"
        }},
        "host",
        "kernel",
        "uptime",
        "packages",
        "shell",
        "de",
        "wm",
        "terminal",
        "cpu",
        "gpu",
        "memory",
        "disk",
        "break",
        "colors"
    ]
}}
"""
