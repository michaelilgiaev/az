"""Az'arch OWN package recipes, authored as configuration-as-Python.

Everything the ISO installs that is NOT in the official Arch repositories is
built from recipes WE write and maintain here -- never from the AUR or any
community source. Like the rest of azarch.config, each artifact (the PKGBUILDs
and their companion files) is held as a Python string and emitted into the build
tree by steps.py; the emitted files are then consumed by `makepkg`, the official
Arch build tool, which produces *.pkg.tar.zst dropped into the ISO's offline
repo. No AUR helper (yay/paru/...) is used.

Two packages are built. Neither is in an official Arch repo, so both are built
in EVERY tier; --full-compile only changes the recipe librewolf uses:

  calamares   -- the graphical system installer (Manjaro-style). It USED to be an
                 official Arch package (extra/calamares), but Arch DROPPED it --
                 it is now AUR-only, and this project never builds from the AUR.
                 So it is compiled from OUR own recipe below in BOTH tiers: a
                 moderate C++/CMake build (minutes), with the release tarball
                 verified by the pinned sha256 (makepkg aborts on mismatch;
                 upstream ships no detached .sig for it). recipe_dirs() emits it
                 unconditionally now.

  librewolf   -- the privacy-hardened Firefox fork. A from-source Firefox build
                 takes 1.5-3+ hours and ~16 GB RAM, so there are TWO recipes:
                   * DEFAULT tier (`compile.sh`)          -> pkgbuild_librewolf()
                     repackages LibreWolf's official prebuilt tarball, verified by
                     BOTH a pinned sha256 AND its OpenPGP signature.
                   * FULL tier   (`compile.sh --full-compile`) -> pkgbuild_librewolf_src()
                     compiles LibreWolf from Firefox source via LibreWolf's bsys6
                     build harness.
                 recipe_dirs(full_compile) picks which pair of recipes to emit.

Pinned upstream facts (versions, URLs, checksums, signing key) live as the
constants below -- the single source of truth. All checksums were obtained by
downloading the real artifacts and hashing them, and are re-checked by makepkg
at build time (it aborts on mismatch). See update notes at the bottom.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Pinned upstream facts (single source of truth)
# ---------------------------------------------------------------------------
CALAMARES_VERSION = "3.4.2"
# sha256 of the official release tarball, obtained by download + sha256sum.
CALAMARES_SHA256 = "733bbbb00dc9f84874bd5c22960952f317ea2537565431179fa2152b2fbfdccc"

# LibreWolf: upstream tag is "153.0.1-1"; pacman-legal pkgver is "153.0.1.1".
LIBREWOLF_VERSION = "153.0.1-1"
LIBREWOLF_PKGVER = "153.0.1.1"
# sha256 from upstream's published .sha256sum, re-verified by download + hash.
LIBREWOLF_SHA256 = "7b56e06071ece9e711a1c811e64129a3a14775c5fe00a4b777e5cbb0b087b5b5"
# LibreWolf release signing key -- the PRIMARY key fingerprint of
# "LibreWolf Maintainers <gpg@librewolf.net>". makepkg's validpgpkeys=() must list
# the PRIMARY key, NOT the signing subkey: the tarball's detached .sig is made by
# an ed25519 *subkey* (915585A1C36690B1 / 230FE8E0...C36690B1), and makepkg maps a
# signing subkey back to its primary and requires THAT primary to be in
# validpgpkeys. Pinning the subkey fingerprint here made makepkg abort with
# "invalid public key 662E3CDD...2B12EF16" (the primary it actually needs). Verify
# on update: `gpg --list-packets <tarball>.sig` shows the signing subkey keyid;
# `gpg --recv-keys <that keyid>` then shows the primary under `pub`.
LIBREWOLF_PGP_KEY = "662E3CDD6FE329002D0CA5BB40339DD82B12EF16"


# ---------------------------------------------------------------------------
# calamares -- source patch: Az'arch installer UI defaults
# ---------------------------------------------------------------------------
# Two of the installer's default selections are decided in Calamares' C++ (its
# module *.conf schemas expose no key for either), so they can only be changed by
# patching the source before the build. This single patch, applied in the recipe's
# prepare(), carries both:
#
#   1. Keyboard page -- "Switch Keyboard" (the xkb group-switcher dropdown).
#      Upstream builds the dropdown from a QMap sorted by human-readable label and
#      leaves the current index at 0 (the alphabetically-first combo), so "Alt+Shift"
#      is present but NOT pre-selected. The patch makes KeyboardGroupsSwitchersModel's
#      constructor select the entry whose xkb id is `alt_shift_toggle` once the list
#      is built, so the dropdown defaults to "Alt+Shift". (Nothing else on the page
#      changes; layout stays "us" via modules/keyboard.conf guessLayout:false.)
#
#   2. Users page -- "What is the name of this computer?" (hostname).
#      Upstream seeds the hostname field ONLY once the user types a name, expanding
#      the `hostname.template` ("${first}-${product}" by default) on every keystroke
#      so the hostname keeps changing as the Full Name / Login fields change. The
#      patch seeds the template's expansion as the INITIAL hostname at module load
#      and (via setHostName, which marks the value "custom") takes the field off the
#      auto-derive path -- so with modules/users.conf `template: "azarch"` the field
#      shows "azarch" by default and stays "azarch" regardless of the other inputs.
#
# Both hunks are small and target stable code paths in calamares 3.4.2; the pinned
# tarball guarantees the context lines below match. A context drift on a version
# bump makes `patch` fail LOUDLY in prepare() (the build aborts) rather than
# silently dropping the customization -- refresh the hunks when bumping the version.
CALAMARES_DEFAULTS_PATCH_NAME = "azarch-calamares-defaults.patch"


def calamares_defaults_patch() -> str:
    r"""Unified diff (-p1) applied to the extracted calamares-3.4.2 source in the
    recipe's prepare(): default the keyboard group-switcher to Alt+Shift and seed a
    fixed, non-reactive default hostname. See the block comment above for why these
    live in a source patch rather than a module .conf. The paths are a/ b/ prefixed
    so `patch -p1` (run from the source root) applies them.

    The diff is built line-by-line rather than as one big triple-quoted literal
    ON PURPOSE: a unified diff's CONTEXT lines (unchanged surrounding source) must
    each begin with a single leading SPACE, and blank context lines are therefore a
    line that is exactly one space. A triple-quoted literal makes those
    space-only lines invisible and trivially corrupted by an editor that strips
    trailing whitespace -- which silently breaks `patch`. Assembling from a list
    keeps every context line's leading space explicit and greppable. The hunk
    headers (@@ -284,4 ... / @@ -1020,6 ...) were generated by `diff -u` against the
    pinned 3.4.2 source and verified to apply with `patch -p1`; regenerate them the
    same way on a version bump."""
    # Each entry is one full diff line. Context lines start with " " (space),
    # additions with "+", hunk headers with "@@", file headers with ---/+++.
    lines = [
        "--- a/src/modules/keyboard/KeyboardLayoutModel.cpp",
        "+++ b/src/modules/keyboard/KeyboardLayoutModel.cpp",
        "@@ -284,4 +284,18 @@",
        "     }",
        " ",
        '     cDebug() << "Loaded" << m_list.count() << "keyboard groups";',
        "+",
        '+    // Az\'arch: default the "Switch Keyboard" dropdown to Alt+Shift. Upstream leaves',
        "+    // the current index at 0 (the alphabetically-first combo), so alt_shift_toggle is",
        "+    // listed but not pre-selected. Select it here, once the list is populated, so the",
        '+    // page opens with "Alt+Shift" chosen. Falls back to the upstream default (index 0)',
        "+    // if the xkb id is ever absent from the map.",
        "+    for ( int i = 0; i < m_list.count(); ++i )",
        "+    {",
        '+        if ( m_list.at( i ).key == QStringLiteral( "alt_shift_toggle" ) )',
        "+        {",
        "+            setCurrentIndex( i );",
        "+            break;",
        "+        }",
        "+    }",
        " }",
        "--- a/src/modules/users/Config.cpp",
        "+++ b/src/modules/users/Config.cpp",
        "@@ -1020,6 +1020,20 @@",
        '         m_forbiddenHostNames = Calamares::getStringList( hostnameSettings, "forbidden_names" );',
        "         m_forbiddenHostNames << alwaysForbiddenHostNames();",
        "         tidy( m_forbiddenHostNames );",
        "+",
        "+        // Az'arch: seed a fixed default hostname and take it off the auto-derive",
        "+        // path. Upstream leaves the hostname empty until the user types a name, then",
        "+        // re-expands m_hostnameTemplate on every keystroke -- so the hostname keeps",
        "+        // changing as the Full Name / Login fields change. Expanding the template",
        "+        // once here (with no user data) gives the initial value, and setHostName()",
        '+        // marks it "custom" (m_customHostName = true) so setFullName() never',
        '+        // recomputes it. With a literal template ("azarch") the field shows "azarch"',
        "+        // by default and stays \"azarch\" no matter what else is typed.",
        "+        const QString seededHostname = makeHostnameSuggestion( m_hostnameTemplate, QStringList(), QString() );",
        "+        if ( !seededHostname.isEmpty() )",
        "+        {",
        "+            setHostName( seededHostname );",
        "+        }",
        "     }",
        " ",
        "     setConfigurationDefaultGroups( configurationMap, m_defaultGroups );",
    ]
    # Trailing newline so the last line is terminated (patch/POSIX text file).
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# calamares -- built from source, always
# ---------------------------------------------------------------------------
def pkgbuild_calamares() -> str:
    return f"""\
# Maintainer: Az'arch <https://github.com/michaelilgiaev/azarch>
#
# =============================================================================
# Az'arch OWN PKGBUILD -- calamares  (generated by azarch.configuration.pkgbuild)
# =============================================================================
# NOT a community/AUR recipe. Written + maintained by the Az'arch project so the
# build has no dependency on third-party packaging.
#
# Calamares is the distribution-independent graphical system installer. Az'arch
# uses it as the live-ISO installer (Manjaro-style), configured for a Btrfs
# default and optional full-disk LUKS encryption via module configs shipped on
# the ISO (this recipe only builds the binary).
#
# SOURCE (fully auditable):
#   Project : https://codeberg.org/Calamares/calamares
#   Release : https://codeberg.org/Calamares/calamares/releases/tag/v{CALAMARES_VERSION}
#   Tarball : https://codeberg.org/Calamares/calamares/releases/download/v{CALAMARES_VERSION}/calamares-{CALAMARES_VERSION}.tar.gz
#   License : GPL-3.0-or-later
#
# INTEGRITY: pinned sha256 below (from download + sha256sum). Upstream ships no
# detached .sig for the release archive, so the sha256 is the anchor; makepkg
# aborts the build on mismatch.
#
# FROM SOURCE IN EVERY TIER: a moderate C++/CMake build (minutes). Arch dropped
# calamares from extra/ (it is now AUR-only), so there is no Arch-signed binary
# to install anymore; recipe_dirs() emits this recipe for both the default and
# the --full-compile tier.
# =============================================================================

pkgname=calamares
pkgver={CALAMARES_VERSION}
pkgrel=1
pkgdesc="Distribution-independent installer framework (Az'arch build)"
arch=('x86_64')
url="https://codeberg.org/Calamares/calamares"
license=('GPL-3.0-or-later')

# Deps per upstream CMakeLists.txt for the 3.4.x line: Qt6 >= 6.5, KF6 >= 6.5,
# ECM 6.5, CMake >= 3.16, yaml-cpp, kpmcore (partitioning), polkit-qt6, boost +
# bundled pybind11 (Python job modules), squashfs-tools/rsync (unpackfs), plus
# the filesystem tools the partition module drives.
depends=(
  'qt6-base' 'qt6-svg' 'qt6-declarative'
  'kcoreaddons' 'kconfig' 'ki18n' 'kcrash'
  'kpmcore' 'yaml-cpp' 'polkit-qt6' 'boost-libs'
  'python' 'squashfs-tools' 'rsync'
  'cryptsetup' 'dosfstools' 'e2fsprogs' 'btrfs-progs' 'gptfdisk'
  'hwinfo' 'icu'
)
makedepends=('cmake' 'extra-cmake-modules' 'qt6-tools' 'boost' 'git')
optdepends=(
  'btrfs-progs: Btrfs filesystem support'
  'cryptsetup: full-disk LUKS encryption support'
  'grub: GRUB bootloader install'
)

source=(
  "calamares-${{pkgver}}.tar.gz::${{url}}/releases/download/v${{pkgver}}/calamares-${{pkgver}}.tar.gz"
  '{CALAMARES_DEFAULTS_PATCH_NAME}'
)
# Tarball: pinned sha256 (makepkg aborts on mismatch). Patch: shipped in-repo,
# reviewed in azarch.configuration.pkgbuild (SKIP -- a local file, not downloaded).
sha256sums=('{CALAMARES_SHA256}' 'SKIP')

prepare() {{
  cd "calamares-${{pkgver}}"
  # Az'arch installer UI defaults that Calamares only exposes in C++ (Alt+Shift
  # keyboard switch default + fixed non-reactive hostname). -p1 from the source
  # root; the pinned tarball guarantees the context matches, so a failure here
  # (e.g. after a version bump) aborts the build loudly instead of silently
  # dropping the customization.
  patch -p1 < "$srcdir/{CALAMARES_DEFAULTS_PATCH_NAME}"
}}

build() {{
  cd "calamares-${{pkgver}}"
  # Qt6 + KF6, bundled pybind11 for Python job modules, QML on for the branding
  # slideshow, crash reporter off (extra deps, pointless on a live ISO).
  cmake -B build -S . \\
    -DCMAKE_BUILD_TYPE=Release \\
    -DCMAKE_INSTALL_PREFIX=/usr \\
    -DCMAKE_INSTALL_LIBDIR=lib \\
    -DWITH_QT6=ON \\
    -DWITH_PYBIND11=ON \\
    -DWITH_QML=ON \\
    -DBUILD_CRASH_REPORTING=OFF \\
    -DINSTALL_POLKIT=ON \\
    -DWEBVIEW_FORCE_WEBKIT=OFF
  cmake --build build
}}

package() {{
  cd "calamares-${{pkgver}}"
  DESTDIR="$pkgdir" cmake --install build
}}
"""


# ---------------------------------------------------------------------------
# librewolf -- shared companion files (used by BOTH tiers)
# ---------------------------------------------------------------------------
def librewolf_desktop() -> str:
    return """\
[Desktop Entry]
Name=LibreWolf
GenericName=Web Browser
Comment=Browse the web (Az'arch build, sessions/cookies persist)
Exec=/opt/librewolf/librewolf %u
Icon=librewolf
Terminal=false
Type=Application
MimeType=text/html;text/xml;application/xhtml+xml;application/xml;application/vnd.mozilla.xul+xml;application/rss+xml;application/rdf+xml;image/gif;image/jpeg;image/png;x-scheme-handler/http;x-scheme-handler/https;x-scheme-handler/ftp;x-scheme-handler/chrome;video/webm;application/x-xpinstall;
StartupNotify=true
StartupWMClass=librewolf
Categories=Network;WebBrowser;
Keywords=Internet;WWW;Browser;Web;Explorer;
Actions=new-window;new-private-window;

[Desktop Action new-window]
Name=Open a New Window
Exec=/opt/librewolf/librewolf --new-window %u

[Desktop Action new-private-window]
Name=Open a New Private Window
Exec=/opt/librewolf/librewolf --private-window %u
"""


def librewolf_overrides_cfg() -> str:
    """LibreWolf's officially-supported override file (loaded AFTER the stock
    librewolf.cfg). Relaxes ONLY the sanitise-on-shutdown prefs so sessions and
    cookies persist; every other LibreWolf hardening pref is left as upstream
    ships it. https://librewolf.net/docs/settings/"""
    return """\
// Az'arch LibreWolf overrides -- session & cookie persistence
//
// LibreWolf ships privacy-hardened and by DEFAULT wipes cookies + history on
// shutdown (privacy.sanitize.sanitizeOnShutdown = true, plus the clearOnShutdown
// keys). Az'arch wants sessions and logins to PERSIST across restarts, so this
// file -- LibreWolf's officially-supported override, loaded AFTER librewolf.cfg
// -- turns that behaviour off. It ONLY relaxes the shutdown-sanitisation prefs;
// every other LibreWolf hardening pref is left exactly as upstream ships it.
//
// AutoConfig files must begin with a comment line; the engine ignores line 1.

// --- Do not sanitise on shutdown ------------------------------------------
defaultPref("privacy.sanitize.sanitizeOnShutdown", false);

// --- Keep each data category on shutdown (new _v2 keys, FF/LW current) -----
defaultPref("privacy.clearOnShutdown_v2.cookiesAndStorage", false);
defaultPref("privacy.clearOnShutdown_v2.historyFormDataAndDownloads", false);
defaultPref("privacy.clearOnShutdown_v2.browsingHistoryAndDownloads", false);
defaultPref("privacy.clearOnShutdown_v2.cache", false);
defaultPref("privacy.clearOnShutdown_v2.siteSettings", false);
defaultPref("privacy.clearOnShutdown_v2.formdata", false);

// --- Legacy keys (older builds still honour these) -------------------------
defaultPref("privacy.clearOnShutdown.cookies", false);
defaultPref("privacy.clearOnShutdown.history", false);
defaultPref("privacy.clearOnShutdown.sessions", false);
defaultPref("privacy.clearOnShutdown.cache", false);
defaultPref("privacy.clearOnShutdown.offlineApps", false);
defaultPref("privacy.clearOnShutdown.formdata", false);
defaultPref("privacy.clearOnShutdown.siteSettings", false);

// --- Cookies live their normal lifetime (0 = accept normally) --------------
defaultPref("network.cookie.lifetimePolicy", 0);

// --- Restore the previous session on start, so open tabs come back ---------
defaultPref("browser.startup.page", 3);
"""


# ---------------------------------------------------------------------------
# librewolf -- DEFAULT tier (repackage the verified upstream tarball)
# ---------------------------------------------------------------------------
def pkgbuild_librewolf() -> str:
    dl = f"https://codeberg.org/api/packages/librewolf/generic/librewolf/{LIBREWOLF_VERSION}"
    tar = f"librewolf-{LIBREWOLF_VERSION}-linux-x86_64-package.tar.xz"
    return f"""\
# Maintainer: Az'arch <https://github.com/michaelilgiaev/azarch>
#
# =============================================================================
# Az'arch OWN PKGBUILD -- librewolf (DEFAULT tier: repackage verified upstream)
# =============================================================================
# NOT a community/AUR recipe. Written + maintained by the Az'arch project.
# Generated by azarch.configuration.pkgbuild.
#
# A from-source LibreWolf/Firefox compile takes 1.5-3+ hours and needs ~16 GB
# RAM. To keep the DEFAULT `compile.sh` build fast, this recipe repackages
# LibreWolf's OFFICIAL prebuilt generic-Linux tarball, verified TWO ways:
#   1. pinned sha256sum (from upstream's published .sha256sum), and
#   2. detached OpenPGP signature (.sig) against the LibreWolf release key.
# For an all-self-compiled build use `compile.sh --full-compile`, which selects
# the source recipe instead.
#
# SOURCE (fully auditable):
#   Build system : https://codeberg.org/librewolf/bsys6
#   Website      : https://librewolf.net/
#   Tarball      : {dl}/{tar}
#   Signature    : {dl}/{tar}.sig   (key {LIBREWOLF_PGP_KEY})
#   Checksum src : {dl}/{tar}.sha256sum
#   Mirror note  : dl.librewolf.net is the upstream CDN; Codeberg's package API
#                  hosts the same files (same sha256) and is the active mirror.
#   License      : MPL-2.0
# The tarball is built by LibreWolf from Firefox source + LibreWolf's public
# patch set, so the lineage traces to scrutinizable source even in this path.
#
# AZ'ARCH CUSTOMISATION: LibreWolf clears cookies + history on shutdown by
# default; Az'arch ships librewolf.overrides.cfg (LibreWolf's supported override)
# so sessions and cookies persist. Everything else is stock LibreWolf.
# =============================================================================

pkgname=librewolf
pkgver={LIBREWOLF_PKGVER}
_lwver={LIBREWOLF_VERSION}
pkgrel=1
pkgdesc="Privacy-hardened Firefox fork, session/cookie persistence (Az'arch build)"
arch=('x86_64')
url="https://librewolf.net/"
license=('MPL-2.0')
depends=('gtk3' 'libxt' 'mime-types' 'dbus' 'ffmpeg' 'nss' 'ttf-font'
         'libpulse' 'libnotify' 'pciutils')
options=('!strip')

_dl="{dl}"
source=(
  "librewolf-${{_lwver}}-linux-x86_64-package.tar.xz::${{_dl}}/librewolf-${{_lwver}}-linux-x86_64-package.tar.xz"
  "librewolf-${{_lwver}}-linux-x86_64-package.tar.xz.sig::${{_dl}}/librewolf-${{_lwver}}-linux-x86_64-package.tar.xz.sig"
  'librewolf.desktop'
  'librewolf.overrides.cfg'
)
# Tarball: pinned sha256 (+ GPG). .sig: GPG-checked (SKIP sha). Local files:
# shipped in-repo, reviewed in azarch.configuration.pkgbuild (SKIP sha).
sha256sums=('{LIBREWOLF_SHA256}' 'SKIP' 'SKIP' 'SKIP')
validpgpkeys=('{LIBREWOLF_PGP_KEY}')

package() {{
  # Tarball extracts to a top-level librewolf/ dir (Firefox-style layout).
  install -d "$pkgdir/opt"
  cp -a "$srcdir/librewolf" "$pkgdir/opt/librewolf"

  install -d "$pkgdir/usr/bin"
  ln -s /opt/librewolf/librewolf "$pkgdir/usr/bin/librewolf"

  install -Dm644 "$srcdir/librewolf.desktop" \\
    "$pkgdir/usr/share/applications/librewolf.desktop"

  local icon="$srcdir/librewolf/browser/chrome/icons/default/default128.png"
  [[ -f "$icon" ]] && install -Dm644 "$icon" \\
    "$pkgdir/usr/share/icons/hicolor/128x128/apps/librewolf.png"

  # Az'arch persistence override (loaded after the stock librewolf.cfg).
  install -Dm644 "$srcdir/librewolf.overrides.cfg" \\
    "$pkgdir/opt/librewolf/librewolf.overrides.cfg"
}}
"""


# ---------------------------------------------------------------------------
# librewolf -- FULL tier (compile from Firefox source via bsys6)
# ---------------------------------------------------------------------------
def pkgbuild_librewolf_src() -> str:
    return f"""\
# Maintainer: Az'arch <https://github.com/michaelilgiaev/azarch>
#
# =============================================================================
# Az'arch OWN PKGBUILD -- librewolf (FULL-COMPILE tier: build from source)
# =============================================================================
# NOT a community/AUR recipe. Written + maintained by the Az'arch project.
# Generated by azarch.configuration.pkgbuild. Selected ONLY by `compile.sh --full-compile`.
#
# ///////////////////////////////////////////////////////////////////////////
#  HEAVY BUILD WARNING: a from-source LibreWolf/Firefox compile takes 1.5-3+
#  hours on a strong multi-core machine and needs ~16 GB RAM + tens of GB disk.
#  The default `compile.sh` (repackage tier) exists to avoid this.
# ///////////////////////////////////////////////////////////////////////////
#
# SOURCE (fully auditable):
#   Build system : https://codeberg.org/librewolf/bsys6   (tag {LIBREWOLF_VERSION})
#   which fetches Mozilla Firefox source (release 153.0) + LibreWolf's public
#   patch set/settings, all in the codeberg repos.
#   License      : MPL-2.0
#
# INTEGRITY: bsys6 verifies the Firefox source it downloads against Mozilla's
# published checksums as part of its own build. We pin bsys6 by git tag.
# =============================================================================

pkgname=librewolf
pkgver={LIBREWOLF_PKGVER}
_lwver={LIBREWOLF_VERSION}
pkgrel=1
pkgdesc="Privacy-hardened Firefox fork built FROM SOURCE, persistence (Az'arch build)"
arch=('x86_64')
url="https://librewolf.net/"
license=('MPL-2.0')
depends=('gtk3' 'libxt' 'mime-types' 'dbus' 'ffmpeg' 'nss' 'ttf-font'
         'libpulse' 'libnotify' 'pciutils')
# The Firefox build toolchain -- the bulk of what makes the full compile heavy.
makedepends=('rust' 'clang' 'llvm' 'lld' 'nodejs' 'cbindgen' 'nasm' 'yasm'
             'python' 'python-setuptools' 'unzip' 'zip' 'gawk' 'perl' 'wget'
             'mercurial' 'git' 'make' 'pkgconf' 'gtk3' 'nss' 'gcc' 'which'
             'mesa' 'libpulse' 'dbus-glib' 'alsa-lib')
options=('!strip' '!lto' '!debug')

source=(
  "librewolf-bsys6::git+https://codeberg.org/librewolf/bsys6.git#tag=${{_lwver}}"
  'librewolf.desktop'
  'librewolf.overrides.cfg'
)
sha256sums=('SKIP' 'SKIP' 'SKIP')

build() {{
  cd "$srcdir/librewolf-bsys6"
  # bsys6's documented top-level targets: fetch Firefox source + LibreWolf
  # patches/settings, build, then produce the generic-linux package tree.
  #
  # `make fetch` is the ONLY network step. On an OFFLINE --full-compile rerun the
  # Az'arch build sets AZARCH_OFFLINE=1 and passes makepkg --noextract, so this
  # same bsys6 tree (already populated by the prior online run's `make fetch`) is
  # reused as-is: we skip the fetch and go straight to build. If the tree were
  # gone (a wiped cache) `make build` fails loudly here -- we never silently go
  # back online. On the normal online run AZARCH_OFFLINE is unset and `make fetch`
  # populates the tree as before.
  if [[ -z "${{AZARCH_OFFLINE:-}}" ]]; then make fetch; fi
  make build
  make package
}}

package() {{
  cd "$srcdir/librewolf-bsys6"
  # Locate the produced package tree / tarball (bsys6 emits under its own dir).
  local tree
  tree="$(find . -maxdepth 4 -type d -name librewolf -path '*obj*' 2>/dev/null | head -1)"
  if [[ -z "$tree" ]]; then
    local tarball
    tarball="$(find . -maxdepth 3 -name 'librewolf-*.tar.xz' 2>/dev/null | head -1)"
    [[ -n "$tarball" ]] || {{ echo "librewolf-src: could not locate build output"; return 1; }}
    bsdtar -xf "$tarball" -C "$srcdir"
    tree="$srcdir/librewolf"
  fi

  install -d "$pkgdir/opt"
  cp -a "$tree" "$pkgdir/opt/librewolf"

  install -d "$pkgdir/usr/bin"
  ln -s /opt/librewolf/librewolf "$pkgdir/usr/bin/librewolf"

  install -Dm644 "$srcdir/librewolf.desktop" \\
    "$pkgdir/usr/share/applications/librewolf.desktop"

  local icon="$pkgdir/opt/librewolf/browser/chrome/icons/default/default128.png"
  [[ -f "$icon" ]] && install -Dm644 "$icon" \\
    "$pkgdir/usr/share/icons/hicolor/128x128/apps/librewolf.png"

  install -Dm644 "$srcdir/librewolf.overrides.cfg" \\
    "$pkgdir/opt/librewolf/librewolf.overrides.cfg"
}}
"""


# ---------------------------------------------------------------------------
# Recipe emission plan: (dirname, {filename: content}) tuples.
# steps.py iterates this to write each recipe dir into the build tree, then the
# makepkg stage builds each and drops the result into the offline repo.
# ---------------------------------------------------------------------------
def recipe_dirs(full_compile: bool) -> list[tuple[str, dict[str, str]]]:
    """Which recipes to emit. BOTH calamares and librewolf are built in EVERY
    tier now -- neither is in an official Arch repo (librewolf never was;
    calamares was dropped from extra/ and is AUR-only). --full-compile only
    changes the RECIPE, not the set:

      calamares : always compiled from source (pinned-sha256 Codeberg tarball,
                  a moderate C++/CMake build of minutes). There is no prebuilt
                  Arch binary to fall back to anymore, so both tiers use the
                  same source recipe.
      librewolf : default = repackage the verified upstream binary tarball;
                  --full-compile = compile from Firefox source (1.5-3+ hours)."""
    lw_common = {
        "librewolf.desktop": librewolf_desktop(),
        "librewolf.overrides.cfg": librewolf_overrides_cfg(),
    }
    calamares = ("calamares", {
        "PKGBUILD": pkgbuild_calamares(),
        CALAMARES_DEFAULTS_PATCH_NAME: calamares_defaults_patch(),
    })
    if full_compile:
        librewolf = ("librewolf", {"PKGBUILD": pkgbuild_librewolf_src(), **lw_common})
        return [calamares, librewolf]
    librewolf = ("librewolf", {"PKGBUILD": pkgbuild_librewolf(), **lw_common})
    # Default tier: repackage librewolf, but calamares is still built from source.
    return [calamares, librewolf]


# ---------------------------------------------------------------------------
# Updating versions:
#   1. Bump CALAMARES_VERSION / LIBREWOLF_VERSION / LIBREWOLF_PKGVER above.
#      LIBREWOLF_VERSION is the upstream tag (e.g. "153.0.1-1");
#      LIBREWOLF_PKGVER is the pacman-legal form (dots only, e.g. "153.0.1.1").
#   2. Refresh the pinned sha256 from Codeberg's package API:
#      https://codeberg.org/api/packages/librewolf/generic/librewolf/<tag>/
#        librewolf-<tag>-linux-x86_64-package.tar.xz.sha256sum
#   3. If LibreWolf rotates its signing key, update LIBREWOLF_PGP_KEY.
#   4. Rebuild with FORCE_ONLINE=1 so the new sources are fetched.
# ---------------------------------------------------------------------------
