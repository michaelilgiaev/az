"""The ISO variant matrix -- the single source of truth for WHICH ISOs a build
produces and what each one is called.

Historically the build had exactly two variants keyed by the flat strings
``"base"`` and ``"sshd"`` (desktop, ssh off vs. on). That is one boolean. The
product now spans THREE orthogonal booleans, so a flat tuple no longer captures
it. A build point is a :class:`Variant` -- one cell of the cube:

    line     "desktop" | "server"   -- server strips the whole GUI (X11/OpenBox/
                                        Calamares/apps); it is console-only + the
                                        headless CLI installer.
    instant  False | True           -- instant auto-installs to the largest
                                        non-USB disk at boot with defaults.
    ssh      False | True            -- ssh enables sshd and gives `main` the
                                        operator's build-time password (the
                                        pre-existing --ssh behaviour).

The eight cells map 1:1 onto the eight artifact filenames the product ships,
built by :attr:`Variant.iso_name` as ``azarch-<line>[-instant][-ssh]`` (mkarchiso
appends ``-<version>-<arch>.iso``):

    azarch-desktop                 azarch-server
    azarch-desktop-ssh             azarch-server-ssh
    azarch-desktop-instant         azarch-server-instant
    azarch-desktop-instant-ssh     azarch-server-instant-ssh

The ``-instant`` segment sits BEFORE ``-ssh`` so the names match the order the
prompt lists them.

This module is PURE (no I/O, no subprocess) -- it is imported by profile.py (for
names) and compiler.py (for selection + per-variant behaviour), and unit-tested
directly. The flag PARSING that feeds :func:`selected_variants` lives in
compiler.py alongside the existing --ssh parsing; here we only model the matrix.

Back-compat: :func:`from_legacy_key` maps the old ``"base"``/``"sshd"`` strings
onto the desktop/plain/(no-ssh|ssh) cells, so profile.py and the existing tests
that still speak those strings keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

# The product-line values. "desktop" is the GUI line (the historical default);
# "server" is the headless line. Kept as named constants so call sites and tests
# never hard-code the bare strings.
LINE_DESKTOP = "desktop"
LINE_SERVER = "server"
LINES = (LINE_DESKTOP, LINE_SERVER)

# The base name every artifact starts with; the line and the flavour segments are
# appended to it (see Variant.iso_name).
PRODUCT = "azarch"


@dataclass(frozen=True)
class Variant:
    """One cell of the ISO matrix: a product line plus the instant/ssh flavours.

    Frozen + hashable so variants can go in sets/dict keys and compare by value.
    All behaviour is derived (no stored name), so the dataclass is the sole source
    of truth and cannot drift from the filename.
    """

    line: str = LINE_DESKTOP
    instant: bool = False
    ssh: bool = False

    def __post_init__(self) -> None:
        if self.line not in LINES:
            raise ValueError(
                f"Variant.line must be one of {LINES!r}, got {self.line!r}."
            )

    @property
    def is_gui(self) -> bool:
        """True for the desktop line (ships X11/OpenBox/Calamares/apps), False for
        the headless server line. compiler.py keys the GUI emit steps + the desktop
        package add-on off this."""
        return self.line == LINE_DESKTOP

    @property
    def key(self) -> str:
        """A stable, filesystem-safe identifier for this cell, e.g.
        ``"desktop"``, ``"server-ssh"``, ``"desktop-instant-ssh"``. Same segments
        as the ISO name minus the ``azarch-`` prefix -- used for labels, log lines,
        and as a dict key. Equal to the historical variant key for the two legacy
        cells only via from_legacy_key; new cells have new keys."""
        return "-".join(self._segments())

    @property
    def iso_name(self) -> str:
        """The mkarchiso ``iso_name`` for this cell: ``azarch-<line>[-instant][-ssh]``.
        mkarchiso names the artifact ``<iso_name>-<version>-<arch>.iso``, so this is
        the filename stem. The eight cells yield the eight required filenames."""
        return f"{PRODUCT}-{self.key}"

    def _segments(self) -> tuple[str, ...]:
        # line first, then the flavour flags in the fixed order instant, ssh -- so
        # the name reads azarch-server-instant-ssh, matching the prompt's list.
        segs = [self.line]
        if self.instant:
            segs.append("instant")
        if self.ssh:
            segs.append("ssh")
        return tuple(segs)


# --- Selection --------------------------------------------------------------
# The desktop/plain/no-ssh cell is the ALWAYS-BUILT base point (a bare compile.sh
# with no axis flags builds exactly this one ISO -- the historical default). Each
# axis flag ADDS its half of that axis, and the build is the Cartesian product of
# whatever was requested, so the flags compose without combinatorial flag names.


def selected_variants(*, server: bool = False, instant: bool = False,
                      ssh: bool = False) -> tuple[Variant, ...]:
    """The variants a build produces, given which axes were opted into.

    Each boolean turns on the SECOND value of its axis while the first value
    always stays in play, so the result is the full product of the enabled
    choices and ALWAYS contains the desktop/plain/no-ssh base point:

        selected_variants()                       -> (desktop,)
        selected_variants(ssh=True)               -> (desktop, desktop-ssh)
        selected_variants(server=True)            -> (desktop, server)
        selected_variants(server=True, ssh=True,
                          instant=True)           -> all 8

    Order is STABLE and deterministic (desktop before server; within a line,
    plain before instant; within that, no-ssh before ssh), so the build order,
    the progress-bar sizing, and the tests are reproducible."""
    lines = (LINE_DESKTOP, LINE_SERVER) if server else (LINE_DESKTOP,)
    instants = (False, True) if instant else (False,)
    sshs = (False, True) if ssh else (False,)
    return tuple(
        Variant(line=ln, instant=inst, ssh=s)
        for ln in lines
        for inst in instants
        for s in sshs
    )


# --- Back-compat with the old "base"/"sshd" keys ----------------------------
# profile.py's public iso_name_for() and the existing tests still pass the flat
# legacy strings. Map them onto the equivalent cells so nothing that speaks the
# old vocabulary breaks: both are the desktop line, plain (non-instant); "base"
# is no-ssh, "sshd" is ssh.
_LEGACY = {
    "base": Variant(line=LINE_DESKTOP, instant=False, ssh=False),
    "sshd": Variant(line=LINE_DESKTOP, instant=False, ssh=True),
}


def from_legacy_key(key: str) -> Variant:
    """Map a legacy ``"base"``/``"sshd"`` variant string onto its Variant. An
    unknown key falls back to the desktop base point, mirroring the old
    iso_name_for() default (unknown -> base 'azarch-desktop')."""
    return _LEGACY.get(key, _LEGACY["base"])


def coerce(variant: "Variant | str") -> Variant:
    """Accept either a Variant or a string and return a Variant, so callers
    (profile.iso_name_for / permissions_for, tests) can pass whichever they have.

    A bare LINE NAME ("desktop"/"server") maps to that line's plain, no-ssh base
    Variant -- so `coerce("server")` is the headless line (is_gui False), NOT a
    desktop fallback. This matters for permissions_for, which keys the desktop-only
    file_permissions split off is_gui: without this, the valid string "server" would
    slip through from_legacy_key's unknown-key default to the desktop base and
    re-list the GUI-only paths (e.g. /usr/bin/ckbcomp) that abort the server ISO.
    Any OTHER string (the legacy "base"/"sshd", or an unrecognised token) still goes
    through from_legacy_key, preserving the old default-to-desktop-base behaviour."""
    if isinstance(variant, Variant):
        return variant
    if variant in LINES:
        return Variant(line=variant)
    return from_legacy_key(variant)
