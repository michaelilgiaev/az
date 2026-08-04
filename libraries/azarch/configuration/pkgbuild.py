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
# calamares -- source patch: region-driven keyboard (English + region language)
# ---------------------------------------------------------------------------
# The single most-requested installer behaviour (issue #46 / PROMPT): when the
# user picks a REGION on the Location page, the Keyboard page must automatically
# carry TWO xkb layouts -- English ("us") active first, and the region's native
# layout as a switchable SECOND (Alt+Shift) -- applied to the LIVE installer X11
# session (so the "Type here to test" box switches scripts on Alt+Shift) AND
# persisted to the installed target. An English-speaking region gets English only.
#
# None of this is expressible in a module .conf: the linkage lives entirely in
# Calamares' C++ (the keyboard module reads GlobalStorage and drives setxkbmap),
# so it can only be changed by patching the source. This SECOND patch (kept apart
# from azarch-calamares-defaults.patch so the two concerns stay independent) makes
# three coordinated edits, all verified against the pinned 3.4.2 source:
#
#   1. locale/Config.cpp -- publish the selected zone's ISO-3166 country code to
#      GlobalStorage as "locationCountry". Neither locationRegion (America/Asia)
#      nor locationZone (El_Salvador/Riyadh) is a country code, and nothing else
#      in GS carries one -- but the keyboard module needs it to pick the layout.
#
#   2. keyboard/Config.h + Config.cpp -- add an opt-in `regionSecondLayout` config
#      knob (default false, so upstream is unaffected) and a guessRegionKeyboardLayout()
#      that, when the knob is on, reads "locationCountry", maps it to the region's
#      xkb layout via an embedded country->layout table (covers Latin-script langs
#      like Spanish/French too, which upstream's non-ascii-layouts does NOT), makes
#      the region layout the primary with "us" force-added as the additional layout
#      (so the emitted order is "us,<region>" -- English first/active), and applies
#      it live. It runs from onActivate() inside the existing Guessing state scope,
#      so navigating Location->Keyboard (even after changing the region) re-derives
#      it. apply() is patched to keep that "us" additional instead of re-deriving
#      one from the (ASCII) primary.
#
# The region xkb layout codes are real base.lst identifiers (VERIFIED against
# /usr/share/X11/xkb/rules/base.lst): Hebrew is "il" (not "he"), generic Arabic is
# "ara", Latin-American Spanish is "latam". The pinned tarball guarantees the
# context lines match; a drift on a version bump makes `patch` fail LOUDLY in
# prepare() rather than silently dropping the feature -- refresh the hunks then.
CALAMARES_REGION_KEYBOARD_PATCH_NAME = "azarch-calamares-region-keyboard.patch"


def calamares_region_keyboard_patch() -> str:
    r"""Unified diff (-p1) applied to the extracted calamares-3.4.2 source in the
    recipe's prepare(), AFTER azarch-calamares-defaults.patch: wire region selection
    on the Location page to an English+region two-layout keyboard config (see the
    block comment above). Touches locale/Config.cpp (publish locationCountry to GS)
    and keyboard/Config.h + keyboard/Config.cpp (the guessRegionKeyboardLayout()
    machinery + the regionSecondLayout knob + the apply() guard).

    Same authoring rule as calamares_defaults_patch(): the diff is assembled from a
    line-by-line list so every unified-diff CONTEXT line keeps its exact single
    leading space (blank context lines are one space) -- a triple-quoted literal
    would let an editor strip that trailing space and silently break `patch`. The
    hunks were generated by `diff -u` against the pinned 3.4.2 source and verified to
    apply with `patch -p1 --dry-run`; regenerate them the same way on a version bump.
    """
    # Each entry is one full diff line. Context lines start with " " (a single
    # space), additions with "+", removals with "-", hunk headers with "@@".
    lines = [
        "--- a/src/modules/keyboard/Config.h",
        "+++ b/src/modules/keyboard/Config.h",
        "@@ -37,6 +37,9 @@",
        "     void detectCurrentKeyboardLayout();",
        "     /// @brief Based on current locale, pick a layout",
        "     void guessLocaleKeyboardLayout();",
        "+    /// @brief Az'arch: derive an English+region two-layout config from the",
        '+    /// region picked on the Location page (GlobalStorage "locationCountry").',
        "+    void guessRegionKeyboardLayout();",
        " ",
        "     Calamares::JobList createJobs();",
        "     QString prettyStatus() const;",
        "@@ -124,6 +127,22 @@",
        "     bool m_configureGnome = false;",
        "     bool m_guessLayout = false;",
        " ",
        "+    // Az'arch: when true, guessLocaleKeyboardLayout() ALSO derives a SECOND keyboard",
        "+    // layout from the region the user picked on the Location page (GlobalStorage",
        "+    // \"locationCountry\"): English (\"us\") stays the active layout and the region's",
        "+    // native layout is added as a switchable second (Alt+Shift). English-speaking",
        "+    // regions get English only. See guessRegionKeyboardLayout(). Off (the upstream",
        "+    // default) keeps stock behaviour.",
        "+    bool m_regionSecondLayout = false;",
        "+    // The region's native xkb layout picked by guessRegionKeyboardLayout() (e.g.",
        '+    // "latam", "fr", "il", "ara"), or empty for an English-speaking region. Held so',
        "+    // apply() keeps it as the additional layout instead of re-deriving one from the",
        '+    // (ASCII, "us") primary -- which getAdditionalLayoutInfo() returns empty for.',
        "+    QString m_regionLayout;",
        "+    // The console keymap paired with m_regionLayout (vconsole KEYMAP=), e.g.",
        '+    // "la-latin1", "fr", "il", "ar". Empty when m_regionLayout is empty.',
        "+    QString m_regionVConsoleKeymap;",
        "+",
        "     // The state determines whether we guess settings or preserve them:",
        "     // - Initial -> Guessing",
        "     // - Initial -> UserSelected",
        "--- a/src/modules/keyboard/Config.cpp",
        "+++ b/src/modules/keyboard/Config.cpp",
        "@@ -447,7 +447,28 @@",
        " void",
        " Config::apply()",
        " {",
        "-    m_additionalLayoutInfo = getAdditionalLayoutInfo( m_current.selectedLayout );",
        "+    // Az'arch: while the region-driven pair is in effect (primary is still the",
        '+    // region layout guessRegionKeyboardLayout() selected), force "us" as the',
        '+    // additional layout so English stays first/active in the emitted "us,<region>"',
        "+    // -- even for Latin-script regions (latam/es/fr/...) that getAdditionalLayoutInfo()",
        "+    // does not cover. The moment the user picks a DIFFERENT primary layout by hand,",
        "+    // m_current.selectedLayout no longer equals m_regionLayout, so we fall back to",
        "+    // the stock derivation and the user's explicit choice wins.",
        "+    if ( m_regionSecondLayout && !m_regionLayout.isEmpty() && m_current.selectedLayout == m_regionLayout )",
        "+    {",
        "+        AdditionalLayoutInfo extra;",
        '+        extra.additionalLayout = QStringLiteral( "us" );',
        "+        extra.additionalVariant = QString();",
        "+        // applyXkb() overrides this with the user's chosen group when one is set;",
        "+        // otherwise Alt+Shift (also the group-switcher dropdown's default).",
        '+        extra.groupSwitcher = QStringLiteral( "grp:alt_shift_toggle" );',
        "+        extra.vconsoleKeymap = m_regionVConsoleKeymap;",
        "+        m_additionalLayoutInfo = extra;",
        "+    }",
        "+    else",
        "+    {",
        "+        m_additionalLayoutInfo = getAdditionalLayoutInfo( m_current.selectedLayout );",
        "+    }",
        "     if ( m_configureXkb )",
        "     {",
        "         applyXkb( m_current, m_additionalLayoutInfo );",
        "@@ -832,12 +853,168 @@",
        "             lang = newLang;",
        "         }",
        "     }",
        "+    // Az'arch: when region-driven second layout is enabled, ignore the (always",
        "+    // English) display LANG for the keyboard and derive the layout pair from the",
        "+    // region the user picked on the Location page instead. Runs inside the same",
        "+    // Guessing scope so the programmatic selection below does not flip the state",
        "+    // machine to UserSelected (which would freeze re-guessing on a later visit).",
        "+    if ( m_regionSecondLayout )",
        "+    {",
        "+        guessRegionKeyboardLayout();",
        "+        return;",
        "+    }",
        "     if ( !lang.isEmpty() )",
        "     {",
        "         guessLayout( lang.split( '_', SplitSkipEmptyParts ), m_keyboardLayoutsModel, m_keyboardVariantsModel );",
        "     }",
        " }",
        " ",
        "+// Az'arch: map an ISO-3166 country code (as written to GlobalStorage",
        '+// "locationCountry" by the patched locale module) to the region\'s native xkb',
        "+// LAYOUT and console KEYMAP. English-speaking countries are deliberately absent:",
        "+// they get English only (no second layout). The layout codes are real",
        '+// /usr/share/X11/xkb/rules/base.lst identifiers (verified): Hebrew is "il" (NOT',
        '+// "he"), generic Arabic is "ara", Latin-American Spanish is "latam" (Spain is',
        '+// "es"). Extend this table to add a language -- it is the single source of truth',
        "+// for the installer's region->keyboard mapping.",
        "+static QString",
        "+regionLayoutForCountry( const QString& cc, QString& vconsoleKeymap )",
        "+{",
        "+    struct Entry",
        "+    {",
        "+        const char* country;",
        "+        const char* layout;",
        "+        const char* keymap;",
        "+    };",
        "+    // clang-format off",
        "+    static const Entry table[] = {",
        "+        // Spanish (Latin America) and Spanish (Spain)",
        '+        { "SV", "latam", "la-latin1" }, { "MX", "latam", "la-latin1" },',
        '+        { "AR", "latam", "la-latin1" }, { "CO", "latam", "la-latin1" },',
        '+        { "CL", "latam", "la-latin1" }, { "PE", "latam", "la-latin1" },',
        '+        { "VE", "latam", "la-latin1" }, { "EC", "latam", "la-latin1" },',
        '+        { "GT", "latam", "la-latin1" }, { "BO", "latam", "la-latin1" },',
        '+        { "CR", "latam", "la-latin1" }, { "PY", "latam", "la-latin1" },',
        '+        { "PA", "latam", "la-latin1" }, { "UY", "latam", "la-latin1" },',
        '+        { "HN", "latam", "la-latin1" }, { "NI", "latam", "la-latin1" },',
        '+        { "DO", "latam", "la-latin1" }, { "CU", "latam", "la-latin1" },',
        '+        { "ES", "es", "es" },',
        "+        // Other Latin-script languages",
        '+        { "FR", "fr", "fr" }, { "DE", "de", "de" }, { "AT", "de", "de" },',
        '+        { "CH", "ch", "de_CH-latin1" }, { "IT", "it", "it" },',
        '+        { "PT", "pt", "pt-latin1" }, { "BR", "br", "br-abnt2" },',
        '+        { "NL", "nl", "nl" }, { "PL", "pl", "pl" }, { "SE", "se", "sv-latin1" },',
        '+        { "NO", "no", "no-latin1" }, { "DK", "dk", "dk-latin1" },',
        '+        { "FI", "fi", "fi" }, { "CZ", "cz", "cz-lat2" }, { "HU", "hu", "hu" },',
        '+        { "TR", "tr", "trq" }, { "RO", "ro", "ro" }, { "HR", "hr", "croat" },',
        '+        { "SK", "sk", "sk-qwerty" }, { "SI", "si", "slovene" },',
        '+        { "EE", "ee", "et" }, { "LV", "lv", "lv" }, { "LT", "lt", "lt" },',
        '+        { "IS", "is", "is-latin1" }, { "VN", "vn", "us" },',
        "+        // Non-Latin scripts. The xkb LAYOUT is the region's; the console KEYMAP is",
        '+        // the region\'s ONLY where the kbd package ships one (il/ua/by/bg/rs/mk/gr/',
        '+        // ge/jp), else "us" -- an absent keymap would make loadkeys fail and a raw VT',
        "+        // cannot render most of these scripts without a graphical IME anyway.",
        '+        { "IL", "il", "il" },',
        '+        { "RU", "ru", "ruwin_alt_sh-UTF-8" }, { "UA", "ua", "ua-utf" },',
        '+        { "BY", "by", "by" }, { "BG", "bg", "bg_bds-utf8" },',
        '+        { "RS", "rs", "sr-cy" }, { "MK", "mk", "mk-utf" },',
        '+        { "GR", "gr", "gr" }, { "GE", "ge", "ge" }, { "AM", "am", "us" },',
        '+        { "IR", "ir", "us" }, { "PK", "pk", "us" }, { "IN", "in", "us" },',
        '+        { "TH", "th", "us" }, { "KH", "kh", "us" }, { "LA", "la", "us" },',
        '+        { "MM", "mm", "us" }, { "LK", "lk", "us" },',
        '+        { "JP", "jp", "jp106" }, { "KR", "kr", "us" },',
        '+        { "CN", "cn", "us" }, { "TW", "tw", "us" }, { "MN", "mn", "us" },',
        "+        // Arabic-script (generic Arabic keyboard for all Arab states). kbd ships no",
        '+        // Arabic console keymap, so the raw-TTY keymap is "us" (X11 "ara" unaffected).',
        '+        { "SA", "ara", "us" }, { "AE", "ara", "us" }, { "EG", "ara", "us" },',
        '+        { "IQ", "ara", "us" }, { "JO", "ara", "us" }, { "KW", "ara", "us" },',
        '+        { "LB", "ara", "us" }, { "LY", "ara", "us" }, { "OM", "ara", "us" },',
        '+        { "QA", "ara", "us" }, { "SY", "ara", "us" }, { "YE", "ara", "us" },',
        '+        { "BH", "ara", "us" }, { "DZ", "ara", "us" }, { "MA", "ara", "us" },',
        '+        { "TN", "ara", "us" }, { "SD", "ara", "us" },',
        "+    };",
        "+    // clang-format on",
        "+    for ( const auto& e : table )",
        "+    {",
        "+        if ( cc.compare( QString::fromLatin1( e.country ), Qt::CaseInsensitive ) == 0 )",
        "+        {",
        "+            vconsoleKeymap = QString::fromLatin1( e.keymap );",
        "+            return QString::fromLatin1( e.layout );",
        "+        }",
        "+    }",
        "+    vconsoleKeymap.clear();",
        "+    return QString();",
        "+}",
        "+",
        "+void",
        "+Config::guessRegionKeyboardLayout()",
        "+{",
        "+    // MUST be called from guessLocaleKeyboardLayout() while m_state == Guessing so",
        "+    // the setCurrentIndex() calls below (which fire selectionChange()) do not flip",
        '+    // the state machine to UserSelected. On entry English ("us") is the active,',
        "+    // preferred/primary layout; a non-English region adds its native layout as a",
        "+    // switchable SECOND (Alt+Shift), matching the layout order applyXkb() and",
        '+    // SetKeyboardLayoutJob emit: { additionalLayout="us", primary=<region> } ->',
        '+    // "us,<region>" (English first/active). English-speaking regions get English',
        '+    // only. GlobalStorage "locationCountry" is written by the patched locale module.',
        "+    Calamares::GlobalStorage* gs = Calamares::JobQueue::instance()->globalStorage();",
        '+    const QString country = gs->value( QStringLiteral( "locationCountry" ) ).toString().trimmed().toUpper();',
        '+    cDebug() << "Az\'arch region keyboard: locationCountry" << country;',
        "+",
        "+    QString regionKeymap;",
        "+    const QString regionLayout = country.isEmpty() ? QString() : regionLayoutForCountry( country, regionKeymap );",
        "+    m_regionLayout = regionLayout;",
        "+    m_regionVConsoleKeymap = regionKeymap;",
        "+",
        "+    if ( regionLayout.isEmpty() )",
        "+    {",
        '+        // English-speaking (or unknown) region: English only. Select "us" as the',
        "+        // sole layout and clear any additional layout a previous region left set.",
        '+        const QPersistentModelIndex us = findLayout( m_keyboardLayoutsModel, QStringLiteral( "us" ) );',
        "+        if ( us.isValid() )",
        "+        {",
        "+            m_keyboardLayoutsModel->setCurrentIndex( us.row() );",
        "+        }",
        "+        m_additionalLayoutInfo = AdditionalLayoutInfo();",
        '+        cDebug() << Logger::SubEntry << "English-speaking region -> English-only keyboard";',
        "+    }",
        "+    else",
        "+    {",
        "+        // Non-English region: the region layout becomes the primary (selected), and",
        '+        // "us" is force-added as the additional layout so English stays first/active',
        '+        // in the emitted "us,<region>" and the ASCII layout is always present -- even',
        "+        // for Latin-script regions (es/latam/fr/...) that getAdditionalLayoutInfo()",
        "+        // does not cover. Alt+Shift is the group switcher (also the page default).",
        "+        const QPersistentModelIndex regionItem = findLayout( m_keyboardLayoutsModel, regionLayout );",
        "+        if ( regionItem.isValid() )",
        "+        {",
        "+            m_keyboardLayoutsModel->setCurrentIndex( regionItem.row() );",
        "+        }",
        "+        else",
        "+        {",
        '+            cWarning() << "Az\'arch region keyboard: layout" << regionLayout << "not in model; keeping us";',
        "+            m_additionalLayoutInfo = AdditionalLayoutInfo();",
        "+            m_regionLayout.clear();",
        "+            m_regionVConsoleKeymap.clear();",
        "+            apply();",
        "+            return;",
        "+        }",
        "+        AdditionalLayoutInfo extra;",
        '+        extra.additionalLayout = QStringLiteral( "us" );',
        "+        extra.additionalVariant = QString();",
        '+        extra.groupSwitcher = QStringLiteral( "grp:alt_shift_toggle" );',
        "+        extra.vconsoleKeymap = regionKeymap;",
        "+        m_additionalLayoutInfo = extra;",
        '+        cDebug() << Logger::SubEntry << "region layout" << regionLayout << "+ additional us (Alt+Shift)";',
        "+    }",
        "+",
        "+    // Push the guessed selection to the live session (and, at page-leave, to GS via",
        "+    // finalize()). The apply timer is armed only by the variants-model change, which",
        "+    // may not fire here, so apply() is called directly. apply() is patched to keep",
        "+    // m_additionalLayoutInfo (above) instead of re-deriving it from the primary.",
        "+    apply();",
        "+}",
        "+",
        " void",
        " Config::finalize()",
        " {",
        "@@ -899,6 +1072,9 @@",
        '     m_configureGnome = getBool( configureItems, "gnome", false );',
        " ",
        '     m_guessLayout = getBool( configurationMap, "guessLayout", true );',
        "+    // Az'arch: opt-in region-driven second layout (English + region language,",
        "+    // Alt+Shift). Default false so upstream / other distros are unaffected.",
        '+    m_regionSecondLayout = getBool( configurationMap, "regionSecondLayout", false );',
        " }",
        " ",
        " void",
        "--- a/src/modules/locale/Config.cpp",
        "+++ b/src/modules/locale/Config.cpp",
        "@@ -151,6 +151,12 @@",
        " {",
        '     const QString regionKey = QStringLiteral( "locationRegion" );',
        '     const QString zoneKey = QStringLiteral( "locationZone" );',
        "+    // Az'arch: also publish the ISO-3166 country code of the selected zone. Neither",
        "+    // the region (America/Asia/...) nor the zone (El_Salvador/Riyadh/...) is a",
        "+    // country code, and nothing else in GlobalStorage carries one -- but the patched",
        "+    // keyboard module needs it to pick the region's native keyboard layout. This is",
        '+    // the only clean country signal (TimeZoneData::country(), e.g. "SV", "IL").',
        '+    const QString countryKey = QStringLiteral( "locationCountry" );',
        " ",
        "     if ( !location )",
        "     {",
        "@@ -158,6 +164,7 @@",
        "         {",
        "             gs->remove( regionKey );",
        "             gs->remove( zoneKey );",
        "+            gs->remove( countryKey );",
        "             return true;",
        "         }",
        "         return false;",
        "@@ -169,6 +176,7 @@",
        " ",
        "     gs->insert( regionKey, location->region() );",
        "     gs->insert( zoneKey, location->zone() );",
        "+    gs->insert( countryKey, location->country() );",
        " ",
        "     return locationChanged;",
        " }",
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
  '{CALAMARES_REGION_KEYBOARD_PATCH_NAME}'
)
# Tarball: pinned sha256 (makepkg aborts on mismatch). Patches: shipped in-repo,
# reviewed in azarch.configuration.pkgbuild (SKIP -- local files, not downloaded).
sha256sums=('{CALAMARES_SHA256}' 'SKIP' 'SKIP')

prepare() {{
  cd "calamares-${{pkgver}}"
  # Az'arch installer UI defaults that Calamares only exposes in C++ (Alt+Shift
  # keyboard switch default + fixed non-reactive hostname). -p1 from the source
  # root; the pinned tarball guarantees the context matches, so a failure here
  # (e.g. after a version bump) aborts the build loudly instead of silently
  # dropping the customization.
  patch -p1 < "$srcdir/{CALAMARES_DEFAULTS_PATCH_NAME}"
  # Az'arch region-driven keyboard: when a region is picked on the Location page,
  # add the region's native layout as a switchable second (English stays first,
  # Alt+Shift), live in the installer and persisted to the target. Touches the
  # keyboard + locale modules (disjoint from the defaults patch above, so order is
  # not load-bearing). Same fail-loud-on-drift contract.
  patch -p1 < "$srcdir/{CALAMARES_REGION_KEYBOARD_PATCH_NAME}"
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
        CALAMARES_REGION_KEYBOARD_PATCH_NAME: calamares_region_keyboard_patch(),
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
