"""Partition the package manifest by product line (headed vs. headless).

``packages/packages.x86_64`` stays the single, VERBATIM superset the build always
warms into the offline cache -- the cache-completeness and download-coverage logic
(downloader.py, compiler.cache_is_complete) is unchanged and keeps operating on
that full list. What differs between the HEADED line and the HEADLESS line is only
WHICH of those cached packages each one's pacstrap actually installs:

    headed    ->  the full manifest (base + the GUI stack + Calamares)
    headless  ->  the full manifest MINUS HEADLESS_EXCLUDED

Keeping one physical manifest file (rather than splitting it in two) means the
offline repo is a superset of BOTH airootfs needs -- always a valid cache for
either line -- and none of the cache machinery has to learn about lines. Only the
pacstrap manifest STAGED into a given airootfs is filtered, here, at emit time.

USER DECISION (final): the ONLY thing stripped from the headless line is the
CALAMARES GRAPHICAL INSTALLER and its GUI-only toolkit. Headless installs via the
CLI installer (`azarch-install --cli` / the staged azarch-install-cli.sh), so the
Qt6/KDE-Frameworks Calamares stack has no purpose there. EVERYTHING ELSE STAYS on
headless -- the X11 server, OpenBox, the GUI apps (LibreWolf/LibreOffice/GIMP/VLC/
Thunar/...), themes/fonts, cups, bluez, spice-vdagent, AND the whole GPU/compute
driver stack. The rationale: the headless machine may still want the scriptable
apps' headless APIs (soffice --convert-to, gimp -i -b, cvlc) and X-based UI
automation on demand, and it may be an AI/compute box needing CUDA/ROCm; only the
interactive graphical INSTALLER is genuinely useless without a display.

HEADLESS_EXCLUDED is therefore Calamares + the Qt6/KF6/GTK deps that exist ONLY to
serve it. It is deliberately CONSERVATIVE: any package that is dual-use, or shared
with a GUI app that STAYS, must NOT appear here. A name here that is not in the
manifest is simply inert (the filter is a set-difference); the danger is the
reverse -- listing a package the headed line also needs elsewhere would strip it
from a still-shipped app. The Calamares set below is cross-checked against the
manifest by a test (see tests/test_headless_line.py).
"""

from __future__ import annotations

import downloader

# The GUI toolkit dependencies Calamares pulls in that ALSO back GUI apps the
# headless line KEEPS (gtk3 -> Thunar/GIMP/gedit; nss -> LibreWolf; libnotify/
# libpulse -> desktop apps; qt6-base can be pulled by other Qt software). These
# must NOT be excluded -- stripping them would break a still-shipped app. Kept as a
# named guard so the exclusion set below can be audited against it.
_SHARED_WITH_KEPT_APPS: frozenset[str] = frozenset({
    "gtk3", "nss", "libnotify", "libpulse",
})

# Package names stripped from the HEADLESS pacstrap: Calamares + the Qt6 / KDE-
# Frameworks libraries that exist SOLELY to serve the graphical installer. Only
# Calamares-exclusive deps are listed; anything dual-use (gtk3/nss/libnotify/
# libpulse, and every partition/filesystem tool the CLI installer also needs) is
# deliberately absent. polkit and mailcap STAY (base plumbing).
HEADLESS_EXCLUDED: frozenset[str] = frozenset({
    "calamares",
    "kpmcore",         # KDE Partition Manager core -- Calamares partition page only
    "qt6-base",
    "qt6-svg",
    "qt6-declarative",
    "qt6-5compat",
    "kconfig",
    "kcoreaddons",
    "ki18n",
    "kcrash",
    "kwidgetsaddons",
    "kiconthemes",
    "kpackage",
    "yaml-cpp",        # Calamares config parser
    "polkit-qt6",      # Qt6 polkit bindings -- Calamares privilege escalation UI
    "hwinfo",          # Calamares hardware page
}) - _SHARED_WITH_KEPT_APPS

# Back-compat alias: the historical name for the exclusion set. Kept so any external
# reference (or a test) that still imports DESKTOP_ONLY resolves to the same frozenset.
DESKTOP_ONLY = HEADLESS_EXCLUDED


def manifest_for(is_gui: bool) -> list[str]:
    """The pacstrap package list for a line: the full manifest for the headed line
    (is_gui True), or the manifest minus HEADLESS_EXCLUDED for the headless line.
    Order is preserved from the manifest so the emitted packages.x86_64 reads the
    same as the source for the packages it keeps."""
    pkgs = downloader.manifest_packages()
    if is_gui:
        return pkgs
    return [p for p in pkgs if p not in HEADLESS_EXCLUDED]


def manifest_text_for(is_gui: bool) -> str:
    """The pacstrap packages.x86_64 CONTENTS for a line -- newline-joined names with
    a trailing newline, the plain one-name-per-line format mkarchiso and the on-disk
    installer parse. This is what compiler.py stages into the airootfs / installer
    payload instead of copying packages.x86_64 verbatim, so a headless airootfs never
    pulls the GUI stack. The headed text is byte-equivalent to the manifest's own
    package lines (comments dropped), so the headed build is unchanged."""
    return "\n".join(manifest_for(is_gui)) + "\n"
