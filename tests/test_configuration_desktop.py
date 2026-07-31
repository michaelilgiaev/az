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

from azarch.configuration import desktop


# --- PLAN mode/owner/dest table --------------------------------------------

def test_plan_has_exactly_eight_entries():
    # steps.py iterates PLAN; a dropped/extra entry silently un-emits a file.
    # (8 = the original 7 + the ~/Desktop installer launcher.)
    assert len(desktop.PLAN) == 8


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
    # The live-session "Azarch Installer" launcher must land in ~/Desktop, be
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
    assert "Name=Azarch Installer" in body
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
        assert "Name=Azarch Installer" in body


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

def test_emit_plan_length_is_nine():
    assert len(desktop.emit_plan()) == 9


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
    # (PLAN + [x] builds a new list, so the constant stays at seven).
    before = len(desktop.PLAN)
    desktop.emit_plan()
    desktop.emit_plan()
    assert len(desktop.PLAN) == before == 8


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
    # Plasma's own wallpaper repaint is invisible (identical pixels).
    out = desktop.xinitrc()
    assert "feh --no-fehbg --bg-fill '" + desktop.WALLPAPER_DEST + "'" in out
    feh_idx = out.index("feh --no-fehbg --bg-fill")
    exec_idx = out.index("exec startplasma-x11")
    assert feh_idx < exec_idx


# --- Plasma wallpaper appletsrc ---------------------------------------------

def test_appletsrc_sets_wallpaper_in_nested_image_group():
    # The wallpaper Image= MUST live in the nested
    # [Containments][1][Wallpaper][org.kde.image][General] group (not the
    # containment's own [General]) or Plasma ignores it. Value is a file:// URI.
    out = desktop.plasma_appletsrc()
    assert "[Containments][1][Wallpaper][org.kde.image][General]" in out
    assert "Image=file://" + desktop.WALLPAPER_DEST in out


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


def test_wallpaper_dest_and_asset_values():
    # The wallpaper ships to a system path (referenced by both the appletsrc and
    # the xinitrc pre-paint) and is sourced from the requested asset.
    assert desktop.WALLPAPER_DEST == "/usr/share/azarch/wallpaper.png"
    assert desktop.WALLPAPER_ASSET == "wallpapers/wallpaper_years.png"


def test_wallpaper_dest_used_in_xinitrc_and_appletsrc():
    # The wallpaper path is spliced into two builders; both must carry it verbatim
    # so the pre-paint and the Plasma wallpaper are the same image (no flash).
    assert desktop.WALLPAPER_DEST in desktop.xinitrc()
    assert desktop.WALLPAPER_DEST in desktop.plasma_appletsrc()


# --- Every builder returns non-empty content --------------------------------

def test_all_builders_return_nonempty_str():
    # Catches an import-time f-string ValueError or an accidental None return: each
    # builder in the plan (plus bash_profile) must yield a non-empty string.
    for entry in desktop.emit_plan():
        content = entry["builder"]()
        assert isinstance(content, str)
        assert content.strip(), entry["dest"]
