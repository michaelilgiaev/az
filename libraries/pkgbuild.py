"""Az'arch OWN package recipes, authored as configuration-as-Python.

Everything the ISO installs that is NOT in the official Arch repositories is
built from recipes WE write and maintain here -- never from the AUR or any
community source. Like the rest of azarch.config, each artifact (the PKGBUILDs
and their companion files) is held as a Python string and emitted into the build
tree by compiler.py; the emitted files are then consumed by `makepkg`, the official
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

# Thunar: pinned to the SAME version Arch's extra/ ships (so it is a drop-in replacement of the
# stock binary, no feature/behaviour drift) -- the only change is the Az'arch symlink-resolve
# patch below. sha256 of the official XFCE release tarball (archive.xfce.org), download + hash.
THUNAR_VERSION = "4.20.9"
THUNAR_SHA256 = "eb09869ce93b12ed285678967f55f243c833f2baf2fb10c9844ac7648d9270cb"
THUNAR_RESOLVE_SYMLINK_PATCH_NAME = "azarch-thunar-resolve-symlink.patch"


# ---------------------------------------------------------------------------
# calamares -- source patch: Az'arch installer UI defaults + Users-page refactor
# ---------------------------------------------------------------------------
# A batch of installer UI decisions are made in Calamares' C++ (the module *.conf
# schemas expose no key for them), so they can only be changed by patching the source
# before the build. This single patch, applied in the recipe's prepare(), carries all
# of them (all VERIFIED against the pinned calamares-3.4.2 tarball):
#
#   1. Keyboard page -- "Switch Keyboard" (the xkb group-switcher dropdown).
#      Upstream builds the dropdown from a QMap sorted by human-readable label and
#      leaves the current index at 0 (the alphabetically-first combo), so "Alt+Shift"
#      is present but NOT pre-selected. The patch makes KeyboardGroupsSwitchersModel's
#      constructor select the entry whose xkb id is `alt_shift_toggle` once the list
#      is built, so the dropdown defaults to "Alt+Shift". (KeyboardLayoutModel.cpp)
#
#   2. Users page -- "What is the name of this computer?" (hostname).
#      Upstream seeds the hostname field ONLY once the user types a name, expanding
#      the `hostname.template` ("${first}-${product}" by default) on every keystroke
#      so the hostname keeps changing as the Full Name / Login fields change. The
#      patch seeds the template's expansion as the INITIAL hostname at module load
#      and (via setHostName, which marks the value "custom") takes the field off the
#      auto-derive path -- so with modules/users.conf `template: "azarch"` the field
#      shows "azarch" by default and stays "azarch" regardless of the other inputs.
#      (Config.cpp, the @@ -1020 hunk.)
#
#   3a. Users page -- RENAME the four field-prompt labels in page_usersetup.ui to short
#      "Field:" captions (the QLabel objectNames are username_label_2, hostnameLabel,
#      password_label_2 and labelChooseRootPassword), and change the HOSTNAME field's
#      placeholder from "Computer Name" to "azarch" (the seeded default, so clearing the
#      field shows "azarch" greyed) and the LOGIN field's placeholder from "login" to
#      "main" (the login VALUE stays empty by design; only its greyed hint changes).
#        "What name do you want to use to log in?"          -> "Username:"
#        "What is the name of this computer?"               -> "Hostname:"
#        "Choose a password to keep your account safe."     -> "Username Password:"
#        "Choose a password for the administrator account." -> "Root Password:"
#      The "Use the same password for the administrator account." checkbox label is
#      RE-WORDED to "Use username password for root password." (page_usersetup.ui.)
#
#   3b. Users page -- REMOVE the "What is your name?" (Full Name) row. The account's
#      GECOS/full name is not asked for. UsersPage.cpp hides the label + the field's
#      widgets (the QHBoxLayout is not a widget, so each child is hidden individually),
#      AND Config::isReady() drops its `!fullName().isEmpty()` gate -- because isReady()
#      hard-requires a non-empty full name, hiding the field WITHOUT relaxing isReady()
#      would leave fullName empty forever and Next permanently greyed. The login is NOT
#      seeded (it starts empty; its own required-field error, edit 4, gates Next until a
#      name is typed). (UsersPage.cpp @@ -105 hunk + Config.cpp @@ -765 hunk.)
#
#   4. Users page -- an empty LOGIN or HOSTNAME is a required-field error. Upstream's
#      loginNameStatus()/hostnameStatus() treat an empty value as "ok" (they return an
#      empty status), so Next would be reachable with a blank name. The patch makes the
#      empty branch return a message instead -- "User parameter must include at least
#      one character." / "Hostname parameter must include at least two characters." --
#      which both shows the field error AND (via isReady()'s
#      loginNameStatus().isEmpty()/hostnameStatus().isEmpty() gates) disables Next until
#      filled. The login is NOT seeded (starts empty); the hostname is seeded to "azarch"
#      by edit 2, so its error only appears if the user clears the field. (Config.cpp
#      @@ -236 / @@ -301 hunks.)
#
#   5. Users page -- REMOVE the "Require strong passwords." checkbox (UsersPage.cpp
#      force-hides it: setVisible(false) regardless of the config value). Password-
#      strength enforcement is not offered (no libpwquality checks in users.conf).
#      (UsersPage.cpp.)
#
#   6. SetPasswordJob -- a SKIPPED (empty) password locks the account. Upstream locks
#      only root on an empty password (usermod -p '!'); the installer lets the user
#      skip the password field, and a skipped password must become a locked "*" account
#      (not crypt("") -- an empty but usable password). The patch broadens the
#      empty-password special case from root-only to ANY user. (SetPasswordJob.cpp.)
#
# The hunks are small and target stable code paths; the pinned tarball guarantees the
# context lines below match. A context drift on a version bump makes `patch` fail
# LOUDLY in prepare() (the build aborts) rather than silently dropping the
# customization -- refresh the hunks (regenerate via `diff -u`) when bumping the
# version. (See modules/users.conf in packages/calamares/calamares.py for the .conf
# side: doReusePassword:true checks the reuse-for-root box by default,
# allowWeakPasswords:false + no passwordRequirements so an empty password is accepted.)
CALAMARES_DEFAULTS_PATCH_NAME = "azarch-calamares-defaults.patch"


def calamares_defaults_patch() -> str:
    r"""Unified diff (-p1) applied to the extracted calamares-3.4.2 source in the
    recipe's prepare(): default the keyboard group-switcher to Alt+Shift, seed a fixed
    non-reactive hostname (the login is LEFT empty by default), hide the strong-
    password checkbox, RENAME the four Users-page field labels (login prompt ->
    "Username:", hostname prompt -> "Hostname:", user-password prompt -> "Username
    Password:", root-password prompt -> "Root Password:"), make an empty login /
    hostname report a required-field error, and lock a skipped (empty) password. See
    the block comment above for the per-edit rationale and why these live in a source
    patch rather than a module .conf. Paths are a/ b/ prefixed so `patch -p1` (run
    from the source root) applies them.

    The Full Name ("What is your name?") row is HIDDEN and Config::isReady() is relaxed
    (dropping its non-empty-full-name gate) so hiding the field does not permanently
    disable Next. The login VALUE is NOT seeded -- it starts empty (placeholder hint
    "main") and its own required-field error gates Next until a username is typed. The
    "Use the same password for the administrator account." checkbox label is re-worded
    to "Use username password for root password.".

    The diff is built line-by-line rather than as one big triple-quoted literal
    ON PURPOSE: a unified diff's CONTEXT lines (unchanged surrounding source) must
    each begin with a single leading SPACE, and blank context lines are therefore a
    line that is exactly one space. A triple-quoted literal makes those
    space-only lines invisible and trivially corrupted by an editor that strips
    trailing whitespace -- which silently breaks `patch`. Assembling from a list
    keeps every context line's leading space explicit and greppable. The hunk
    headers (@@ -284,4 / @@ -123,3 (x2) / @@ -222,3 / @@ -324,3 / @@ -494,3 /
    @@ -156,1 / @@ -236,5 (x2) / @@ -1020,7 / @@ -81,12 ...) were generated by
    `diff -u` against the pinned 3.4.2 source (edit a pristine extraction, then diff)
    and verified to apply with `patch -p1`; regenerate them the same way on a version
    bump."""
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
        # --- page_usersetup.ui: RENAME the four field-prompt labels ----------
        # Each hunk keeps 1 line of context above/below the changed <string> so
        # the anchors are unambiguous. The reuse-password checkbox and the Full
        # Name label are deliberately NOT touched (left at pristine wording).
        "--- a/src/modules/users/page_usersetup.ui",
        "+++ b/src/modules/users/page_usersetup.ui",
        # login prompt "What name do you want to use to log in?" -> "Username:"
        "@@ -123,3 +123,3 @@",
        '      <property name="text">',
        "-      <string>What name do you want to use to log in?</string>",
        "+      <string>Username:</string>",
        "      </property>",
        # login field placeholder "login" -> "main": per PROMPT.md the Username field
        # defaults EMPTY (never seeded), but its greyed placeholder must HINT "main" --
        # the default account name used elsewhere in the installer. The field VALUE stays
        # empty (so loginNameStatus() shows the required-field error until typed); only
        # the placeholder text changes. This textBox is nested one level deeper than the
        # prompt labels (7-space indent). Ascending order: line 147, after 123, before 222.
        "@@ -147,3 +147,3 @@",
        '        <property name="placeholderText">',
        "-        <string>login</string>",
        "+        <string>main</string>",
        "        </property>",
        # hostname prompt "What is the name of this computer?" -> "Hostname:"
        "@@ -222,3 +222,3 @@",
        '      <property name="text">',
        "-      <string>What is the name of this computer?</string>",
        "+      <string>Hostname:</string>",
        "      </property>",
        # hostname field placeholder "Computer Name" -> "azarch": the field is seeded
        # to "azarch", but if the user CLEARS it the greyed placeholder shows "azarch"
        # (the default that will be used) instead of the generic "Computer Name". This
        # textBox is nested one level deeper than the prompt labels (8/9-space indent).
        # MUST stay in ascending file-line order (line 249, after 222, before 324).
        # Indent: all four lines are 8-space indented (verified via `diff -u`).
        "@@ -249,3 +249,3 @@",
        '        <property name="placeholderText">',
        "-        <string>Computer Name</string>",
        "+        <string>azarch</string>",
        "        </property>",
        # user-password prompt "Choose a password ... safe." -> "Username Password:"
        "@@ -324,3 +324,3 @@",
        '      <property name="text">',
        "-      <string>Choose a password to keep your account safe.</string>",
        "+      <string>Username Password:</string>",
        "      </property>",
        # reuse-password checkbox "Use the same password for the administrator account."
        # -> "Use username password for root password." per PROMPT.md Prompt#1. This is the
        # checkbox that (with doReusePassword:true) is checked by default, making root reuse
        # the user's password. Ascending order: line 471, after 324, before 494.
        "@@ -471,3 +471,3 @@",
        '      <property name="text">',
        "-      <string>Use the same password for the administrator account.</string>",
        "+      <string>Use username password for root password.</string>",
        "      </property>",
        # root-password prompt "Choose a password ... administrator account." -> "Root Password:"
        "@@ -494,3 +494,3 @@",
        '      <property name="text">',
        "-      <string>Choose a password for the administrator account.</string>",
        "+      <string>Root Password:</string>",
        "      </property>",
        # --- UsersPage.cpp: hide the Full Name row + the strong-password checkbox
        # The "What is your name?" (Full Name) row is REMOVED (hidden): the account's
        # GECOS/full name is not asked for. Each child widget of the QHBoxLayout is
        # hidden individually (the layout itself is not a widget). Config::isReady()
        # is relaxed below so a permanently-empty full name does not disable Next.
        # The "Require strong passwords." checkbox is likewise force-hidden.
        "--- a/src/modules/users/UsersPage.cpp",
        "+++ b/src/modules/users/UsersPage.cpp",
        "@@ -105,6 +105,17 @@",
        "     connect( ui->textBoxFullName, &QLineEdit::textEdited, config, &Config::setFullName );",
        "     connect( config, &Config::fullNameChanged, this, &UsersPage::onFullNameTextEdited );",
        " ",
        '+    // Az\'arch: hide the "What is your name?" (Full Name) row entirely. The account\'s',
        "+    // GECOS/full name is not asked for; Config::isReady() no longer requires a",
        "+    // non-empty full name (see Config.cpp), so Next stays reachable with these widgets",
        "+    // gone. The QHBoxLayout that holds the field is not a widget, so each child widget",
        "+    // is hidden individually. The login VALUE is deliberately NOT seeded: the Username",
        "+    // field defaults EMPTY and shows the \"main\" placeholder hint.",
        "+    ui->labelWhatIsYourName->setVisible( false );",
        "+    ui->textBoxFullName->setVisible( false );",
        "+    ui->labelFullName->setVisible( false );",
        "+    ui->labelFullNameError->setVisible( false );",
        "+",
        "     // If the hostname is going to be written out, then show the field",
        "     if ( ( m_config->hostnameAction() == HostNameAction::EtcHostname )",
        "          || ( m_config->hostnameAction() == HostNameAction::SystemdHostname ) )",
        "@@ -156,1 +166,5 @@",
        "-    ui->checkBoxRequireStrongPassword->setVisible( m_config->permitWeakPasswords() );",
        '+    // Az\'arch: never show the "Require strong passwords." checkbox. Password-strength',
        "+    // enforcement is not offered on this installer (no libpwquality checks are",
        "+    // configured in users.conf, so any password -- including an empty one -- is",
        "+    // accepted). Force the checkbox hidden regardless of the config value.",
        "+    ui->checkBoxRequireStrongPassword->setVisible( false );",
        # --- Config.cpp: required-field errors + fixed hostname seed ---------
        # isReady() is LEFT pristine (still gates on a non-empty full name AND a
        # non-empty login), so there is NO isReady() hunk. Two status functions
        # get a required-field message on empty; the hostname is still seeded to
        # the template default. The login is NOT seeded (starts empty by design).
        "--- a/src/modules/users/Config.cpp",
        "+++ b/src/modules/users/Config.cpp",
        # loginNameStatus(): empty login -> required-field error (was "ok" / "")
        # 1 leading + 1 trailing context line; old=6 (1+4+1), new=9 (1+7+1).
        "@@ -236,6 +236,9 @@",
        '     // An empty login is "ok", even if it isn\'t really',
        "-    if ( m_loginName.isEmpty() )",
        "-    {",
        "-        return QString();",
        "-    }",
        "+    // Az'arch: an empty login is NOT ok -- a username is required. Returning a",
        "+    // non-empty status both surfaces this as the field error and (via isReady()'s",
        "+    // loginNameStatus().isEmpty() gate) keeps Next disabled until a name is typed.",
        "+    if ( m_loginName.isEmpty() )",
        "+    {",
        '+        return tr( "User parameter must include at least one character." );',
        "+    }",
        " ",
        # hostnameStatus(): empty hostname -> required-field error (was "ok" / "")
        # 1 leading + 1 trailing context line; old=6 (1+4+1), new=10 (1+8+1).
        "@@ -301,6 +304,10 @@",
        '     // An empty hostname is "ok", even if it isn\'t really',
        "-    if ( m_hostname.isEmpty() )",
        "-    {",
        "-        return QString();",
        "-    }",
        "+    // Az'arch: an empty hostname is NOT ok -- a hostname is required. The default",
        '+    // template seeds "azarch", but if the user clears the field this shows the error',
        "+    // and (via isReady()'s hostnameStatus().isEmpty() gate) blocks Next. Two-char",
        "+    // minimum mirrors HOSTNAME_MIN_LENGTH.",
        "+    if ( m_hostname.isEmpty() )",
        "+    {",
        '+        return tr( "Hostname parameter must include at least two characters." );',
        "+    }",
        " ",
        # isReady(): drop the readyFullName gate. The Full Name row is hidden
        # (UsersPage.cpp), so fullName() is always empty by design -- gating on it
        # would leave Next permanently disabled. Login/hostname/password still gate.
        # old=6 (3 ctx + del + 2 ctx + del); new=5 (3 ctx + 2 ctx) -- net -2 lines... wait:
        # explicit: old has 1 ctx('{'), the readyFullName del line, then readyHostname/
        # readyUsername/readyUserPassword/readyRootPassword ctx, then the return del +
        # return add. Counted directly below.
        "@@ -765,8 +775,7 @@",
        " {",
        "-    bool readyFullName = !fullName().isEmpty();  // Needs some text",
        "     bool readyHostname = hostnameStatus().isEmpty();  // .. no warning message",
        "     bool readyUsername = !loginName().isEmpty() && loginNameStatus().isEmpty();  // .. no warning message",
        "     bool readyUserPassword = userPasswordValidity() != Config::PasswordValidity::Invalid;",
        "     bool readyRootPassword = rootPasswordValidity() != Config::PasswordValidity::Invalid;",
        "-    return readyFullName && readyHostname && readyUsername && readyUserPassword && readyRootPassword;",
        "+    return readyHostname && readyUsername && readyUserPassword && readyRootPassword;",
        " }",
        # Seed the fixed hostname from the template (login NOT seeded).
        # old=6 (3 ctx + } + blank + setConfig ctx); new=19 (6 ctx + 13 added).
        "@@ -1020,6 +1027,19 @@",
        '         m_forbiddenHostNames = Calamares::getStringList( hostnameSettings, "forbidden_names" );',
        "         m_forbiddenHostNames << alwaysForbiddenHostNames();",
        "         tidy( m_forbiddenHostNames );",
        "+",
        "+        // Az'arch: seed a fixed default hostname and take it off the auto-derive",
        "+        // path. Upstream leaves the hostname empty until the user types a name, then",
        "+        // re-expands m_hostnameTemplate on every keystroke -- so the hostname keeps",
        "+        // changing as the Login field changes. Expanding the template once here (with",
        '+        // no user data) gives the initial value, and setHostName() marks it "custom"',
        "+        // (m_customHostName = true) so nothing later recomputes it. With a literal",
        '+        // template ("azarch") the field shows "azarch" by default and stays "azarch".',
        "+        const QString seededHostname = makeHostnameSuggestion( m_hostnameTemplate, QStringList(), QString() );",
        "+        if ( !seededHostname.isEmpty() )",
        "+        {",
        "+            setHostName( seededHostname );",
        "+        }",
        "     }",
        " ",
        "     setConfigurationDefaultGroups( configurationMap, m_defaultGroups );",
        "--- a/src/modules/users/SetPasswordJob.cpp",
        "+++ b/src/modules/users/SetPasswordJob.cpp",
        "@@ -81,12 +81,17 @@",
        '                                             tr( "rootMountPoint is %1" ).arg( destDir.absolutePath() ) );',
        "     }",
        " ",
        '-    if ( m_userName == "root" && m_newPassword.isEmpty() )  //special case for disabling root account',
        '+    // Az\'arch: an empty password locks the account (shadow "!") for ANY user, not just',
        "+    // root. The installer lets the user skip the password field; a skipped password must",
        '+    // yield a locked account (no usable password) rather than crypt("") -- an empty but',
        "+    // *valid* password that would allow passwordless login. Upstream only special-cased",
        '+    // "root" here; broadening it to every user gives the "skip -> * (locked)" behaviour.',
        '+    if ( m_newPassword.isEmpty() )  //special case for disabling the account (no usable password)',
        "     {",
        '         int ec = Calamares::System::instance()->targetEnvCall( { "usermod", "-p", "!", m_userName } );',
        "         if ( ec )",
        "         {",
        '-            return Calamares::JobResult::error( tr( "Cannot disable root account." ),',
        '+            return Calamares::JobResult::error( tr( "Cannot disable account %1." ).arg( m_userName ),',
        '                                                 tr( "usermod terminated with error code %1." ).arg( ec ) );',
        "         }",
        "         return Calamares::JobResult::ok();",
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
        "@@ -37,6 +37,12 @@",
        "     void detectCurrentKeyboardLayout();",
        "     /// @brief Based on current locale, pick a layout",
        "     void guessLocaleKeyboardLayout();",
        "+    /// @brief Az'arch: derive an English+region two-layout config from the",
        '+    /// region picked on the Location page (GlobalStorage "locationCountry").',
        "+    /// @param userHadSelected true if the user had already hand-picked a layout on",
        "+    /// the keyboard page (m_state was UserSelected on entry); used to preserve that",
        "+    /// choice on a same-region revisit instead of re-selecting the region layout.",
        "+    void guessRegionKeyboardLayout( bool userHadSelected );",
        " ",
        "     Calamares::JobList createJobs();",
        "     QString prettyStatus() const;",
        "@@ -124,6 +127,28 @@",
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
        "+    // The ISO-3166 country guessRegionKeyboardLayout() last derived a layout for.",
        "+    // Used to tell a REGION CHANGE (country differs -> re-derive) from a pure",
        "+    // Keyboard-page revisit (same country -> preserve a hand-picked layout instead",
        "+    // of re-selecting the region layout, so revisiting does not clobber the user's",
        "+    // explicit choice). Empty until the first region guess.",
        "+    QString m_regionGuessedCountry;",
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
        # --- gate: let the region path re-run on EVERY Keyboard activation --------
        # The stock gate early-returns unless m_state==Initial, which after the first
        # visit (state becomes UserSelected) blocks the region guess -- so changing the
        # region on the Location page and returning never re-derives the keyboard (the
        # bug: installer keyboard does not follow the region). Add `&& !m_regionSecondLayout`
        # so the region path is NOT gated by m_state (it runs on every activate); the
        # stock locale path keeps the Initial-only behaviour. The `cScopedAssignment
        # returnToIntial(&m_state, State::Initial)` on the next line then restores state
        # to Initial each time, keeping re-guessing enabled and making the programmatic
        # selection in guessRegionKeyboardLayout() a no-op for the state machine.
        "@@ -750,8 +750,12 @@",
        " Config::guessLocaleKeyboardLayout()",
        " {",
        "-    if ( m_state != State::Initial || !m_guessLayout )",
        "+    // Az'arch: capture whether the user had already hand-picked a layout (state",
        "+    // UserSelected) BEFORE the scoped assignment below resets it -- the region",
        "+    // guess uses it to preserve that choice on a same-region revisit.",
        "+    const bool azUserHadSelected = ( m_state == State::UserSelected );",
        "+    if ( ( m_state != State::Initial && !m_regionSecondLayout ) || !m_guessLayout )",
        "     {",
        "         return;",
        "     }",
        "     cScopedAssignment returnToIntial( &m_state, State::Initial );",
        "     m_state = State::Guessing;",
        "@@ -832,12 +853,245 @@",
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
        "+        guessRegionKeyboardLayout( azUserHadSelected );",
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
        "+// Az'arch: fallback country when GlobalStorage \"locationCountry\" is not yet",
        "+// populated on the first Keyboard activation. Derive it from the zone the locale",
        '+// module DID publish ("locationZone", e.g. "Jerusalem"/"El_Salvador"/"Riyadh").',
        '+// The default Asia/Jerusalem MUST map to "IL" so the out-of-the-box installer',
        "+// still shows us,il rather than English-only; an unknown zone -> empty (English",
        "+// only), the correct conservative default.",
        "+static QString",
        "+countryForZone( const QString& zone )",
        "+{",
        "+    struct ZoneEntry { const char* zone; const char* country; };",
        "+    // clang-format off",
        "+    static const ZoneEntry table[] = {",
        '+        { "Jerusalem", "IL" }, { "Tel_Aviv", "IL" },',
        '+        { "El_Salvador", "SV" }, { "Mexico_City", "MX" }, { "Buenos_Aires", "AR" },',
        '+        { "Bogota", "CO" }, { "Santiago", "CL" }, { "Lima", "PE" }, { "Caracas", "VE" },',
        '+        { "Guayaquil", "EC" }, { "Guatemala", "GT" }, { "La_Paz", "BO" },',
        '+        { "Costa_Rica", "CR" }, { "Asuncion", "PY" }, { "Panama", "PA" },',
        '+        { "Montevideo", "UY" }, { "Tegucigalpa", "HN" }, { "Managua", "NI" },',
        '+        { "Santo_Domingo", "DO" }, { "Havana", "CU" }, { "Madrid", "ES" },',
        '+        { "Paris", "FR" }, { "Berlin", "DE" }, { "Vienna", "AT" }, { "Zurich", "CH" },',
        '+        { "Rome", "IT" }, { "Lisbon", "PT" }, { "Sao_Paulo", "BR" },',
        '+        { "Amsterdam", "NL" }, { "Warsaw", "PL" }, { "Stockholm", "SE" },',
        '+        { "Oslo", "NO" }, { "Copenhagen", "DK" }, { "Helsinki", "FI" },',
        '+        { "Prague", "CZ" }, { "Budapest", "HU" }, { "Istanbul", "TR" },',
        '+        { "Bucharest", "RO" }, { "Zagreb", "HR" }, { "Bratislava", "SK" },',
        '+        { "Ljubljana", "SI" }, { "Tallinn", "EE" }, { "Riga", "LV" },',
        '+        { "Vilnius", "LT" }, { "Reykjavik", "IS" }, { "Ho_Chi_Minh", "VN" },',
        '+        { "Moscow", "RU" }, { "Kiev", "UA" }, { "Kyiv", "UA" }, { "Minsk", "BY" },',
        '+        { "Sofia", "BG" }, { "Belgrade", "RS" }, { "Skopje", "MK" },',
        '+        { "Athens", "GR" }, { "Tbilisi", "GE" }, { "Yerevan", "AM" },',
        '+        { "Tehran", "IR" }, { "Karachi", "PK" }, { "Kolkata", "IN" },',
        '+        { "Bangkok", "TH" }, { "Phnom_Penh", "KH" }, { "Vientiane", "LA" },',
        '+        { "Yangon", "MM" }, { "Colombo", "LK" }, { "Tokyo", "JP" },',
        '+        { "Seoul", "KR" }, { "Shanghai", "CN" }, { "Taipei", "TW" },',
        '+        { "Ulaanbaatar", "MN" }, { "Riyadh", "SA" }, { "Dubai", "AE" },',
        '+        { "Cairo", "EG" }, { "Baghdad", "IQ" }, { "Amman", "JO" },',
        '+        { "Kuwait", "KW" }, { "Beirut", "LB" }, { "Tripoli", "LY" },',
        '+        { "Muscat", "OM" }, { "Qatar", "QA" }, { "Damascus", "SY" },',
        '+        { "Aden", "YE" }, { "Bahrain", "BH" }, { "Algiers", "DZ" },',
        '+        { "Casablanca", "MA" }, { "Tunis", "TN" }, { "Khartoum", "SD" },',
        "+    };",
        "+    // clang-format on",
        "+    for ( const auto& e : table )",
        "+    {",
        "+        if ( zone.compare( QString::fromLatin1( e.zone ), Qt::CaseInsensitive ) == 0 )",
        "+        {",
        "+            return QString::fromLatin1( e.country );",
        "+        }",
        "+    }",
        "+    return QString();",
        "+}",
        "+",
        "+void",
        "+Config::guessRegionKeyboardLayout( bool userHadSelected )",
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
        '+    QString country = gs->value( QStringLiteral( "locationCountry" ) ).toString().trimmed().toUpper();',
        "+    if ( country.isEmpty() )",
        "+    {",
        "+        // Not published yet on the first Keyboard visit (the locale module writes",
        "+        // locationCountry when the location CHANGES / at finalize). Derive it from",
        '+        // the zone it DID publish ("locationZone", e.g. "Jerusalem"/"El_Salvador")',
        "+        // so the default Asia/Jerusalem still resolves to IL (us,il) instead of",
        "+        // English-only. See countryForZone().",
        '+        const QString zone = gs->value( QStringLiteral( "locationZone" ) ).toString().trimmed();',
        "+        country = countryForZone( zone ).toUpper();",
        '+        cDebug() << "Az\'arch region keyboard: locationCountry empty; zone" << zone << "-> country" << country;',
        "+    }",
        '+    cDebug() << "Az\'arch region keyboard: locationCountry" << country;',
        "+",
        "+    // Az'arch: do NOT clobber a hand-picked layout on a same-region revisit. If the",
        "+    // user already selected a layout by hand (userHadSelected) AND the region has not",
        "+    // changed since our last guess (country == m_regionGuessedCountry), preserve their",
        "+    // choice -- the whole point of re-running on every activate is to follow a REGION",
        "+    // CHANGE, not to overwrite an explicit pick. A genuine region change (country",
        "+    // differs) falls through and re-derives. (First visit/no hand-pick: userHadSelected",
        "+    // is false, so this never triggers.)",
        "+    if ( userHadSelected && !m_regionGuessedCountry.isEmpty() && country == m_regionGuessedCountry )",
        "+    {",
        '+        cDebug() << Logger::SubEntry << "region unchanged + user hand-picked -> preserving layout";',
        "+        return;",
        "+    }",
        "+    m_regionGuessedCountry = country;",
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
# calamares -- source patch: hide Back + Next on the Finish page
# ---------------------------------------------------------------------------
# The installer's Back/Next buttons are the MAIN-WINDOW navigation buttons driven by
# libcalamaresui's ViewManager, not anything a module .conf can reach -- so removing
# them from the Finish ("finished") page can only be done in C++. The finished ViewStep
# ALREADY returns false from isBackEnabled()/isNextEnabled(), but that only DISABLES
# (greys) the buttons; they stay visible. To HIDE them, this patch adds one call in
# ViewManager::updateButtonLabels(): inside the existing `isAtVeryEnd()` branch (taken
# only on the last step, which the finished page is -- it returns isAtEnd()==true), call
# updateBackAndNextVisibility(false). That fires backAndNextVisibleChanged(false), wired
# in CalamaresWindow to setVisible(false) on BOTH buttons, so the finished page shows
# neither Back nor Next -- only the "Done" (quit) button, kept visible in that same
# branch. updateButtonLabels() runs LAST in next() (after next()'s own
# updateBackAndNextVisibility() call), so this wins for the finished step; every
# non-final step takes the else branch and keeps its normal button visibility.
#
# Kept in its OWN patch (not folded into azarch-calamares-defaults.patch) so the two
# concerns stay independent -- defaults is the Users/Keyboard UI, this is a libcalamaresui
# navigation tweak. Same fail-loud-on-drift contract: the pinned tarball guarantees the
# context; a version bump that moves these lines makes `patch` abort the build.
CALAMARES_FINISH_BUTTONS_PATCH_NAME = "azarch-calamares-finish-buttons.patch"


def calamares_finish_buttons_patch() -> str:
    r"""Unified diff (-p1) applied to the extracted calamares-3.4.2 source in the
    recipe's prepare(), after the other two calamares patches: hide the Back and Next
    navigation buttons on the Finish page (see the block comment above). Touches only
    src/libcalamaresui/ViewManager.cpp.

    Same authoring rule as the sibling patches: assembled line-by-line so every
    unified-diff CONTEXT line keeps its exact single leading space (blank context lines
    are one space) -- a triple-quoted literal would let an editor strip that trailing
    space and silently break `patch`. The hunk header (@@ -437,6 ...) was generated by
    `diff -u` against the pinned 3.4.2 source and verified to apply with `patch -p1`;
    regenerate it the same way on a version bump."""
    lines = [
        "--- a/src/libcalamaresui/ViewManager.cpp",
        "+++ b/src/libcalamaresui/ViewManager.cpp",
        "@@ -437,6 +437,13 @@",
        "         UPDATE_BUTTON_PROPERTY( quitVisible, true );",
        '         UPDATE_BUTTON_PROPERTY( quitIcon, "dialog-ok-apply" );',
        "         updateCancelEnabled( true );",
        "+        // Az'arch: on the very last step (the Finish page) hide BOTH the Back and Next",
        "+        // buttons -- the install is complete, there is nowhere to go back to and nothing",
        '+        // to advance to; only the "Done" (quit) button, kept visible just above, remains.',
        "+        // This runs after next()'s own updateBackAndNextVisibility() call (updateButtonLabels",
        "+        // is invoked last), so it wins for the finished step. Non-final steps take the else",
        "+        // branch and keep their normal button visibility.",
        "+        updateBackAndNextVisibility( false );",
        "         if ( settings->quitAtEnd() )",
        "         {",
        "             quit();",
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
# Az'arch OWN PKGBUILD -- calamares  (generated by packages.pkgbuild)
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
  '{CALAMARES_FINISH_BUTTONS_PATCH_NAME}'
)
# Tarball: pinned sha256 (makepkg aborts on mismatch). Patches: shipped in-repo,
# reviewed in packages.pkgbuild (SKIP -- local files, not downloaded).
sha256sums=('{CALAMARES_SHA256}' 'SKIP' 'SKIP' 'SKIP')

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
  # Az'arch: hide the Back + Next buttons on the Finish page (libcalamaresui
  # ViewManager). Independent of the two patches above (touches only ViewManager.cpp),
  # so order is not load-bearing. Same fail-loud-on-drift contract.
  patch -p1 < "$srcdir/{CALAMARES_FINISH_BUTTONS_PATCH_NAME}"
}}

build() {{
  cd "calamares-${{pkgver}}"
  # Qt6 + KF6, bundled pybind11 for Python job modules, QML on for the branding
  # slideshow, crash reporter off (extra deps, pointless on a live ISO).
  #
  # PIN Python to the SYSTEM interpreter (/usr/bin/python3) and its matching library.
  # calamares links libpython into libcalamares.so for the Python job modules, so the
  # linked ABI MUST match the python package the ISO ships (the `python` depends), i.e.
  # the running system's /usr/lib/libpython3.X.so. Without pinning, CMake can discover
  # an UNRELATED interpreter that happens to be on the build host (e.g. a uv-managed
  # cpython-3.12 under ~/.local/share/uv, reachable via the ~/.local/bin/python3.12
  # shim on PATH), link against THAT libpython3.12.so.1.0, and produce a calamares that
  # dies on the target with "error while loading shared libraries:
  # libpython3.12.so.1.0: cannot open shared object file" -- because the target only
  # has 3.14.
  #
  # IMPORTANT: calamares-3.4.2's CMakeLists.txt uses the LEGACY module --
  #   find_package(Python ... COMPONENTS Interpreter Development)  (no "3") --
  # and it is the Development component of THAT module which links libpython into
  # libcalamares.so. The legacy FindPython reads the Python_* hint variables; the
  # Python3_* hints only steer the newer FindPython3 (used by bundled pybind11). So we
  # MUST pin BOTH module families or FindPython silently re-discovers the uv 3.12.
  # FIND_STRATEGY=LOCATION + FIND_VIRTUALENV=STANDARD + an absolute _ROOT_DIR/_EXECUTABLE
  # make the ABI track the system python (whatever version Arch currently ships), so the
  # binary is portable to any ISO built from the same python package. Belt-and-suspenders,
  # _makepkg_one also strips ~/.local from PATH so the uv shim can't win the search.
  #
  # DISABLE libpwquality (same portability class as Python above). The users module's
  # CMakeLists does an UNCONDITIONAL find_package(LibPWQuality) with no WITH_ toggle: if
  # the BUILD host happens to have libpwquality (many distros pull it in transitively),
  # the module links libpwquality.so.1 and #defines CHECK_PWQUALITY. The Az'arch ISO does
  # NOT ship libpwquality, so that build produces a users viewmodule that fails to
  # dlopen on the target ("undefined symbol: pwquality_*" / "libpwquality.so.1: cannot
  # open shared object file") and calamares aborts with 'Module "users@users" ... FAILED'.
  # CMAKE_DISABLE_FIND_PACKAGE_LibPWQuality=ON forces that find_package to report
  # not-found, so the module builds WITHOUT the optional strong-password check -- which is
  # exactly what we want anyway (the strong-password checkbox is force-hidden and empty
  # passwords lock the account; there is no path in the Az'arch flow that uses pwquality).
  _pyexe="/usr/bin/python3"
  cmake -B build -S . \\
    -DCMAKE_BUILD_TYPE=Release \\
    -DCMAKE_INSTALL_PREFIX=/usr \\
    -DCMAKE_INSTALL_LIBDIR=lib \\
    -DPython_EXECUTABLE="$_pyexe" \\
    -DPython_ROOT_DIR=/usr \\
    -DPython_FIND_STRATEGY=LOCATION \\
    -DPython_FIND_VIRTUALENV=STANDARD \\
    -DPython3_EXECUTABLE="$_pyexe" \\
    -DPython3_ROOT_DIR=/usr \\
    -DPython3_FIND_STRATEGY=LOCATION \\
    -DPython3_FIND_VIRTUALENV=STANDARD \\
    -DCMAKE_DISABLE_FIND_PACKAGE_LibPWQuality=ON \\
    -DWITH_QT6=ON \\
    -DWITH_PYBIND11=ON \\
    -DWITH_QML=ON \\
    -DBUILD_CRASH_REPORTING=OFF \\
    -DINSTALL_POLKIT=ON \\
    -DWEBVIEW_FORCE_WEBKIT=OFF
  # -j caps parallel compile jobs. cmake's Makefiles/Ninja generator otherwise
  # auto-detects every core and pins the whole machine; AZARCH_JOBS is exported by
  # makepkg._makepkg_one (= cores - reserved), defaulting to 1 if unset.
  cmake --build build -j"${{AZARCH_JOBS:-1}}"
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


# NOTE on the LibreWolf AutoConfig override (librewolf.overrides.cfg): it is NO LONGER
# a package companion file. LibreWolf's compiled AutoConfig loader reads it from the
# user's PROFILE dir (~/.config/librewolf/librewolf/), never from /opt, so shipping it
# in the package did nothing. It is delivered as a HOME file (mirrored into /etc/skel)
# by packages/librewolf.emit_plan(), which owns both its content AND its location. This
# recipe therefore neither generates nor installs it.


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
# Generated by packages.pkgbuild.
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
# default; Az'arch relaxes that (sessions/cookies persist) + hides the bookmarks
# toolbar via LibreWolf's supported AutoConfig override. That override is delivered
# as a HOME file at the profile path LibreWolf actually reads (NOT packaged here --
# see packages/librewolf); this recipe is otherwise stock LibreWolf.
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
)
# Tarball: pinned sha256 (+ GPG). .sig: GPG-checked (SKIP sha). Local .desktop:
# shipped in-repo, reviewed in packages.pkgbuild (SKIP sha). The AutoConfig override
# is NOT packaged (LibreWolf reads it from the profile dir, not /opt) -- it ships as a
# home file via packages/librewolf.emit_plan().
sha256sums=('{LIBREWOLF_SHA256}' 'SKIP' 'SKIP')
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

  # NOTE: the Az'arch persistence/bookmarks override is NOT installed here. LibreWolf's
  # AutoConfig loader reads librewolf.overrides.cfg from the user's PROFILE dir
  # (~/.config/librewolf/librewolf/), never from /opt, so it is delivered as a home file
  # by packages/librewolf.emit_plan() (compiler.py) instead.
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
# Generated by packages.pkgbuild. Selected ONLY by `compile.sh --full-compile`.
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
)
# The AutoConfig override is NOT packaged (LibreWolf reads it from the profile dir, not
# /opt) -- it ships as a home file via packages/librewolf.emit_plan().
sha256sums=('SKIP' 'SKIP')

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
  # -j caps parallel compile jobs so the Firefox build (bsys6 -> mach) does not
  # pin every core for hours. AZARCH_JOBS is exported by makepkg (= cores -
  # reserved); it defaults to 1 if unset so an isolated recipe run stays safe.
  make build -j"${{AZARCH_JOBS:-1}}"
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

  # NOTE: the Az'arch override is NOT installed here -- LibreWolf reads it from the
  # profile dir, not /opt, so packages/librewolf.emit_plan() (compiler.py) delivers it as
  # a home file. See packages/librewolf.
}}
"""


# ---------------------------------------------------------------------------
# thunar -- source patch: show the fully-resolved (symlink-dereferenced) path
# ---------------------------------------------------------------------------
# The user wants Thunar's location bar / window title to ALWAYS show the real
# filesystem path, even when a directory is reached through a symlink (e.g. the
# convenience link ~/Trash -> ~/.local/share/Trash/files created by
# packages/thunar/home_directory): "I WANT FULL ACTUAL PATHS, /home/main/.local/
# share/Trash/files/". The sidebar bookmarks already point at resolved targets
# (packages/thunar/sidebar), so the shortcut route is correct -- but
# navigating the symlink DIRECTLY (double-clicking it in the folder view / typing
# its path) kept the symlink path.
#
# WHY A SOURCE PATCH. Upstream added the `misc-resolve-links` preference that does
# exactly this in Thunar 4.21.6; it is ABSENT from the 4.20.x series Arch ships
# (verified: `strings /usr/bin/thunar` on 4.20.9 has no misc-resolve-links, and the
# 4.20 source prints g_file_get_path() of the as-requested GFile with no
# canonicalisation). There is NO config lever on 4.20, so the only way to get the
# behaviour on the shipped version is to patch it in. We pin the SAME version Arch
# ships (4.20.9) so this is a drop-in binary replacement whose ONLY change is this
# patch. packages/thunar/settings still ships misc-resolve-links=true too, so
# the day Arch moves to >=4.21.6 the upstream pref takes over and this patch (which
# would then fail to apply and abort the build, loudly) is removed.
#
# THE PATCH. thunar_window_set_current_directory() is the single chokepoint every
# directory change flows through. When the requested directory is a symlink, we
# realpath() it and re-enter with a ThunarFile for the canonical target, so the
# path bar, window title and history all show the real path. Guarded to symlinks
# only; no-ops if resolution fails. VERIFIED: the patched 4.20.9 tree builds clean
# (autotools) and the binary links realpath.
def thunar_resolve_symlink_patch() -> str:
    r"""Unified diff (-p1) applied to the extracted thunar-4.20.9 source in the recipe's
    prepare(): make thunar_window_set_current_directory() canonicalise a symlinked directory
    (realpath + re-enter) so the location bar / title show the real path. See the block comment
    above for why this lives in a source patch (4.20 has no misc-resolve-links pref).

    Assembled line-by-line (not one triple-quoted literal) for the SAME reason
    calamares_defaults_patch() is: a unified diff's blank CONTEXT lines are a single leading
    space, which a triple-quoted literal makes invisible and an editor trivially strips --
    silently breaking `patch`. Every context line's leading space is explicit here. The hunk
    headers were generated by `diff -u` against the pinned 4.20.9 tarball and verified to apply
    with `patch -p1` (and the result compiles + links). Regenerate the same way on a version
    bump; a drift makes `patch` fail LOUDLY (build aborts) rather than dropping the fix."""
    lines = [
        "--- a/thunar/thunar-window.c",
        "+++ b/thunar/thunar-window.c",
        "@@ -21,6 +21,8 @@",
        " ",
        " #ifdef HAVE_CONFIG_H",
        ' #include "config.h"',
        "+#include <stdlib.h> /* Az'arch realpath */",
        "+#include <string.h> /* Az'arch strcmp */",
        " #endif",
        " ",
        " #ifdef HAVE_UNISTD_H",
        "@@ -5529,6 +5531,39 @@",
        "   _thunar_return_if_fail (THUNAR_IS_WINDOW (window));",
        "   _thunar_return_if_fail (current_directory == NULL || THUNAR_IS_FILE (current_directory));",
        " ",
        "+  /* Az'arch: ALWAYS show the FULLY-RESOLVED (symlink-dereferenced) path. Thunar 4.20 has no",
        "+   * misc-resolve-links pref (that arrived in 4.21.6), so navigating a symlink such as",
        "+   * ~/Trash -> ~/.local/share/Trash/files would otherwise keep the symlink path in the",
        "+   * location bar and window title. When the requested directory is a symlink, canonicalise it",
        "+   * with realpath() and re-enter with a ThunarFile for the real target, so every surface (path",
        "+   * bar, title, history) shows the actual path -- matching what the sidebar bookmarks already",
        "+   * do. Guarded to symlinks only, and no-ops if resolution fails or already matches. */",
        "+  if (current_directory != NULL && thunar_file_is_symlink (current_directory))",
        "+    {",
        "+      GFile *az_gfile = thunar_file_get_file (current_directory);",
        "+      gchar *az_path  = (az_gfile != NULL) ? g_file_get_path (az_gfile) : NULL;",
        "+      if (az_path != NULL)",
        "+        {",
        "+          char *az_real = realpath (az_path, NULL);",
        "+          if (az_real != NULL && strcmp (az_real, az_path) != 0)",
        "+            {",
        "+              GFile      *az_canon = g_file_new_for_path (az_real);",
        "+              ThunarFile *az_rfile = thunar_file_get (az_canon, NULL);",
        "+              g_object_unref (az_canon);",
        "+              if (az_rfile != NULL)",
        "+                {",
        "+                  thunar_window_set_current_directory (window, az_rfile);",
        "+                  g_object_unref (az_rfile);",
        "+                  free (az_real);",
        "+                  g_free (az_path);",
        "+                  return;",
        "+                }",
        "+            }",
        "+          free (az_real);",
        "+          g_free (az_path);",
        "+        }",
        "+    }",
        "+",
        "   /* check if we already display the requested directory */",
        "   if (G_UNLIKELY (window->current_directory == current_directory))",
        "     return;",
    ]
    return "\n".join(lines) + "\n"


def pkgbuild_thunar() -> str:
    return f"""\
# Maintainer: Az'arch <https://github.com/michaelilgiaev/azarch>
#
# =============================================================================
# Az'arch OWN PKGBUILD -- thunar  (generated by packages.pkgbuild)
# =============================================================================
# NOT a community/AUR recipe. Written + maintained by the Az'arch project.
#
# Thunar is the Xfce file manager. Az'arch ships it as the default file manager
# and needs ONE behaviour change the shipped 4.20 series cannot be configured to
# do: always show the fully-resolved (symlink-dereferenced) path in the location
# bar/title (the misc-resolve-links pref only exists in Thunar >= 4.21.6). This
# recipe rebuilds the SAME version Arch's extra/ ships ({THUNAR_VERSION}) -- a
# drop-in replacement -- with a single source patch that adds that resolution.
#
# SOURCE (fully auditable):
#   Project : https://gitlab.xfce.org/xfce/thunar
#   Tarball : https://archive.xfce.org/src/xfce/thunar/{THUNAR_VERSION[:THUNAR_VERSION.rindex('.')]}/thunar-{THUNAR_VERSION}.tar.bz2
#   License : GPL-2.0-or-later
#
# INTEGRITY: pinned sha256 below (download + sha256sum). makepkg aborts on
# mismatch. The patch is shipped in-repo (SKIP -- a local file, reviewed in
# packages.pkgbuild).
#
# FROM SOURCE IN EVERY TIER: a moderate autotools C build (a couple of minutes).
# Built and dropped into the offline repo so pacstrap installs OUR thunar instead
# of extra/'s. The pkgver MATCHES extra/ so pacman treats it as the same package
# (our repo is ordered first, so ours wins).
# =============================================================================

pkgname=thunar
pkgver={THUNAR_VERSION}
# pkgrel=2 (extra/thunar is -1): our repo is appended AFTER [extra] on an ONLINE build
# (pacman.append_local_repo lists the local repo last), so pacstrap would pick extra/'s
# UNPATCHED thunar for the same version. A higher pkgrel makes OURS strictly newer, so pacman
# selects it regardless of repo order (and on an OFFLINE build [extra] is dropped, so ours wins
# anyway). If extra ever ships thunar-4.20.9-2+ or a newer pkgver, bump THUNAR_VERSION/this rel
# in lock-step (the pinned sha256 already forces a conscious version update).
pkgrel=2
pkgdesc="Modern file manager for Xfce (Az'arch build: resolves symlink paths)"
arch=('x86_64')
url="https://gitlab.xfce.org/xfce/thunar"
license=('GPL-2.0-or-later')
groups=('xfce4')

# Runtime deps mirror extra/thunar's Depends On (pacman -Si thunar), so the built
# package needs exactly what the stock one does.
depends=(
  'desktop-file-utils' 'libexif' 'hicolor-icon-theme' 'libnotify'
  'pcre2' 'libgudev' 'exo' 'libxfce4util' 'libxfce4ui'
)
# Build deps: the -dev headers/tools the autotools build needs. gettext/intltool
# for the translations, xfce4-dev-tools for the xdt macros (the release tarball
# already carries a generated ./configure, but the tools are cheap insurance).
makedepends=('gtk3' 'gettext' 'intltool' 'xfce4-dev-tools' 'gobject-introspection')
optdepends=(
  'gvfs: trash support, mounting with GIO'
  'tumbler: thumbnails'
  'thunar-volman: automanagement of removable devices'
)
options=('!emptydirs')

source=(
  "https://archive.xfce.org/src/xfce/thunar/{THUNAR_VERSION[:THUNAR_VERSION.rindex('.')]}/thunar-${{pkgver}}.tar.bz2"
  '{THUNAR_RESOLVE_SYMLINK_PATCH_NAME}'
)
sha256sums=('{THUNAR_SHA256}' 'SKIP')

prepare() {{
  cd "thunar-${{pkgver}}"
  # Az'arch: always show the resolved (symlink-dereferenced) path in the location
  # bar/title -- the 4.20 series has no misc-resolve-links pref (added upstream in
  # 4.21.6), so it is patched in. -p1 from the source root; the pinned tarball
  # guarantees the context matches, so a failure here (e.g. after a version bump)
  # aborts the build LOUDLY instead of silently dropping the fix.
  patch -p1 < "$srcdir/{THUNAR_RESOLVE_SYMLINK_PATCH_NAME}"
}}

build() {{
  cd "thunar-${{pkgver}}"
  # Match a stock Thunar build. gtk-doc/apidocs off (extra deps, pointless on the
  # ISO). The tarball ships a generated ./configure, so no autogen is needed.
  ./configure \\
    --prefix=/usr \\
    --sysconfdir=/etc \\
    --libexecdir=/usr/lib \\
    --localstatedir=/var \\
    --disable-static \\
    --disable-gtk-doc \\
    --disable-gtk-doc-html \\
    --disable-silent-rules
  # -j caps parallel compile jobs (AZARCH_JOBS is exported by makepkg, = cores -
  # reserved, default 1) so the build does not pin the whole machine.
  make -j"${{AZARCH_JOBS:-1}}"
}}

package() {{
  cd "thunar-${{pkgver}}"
  make DESTDIR="$pkgdir" install
}}
"""


# ---------------------------------------------------------------------------
# Recipe emission plan: (dirname, {filename: content}) tuples.
# compiler.py iterates this to write each recipe dir into the build tree, then the
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
    # The .desktop is the ONLY companion file the package ships now. The AutoConfig
    # override (librewolf.overrides.cfg) is NOT packaged: LibreWolf reads it from the
    # user's PROFILE dir, not /opt, so it is delivered as a home file by
    # packages/librewolf.emit_plan() (compiler.py) instead -- shipping it under /opt did
    # nothing. See packages/librewolf.
    lw_common = {
        "librewolf.desktop": librewolf_desktop(),
    }
    calamares = ("calamares", {
        "PKGBUILD": pkgbuild_calamares(),
        CALAMARES_DEFAULTS_PATCH_NAME: calamares_defaults_patch(),
        CALAMARES_REGION_KEYBOARD_PATCH_NAME: calamares_region_keyboard_patch(),
        CALAMARES_FINISH_BUTTONS_PATCH_NAME: calamares_finish_buttons_patch(),
    })
    # thunar: rebuilt (same version as extra/) with the symlink-resolve patch, in EVERY tier --
    # the patched location-bar behaviour is not optional. Built from source like calamares.
    thunar = ("thunar", {
        "PKGBUILD": pkgbuild_thunar(),
        THUNAR_RESOLVE_SYMLINK_PATCH_NAME: thunar_resolve_symlink_patch(),
    })
    if full_compile:
        librewolf = ("librewolf", {"PKGBUILD": pkgbuild_librewolf_src(), **lw_common})
        return [calamares, thunar, librewolf]
    librewolf = ("librewolf", {"PKGBUILD": pkgbuild_librewolf(), **lw_common})
    # Default tier: repackage librewolf, but calamares + thunar are still built from source.
    return [calamares, thunar, librewolf]


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
