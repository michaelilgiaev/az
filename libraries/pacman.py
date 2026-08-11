"""All pacman.conf variants, generated in Python.

The variants:

  download_conf()          used by the package-cache step to fetch ISO packages on
                           ANY host (even Manjaro): hard-coded Arch mirrors, no host
                           mirrorlist, SigLevel=Never, no alpm DownloadUser.

  build_profile_conf()     the archiso profile's pacman.conf that mkarchiso's
                           internal pacstrap uses. Standard Arch base, PLUS:
                             - NoExtract usr/lib/os-release (Az'arch branding wins)
                             - an injected CacheDir (the persistent build cache)
                             - optionally rewritten to a file:// local repo for
                               fully-offline rebuilds.

  installer_base_conf()    the pacman.conf shipped to the INSTALLED system
                           (/etc/pacman.conf): plain Arch defaults, multilib on.

  installer_pacstrap_conf()the transient pacman.conf the on-disk installer swaps in
                           during pacstrap: adds the file:// [pacstrap-azarch-repo]
                           so installation works fully offline from the ISO's repo.
"""

from __future__ import annotations

# Header shared by the base/profile/pacstrap variants (verbatim Arch default).
_STD_HEADER = """\
#
# /etc/pacman.conf
#
# See the pacman.conf(5) manpage for option and repository directives

#
# GENERAL OPTIONS
#
[options]
# The following paths are commented out with their default values listed.
# If you wish to use different paths, uncomment and update the paths.
#RootDir     = /
#DBPath      = /var/lib/pacman/
{cachedir_line}#LogFile      = /var/log/pacman.log
#GPGDir      = /etc/pacman.d/gnupg/
#HookDir     = /etc/pacman.d/hooks/
HoldPkg     = pacman glibc
#XferCommand = /usr/bin/curl -L -C - -f -o %o %u
#XferCommand = /usr/bin/wget --passive-ftp -c -O %o %u
#CleanMethod = KeepInstalled
Architecture = auto

# Pacman won't upgrade packages listed in IgnorePkg and members of IgnoreGroup
#IgnorePkg   =
#IgnoreGroup =

#NoUpgrade   =
{noextract_line}
# Misc options
#UseSyslog
#Color
#NoProgressBar
CheckSpace
#VerbosePkgLists
ParallelDownloads = 5
DownloadUser = alpm
#DisableSandbox

# By default, pacman accepts packages signed by keys that its local keyring
# trusts (see pacman-key and its man page), as well as unsigned packages.
SigLevel    = Required DatabaseOptional
LocalFileSigLevel = Optional
#RemoteFileSigLevel = Required

# NOTE: You must run `pacman-key --init` before first using pacman; the local
# keyring can then be populated with the keys of all official Arch Linux
# packagers with `pacman-key --populate archlinux`.

#
# REPOSITORIES
#   - can be defined here or included from another file
#   - pacman will search repositories in the order defined here
#   - local/custom mirrors can be added here or in separate files
#   - repositories listed first will take precedence when packages
#     have identical names, regardless of version number
#   - URLs will have $repo replaced by the name of the current repo
#   - URLs will have $arch replaced by the name of the architecture
#
# Repository entries are of the format:
#       [repo-name]
#       Server = ServerName
#       Include = IncludePath
#
# The header [repo-name] is crucial - it must be present and
# uncommented to enable the repo.
#

# The testing repositories are disabled by default. To enable, uncomment the
# repo name header and Include lines. You can add preferred servers immediately
# after the header, and they will be used before the default mirrors.
"""

_STD_TESTING_TAIL = """\
#[core-testing]
#Include = /etc/pacman.d/mirrorlist

#[extra-testing]
#Include = /etc/pacman.d/mirrorlist

# If you want to run 32 bit applications on your x86_64 system,
# enable the multilib repositories as required here.

#[multilib-testing]
#Include = /etc/pacman.d/mirrorlist
"""

_CUSTOM_EXAMPLE = """\
# An example of a custom package repository.  See the pacman manpage for
# tips on creating your own repositories.
#[custom]
#SigLevel = Optional TrustAll
#Server = file:///home/custompkgs
"""


# Files the ISO overrides / suppresses. pacstrap must NOT extract the owning
# package's version:
#   usr/lib/os-release   owned by `filesystem`; we replace it with the Az'arch-branded
#                        file, planted post-pacstrap by customize_airootfs.sh.
# This MUST be NoExtract'd (not just overlaid): pacman's file-conflict check runs
# BEFORE extraction and is not suppressed by NoExtract, so pre-placing our copy in the
# airootfs overlay aborts pacstrap with "exists in filesystem". NoExtract keeps the
# package from owning the path; customize_airootfs.sh then lays our copy down after
# pacstrap, conflict-free (see system.CUSTOMIZE_AIROOTFS + compiler.py step 7).
_ISO_NOEXTRACT = [
    "usr/lib/os-release",
]


def _options_block(cachedir: str | None, noextract: list[str] | None = None) -> str:
    cachedir_line = f"CacheDir     = {cachedir}\n" if cachedir else "#CacheDir     = /var/cache/pacman/pkg/\n"
    # A single NoExtract line takes multiple space-separated paths. We NoExtract the
    # files the ISO overrides with its own airootfs copies so pacstrap's owning
    # package (filesystem) does not lay down a conflicting file:
    #   usr/lib/os-release -> our Az'arch branding wins
    noextract_line = (
        f"NoExtract   = {' '.join(noextract)}" if noextract else "#NoExtract   ="
    )
    return _STD_HEADER.format(cachedir_line=cachedir_line, noextract_line=noextract_line)


def _net_repos(multilib: bool) -> str:
    """The standard network repo sections (Include the host mirrorlist)."""
    block = "\n[core]\nInclude = /etc/pacman.d/mirrorlist\n\n[extra]\nInclude = /etc/pacman.d/mirrorlist\n"
    if multilib:
        block += "\n[multilib]\nInclude = /etc/pacman.d/mirrorlist\n"
    else:
        block += "\n#[multilib]\n#Include = /etc/pacman.d/mirrorlist\n"
    return block


def download_conf() -> str:
    """Host-independent configuration for the package-cache download step (cache-pkgs).

    Hard-codes Arch's official mirrors and never Includes the host mirrorlist, so
    the fetch behaves identically on Manjaro, real Arch, and Docker. SigLevel=Never
    (trust is re-established at pacstrap against the file:// repo) and no
    DownloadUser=alpm (pacman runs as root into root-owned scratch here).
    """
    mirrors = (
        "Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch\n"
        "Server = https://mirror.rackspace.com/archlinux/$repo/os/$arch\n"
    )
    return f"""\
#
# Self-contained Arch Linux configuration used ONLY by the package-cache step to
# download the packages that get baked into the ISO's offline install repo.
#
# Why this file exists: the build may run on a non-Arch host (e.g. Manjaro).
# The default pacman configuration on such a host points at the wrong distro's
# repos/mirrors and lacks Arch-only packages, which aborts the build. This
# configuration is fully host-independent: it hard-codes Arch's official mirrors and
# never Includes the host mirrorlist.
#
# SigLevel = Never here only affects the *download* step. Final package trust is
# re-established at pacstrap time against the file:// [pacstrap-azarch-repo].
#
[options]
Architecture      = x86_64
HoldPkg           = pacman glibc
CheckSpace
ParallelDownloads = 5
SigLevel          = Never
LocalFileSigLevel = Never
# Intentionally NO 'DownloadUser = alpm': pacman runs as root here and writes into
# root-owned scratch dirs, so the privilege-dropped alpm helper would fail.

[core]
{mirrors}
[extra]
{mirrors}
[multilib]
{mirrors}"""


def build_profile_conf(cachedir: str | None = None) -> str:
    """The archiso profile's pacman.conf for mkarchiso's internal pacstrap.

    Standard Arch base with two build-specific tweaks folded in:
      - NoExtract usr/lib/os-release -> our Az'arch branding wins
      - an injected CacheDir         -> persistent build cache reuse

    Multilib is left OFF here. The offline rewrite to a file:// repo is applied
    separately (see ``switch_to_local_repo``) so this generator stays declarative.
    """
    conf = _options_block(cachedir=cachedir, noextract=_ISO_NOEXTRACT)
    conf += _STD_TESTING_TAIL
    conf += _net_repos(multilib=False)
    conf += "\n" + _CUSTOM_EXAMPLE
    return conf


def append_local_repo(conf: str, localrepo_path: str) -> str:
    """Append the local file:// [pacstrap-azarch-repo] to a conf that KEEPS its
    network repos. Used for ONLINE builds so mkarchiso's pacstrap pulls Arch
    packages from the mirrors AND Az'arch's own packages (calamares, librewolf,
    which are not on any mirror) from the local repo. Listed LAST so the network
    repos take precedence for any name they both carry (they won't overlap, but
    ordering makes intent explicit)."""
    if "[pacstrap-azarch-repo]" in conf:
        return conf
    return conf.rstrip("\n") + (
        "\n\n[pacstrap-azarch-repo]\n"
        "SigLevel = Never\n"
        f"Server = file://{localrepo_path}\n"
    )


def switch_to_local_repo(conf: str, localrepo_path: str) -> str:
    """Rewrite a profile pacman.conf so pacstrap installs from the local file://
    repo instead of the network mirrors -- the fully-offline rebuild path.

    Drops every network repo section ([core]/[extra]/[multilib], commented or
    not) and appends a single [pacstrap-azarch-repo] pointing at the local repo.
    SigLevel=Never: the cached packages have no .sig files and pacstrap runs with
    -G (no keyring copied into the target), so there is nothing to verify against.
    """
    out_lines: list[str] = []
    skip = False
    for line in conf.splitlines():
        stripped = line.strip()
        if stripped in ("[core]", "[extra]", "[multilib]"):
            skip = True
            continue
        if skip:
            # A repo section runs until the next blank line.
            if stripped == "":
                skip = False
            continue
        out_lines.append(line)
    out = "\n".join(out_lines).rstrip("\n")
    out += (
        "\n\n[pacstrap-azarch-repo]\n"
        "SigLevel = Never\n"
        f"Server = file://{localrepo_path}\n"
    )
    return out


def installer_base_conf() -> str:
    """The /etc/pacman.conf shipped to the INSTALLED system: plain Arch defaults
    with multilib enabled and no build tweaks."""
    conf = _options_block(cachedir=None, noextract=None)
    conf += _STD_TESTING_TAIL
    conf += _net_repos(multilib=True)
    conf += "\n" + _CUSTOM_EXAMPLE
    return conf


def installer_pacstrap_conf() -> str:
    """The transient pacman.conf the on-disk installer swaps in during pacstrap:
    the standard base with the file:// offline install repo appended, and
    multilib left OFF (the installed base doesn't need it during pacstrap)."""
    conf = _options_block(cachedir=None, noextract=_ISO_NOEXTRACT)
    conf += _STD_TESTING_TAIL
    # All network repos commented out; only the local file:// repo is active.
    conf += (
        "\n#[core]\n#Include = /etc/pacman.d/mirrorlist\n"
        "\n#[extra]\n#Include = /etc/pacman.d/mirrorlist\n"
        "\n#[multilib]\n#Include = /etc/pacman.d/mirrorlist\n"
    )
    conf += "\n" + _CUSTOM_EXAMPLE
    conf += (
        "\n[pacstrap-azarch-repo]\n"
        "SigLevel = Never\n"
        "Server = file:///mnt/pacstrap-azarch-repo/\n"
    )
    return conf
