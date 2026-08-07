"""azarch.configuration.desktop -- the KDE Plasma live-session configuration-as-Python payloads.

Why these tests matter: steps.py never inspects the CONTENT of these builders;
it blindly iterates PLAN/emit_plan() and calls emit.write_text/write_exec with
the (dest, mode) each entry declares, then chowns the /home/main subtree to the
live user only for entries marked owner "home". So the declarative PLAN table IS
the contract -- a wrong mode makes a script non-executable (the ISO's `[ -x ]`
guards then silently skip it) or a configuration world-writable; a wrong owner chowns a
root-owned wrapper to uid 1000 (or leaves a home dotfile root-owned so the live
user cannot read it). None of that raises in Python; it only shows up as a dead
live session. These tests pin the mode/owner/dest table, prove emit_plan() does
not mutate the module-level PLAN (steps.py may call it more than once), lock the
Plasma session contract (xinitrc execs startplasma-x11, no cyan flash, wallpaper
baked in), and the privileged wrapper's `unset XDG_RUNTIME_DIR` before `exec sudo`.
"""

from __future__ import annotations

import pytest

from azarch.configuration import desktop


# --- PLAN mode/owner/dest table --------------------------------------------

def test_plan_has_exactly_nineteen_entries():
    # steps.py iterates PLAN; a dropped/extra entry silently un-emits a file.
    # (19 = original 7 + ~/Desktop launcher + plasmashellrc + kdeglobals + krunnerrc
    #  + kxkbrc keyboard-layouts + plasma-localerc (d/m/y clock) + powerdevilrc
    #  (PC/laptop sleep policy, Plasma-6 schema) + powermanagementprofilesrc migration
    #  flag + kscreenlockerrc (disable auto-lock) + klaunchrc (no launch feedback)
    #  + kwinrc (no window animation) + the org.kde.plasma.icon menu backing
    #  .desktop under ~/.local/share/plasma_icons -- the paper-icon fix.)
    assert len(desktop.PLAN) == 19


def test_plan_entries_have_the_four_declared_keys():
    for entry in desktop.PLAN:
        assert set(entry) == {"builder", "dest", "mode", "owner"}


def test_plan_modes_are_only_exec_or_conf():
    # Every mode must be one of the two declared octals (0o755 script / 0o644 conf);
    # anything else means a hand-typed literal drifted.
    for entry in desktop.PLAN:
        assert entry["mode"] in (0o755, 0o644), entry["dest"]


def test_plan_owners_are_only_home_or_root():
    for entry in desktop.PLAN:
        assert entry["owner"] in ("home", "root"), entry["dest"]


def test_exec_and_conf_octal_values():
    # Guard the module-level octal constants directly: a script must be 0o755 and
    # a configuration 0o644, or the ISO's [ -x ] guards skip scripts / configs go writable.
    assert desktop._EXEC == 0o755
    assert desktop._CONF == 0o644


def test_scripts_are_exec_configs_are_conf():
    # xinitrc is a shell script -> 0o755; the Plasma dotfiles (appletsrc, ksplashrc,
    # the .desktop launchers) are data -> 0o644.
    by_builder = {e["builder"].__name__: e for e in desktop.PLAN}
    assert by_builder["xinitrc"]["mode"] == 0o755
    assert by_builder["plasma_appletsrc"]["mode"] == 0o644
    assert by_builder["ksplashrc"]["mode"] == 0o644
    assert by_builder["autostart_install_desktop"]["mode"] == 0o644
    assert by_builder["install_menu_desktop"]["mode"] == 0o644
    # The Desktop launcher is the exception: it must be EXECUTABLE so Plasma runs it
    # on double-click without the untrusted-.desktop prompt.
    assert by_builder["desktop_installer_launcher"]["mode"] == 0o755


def test_install_wrapper_entry_is_root_owned_exec():
    # The privileged launcher lives in /usr/local/bin and must stay root-owned
    # (0:0) and executable; chowning it to the live user would let uid 1000 rewrite
    # the thing that runs `sudo -E calamares`.
    entry = next(e for e in desktop.PLAN if e["dest"] == desktop.INSTALL_WRAPPER_PATH)
    assert entry["mode"] == 0o755
    assert entry["owner"] == "root"
    assert entry["builder"] is desktop.install_wrapper_sh


def test_appletsrc_entry_is_home_owned_conf():
    entry = next(
        e for e in desktop.PLAN
        if e["dest"] == f"{desktop.HOME}/.config/plasma-org.kde.plasma.desktop-appletsrc"
    )
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"
    assert entry["builder"] is desktop.plasma_appletsrc


def test_root_owned_dests_are_wrapper_cli_and_menu_launcher():
    # Exactly three PLAN entries are root-owned: the azarch CLI, the installer
    # wrapper (both /usr/local/bin), and the system-wide menu launcher
    # (/usr/share/applications). Everything else is a /home/main dotfile handed to
    # the live user (uid 1000, gid 998).
    root_dests = [e["dest"] for e in desktop.PLAN if e["owner"] == "root"]
    assert set(root_dests) == {
        desktop.INSTALL_WRAPPER_PATH,
        desktop.AZARCH_BIN_PATH,
        "/usr/share/applications/azarch-install.desktop",
    }


def test_desktop_launcher_is_on_the_desktop_executable_and_home_owned():
    # The live-session "Az'arch Linux Installer" launcher must land in ~/Desktop, be
    # executable (0o755, so Plasma trusts it), and be handed to the live user.
    entry = next(
        e for e in desktop.PLAN
        if e["dest"] == f"{desktop.HOME}/Desktop/azarch-install.desktop"
    )
    assert entry["builder"] is desktop.desktop_installer_launcher
    assert entry["mode"] == 0o755
    assert entry["owner"] == "home"


def test_desktop_launcher_content_names_installer_and_wrapper_and_icon():
    body = desktop.desktop_installer_launcher()
    assert "[Desktop Entry]" in body
    assert "Name=Az'arch Linux Installer" in body
    assert f"Exec={desktop.INSTALL_WRAPPER_PATH}" in body
    assert f"Icon={desktop.INSTALLER_ICON_NAME}" in body
    assert "Type=Application" in body


def test_installer_launchers_all_use_the_azarch_icon():
    # Desktop, application-menu, and autostart launchers must all reference the
    # "Az'" installer icon (not the old generic system-software-install).
    for body in (
        desktop.desktop_installer_launcher(),
        desktop.install_menu_desktop(),
        desktop.autostart_install_desktop(),
    ):
        assert f"Icon={desktop.INSTALLER_ICON_NAME}" in body
        assert "system-software-install" not in body
        assert "Name=Az'arch Linux Installer" in body


def test_installer_icon_paths_are_standard_system_locations():
    # The icon is installed to /usr/share/pixmaps and hicolor 256x256 apps so the
    # basename Icon= resolves; both must be absolute system paths.
    assert desktop.INSTALLER_ICON_PIXMAP == "/usr/share/pixmaps/azarch-installer.png"
    assert desktop.INSTALLER_ICON_HICOLOR == (
        "/usr/share/icons/hicolor/256x256/apps/azarch-installer.png"
    )
    assert desktop.INSTALLER_ICON_ASSET == "logo/azarch_installer_icon.png"


def test_home_owned_dests_live_under_home():
    for entry in desktop.PLAN:
        if entry["owner"] == "home":
            assert entry["dest"].startswith(desktop.HOME + "/"), entry["dest"]


def test_home_owner_gid_is_autologin_group():
    # The chown after emit uses (1000, 998); 998 is the autologin group gid that
    # configuration/system.py assigns. A drift here would chown the live tree to a
    # nonexistent gid.
    assert desktop.HOME_OWNER == (1000, 998)
    assert desktop.HOME == "/home/main"


# --- emit_plan(): PLAN + bash_profile, without mutating PLAN ----------------

def test_emit_plan_length_is_twenty():
    # 19 PLAN entries + the appended .bash_profile.
    assert len(desktop.emit_plan()) == 20


def test_emit_plan_prefix_is_plan():
    # The first entries are exactly PLAN (same dict objects), the bash_profile is
    # appended last.
    assert desktop.emit_plan()[:len(desktop.PLAN)] == desktop.PLAN


def test_emit_plan_last_entry_is_bash_profile():
    last = desktop.emit_plan()[-1]
    assert last["builder"] is desktop.bash_profile_startx
    assert last["dest"] == desktop.BASH_PROFILE_DEST
    assert last["mode"] == 0o644
    assert last["owner"] == "home"


def test_bash_profile_dest_is_home_bash_profile():
    assert desktop.BASH_PROFILE_DEST == f"{desktop.HOME}/.bash_profile"


def test_emit_plan_does_not_mutate_module_plan():
    # steps.py may call emit_plan() more than once; it must not grow PLAN each call
    # (PLAN + [x] builds a new list, so the constant stays fixed).
    before = len(desktop.PLAN)
    desktop.emit_plan()
    desktop.emit_plan()
    assert len(desktop.PLAN) == before == 19


# --- xinitrc: Plasma X11 session, no flash ----------------------------------

def test_xinitrc_execs_startplasma_x11():
    # startx hands the session to the Plasma X11 session launcher.
    assert "exec startplasma-x11" in desktop.xinitrc()


def test_xinitrc_exports_desktop_session_plasma():
    # The one env var the Arch Wiki has you set for a startx Plasma session.
    assert "export DESKTOP_SESSION=plasma" in desktop.xinitrc()


def test_xinitrc_has_no_cyan_solid_flash():
    # THE regression this fixes: the old session did `xsetroot -solid <cyan>`,
    # flashing a solid color before the desktop painted. The new xinitrc must NOT
    # set any solid color; it paints the wallpaper instead (see below).
    out = desktop.xinitrc()
    assert "xsetroot -solid" not in out
    assert "#06b8fd" not in out


def test_xinitrc_prepaints_wallpaper_before_exec():
    # No-flash contract: feh paints the SAME wallpaper onto the X root BEFORE the
    # exec that starts Plasma, so the first visible frame is the wallpaper and
    # Plasma's own wallpaper repaint is invisible (identical pixels). feh needs the
    # actual image FILE (it cannot take a package dir).
    out = desktop.xinitrc()
    assert "feh --no-fehbg --bg-fill '" + desktop.WALLPAPER_IMAGE_FILE + "'" in out
    feh_idx = out.index("feh --no-fehbg --bg-fill")
    exec_idx = out.index("exec startplasma-x11")
    assert feh_idx < exec_idx


# --- Plasma wallpaper appletsrc ---------------------------------------------

def test_appletsrc_sets_wallpaper_in_nested_image_group():
    # The wallpaper Image= MUST live in the nested
    # [Containments][1][Wallpaper][org.kde.image][General] group (not the
    # containment's own [General]) or Plasma ignores it. Value is a file:// URI to the
    # package DIRECTORY (the duplicate-tile fix).
    out = desktop.plasma_appletsrc()
    assert "[Containments][1][Wallpaper][org.kde.image][General]" in out
    assert "Image=file://" + desktop.WALLPAPER_PACKAGE_DIR in out


def test_appletsrc_uses_image_wallpaper_plugin():
    out = desktop.plasma_appletsrc()
    assert "wallpaperplugin=org.kde.image" in out
    assert "plugin=org.kde.desktopcontainment" in out


# --- KSplash disabled (no splash frame) -------------------------------------

def test_ksplashrc_disables_splash():
    # KSplash off so the only paint between the wallpaper root-pixmap and the live
    # desktop is the wallpaper itself -- no splash frame, reinforcing no-flash.
    out = desktop.ksplashrc()
    assert "[KSplash]" in out
    assert "Engine=none" in out
    assert "Theme=None" in out


# --- Autostart + menu launchers open the installer via the wrapper ----------

def test_autostart_desktop_execs_the_wrapper():
    # The Plasma autostart .desktop must run the single privileged wrapper so the
    # installer auto-opens once at login.
    out = desktop.autostart_install_desktop()
    assert out.splitlines()[0] == "[Desktop Entry]"
    assert "Exec=" + desktop.INSTALL_WRAPPER_PATH in out
    assert "Type=Application" in out


def test_autostart_desktop_runs_in_phase_two():
    # Delay until the desktop/panel are ready so the installer window has a session
    # to map into.
    assert "X-KDE-autostart-phase=2" in desktop.autostart_install_desktop()


def test_menu_launcher_execs_the_wrapper():
    # The application-menu launcher (re-open after close) shares the same wrapper.
    out = desktop.install_menu_desktop()
    assert out.splitlines()[0] == "[Desktop Entry]"
    assert "Exec=" + desktop.INSTALL_WRAPPER_PATH in out
    assert "Categories=System;" in out


# --- Privileged wrapper: unset before exec ----------------------------------

def test_install_wrapper_unsets_runtime_dir_before_exec():
    # sudo -E would otherwise pass main's /run/user/1000 to root; the unset must
    # come strictly before the exec that elevates.
    out = desktop.install_wrapper_sh()
    unset_idx = out.index("unset XDG_RUNTIME_DIR")
    exec_idx = out.index("exec sudo -E calamares")
    assert unset_idx < exec_idx


def test_install_wrapper_exec_line_present():
    # The exact privileged launch: sudo -E (preserve X env). NO `-c /etc/calamares`:
    # that overrides the app-data dir and makes Calamares look for qml/ under
    # /etc/calamares (absent) -> fatal startup error. Calamares reads
    # /etc/calamares/settings.conf and branding by default without it.
    assert "exec sudo -E calamares\n" in desktop.install_wrapper_sh()


def test_install_wrapper_does_not_override_appdata_dir():
    # Regression: `-c /etc/calamares` is a testing-only app-data override that
    # broke QML resolution (no /etc/calamares/qml) and crashed the installer.
    # Check the actual command line (the `exec` line), not the explanatory
    # comments, which mention the flag on purpose.
    exec_line = next(
        ln for ln in desktop.install_wrapper_sh().splitlines()
        if ln.startswith("exec ")
    )
    assert "-c" not in exec_line
    assert exec_line == "exec sudo -E calamares"


def test_install_wrapper_is_sh_script():
    assert desktop.install_wrapper_sh().startswith("#!/bin/sh\n")


# --- azarch --sshd-hypervisor guest CLI -------------------------------------

def test_azarch_subcommand_is_sshd_hypervisor():
    # The guest CLI subcommand was renamed --sshd -> --sshd-hypervisor (the binary
    # stays `azarch`). Assert the new case branch + usage line exist and no bare
    # `--sshd` token survives (which would be a stale, unreachable spelling).
    out = desktop.azarch_sh()
    assert "--sshd-hypervisor)" in out
    assert "--sshd-hypervisor    Install host pubkey" in out
    # No standalone `--sshd` (not followed by `-hypervisor`) anywhere.
    import re

    assert not re.search(r"--sshd(?!-hypervisor)", out)


def test_azarch_sshd_installs_pubkey_and_starts_sshd():
    # The --sshd-hypervisor path must stage the host pubkey into the target user's
    # ~/.ssh/authorized_keys, (re)generate host keys, and enable+start sshd.
    out = desktop.azarch_sh()
    assert '"$TARGET_HOME/.ssh/authorized_keys"' in out
    assert "sudo ssh-keygen -A" in out
    assert "sudo systemctl enable --now sshd" in out


def test_azarch_sshd_targets_sudo_invoking_user_not_root_home():
    # The documented invocation is `sudo azarch --sshd-hypervisor`, under which $HOME=/root
    # and $USER=root. Keying off $HOME would stage the key into /root/.ssh and the
    # `main` login would stay locked out. The script must resolve the REAL user via
    # $SUDO_USER (fallback to the current user) and never key the install off $HOME.
    out = desktop.azarch_sh()
    assert 'TARGET_USER="${SUDO_USER:-$(id -un)}"' in out
    assert 'getent passwd "$TARGET_USER"' in out
    # It must NOT install the login key at $HOME (that is /root under sudo).
    assert '"$HOME/.ssh/authorized_keys"' not in out


def test_azarch_sshd_chowns_key_to_target_user():
    # Under sudo the ~/.ssh tree is created as root; a root-owned
    # authorized_keys trips sshd StrictModes and is ignored. The install must hand
    # ownership to the target user.
    out = desktop.azarch_sh()
    assert '-o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.ssh"' in out
    assert (
        '-o "$TARGET_USER" -g "$TARGET_USER" "$KEY" "$TARGET_HOME/.ssh/authorized_keys"'
        in out
    )


def test_azarch_sshd_refuses_bare_root_target():
    # If the resolved target is root (no SUDO_USER, invoked as root), there is no
    # home pubkey login for root here, so the script must bail with a clear error
    # rather than silently staging a key nobody can use.
    out = desktop.azarch_sh()
    assert 'if [ "$TARGET_USER" = "root" ]; then' in out


def test_azarch_sshd_opens_firewall_before_starting_sshd():
    # setup-pkgs.sh sets 'ufw default reject incoming', so without an explicit
    # allow the forwarded host->guest :22 connection is dropped and SSH fails
    # even though sshd is listening. The rule must come BEFORE sshd starts so the
    # port is reachable the instant it listens.
    out = desktop.azarch_sh()
    assert "sudo ufw allow ssh" in out
    allow_idx = out.index("sudo ufw allow ssh")
    start_idx = out.index("sudo systemctl enable --now sshd")
    assert allow_idx < start_idx


# --- azarch --resolve-* guest CLI (IP geolocation, user-chosen server) ------

def test_azarch_resolve_subcommands_present_in_case_and_usage():
    # All three resolvers must be real case branches AND advertised in usage.
    out = desktop.azarch_sh()
    for sub in ("--resolve-region", "--resolve-date-time", "--resolve-language"):
        assert (sub + ")") in out                 # case branch
        assert (sub + " ") in out or (sub + "\\n") in out  # usage line mentions it


def test_azarch_resolve_offers_five_shuffled_servers():
    # The user must be presented FIVE servers, shuffled, including the two called
    # out in issue #46 (ipapi.co, ipquery.io). The prompt says 1-5.
    out = desktop.azarch_sh()
    assert "ipapi.co|" in out
    assert "ipquery.io|" in out
    servers = [ln for ln in out.splitlines() if "|http" in ln and ".co" in ln or "|http" in ln]
    # Exactly five server definition lines in the servers heredoc.
    server_lines = [ln for ln in out.splitlines() if "|http" in ln]
    assert len(server_lines) == 5, server_lines
    assert "shuf" in out                          # shuffled before display
    assert "(1-5)" in out


def test_azarch_resolve_requires_curl_and_jq():
    # The resolvers ping the network with curl and parse JSON with jq; both are on
    # the ISO. The script must guard on their presence with a clear error.
    out = desktop.azarch_sh()
    assert "command -v curl" in out
    assert "command -v jq" in out


def test_azarch_resolve_language_english_first_with_alt_shift():
    # The applied keyboard must put English ("us") FIRST/active and the region
    # layout SECOND, switched with Alt+Shift -- never the region layout alone.
    out = desktop.azarch_sh()
    assert 'xkb_layout="us,$layout"' in out
    assert "grp:alt_shift_toggle" in out
    # English-speaking regions get a lone "us" layout (English only).
    assert 'xkb_layout="us"' in out


def test_azarch_resolve_language_keeps_lang_english():
    # Matching the installer: the display language stays English (LANG=en_US) and
    # only the region FORMAT locale (LC_*) follows the country. The LC_* keys are
    # written in a `for k in ...` loop over the format categories.
    out = desktop.azarch_sh()
    assert "LANG=en_US.UTF-8" in out
    assert "for k in LC_NUMERIC LC_TIME LC_MONETARY LC_PAPER LC_MEASUREMENT" in out


def test_azarch_resolve_region_does_both_timezone_and_language():
    # --resolve-region must apply BOTH the timezone and the language from a single
    # server query.
    out = desktop.azarch_sh()
    region_branch = out.split("--resolve-region)", 1)[1].split(";;", 1)[0]
    assert "azarch_apply_timezone" in region_branch
    assert "azarch_apply_language" in region_branch


def test_azarch_resolve_date_time_sets_timezone_only():
    out = desktop.azarch_sh()
    dt_branch = out.split("--resolve-date-time)", 1)[1].split(";;", 1)[0]
    assert "azarch_apply_timezone" in dt_branch
    assert "azarch_apply_language" not in dt_branch


def test_azarch_resolve_embeds_country_table_from_locale():
    # The country->layout table is the single source of truth in configuration/locale;
    # the CLI must embed exactly that rendering. Spot-check a few rows and that the
    # Hebrew layout is the real "il" (not "he") and Latin-American Spanish is "latam".
    from azarch.configuration import locale

    out = desktop.azarch_sh()
    table = locale.resolver_country_table_sh()
    assert table in out
    assert "IL|he_IL.UTF-8|il|il|0" in table
    assert "SV|es_SV.UTF-8|latam|la-latin1|0" in table
    assert "US|en_US.UTF-8|us|us|1" in table          # English-speaking flag = 1
    # Arabic uses the "ara" xkb layout; the console keymap falls back to "us"
    # (the kbd package ships no Arabic console keymap).
    assert "SA|ar_SA.UTF-8|ara|us|0" in table


def test_azarch_cli_is_posix_sh_syntax():
    # The whole CLI (f-string with an embedded heredoc table) must be valid POSIX sh
    # -- a stray unescaped brace from the f-string conversion would break it.
    import shutil
    import subprocess

    if shutil.which("sh") is None:
        pytest.skip("no /bin/sh to syntax-check with")
    out = desktop.azarch_sh()
    # No f-string artefacts leaked into the emitted script.
    assert "{{" not in out
    assert "}}" not in out
    r = subprocess.run(["sh", "-n"], input=out, text=True, capture_output=True, timeout=30)
    assert r.returncode == 0, f"sh -n rejected the CLI:\n{r.stderr}"


# --- bash_profile tty1 guard ------------------------------------------------

def test_bash_profile_guard_keys_off_tty():
    # The autostart guard keys off the controlling terminal (/dev/tty1), NOT
    # $XDG_VTNR, because on a bare agetty autologin XDG_VTNR can be empty.
    out = desktop.bash_profile_startx()
    assert '[[ -z $DISPLAY && "$(tty)" == /dev/tty1 ]]' in out
    assert "exec startx" in out


def test_bash_profile_guard_line_does_not_reference_xdg_vtnr():
    # SOURCE TRUTH: the returned content DOES mention $XDG_VTNR -- but only in an
    # explanatory comment. The actual `if` guard line must not reference it (that
    # was the whole point of keying off tty). Assert the guard line specifically,
    # not the whole string.
    out = desktop.bash_profile_startx()
    guard_lines = [
        line for line in out.splitlines() if line.strip().startswith("if [[")
    ]
    assert guard_lines, "no guard line found"
    for line in guard_lines:
        assert "XDG_VTNR" not in line


def test_bash_profile_sources_bashrc():
    assert "[[ -f ~/.bashrc ]] && . ~/.bashrc" in desktop.bash_profile_startx()


# --- Branding / wrapper / wallpaper constants -------------------------------

def test_install_wrapper_path_value():
    assert desktop.INSTALL_WRAPPER_PATH == "/usr/local/bin/azarch-install"


def test_wallpaper_package_dir_and_image_file_values():
    # THE DUPLICATE-TILE FIX: Plasma's Image= must point at the package DIRECTORY
    # (trailing slash) so Plasma matches the "years" package tile instead of injecting
    # a loose "1672x941" tile; feh needs the actual image FILE. Both constants derive
    # from the "years" package. The asset carries no "wallpaper_" prefix any more.
    assert desktop.WALLPAPER_PACKAGE_DIR == "/usr/share/wallpapers/years/"
    assert desktop.WALLPAPER_IMAGE_FILE == (
        "/usr/share/wallpapers/years/contents/images/1672x941.png"
    )
    assert desktop.WALLPAPER_ASSET == "wallpapers/years.png"
    # The default must be one of the shipped packages (no separate standalone copy).
    assert desktop.WALLPAPER_DEFAULT_ID in [p["id"] for p in desktop.WALLPAPER_PACKAGES]


def test_wallpaper_default_is_a_shipped_package_dir():
    # REGRESSION GUARD for the "three wallpapers, one duplicate" report: the Plasma
    # default must be the years KPackage's DIRECTORY (not its inner png), so Plasma
    # selects the existing tile rather than adding a standalone resolution-labelled one.
    years = next(p for p in desktop.WALLPAPER_PACKAGES if p["id"] == "years")
    expected_dir = f"{desktop.WALLPAPERS_SYSTEM_DIR}/{years['id']}/"
    assert desktop.WALLPAPER_PACKAGE_DIR == expected_dir
    # The package dir must be a strict prefix of the inner image file it contains.
    assert desktop.WALLPAPER_IMAGE_FILE.startswith(desktop.WALLPAPER_PACKAGE_DIR)
    # No asset carries the old "wallpaper_" prefix.
    for p in desktop.WALLPAPER_PACKAGES:
        assert "wallpaper_" not in p["asset"]


def test_wallpaper_paths_used_in_xinitrc_and_appletsrc():
    # feh (xinitrc) paints the FILE; Plasma (appletsrc Image=) references the package
    # DIR. Neither may point Plasma at the inner png (that is the duplicate-tile bug).
    assert desktop.WALLPAPER_IMAGE_FILE in desktop.xinitrc()
    assert f"Image=file://{desktop.WALLPAPER_PACKAGE_DIR}" in desktop.plasma_appletsrc()
    # The appletsrc must NOT reference the inner image file for Plasma's Image= (the
    # whole point of the fix). Guard the Image= line specifically.
    image_lines = [
        ln for ln in desktop.plasma_appletsrc().splitlines() if ln.startswith("Image=")
    ]
    assert image_lines == [f"Image=file://{desktop.WALLPAPER_PACKAGE_DIR}"]


# --- Every builder returns non-empty content --------------------------------

def test_all_builders_return_nonempty_str():
    # Catches an import-time f-string ValueError or an accidental None return: each
    # builder in the plan (plus bash_profile) must yield a non-empty string.
    for entry in desktop.emit_plan():
        content = entry["builder"]()
        assert isinstance(content, str)
        assert content.strip(), entry["dest"]


# --- KDE panel / menu / theme / wallpapers (tasks: pinned panel, Breeze Dark,
#     generic menu icon, no tray/peek, flat app menu, pinned apps, wallpapers) ---

import configparser as _configparser
import json as _json


def _parse_ini(text: str) -> _configparser.ConfigParser:
    # Plasma config files are INI-ish with [Group][Sub] section names; ConfigParser
    # reads them fine for key/value assertions (it treats the whole bracket run as
    # one section name, which is exactly what we want to look up).
    cp = _configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # keep key case (Plasma keys are case-sensitive)
    cp.read_string(text)
    return cp


def test_appletsrc_has_desktop_and_panel_containments():
    cp = _parse_ini(desktop.plasma_appletsrc())
    d, p = desktop.DESKTOP_CONTAINMENT_ID, desktop.PANEL_CONTAINMENT_ID
    assert cp[f"Containments][{d}"]["wallpaperplugin"] == "org.kde.image"
    assert cp[f"Containments][{p}"]["plugin"] == "org.kde.panel"
    # bottom panel: formfactor=2 (horizontal), location=4 (bottom)
    assert cp[f"Containments][{p}"]["formfactor"] == "2"
    assert cp[f"Containments][{p}"]["location"] == "4"


def test_wallpaper_seeded_in_nested_image_group():
    cp = _parse_ini(desktop.plasma_appletsrc())
    d = desktop.DESKTOP_CONTAINMENT_ID
    grp = f"Containments][{d}][Wallpaper][org.kde.image][General"
    assert cp[grp]["Image"] == f"file://{desktop.WALLPAPER_PACKAGE_DIR}"


def test_panel_uses_kickoff_not_kicker():
    # The user asked for labelled shutdown/restart/sleep buttons on the RIGHT and
    # sleep-instead-of-logout: that footer is a KICKOFF feature (kicker only draws
    # icon-only power buttons on the left with no caption key). So the menu applet is
    # org.kde.plasma.kickoff, NOT kicker.
    body = desktop.plasma_appletsrc()
    assert "org.kde.plasma.kickoff" in body
    assert "org.kde.plasma.kicker" not in body


def test_kickoff_menu_flat_list_labelled_power_sleep_generic_icon():
    cp = _parse_ini(desktop.plasma_appletsrc())
    p = desktop.PANEL_CONTAINMENT_ID
    kcfg = f"Containments][{p}][Applets][1][Configuration][General"
    assert cp[kcfg]["icon"] == desktop.MENU_ICON          # generic, not the KDE logo
    assert cp[kcfg]["icon"] != "start-here-kde"
    # Flat alphabetical app List (kickoff's "All Applications" is a flat A-Z list).
    assert cp[kcfg]["applicationsDisplay"] == "1"          # 1 = List view
    assert cp[kcfg]["alphaSort"] == "true"                 # alphabetical
    # Footer power buttons: Power actions, labelled (text beside icon), sleep first.
    assert cp[kcfg]["primaryActions"] == "0"               # 0 = Power actions in footer
    assert cp[kcfg]["showActionButtonCaptions"] == "true"  # TEXT labels on buttons
    # systemFavorites picks WHICH buttons appear: sleep (suspend) replaces logout.
    favs = cp[kcfg]["systemFavorites"].split(",")
    assert favs == ["suspend", "reboot", "shutdown"]
    assert "logout" not in favs                            # logout replaced by sleep
    assert cp[kcfg]["showRecentApps"] == "false"
    assert cp[kcfg]["showRecentDocs"] == "false"


def test_kickoff_system_favorites_constant_is_sleep_restart_shutdown():
    # The power-button set: sleep (suspend) instead of logout. "suspend" is the
    # verified Plasma 6 session-action id that kickoff labels "Sleep".
    assert desktop.KICKOFF_SYSTEM_FAVORITES == ["suspend", "reboot", "shutdown"]
    assert "logout" not in desktop.KICKOFF_SYSTEM_FAVORITES


def test_panel_pins_librewolf_kitty_dolphin_in_order():
    cp = _parse_ini(desktop.plasma_appletsrc())
    p = desktop.PANEL_CONTAINMENT_ID
    tcfg = f"Containments][{p}][Applets][2][Configuration][General"
    launchers = cp[tcfg]["launchers"]
    assert launchers == (
        "applications:librewolf.desktop,"
        "applications:kitty.desktop,"
        "applications:org.kde.dolphin.desktop"
    )
    # icontasks is the pinned task manager applet.
    assert cp[f"Containments][{p}][Applets][2"]["plugin"] == "org.kde.plasma.icontasks"


def test_panel_uses_standalone_status_applets_no_systray_no_peek():
    # The status widgets are STANDALONE panel applets, not a systemtray container --
    # so there is NO "^" overflow arrow and no auto-discovered extras. There must be
    # NO systemtray, NO Peek-at-Desktop (showdesktop/minimizeall), and NO notifications.
    body = desktop.plasma_appletsrc()
    assert "org.kde.plasma.systemtray" not in body        # no tray container -> no "^"
    assert "org.kde.plasma.showdesktop" not in body       # no Peek at Desktop
    assert "org.kde.plasma.minimizeall" not in body
    assert desktop.NOTIFICATIONS_APPLET_ID == "org.kde.plasma.notifications"
    assert desktop.NOTIFICATIONS_APPLET_ID not in body    # notifications gone entirely
    assert desktop.NOTIFICATIONS_APPLET_ID not in desktop.PANEL_STATUS_APPLETS


def test_panel_status_applets_are_the_expected_set_in_order():
    # Exactly: keyboard-layout (leftmost), device-notifier, brightness, network,
    # volume. NO clipboard, NO battery/power (dropped at the user's request).
    assert desktop.PANEL_STATUS_APPLETS == [
        "org.kde.plasma.keyboardlayout",
        "org.kde.plasma.devicenotifier",
        "org.kde.plasma.brightness",
        "org.kde.plasma.networkmanagement",
        "org.kde.plasma.volume",
    ]
    # keyboard-layout must be the LEFTMOST status applet (left of all right-side icons).
    assert desktop.PANEL_STATUS_APPLETS[0] == "org.kde.plasma.keyboardlayout"
    # Explicitly dropped widgets must not appear anywhere.
    body = desktop.plasma_appletsrc()
    assert "org.kde.plasma.clipboard" not in body         # no clipboard history
    assert "org.kde.plasma.battery" not in body           # power reached from the menu


def test_panel_status_applets_each_have_a_block_and_carry_internet_audio():
    # Every status applet is emitted as its own panel-applet block plugin=<item>, and
    # the internet (plasma-nm) + audio (plasma-pa) the user wanted back are present.
    body = desktop.plasma_appletsrc()
    for item in desktop.PANEL_STATUS_APPLETS:
        assert f"plugin={item}" in body
    assert "plugin=org.kde.plasma.networkmanagement" in body   # internet
    assert "plugin=org.kde.plasma.volume" in body              # audio


def test_panel_applet_order_lists_menu_azmenu_tasks_spacer_status_clock():
    # AppletOrder must be Kickoff(1), OUR Az'arch menu icon(11), tasks(2),
    # spacer(3), the N status applets (4..), then the clock (last). A missing id
    # silently drops that applet. Our menu icon sits between Kickoff and tasks
    # (right of the Application Launcher, left of LibreWolf).
    cp = _parse_ini(desktop.plasma_appletsrc())
    p = desktop.PANEL_CONTAINMENT_ID
    n = len(desktop.PANEL_STATUS_APPLETS)
    status = list(range(4, 4 + n))
    clock_id = 4 + n
    expected = ";".join(
        str(i)
        for i in [desktop._MENU_ID, desktop._AZ_MENU_ID, desktop._TASKS_ID,
                  desktop._SPACER_ID, *status, clock_id]
    )
    assert cp[f"Containments][{p}][General"]["AppletOrder"] == expected
    # Our menu icon (id 11) is an org.kde.plasma.icon pointing at the installed
    # .desktop, positioned immediately after Kickoff in the order.
    order = cp[f"Containments][{p}][General"]["AppletOrder"].split(";")
    assert order[0] == str(desktop._MENU_ID)
    assert order[1] == str(desktop._AZ_MENU_ID)
    az = f"Containments][{p}][Applets][{desktop._AZ_MENU_ID}"
    assert cp[az]["plugin"] == "org.kde.plasma.icon"
    # url= MUST be a file:// URI (not a bare path): a bare path made the applet bake a
    # Type=Link/Icon=unknown wrapper -- the paper-icon-launches-nothing bug.
    assert cp[f"{az}][Configuration][General"]["url"] == f"file://{desktop._AZ_MENU_DESKTOP_PATH}"
    assert cp[f"{az}][Configuration][General"]["iconName"] == desktop._AZ_MENU_ICON_NAME
    # localPath points at the backing .desktop WE ship, so the applet reads our real
    # Type=Application launcher instead of generating a broken wrapper.
    assert cp[f"{az}][Configuration"]["localPath"] == desktop._AZ_MENU_LOCAL_PATH
    # The applet must NOT be immutable: a locked applet froze the broken backing file.
    assert cp[az]["immutability"] == "0"
    # The spacer (id 3) must be an expanding panelspacer so the status icons+clock sit right.
    scfg = f"Containments][{p}][Applets][3][Configuration][General"
    assert cp[f"Containments][{p}][Applets][3"]["plugin"] == "org.kde.plasma.panelspacer"
    assert cp[scfg]["expanding"] == "true"
    # The clock is the LAST of the standard applet ids and is the digital clock.
    assert cp[f"Containments][{p}][Applets][{clock_id}"]["plugin"] == "org.kde.plasma.digitalclock"
    # Our menu icon id must NOT collide with any other applet id -- it is computed
    # as one past the clock precisely so adding status applets can never clash.
    all_ids = [desktop._MENU_ID, desktop._AZ_MENU_ID, desktop._TASKS_ID,
               desktop._SPACER_ID, *status, clock_id]
    assert len(all_ids) == len(set(all_ids)), f"applet id collision: {all_ids}"
    assert desktop._AZ_MENU_ID == clock_id + 1


def test_keyboard_layouts_us_and_hebrew_configured():
    # kxkbrc ships US + Hebrew (xkb us/il) shown as US/HE, Alt+Shift toggles them.
    assert desktop.KEYBOARD_LAYOUTS == [
        {"code": "us", "label": "US"},
        {"code": "il", "label": "HE"},
    ]
    cp = _parse_ini(desktop.kxkbrc())
    layout = cp["Layout"]
    assert layout["Use"] == "true"
    assert layout["LayoutList"] == "us,il"
    assert layout["DisplayNames"] == "US,HE"
    assert layout["Options"] == desktop.KEYBOARD_TOGGLE == "grp:alt_shift_toggle"


def test_kxkbrc_is_home_owned_conf():
    by_builder = {e["builder"].__name__: e for e in desktop.PLAN}
    assert by_builder["kxkbrc"]["mode"] == 0o644
    assert by_builder["kxkbrc"]["owner"] == "home"
    assert by_builder["kxkbrc"]["dest"] == f"{desktop.HOME}/.config/kxkbrc"


def test_panel_pinned_not_floating_matches_containment_id():
    cp = _parse_ini(desktop.plasmashellrc())
    grp = f"PlasmaViews][Panel {desktop.PANEL_CONTAINMENT_ID}"
    assert cp[grp]["floating"] == "0"      # 0 = pinned


def test_panel_thickness_is_larger_than_default_in_defaults_group():
    # The user asked for a bigger bottom bar / bigger left icons; settled on 60 px
    # (verified live -- 88 looked too tall, 55 was an intermediate value, 60 gives the
    # ~10%-bigger left launcher/task icons since their size tracks the panel height).
    # CRUCIAL Plasma-6 quirk: `thickness` is read from the NESTED
    # [PlasmaViews][Panel <id>][Defaults] subgroup, NOT the flat group (a flat
    # thickness= is silently ignored). `floating` stays in the flat group.
    assert desktop.PANEL_DEFAULT_THICKNESS == 44
    assert desktop.PANEL_THICKNESS == 60
    assert desktop.PANEL_THICKNESS > desktop.PANEL_DEFAULT_THICKNESS
    out = desktop.plasmashellrc()
    cp = _parse_ini(out)
    flat = f"PlasmaViews][Panel {desktop.PANEL_CONTAINMENT_ID}"
    defaults = f"PlasmaViews][Panel {desktop.PANEL_CONTAINMENT_ID}][Defaults"
    # floating in the flat group; thickness in the nested [Defaults] group.
    assert cp[flat]["floating"] == "0"
    assert cp[defaults]["thickness"] == str(desktop.PANEL_THICKNESS)
    # thickness must NOT be in the flat group (that placement is a no-op on Plasma 6).
    assert "thickness" not in cp[flat]
    # The nested group header must literally appear.
    assert f"[PlasmaViews][Panel {desktop.PANEL_CONTAINMENT_ID}][Defaults]" in out


def test_global_theme_is_breeze_dark():
    cp = _parse_ini(desktop.kdeglobals())
    assert cp["KDE"]["LookAndFeelPackage"] == "org.kde.breezedark.desktop"
    assert cp["General"]["ColorScheme"] == "BreezeDark"
    assert cp["Icons"]["Theme"] == "breeze-dark"


def test_krunner_search_is_applications_only():
    cp = _parse_ini(desktop.krunnerrc())
    plugins = cp["Plugins"]
    assert plugins["krunner_servicesEnabled"] == "true"   # applications runner ON
    # A representative set of non-app runners must be OFF.
    for off in ("baloosearchEnabled", "krunner_bookmarksrunnerEnabled",
                "krunner_shellEnabled", "krunner_webshortcutsEnabled"):
        assert plugins[off] == "false"


def test_new_plasma_config_files_are_home_owned_conf():
    by_builder = {e["builder"].__name__: e for e in desktop.PLAN}
    for name in ("plasmashellrc", "kdeglobals", "krunnerrc"):
        assert by_builder[name]["mode"] == 0o644
        assert by_builder[name]["owner"] == "home"
        assert by_builder[name]["dest"] == f"{desktop.HOME}/.config/{name}"


# --- wallpaper KPackages (years + decades; Waterfall/Next removed) ----------

def test_two_wallpaper_packages_named_years_and_decades():
    ids = [p["id"] for p in desktop.WALLPAPER_PACKAGES]
    assert ids == ["years", "decades"]


def test_wallpaper_metadata_json_is_valid_and_named():
    for wp_id in ("years", "decades"):
        meta = _json.loads(desktop.wallpaper_metadata_json(wp_id))
        assert meta["KPlugin"]["Id"] == wp_id
        assert meta["KPlugin"]["Name"] == wp_id      # grid label
        assert meta["KPlugin"]["Authors"]            # non-empty


def test_wallpaper_package_assets_exist():
    from azarch import paths
    for pkg in desktop.WALLPAPER_PACKAGES:
        assert (paths.ASSETSDIR / pkg["asset"]).exists(), pkg["asset"]


def test_stock_next_wallpaper_removed_in_customize():
    from azarch.configuration import system
    # The grid must show only the azarch wallpapers, so the bundled Plasma "Next"
    # wallpaper is deleted in the post-pacstrap hook.
    assert "rm -rf /usr/share/wallpapers/Next" in system.CUSTOMIZE_AIROOTFS


# --- Plasma date format: day/month/year (Task 3) ----------------------------

def test_plasma_localerc_sets_dmy_time_locale():
    # The KDE clock/calendar formats dates via plasma-localerc [Formats] LC_TIME.
    # en_GB.UTF-8 is English but d/m/y (vs en_US m/d/y) -- the user's request.
    s = desktop.plasma_localerc()
    assert "[Formats]" in s
    assert "LC_TIME=en_GB.UTF-8" in s
    # useDetailedLocales makes Plasma honour the per-category LC_TIME override.
    assert "useDetailedLocales=true" in s


def test_plasma_localerc_matches_system_lc_time():
    # Single source of truth: the Plasma clock locale must equal the system LC_TIME
    # (configuration/locale.DEFAULT_TIME_LOCALE), or the clock and `date` disagree.
    from azarch.configuration import locale
    assert desktop._TIME_LOCALE == locale.DEFAULT_TIME_LOCALE
    assert f"LC_TIME={locale.DEFAULT_TIME_LOCALE}" in desktop.plasma_localerc()


def test_plasma_localerc_in_plan_as_home_conf():
    entry = next(e for e in desktop.PLAN
                 if e["dest"] == f"{desktop.HOME}/.config/plasma-localerc")
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"


# --- PowerDevil sleep policy: PC/laptop (Task 1) ----------------------------

# NOTE: keep this DISTINCT from the module-level _parse_ini above (which returns a
# ConfigParser and normalises [a][b] headers): here we want the RAW "[a][b]" header
# string as the key so a missing/extra SuspendSession subgroup is directly visible.
def _parse_kv_sections(text: str) -> dict:
    out: dict = {}
    section = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line
            out.setdefault(section, {})
        elif "=" in line and section is not None:
            k, v = line.split("=", 1)
            out[section][k.strip()] = v.strip()
    return out


def test_powerdevil_action_enum_values():
    # The action enum (daemon/powerdevilenums.h, powerdevil 6.7.4): 0=NoAction,
    # 1=Sleep(suspend-to-RAM), 8=Shutdown. A drift here silently changes what the
    # AC/Battery profiles do.
    assert desktop._POWERDEVIL_NO_ACTION == 0
    assert desktop._POWERDEVIL_SLEEP == 1
    assert desktop._POWERDEVIL_SHUTDOWN == 8


def test_powerdevil_ac_never_suspends_and_never_blanks():
    # AC profile (plugged in, and the ONLY profile on a battery-less PC): the screen
    # NEVER turns off and the session NEVER idle-suspends. Plasma-6 schema: both are
    # EXPLICIT keys (TurnOffDisplayWhenIdle defaults TRUE, AutoSuspendAction defaults to
    # suspend), so omission would NOT disable them -- they must be written 0/false.
    s = desktop.powerdevilrc()
    d = _parse_kv_sections(s)
    assert d["[AC][Display]"]["TurnOffDisplayWhenIdle"] == "false"   # screen never off
    ac = d["[AC][SuspendAndShutdown]"]
    assert ac["AutoSuspendAction"] == "0"       # 0 = NoAction -> never idle-suspend
    # The dead Plasma-5 subgroup must NOT appear (that schema is ignored by PowerDevil 6).
    assert "[AC][SuspendSession]" not in s


def test_powerdevil_power_button_is_shutdown():
    # Power button -> Shut Down (PROMPT.md #2). PowerDevil 6 block-inhibits logind's
    # handle-power-key, so in a Plasma session THIS key governs the button; value 8 =
    # Shutdown. PowerDownAction pinned 0 (NoAction) for safety (its default is a logout
    # prompt).
    d = _parse_kv_sections(desktop.powerdevilrc())
    ac = d["[AC][SuspendAndShutdown]"]
    assert ac["PowerButtonAction"] == "8"       # 8 = Shutdown
    assert ac["PowerDownAction"] == "0"         # 0 = NoAction (pinned off)


def test_powerdevil_battery_suspends_after_fifteen_minutes():
    # Battery profile (laptop unplugged) -> suspend-to-RAM after 15 min. Plasma-6 schema:
    # AutoSuspendAction=1 (Sleep) + AutoSuspendIdleTimeoutSec in SECONDS (900), NOT the
    # old idleTime in ms. The screen must also not dim/blank on battery.
    d = _parse_kv_sections(desktop.powerdevilrc())
    bd = d["[Battery][Display]"]
    assert bd["DimDisplayWhenIdle"] == "false"
    assert bd["TurnOffDisplayWhenIdle"] == "false"
    bs = d["[Battery][SuspendAndShutdown]"]
    assert bs["AutoSuspendAction"] == "1"       # 1 = Sleep (suspend-to-RAM)
    assert bs["AutoSuspendIdleTimeoutSec"] == str(desktop.POWERDEVIL_BATTERY_IDLE_SECONDS)
    assert bs["PowerButtonAction"] == "8"       # power button shuts down on battery too


def test_powerdevil_timeout_matches_logind_seconds():
    # The Plasma and console-logind 15-minute timeouts must agree (both in SECONDS now),
    # or a laptop sleeps at two different times depending on whether Plasma is running.
    from azarch.configuration import system
    assert desktop.POWERDEVIL_BATTERY_IDLE_SECONDS == system.SLEEP_POLICY_IDLE_SECONDS


def test_powerdevil_uses_new_schema_not_dead_plasma5_file():
    # REGRESSION GUARD: PowerDevil 6 reads `powerdevilrc` (PowerDevilProfileSettings.kcfg
    # kcfgfile). The old `powermanagementprofilesrc` policy schema is ignored (migration
    # only). The policy MUST be in powerdevilrc, and powerdevilrc must NOT use the dead
    # Plasma-5 [SuspendSession]/idleTime/suspendType keys.
    entry = next(e for e in desktop.PLAN
                 if e["dest"] == f"{desktop.HOME}/.config/powerdevilrc")
    assert entry["builder"] is desktop.powerdevilrc
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"
    s = desktop.powerdevilrc()
    for dead in ("SuspendSession", "idleTime", "suspendType"):
        assert dead not in s, dead


def test_powermanagementprofilesrc_is_migration_flag_only():
    # The old file is shipped with ONLY the migration-done flag (no policy), so
    # PowerDevil's one-shot Plasma-5 -> 6 migrator can never run on first boot and layer
    # stale deltas onto the hand-written powerdevilrc.
    s = desktop.powermanagement_migration_flag()
    d = _parse_kv_sections(s)
    assert d == {"[Migration]": {"MigratedProfilesToPlasma6": "powerdevilrc"}}
    # No power-policy groups leaked into this file.
    assert "SuspendSession" not in s
    assert "SuspendAndShutdown" not in s
    assert "[AC]" not in s
    entry = next(e for e in desktop.PLAN
                 if e["dest"] == f"{desktop.HOME}/.config/powermanagementprofilesrc")
    assert entry["builder"] is desktop.powermanagement_migration_flag
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"


# --- KDE screen locker disabled (PROMPT.md #4: the actual "sleep" culprit) ---

def test_kscreenlockerrc_disables_autolock():
    # The KScreenLocker daemon defaults to auto-lock ON at 5 min and BLANKS the display
    # -- the real cause of the screen "going to sleep". Ship the file with auto-lock off.
    cp = _parse_ini(desktop.kscreenlockerrc())
    daemon = cp["Daemon"]
    assert daemon["Autolock"] == "false"       # no idle auto-lock at all
    assert daemon["Timeout"] == "0"            # belt: zero-minute idle-lock timeout
    assert daemon["LockOnResume"] == "false"   # no forced lock on wake/resume


def test_kscreenlockerrc_in_plan_as_home_conf():
    entry = next(e for e in desktop.PLAN
                 if e["dest"] == f"{desktop.HOME}/.config/kscreenlockerrc")
    assert entry["builder"] is desktop.kscreenlockerrc
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"


def test_klaunchrc_disables_launch_feedback():
    # Clicking the menu icon must show NO bouncing/busy "loading" cursor or taskbar
    # launch indicator -- the menu just appears.
    cp = _parse_ini(desktop.klaunchrc())
    assert cp["BusyCursorSettings"]["Bouncing"] == "false"
    assert cp["BusyCursorSettings"]["Enabled"] == "false"
    assert cp["FeedbackStyle"]["BusyCursor"] == "false"
    assert cp["FeedbackStyle"]["TaskbarButton"] == "false"


def test_klaunchrc_in_plan_as_home_conf():
    entry = next(e for e in desktop.PLAN
                 if e["dest"] == f"{desktop.HOME}/.config/klaunchrc")
    assert entry["builder"] is desktop.klaunchrc
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"


def test_kwinrc_disables_window_animations():
    # The menu (and every window) must appear IMMEDIATELY -- no glide/scale/fade.
    # Our menu is an override-redirect Tk window, which KWin treats as a POPUP: its
    # fade/slide comes from the POPUP effects (fadingpopups/slidingpopups), NOT the
    # normal-window fade/glide/scale. So the popup effects must be disabled too, or
    # the menu still fades in. All five *Enabled keys must be false.
    cp = _parse_ini(desktop.kwinrc())
    plugins = cp["Plugins"]
    assert plugins["fadeEnabled"] == "false"
    assert plugins["glideEnabled"] == "false"
    assert plugins["scaleEnabled"] == "false"
    # POPUP effects (the actual pop-in fix for the override-redirect menu window).
    assert plugins["fadingpopupsEnabled"] == "false"
    assert plugins["slidingpopupsEnabled"] == "false"


def test_kwinrc_in_plan_as_home_conf():
    entry = next(e for e in desktop.PLAN
                 if e["dest"] == f"{desktop.HOME}/.config/kwinrc")
    assert entry["builder"] is desktop.kwinrc
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"


# --- Keyboard-layout applet: Flag mode (PROMPT.md #5b: fix low-hanging label) -

def test_keyboard_layout_applet_uses_flag_display_style():
    # The keyboard-layout applet's "US"/"HE" TEXT label hangs low (Qt AlignVCenter
    # centers the line-box, not the caps). Flag mode (displayStyle=1) shows a centered
    # flag ICON instead. The applet is the FIRST (leftmost) status applet, id 4.
    assert desktop.KEYBOARD_DISPLAY_STYLE == 1     # 1 = Flag
    assert desktop.PANEL_STATUS_APPLETS[0] == "org.kde.plasma.keyboardlayout"
    cp = _parse_ini(desktop.plasma_appletsrc())
    p = desktop.PANEL_CONTAINMENT_ID
    # Status applets start at id 4 (_STATUS_ID_BASE); keyboard-layout is index 0 -> id 4.
    kb_id = 4
    assert cp[f"Containments][{p}][Applets][{kb_id}"]["plugin"] == "org.kde.plasma.keyboardlayout"
    cfg = f"Containments][{p}][Applets][{kb_id}][Configuration][General"
    assert cp[cfg]["displayStyle"] == str(desktop.KEYBOARD_DISPLAY_STYLE)


def test_keyboard_flag_config_only_on_keyboard_applet():
    # Only the keyboard-layout applet gets a displayStyle config; the other status
    # applets (device-notifier, brightness, network, volume) must NOT carry it.
    body = desktop.plasma_appletsrc()
    # Exactly one displayStyle assignment in the whole appletsrc.
    assert body.count("displayStyle=") == 1


# --- Az'arch menu icon backing .desktop (THE paper-icon / launches-nothing fix) --

def test_az_menu_icon_backing_is_a_real_application_launcher():
    # THE BUG: org.kde.plasma.icon, given a bare url= path, bakes a
    # Type=Link/Icon=unknown wrapper (a "paper icon" that opens a file location
    # instead of Exec'ing) into ~/.local/share/plasma_icons. We ship that backing
    # file ourselves as a real launcher: Type=Application, Exec=<installed launcher>,
    # a resolvable Icon -- and crucially NOT Type=Link/URL/Icon=unknown.
    body = desktop.az_menu_plasma_icon_backing()
    cp = _parse_ini(body)
    entry = cp["Desktop Entry"]
    assert entry["Type"] == "Application"          # NOT Link
    assert entry["Exec"] == desktop._app_menu.MENU_LAUNCHER_SYSTEM_PATH
    assert entry["Icon"] == desktop._AZ_MENU_ICON_NAME
    assert entry["Icon"] != "unknown"              # not the generic paper glyph
    assert "Type=Link" not in body
    assert "URL=" not in body


def test_az_menu_icon_backing_matches_installed_desktop():
    # Single source of truth: the applet backing file and the installed
    # /usr/local/share/applications .desktop must be identical, so both the panel
    # applet and the menu entry launch the same thing.
    assert desktop.az_menu_plasma_icon_backing() == desktop._app_menu.menu_desktop()


def test_az_menu_local_path_is_the_plasma_icons_backing_path():
    # The localPath the appletsrc points at must be under ~/.local/share/plasma_icons
    # (the dir org.kde.plasma.icon reads its backing file from).
    assert desktop._AZ_MENU_LOCAL_PATH == (
        f"{desktop.HOME}/.local/share/plasma_icons/azarch-application-menu.desktop"
    )
    # And the appletsrc's Configuration/localPath must equal it.
    cp = _parse_ini(desktop.plasma_appletsrc())
    p = desktop.PANEL_CONTAINMENT_ID
    az = f"Containments][{p}][Applets][{desktop._AZ_MENU_ID}][Configuration"
    assert cp[az]["localPath"] == desktop._AZ_MENU_LOCAL_PATH


def test_az_menu_icon_backing_in_plan_as_home_exec():
    # Emitted to the plasma_icons localPath, home-owned (the live user must read it).
    # It MUST be 0o755 (EXECUTABLE), not 0o644: KDE treats a non-executable
    # Type=Application desktop file as UNTRUSTED, so the panel icon's KIO click path
    # pops a modal "not trusted" dialog and launches nothing. The exec bit is the
    # trust signal. steps.py mirrors home-owned files into /etc/skel for installed users.
    entry = next(e for e in desktop.PLAN if e["dest"] == desktop._AZ_MENU_LOCAL_PATH)
    assert entry["builder"] is desktop.az_menu_plasma_icon_backing
    assert entry["mode"] == 0o755
    assert entry["owner"] == "home"
