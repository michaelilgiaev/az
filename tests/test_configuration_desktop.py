"""azarch.configuration.desktop -- the OpenBox live-session configuration-as-Python payloads.

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
OpenBox session contract (xinitrc execs openbox-session, no cyan flash, wallpaper
pre-painted; rc.xml binds the Super key to the menu; autostart arms xcape + the
keyboard + the menu daemon + the installer), and the privileged wrapper's
`unset XDG_RUNTIME_DIR` before `exec sudo`.

KDE Plasma was REMOVED from Az'arch and replaced by a panel-less OpenBox desktop;
every Plasma-specific builder/constant (panel/appletsrc, kdeglobals, kwinrc,
powerdevil, kscreenlocker, kickoff, ...) is gone, so the tests that pinned them are
gone too. The Az'arch application menu (Super key / OpenBox root-menu entry) is the
only shell surface now.
"""

from __future__ import annotations

import pytest

from azarch.configuration import desktop


# --- PLAN mode/owner/dest table --------------------------------------------

def test_plan_has_exactly_eleven_entries():
    # steps.py iterates PLAN; a dropped/extra entry silently un-emits a file. The
    # panel-less OpenBox session ships exactly eleven files via PLAN:
    #   1. ~/.xinitrc                          (startx -> openbox-session)
    #   2. ~/.config/openbox/rc.xml            (keybinds: Super -> menu, root-menu)
    #   3. ~/.config/openbox/menu.xml          (OpenBox root menu: launcher/term/installer/power)
    #   4. ~/.config/openbox/autostart         (feh, setxkbmap, xcape, menu daemon, installer)
    #   5. ~/.config/openbox/environment       (XDG_CURRENT_DESKTOP=openbox)
    #   6. /usr/local/share/azarch/openbox-autostart-installed (staged "installed"
    #      autostart the Calamares install copies over the target's; no keyboard/installer)
    #   7. ~/.local/share menu usage seed       (default menu ordering)
    #   8. /usr/share/applications/azarch-install.desktop (menu re-open entry, system)
    #   9. ~/Desktop/azarch-install.desktop     (double-clickable installer launcher)
    #  10. /usr/local/bin/azarch-install         (privileged Calamares wrapper)
    #  11. /usr/local/bin/azarch                 (guest-side CLI)
    # The .bash_profile snippet is appended by emit_plan(), NOT part of PLAN.
    assert len(desktop.PLAN) == 11


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
    # Shell scripts / executables -> 0o755; plain config/data (OpenBox XML configs, the
    # system-wide .desktop) -> 0o644. The OpenBox `autostart` is a shell script sourced
    # by openbox-session, so it is EXECUTABLE; rc.xml/menu.xml/environment are data.
    by_builder = {e["builder"].__name__: e for e in desktop.PLAN}
    assert by_builder["xinitrc"]["mode"] == 0o755
    assert by_builder["openbox_autostart"]["mode"] == 0o755
    assert by_builder["openbox_rc_xml"]["mode"] == 0o644
    assert by_builder["openbox_menu_xml"]["mode"] == 0o644
    assert by_builder["openbox_environment"]["mode"] == 0o644
    assert by_builder["install_menu_desktop"]["mode"] == 0o644
    # The Desktop launcher is the exception among data files: it must be EXECUTABLE so a
    # file manager runs it on double-click without the untrusted-.desktop prompt.
    assert by_builder["desktop_installer_launcher"]["mode"] == 0o755


def test_install_wrapper_entry_is_root_owned_exec():
    # The privileged launcher lives in /usr/local/bin and must stay root-owned
    # (0:0) and executable; chowning it to the live user would let uid 1000 rewrite
    # the thing that runs `sudo -E calamares`.
    entry = next(e for e in desktop.PLAN if e["dest"] == desktop.INSTALL_WRAPPER_PATH)
    assert entry["mode"] == 0o755
    assert entry["owner"] == "root"
    assert entry["builder"] is desktop.install_wrapper_sh


def test_openbox_rc_xml_entry_is_home_owned_conf():
    # OpenBox's rc.xml is a plain config (0o644) and must be handed to the live user
    # (home-owned; mirrored into /etc/skel) or the session cannot read its keybinds.
    entry = next(
        e for e in desktop.PLAN
        if e["dest"] == f"{desktop.HOME}/.config/openbox/rc.xml"
    )
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"
    assert entry["builder"] is desktop.openbox_rc_xml


def test_root_owned_dests_are_wrapper_cli_menu_entry_and_installed_autostart():
    # Exactly four PLAN entries are root-owned: the azarch CLI, the installer wrapper
    # (both /usr/local/bin), the system-wide installer menu .desktop
    # (/usr/share/applications), and the STAGED "installed" OpenBox autostart the
    # Calamares install copies onto the target (a system path, not a per-user file).
    # (The old KDE Super-key shortcut .desktop is GONE -- OpenBox binds the Super key in
    # rc.xml, not via a /usr/share/applications file.) Everything else is a /home/main
    # dotfile handed to the live user (uid 1000, gid 998).
    root_dests = [e["dest"] for e in desktop.PLAN if e["owner"] == "root"]
    assert set(root_dests) == {
        desktop.INSTALL_WRAPPER_PATH,
        desktop.AZARCH_BIN_PATH,
        "/usr/share/applications/azarch-install.desktop",
        desktop.INSTALLED_AUTOSTART_STAGING_PATH,
    }


def test_desktop_launcher_is_on_the_desktop_executable_and_home_owned():
    # The live-session "Az'arch Linux Installer" launcher must land in ~/Desktop, be
    # executable (0o755, so a file manager trusts it), and be handed to the live user.
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
    # Both installer launchers (the Desktop one and the application-menu one) must
    # reference the "Az'" installer icon (not the old generic system-software-install).
    for body in (
        desktop.desktop_installer_launcher(),
        desktop.install_menu_desktop(),
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

def test_emit_plan_length_is_twelve():
    # 11 PLAN entries + the appended .bash_profile snippet = 12. emit_plan() is the
    # single sequence steps.py iterates.
    assert len(desktop.emit_plan()) == 12


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
    assert len(desktop.PLAN) == before == 11


# --- xinitrc: OpenBox X11 session, no flash ---------------------------------

def test_xinitrc_execs_openbox_session():
    # startx hands the session to `openbox-session`, which is BOTH the window manager
    # AND the session bootstrap (it sources environment/autostart and reads rc.xml).
    assert "exec openbox-session" in desktop.xinitrc()


def test_xinitrc_exports_openbox_desktop_classification():
    # logind sets XDG_SESSION_TYPE=x11; we export XDG_CURRENT_DESKTOP/DESKTOP_SESSION
    # so XDG-aware tools (autostart OnlyShowIn, etc.) classify the session as openbox.
    out = desktop.xinitrc()
    assert "export XDG_CURRENT_DESKTOP=openbox" in out
    assert "export DESKTOP_SESSION=openbox" in out


def test_xinitrc_has_no_cyan_solid_flash():
    # THE regression this fixes: the old session did `xsetroot -solid <cyan>`,
    # flashing a solid color before the desktop painted. The new xinitrc must NOT
    # set any solid color; it paints the wallpaper instead (see below).
    out = desktop.xinitrc()
    assert "xsetroot -solid" not in out
    assert "#06b8fd" not in out


def test_xinitrc_prepaints_wallpaper_before_exec():
    # No-flash contract: feh paints the SAME wallpaper onto the X root BEFORE the
    # exec that starts OpenBox, so the first visible frame is the wallpaper and the
    # autostart's own feh repaint is invisible (identical pixels). feh needs the
    # actual image FILE (it cannot take a directory).
    out = desktop.xinitrc()
    assert "feh --no-fehbg --bg-fill '" + desktop.WALLPAPER_IMAGE_FILE + "'" in out
    feh_idx = out.index("feh --no-fehbg --bg-fill")
    exec_idx = out.index("exec openbox-session")
    assert feh_idx < exec_idx


# --- OpenBox rc.xml: Super -> menu, root-menu, borderless menu window --------

def test_rc_xml_binds_super_and_menu_to_the_launcher():
    # The Super key opens the Az'arch menu. OpenBox cannot bind a lone modifier, so
    # xcape turns a solo Super_L tap into Super_L+Menu; rc.xml binds THAT chord
    # (W-Menu) and the bare Menu/Apps key to the menu launcher so either opens it.
    out = desktop.openbox_rc_xml()
    assert desktop.SUPER_MENU_KEYSYM == "Menu"
    assert '<keybind key="W-Menu">' in out
    assert '<keybind key="Menu">' in out
    # Both keybinds run the single application-menu launcher.
    assert desktop.MENU_LAUNCHER == desktop._app_menu.MENU_LAUNCHER_SYSTEM_PATH
    assert desktop.MENU_LAUNCHER == "/usr/local/bin/azarch-application-menu"
    assert f"<command>{desktop.MENU_LAUNCHER}</command>" in out


def test_rc_xml_root_menu_mousebind_opens_the_root_menu():
    # Right/middle click on the desktop (the "Root" context) must open menu.xml's
    # root-menu, the convenience fallback surface for the panel-less session.
    out = desktop.openbox_rc_xml()
    assert '<context name="Root">' in out
    assert "<menu>root-menu</menu>" in out
    # rc.xml points OpenBox at menu.xml for its menu file.
    assert "<file>menu.xml</file>" in out


def test_rc_xml_menu_window_is_undecorated():
    # The Az'arch application menu is a borderless override-redirect Tk window; rc.xml
    # must match it (`*azarch*menu*`) and give it NO OpenBox decorations, so no
    # titlebar/border wraps the launcher.
    out = desktop.openbox_rc_xml()
    assert '<application name="*azarch*menu*">' in out
    assert "<decor>no</decor>" in out


def _strip_xml_comments(text: str) -> str:
    # OpenBox's XML parser is lenient and our generated comments intentionally contain
    # an em-dash rendered as "--" ("... desktop -- edit the Python ..."), which the
    # strict XML spec forbids INSIDE a comment. We want the wellformedness check to
    # validate the ELEMENT tree OpenBox actually reads (balanced tags), not the comment
    # prose, so drop comments before handing the document to ElementTree.
    import re

    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def test_rc_xml_is_wellformed_xml():
    # A stray unbalanced tag from the f-string would make OpenBox ignore the file and
    # fall back to stock keybinds (no Super -> menu). Parse the comment-stripped
    # document to prove the element tree is valid XML.
    import xml.etree.ElementTree as ET

    ET.fromstring(_strip_xml_comments(desktop.openbox_rc_xml()))


# --- OpenBox root menu (menu.xml): launcher/terminal/installer/power ---------

def test_menu_xml_offers_launcher_terminal_installer_and_power_actions():
    # The OpenBox root menu is a small convenience fallback: it must offer the
    # application-menu launcher, a terminal (kitty), the installer (same privileged
    # wrapper), and the session power actions (suspend/reboot/poweroff + lock).
    out = desktop.openbox_menu_xml()
    assert f"<command>{desktop.MENU_LAUNCHER}</command>" in out          # app menu
    assert "<command>kitty</command>" in out                            # terminal
    assert f"<command>{desktop.INSTALL_WRAPPER_PATH}</command>" in out   # installer
    # Power actions reuse the same tools the menu's power row uses.
    assert "<command>systemctl suspend</command>" in out
    assert "<command>systemctl reboot</command>" in out
    assert "<command>systemctl poweroff</command>" in out
    assert "<command>loginctl lock-session</command>" in out


def test_menu_xml_declares_the_root_menu_rc_xml_binds():
    # rc.xml's mousebind opens <menu>root-menu</menu>; menu.xml MUST define a menu with
    # exactly that id, or the desktop right-click opens nothing.
    out = desktop.openbox_menu_xml()
    assert '<menu id="root-menu"' in out


def test_menu_xml_is_wellformed_xml():
    import xml.etree.ElementTree as ET

    ET.fromstring(_strip_xml_comments(desktop.openbox_menu_xml()))


# --- OpenBox autostart: wallpaper, keyboard, xcape, menu daemon, installer ---

def test_autostart_repaints_wallpaper_with_feh():
    # The autostart repaints the SAME image ~/.xinitrc pre-painted (no flash; also
    # covers a re-login where the root pixmap was reset). feh owns the root pixmap.
    out = desktop.openbox_autostart()
    assert "feh --no-fehbg --bg-fill '" + desktop.WALLPAPER_IMAGE_FILE + "'" in out


def test_autostart_applies_us_and_hebrew_layouts_with_alt_shift():
    # setxkbmap sets US English (default) + Hebrew, Alt+Shift to toggle -- the
    # DE-independent replacement for the old Plasma kxkbrc. Constants are pinned so a
    # test catches a layout/toggle drift.
    assert desktop.KEYBOARD_LAYOUTS == ["us", "il"]
    assert desktop.KEYBOARD_TOGGLE == "grp:alt_shift_toggle"
    out = desktop.openbox_autostart()
    assert "setxkbmap -layout 'us,il' -option 'grp:alt_shift_toggle'" in out


def test_autostart_arms_super_key_via_xcape():
    # OpenBox cannot bind a lone modifier, so xcape turns a solo Super_L tap into the
    # chord Super_L+Menu that rc.xml binds to the menu. -t 200: only a tap under 200ms
    # fires (a held Super stays a normal modifier).
    out = desktop.openbox_autostart()
    assert "xcape -t 200 -e 'Super_L=Super_L|Menu'" in out


def test_autostart_starts_the_application_menu_daemon():
    # The application-menu daemon is started (detached) so the menu is pre-built and
    # hidden -- the first Super press / root-menu open is then instant. It runs the
    # INSTALLED daemon.py (single source of truth in application_menu.py).
    out = desktop.openbox_autostart()
    assert desktop.MENU_DAEMON_PY == desktop._app_menu.MENU_DAEMON_PY_SYSTEM_PATH
    assert f"setsid python3 '{desktop.MENU_DAEMON_PY}'" in out


def test_autostart_launches_the_installer_once():
    # The Calamares installer auto-opens ONCE, a couple seconds in (Manjaro-style
    # first-run), via the privileged wrapper -- the same wrapper the menu/root-menu use.
    out = desktop.openbox_autostart()
    assert f"( sleep 2; '{desktop.INSTALL_WRAPPER_PATH}' )" in out


def test_autostart_is_sh_script():
    # openbox-session runs it via /bin/sh; it ships executable, so a shebang is required.
    assert desktop.openbox_autostart().startswith("#!/bin/sh\n")


# --- OpenBox environment: classify the session as openbox -------------------

def test_environment_exports_openbox_desktop():
    # ~/.config/openbox/environment is sourced by openbox-session before autostart; it
    # re-asserts XDG_CURRENT_DESKTOP=openbox so the classification is correct even if
    # OpenBox is started by some path other than our startx.
    assert "export XDG_CURRENT_DESKTOP=openbox" in desktop.openbox_environment()


# --- OpenBox config files land under home, correct modes --------------------

def test_openbox_config_files_are_home_owned_with_correct_modes():
    # The four OpenBox files live under ~/.config/openbox and are handed to the live
    # user (home-owned; mirrored into /etc/skel). rc.xml/menu.xml/environment are plain
    # data (0o644); autostart is a sourced shell script and must be EXECUTABLE (0o755).
    by_dest = {e["dest"]: e for e in desktop.PLAN}
    expected = {
        f"{desktop.HOME}/.config/openbox/rc.xml": (desktop.openbox_rc_xml, 0o644),
        f"{desktop.HOME}/.config/openbox/menu.xml": (desktop.openbox_menu_xml, 0o644),
        f"{desktop.HOME}/.config/openbox/environment": (desktop.openbox_environment, 0o644),
        f"{desktop.HOME}/.config/openbox/autostart": (desktop.openbox_autostart, 0o755),
    }
    for dest, (builder, mode) in expected.items():
        entry = by_dest[dest]
        assert entry["builder"] is builder, dest
        assert entry["mode"] == mode, dest
        assert entry["owner"] == "home", dest


# --- Menu usage seed lands under home ---------------------------------------

def test_menu_usage_seed_entry_is_home_owned_conf():
    # OUR menu's launch-frequency seed lands under ~/.local/share, is plain data
    # (0o644), and is handed to the live user (mirrored to /etc/skel). Content is owned
    # by application_menu.py; desktop.py just places it.
    entry = next(
        e for e in desktop.PLAN
        if e["dest"] == desktop._app_menu.MENU_USAGE_SEED_SYSTEM_PATH
    )
    assert entry["builder"] is desktop.az_menu_usage_seed_json
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"


def test_menu_usage_seed_content_comes_from_application_menu():
    # Single source of truth: the seed content is application_menu.usage_seed_json().
    assert desktop.az_menu_usage_seed_json() == desktop._app_menu.usage_seed_json()


# --- Autostart + menu launchers open the installer via the wrapper ----------

def test_menu_launcher_execs_the_wrapper():
    # The application-menu installer entry (re-open after close) shares the same wrapper.
    out = desktop.install_menu_desktop()
    assert out.splitlines()[0] == "[Desktop Entry]"
    assert "Exec=" + desktop.INSTALL_WRAPPER_PATH in out
    assert "Categories=System;" in out


def test_install_menu_desktop_is_system_owned_conf():
    # The application-menu installer .desktop lands system-wide in
    # /usr/share/applications (one file for all users), root-owned, plain data (0o644).
    entry = next(
        e for e in desktop.PLAN
        if e["dest"] == "/usr/share/applications/azarch-install.desktop"
    )
    assert entry["builder"] is desktop.install_menu_desktop
    assert entry["mode"] == 0o644
    assert entry["owner"] == "root"


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


def test_wallpaper_image_file_is_the_inner_years_png():
    # feh needs a real FILE (it cannot take a directory), so WALLPAPER_IMAGE_FILE points
    # at the "years" package's inner PNG. The KPackage-style layout is kept only so the
    # steps.py emit paths do not change (nothing reads the package metadata at runtime).
    assert desktop.WALLPAPERS_SYSTEM_DIR == "/usr/share/wallpapers"
    assert desktop.WALLPAPER_DEFAULT_ID == "years"
    assert desktop.WALLPAPER_IMAGE_RES == "1672x941"
    assert desktop.WALLPAPER_IMAGE_FILE == (
        "/usr/share/wallpapers/years/contents/images/1672x941.png"
    )
    assert desktop.WALLPAPER_ASSET == "wallpapers/years.png"
    # The default must be one of the shipped wallpaper packages.
    assert desktop.WALLPAPER_DEFAULT_ID in [p["id"] for p in desktop.WALLPAPER_PACKAGES]


def test_wallpaper_image_file_used_in_xinitrc_and_autostart():
    # feh paints the same FILE in both the xinitrc pre-paint and the autostart repaint;
    # neither may drift, or the two paints differ and the no-flash guarantee breaks.
    assert desktop.WALLPAPER_IMAGE_FILE in desktop.xinitrc()
    assert desktop.WALLPAPER_IMAGE_FILE in desktop.openbox_autostart()


# --- Every builder returns non-empty content --------------------------------

def test_all_builders_return_nonempty_str():
    # Catches an import-time f-string ValueError or an accidental None return: each
    # builder in the plan (plus bash_profile) must yield a non-empty string.
    for entry in desktop.emit_plan():
        content = entry["builder"]()
        assert isinstance(content, str)
        assert content.strip(), entry["dest"]


# --- wallpaper packages (years + decades) -----------------------------------

import json as _json


def test_two_wallpaper_packages_named_years_and_decades():
    ids = [p["id"] for p in desktop.WALLPAPER_PACKAGES]
    assert ids == ["years", "decades"]


def test_wallpaper_metadata_json_is_valid_and_named():
    # The KPackage engine is gone, so nothing reads this at runtime; it is kept only so
    # each wallpaper dir stays self-describing. It must still be valid JSON with Id/Name.
    for wp_id in ("years", "decades"):
        meta = _json.loads(desktop.wallpaper_metadata_json(wp_id))
        assert meta["KPlugin"]["Id"] == wp_id
        assert meta["KPlugin"]["Name"] == wp_id      # grid label
        assert meta["KPlugin"]["Authors"]            # non-empty


def test_wallpaper_package_assets_exist():
    from azarch import paths
    for pkg in desktop.WALLPAPER_PACKAGES:
        assert (paths.ASSETSDIR / pkg["asset"]).exists(), pkg["asset"]
