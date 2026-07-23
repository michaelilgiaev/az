"""azarch.config.desktop -- the Openbox live-session config-as-Python payloads.

Why these tests matter: steps.py never inspects the CONTENT of these builders;
it blindly iterates PLAN/emit_plan() and calls emit.write_text/write_exec with
the (dest, mode) each entry declares, then chowns the /home/main subtree to the
live user only for entries marked owner "home". So the declarative PLAN table IS
the contract -- a wrong mode makes a script non-executable (the ISO's `[ -x ]`
guards then silently skip it) or a config world-writable; a wrong owner chowns a
root-owned wrapper to uid 1000 (or leaves a home dotfile root-owned so the live
user cannot read it). None of that raises in Python; it only shows up as a dead
live session. These tests pin the mode/owner/dest table, prove emit_plan() does
not mutate the module-level PLAN (steps.py may call it more than once), prove the
two Openbox XML documents stay well-formed despite the literal `Az'arch`
apostrophe spliced into them, and lock the two brittle shell contracts: the
installer autostart's exec-bit-or-fallback launch and the privileged wrapper's
`unset XDG_RUNTIME_DIR` happening BEFORE `exec sudo`.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from azarch.config import desktop


# --- PLAN mode/owner/dest table --------------------------------------------

def test_plan_has_exactly_six_entries():
    # steps.py iterates PLAN; a dropped/extra entry silently un-emits a file.
    assert len(desktop.PLAN) == 6


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
    # a config 0o644, or the ISO's [ -x ] guards skip scripts / configs go writable.
    assert desktop._EXEC == 0o755
    assert desktop._CONF == 0o644


def test_scripts_are_exec_configs_are_conf():
    # xinitrc and autostart are shell scripts -> 0o755; the three dotfiles that are
    # parsed (rc.xml, menu.xml, picom.conf) are data -> 0o644.
    by_builder = {e["builder"].__name__: e for e in desktop.PLAN}
    assert by_builder["xinitrc"]["mode"] == 0o755
    assert by_builder["openbox_autostart"]["mode"] == 0o755
    assert by_builder["openbox_rc_xml"]["mode"] == 0o644
    assert by_builder["openbox_menu_xml"]["mode"] == 0o644
    assert by_builder["picom_conf"]["mode"] == 0o644


def test_install_wrapper_entry_is_root_owned_exec():
    # The privileged launcher lives in /usr/local/bin and must stay root-owned
    # (0:0) and executable; chowning it to the live user would let uid 1000 rewrite
    # the thing that runs `sudo -E calamares`.
    entry = next(e for e in desktop.PLAN if e["dest"] == desktop.INSTALL_WRAPPER_PATH)
    assert entry["mode"] == 0o755
    assert entry["owner"] == "root"
    assert entry["builder"] is desktop.install_wrapper_sh


def test_picom_entry_is_home_owned_conf():
    entry = next(
        e for e in desktop.PLAN if e["dest"] == f"{desktop.HOME}/.config/picom.conf"
    )
    assert entry["mode"] == 0o644
    assert entry["owner"] == "home"
    assert entry["builder"] is desktop.picom_conf


def test_only_wrapper_is_root_owned():
    # Exactly one PLAN entry is root-owned: the /usr/local/bin wrapper. Everything
    # else is a /home/main dotfile handed to the live user (uid 1000, gid 998).
    root_dests = [e["dest"] for e in desktop.PLAN if e["owner"] == "root"]
    assert root_dests == [desktop.INSTALL_WRAPPER_PATH]


def test_home_owned_dests_live_under_home():
    for entry in desktop.PLAN:
        if entry["owner"] == "home":
            assert entry["dest"].startswith(desktop.HOME + "/"), entry["dest"]


def test_home_owner_gid_is_autologin_group():
    # The chown after emit uses (1000, 998); 998 is the autologin group gid that
    # config/system.py assigns. A drift here would chown the live tree to a
    # nonexistent gid.
    assert desktop.HOME_OWNER == (1000, 998)
    assert desktop.HOME == "/home/main"


# --- emit_plan(): PLAN + bash_profile, without mutating PLAN ----------------

def test_emit_plan_length_is_seven():
    assert len(desktop.emit_plan()) == 7


def test_emit_plan_prefix_is_plan():
    # First six entries are exactly PLAN (same dict objects), the bash_profile is
    # appended last.
    assert desktop.emit_plan()[:6] == desktop.PLAN


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
    # (PLAN + [x] builds a new list, so the constant stays at six).
    before = len(desktop.PLAN)
    desktop.emit_plan()
    desktop.emit_plan()
    assert len(desktop.PLAN) == before == 6


# --- Openbox XML well-formedness (the Az'arch apostrophe) -------------------

def test_openbox_rc_xml_is_well_formed():
    # The literal apostrophe in "Az'arch" sits inside XML text/attributes; if it
    # ever leaked into an attribute quote it would break the parser here.
    root = ET.fromstring(desktop.openbox_rc_xml())
    assert root.tag.endswith("openbox_config")


def test_openbox_menu_xml_is_well_formed():
    root = ET.fromstring(desktop.openbox_menu_xml())
    assert root.tag.endswith("openbox_menu")


def test_menu_xml_install_command_is_the_wrapper():
    # The top menu entry's <command> must be the single privileged wrapper path,
    # spliced from INSTALL_WRAPPER_PATH.
    xml = desktop.openbox_menu_xml()
    assert (
        "<command>" + desktop.INSTALL_WRAPPER_PATH + "</command>" in xml
    )


def test_rc_xml_desktop_name_is_azarch():
    # The single desktop is named with the branded apostrophe form.
    assert "<name>Az'arch</name>" in desktop.openbox_rc_xml()


# --- Installer autostart: exec-bit-or-fallback launch -----------------------

def test_autostart_has_exec_bit_and_readable_fallback():
    # A lost exec bit (archiso normalizes overlay modes) must not silently stop the
    # installer from opening; the -x branch runs the wrapper, the -r fallback runs
    # it through `sh`.
    out = desktop.openbox_autostart()
    wrapper = desktop.INSTALL_WRAPPER_PATH
    assert f"[ -x {wrapper} ]" in out
    assert f"elif [ -r {wrapper} ]" in out
    assert f"sh {wrapper} &" in out


def test_autostart_backgrounds_helpers():
    # picom / feh / nm-applet must be backgrounded (&) so the autostart script
    # returns and the session comes up.
    out = desktop.openbox_autostart()
    assert "picom --config" in out and "picom" in out
    assert "feh --no-fehbg --bg-color '" + desktop.ACCENT_HEX + "' &" in out
    assert "nm-applet &" in out


# --- Privileged wrapper: unset before exec ----------------------------------

def test_install_wrapper_unsets_runtime_dir_before_exec():
    # sudo -E would otherwise pass main's /run/user/1000 to root; the unset must
    # come strictly before the exec that elevates.
    out = desktop.install_wrapper_sh()
    unset_idx = out.index("unset XDG_RUNTIME_DIR")
    exec_idx = out.index("exec sudo -E calamares -c /etc/calamares")
    assert unset_idx < exec_idx


def test_install_wrapper_exec_line_present():
    # The exact privileged launch: sudo -E (preserve X env) + explicit config tree.
    assert "exec sudo -E calamares -c /etc/calamares" in desktop.install_wrapper_sh()


def test_install_wrapper_is_sh_script():
    assert desktop.install_wrapper_sh().startswith("#!/bin/sh\n")


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


# --- Branding / wrapper constants -------------------------------------------

def test_accent_hex_value_and_length():
    # Matches os-release ANSI_COLOR (6,184,253); a 7-char #rrggbb string used as
    # both the xsetroot solid and the feh --bg-color.
    assert desktop.ACCENT_HEX == "#06b8fd"
    assert len(desktop.ACCENT_HEX) == 7


def test_install_wrapper_path_value():
    assert desktop.INSTALL_WRAPPER_PATH == "/usr/local/bin/azarch-install"


def test_accent_hex_used_in_xinitrc_and_autostart():
    # The accent color is spliced into two builders; both must carry it verbatim.
    assert desktop.ACCENT_HEX in desktop.xinitrc()
    assert desktop.ACCENT_HEX in desktop.openbox_autostart()


# --- Every builder returns non-empty content --------------------------------

def test_all_builders_return_nonempty_str():
    # Catches an import-time f-string ValueError or an accidental None return: each
    # builder in the plan (plus bash_profile) must yield a non-empty string.
    for entry in desktop.emit_plan():
        content = entry["builder"]()
        assert isinstance(content, str)
        assert content.strip(), entry["dest"]


def test_xinitrc_execs_openbox_session():
    # startx hands the session to openbox-session (not bare openbox).
    assert "exec openbox-session" in desktop.xinitrc()
