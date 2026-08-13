"""The `azarch theme` system-wide dark/white toggle + the shipped dark defaults.

Az'arch has a system theme (dark by default) built on the EXISTING freedesktop / GTK
standard so downloaded apps that honour it are configured for free. These tests pin:

  * the `azarch theme` subcommand surface (--dark/-d, --white/-w, --help, bare status) as it
    is BUNDLED into the shipped /usr/local/bin/azarch script;
  * that the theme uses the standard signals (org.gnome.desktop.interface color-scheme +
    the GTK theme files with Adwaita-dark / Adwaita);
  * that the ISO's shipped DEFAULT files (patches.openbox GTK settings.ini + dconf keyfile)
    are DARK and stay byte-for-byte in lock-step with the CLI's theme.py dark output, so the
    shipped default and a later `azarch theme --dark` produce identical files;
  * that the kitty terminal is DELIBERATELY exempt (the theme never touches kitty).

The CLI is exercised via its bundle (packages.azarch.bundle.bundle_source) executed in one
namespace -- exactly the artifact the compiler ships -- so tests drive the real functions.
"""

from __future__ import annotations

import types

import pytest

from packages.azarch.bundle import bundle_source
from patches import openbox as desktop


def _cli():
    """Exec the bundled azarch CLI in a fresh module namespace (as shipped)."""
    mod = types.ModuleType("azarch_cli_theme_test")
    exec(compile(bundle_source(), "azarch_cli", "exec"), mod.__dict__)
    return mod


# --- the `azarch theme` subcommand surface ----------------------------------

def test_theme_is_a_dispatch_branch_in_main():
    # `azarch theme ...` must be a real top-level dispatch branch, and the top-level usage
    # must advertise it.
    src = desktop.azarch_cli()
    assert 'cmd == "theme"' in src
    assert "return cmd_theme(argv[1:])" in src
    assert "theme [--dark|--white]" in src   # advertised in usage()


def test_theme_help_prints_usage_and_exits_zero(capsys):
    cli = _cli()
    rc = cli.main(["theme", "--help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Usage: azarch theme" in out
    assert "--dark" in out and "--white" in out
    # both the long help header AND the standard mention are present
    assert "freedesktop color-scheme" in out


def test_theme_accepts_all_four_flag_spellings():
    # --dark/-d and --white/-w must both map to apply_theme(dark=True/False); assert the
    # dispatch in cmd_theme handles all four spellings.
    src = desktop.azarch_cli()
    assert '("--dark", "-d")' in src
    assert '("--white", "-w")' in src
    assert "apply_theme(dark=True)" in src
    assert "apply_theme(dark=False)" in src


def test_theme_dark_and_white_dispatch_without_touching_the_real_system(monkeypatch):
    # Drive `azarch theme --dark` / `--white` with apply_theme stubbed, so we prove the
    # dispatch wiring without mutating the host. bare `theme` -> status.
    cli = _cli()
    calls = []
    monkeypatch.setattr(cli, "apply_theme", lambda dark: calls.append(dark) or 0)
    monkeypatch.setattr(cli, "theme_status", lambda: calls.append("status") or 0)
    assert cli.main(["theme", "--dark"]) == 0
    assert cli.main(["theme", "-d"]) == 0
    assert cli.main(["theme", "--white"]) == 0
    assert cli.main(["theme", "-w"]) == 0
    assert cli.main(["theme"]) == 0
    assert calls == [True, True, False, False, "status"]


def test_theme_unknown_option_is_rc_two(capsys):
    cli = _cli()
    rc = cli.main(["theme", "--bogus"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown option" in err


def test_bare_theme_prints_current_status(monkeypatch, capsys):
    # `azarch theme` with no args prints the current theme. Stub current_theme so the test
    # does not depend on the host's dconf state.
    cli = _cli()
    monkeypatch.setattr(cli, "current_theme", lambda: "dark")
    monkeypatch.setattr(cli, "_gsettings_get", lambda *a: "")   # avoid shelling gsettings
    rc = cli.main(["theme"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "System theme: dark" in out


# --- the standard the theme uses --------------------------------------------

def test_theme_uses_freedesktop_color_scheme_standard():
    cli = _cli()
    assert cli.COLOR_SCHEME_DARK == "prefer-dark"
    assert cli.COLOR_SCHEME_LIGHT == "prefer-light"
    # apply_theme writes the color-scheme gsetting (the freedesktop appearance signal).
    src = desktop.azarch_cli()
    assert '"org.gnome.desktop.interface", "color-scheme"' in src


def test_theme_uses_adwaita_dark_and_light_gtk_themes():
    cli = _cli()
    assert cli.GTK_THEME_DARK == "Adwaita-dark"
    assert cli.GTK_THEME_LIGHT == "Adwaita"


def test_theme_gtk_settings_ini_dark_and_light():
    cli = _cli()
    dark = cli.gtk3_settings_ini(True)
    light = cli.gtk3_settings_ini(False)
    assert "gtk-application-prefer-dark-theme=1" in dark
    assert "gtk-theme-name=Adwaita-dark" in dark
    assert "gtk-application-prefer-dark-theme=0" in light
    assert "gtk-theme-name=Adwaita" in light and "Adwaita-dark" not in light


# --- kitty is DELIBERATELY exempt -------------------------------------------

def test_theme_never_touches_kitty():
    # The user's explicit exception: kitty keeps its own look. The theme must not CONFIGURE
    # kitty -- no write to a kitty config path and no signal to a running kitty. (A comment
    # DOCUMENTING the exemption is fine and expected; what must be absent is any kitty action.)
    cli = _cli()
    src = desktop.azarch_cli()
    # No kitty config path is ever written and no kitty process is signalled.
    assert ".config/kitty" not in src
    assert "pkill" not in src or "kitty" not in src.split("pkill", 1)[1][:40]
    # apply_theme's action list is openbox + gedit + vlc + librewolf + menu daemon only --
    # there is no kitty rethemer function defined.
    assert not hasattr(cli, "_retheme_kitty")
    assert not hasattr(cli, "kitty_theme_conf")


# --- shipped DARK defaults + lock-step with the CLI -------------------------

def test_shipped_gtk_defaults_are_dark():
    assert "gtk-application-prefer-dark-theme=1" in desktop.gtk3_settings_ini_default()
    assert "Adwaita-dark" in desktop.gtk3_settings_ini_default()
    assert "gtk-application-prefer-dark-theme=1" in desktop.gtk4_settings_ini_default()
    assert "Adwaita-dark" in desktop.gtkrc2_default()


def test_shipped_dconf_default_is_prefer_dark():
    kf = desktop.dconf_theme_keyfile()
    assert "color-scheme='prefer-dark'" in kf
    assert "[org/gnome/desktop/interface]" in kf
    # the profile wires the system `local` db beneath the user db
    prof = desktop.dconf_profile_user()
    assert "user-db:user" in prof and "system-db:local" in prof


def test_shipped_defaults_match_cli_dark_output_no_drift():
    # The ISO's shipped default files and a later `azarch theme --dark` MUST produce
    # identical files. Assert the openbox default builders equal the CLI theme.py dark output.
    cli = _cli()
    assert cli.gtk3_settings_ini(True) == desktop.gtk3_settings_ini_default()
    assert cli.gtk4_settings_ini(True) == desktop.gtk4_settings_ini_default()
    assert cli.gtkrc2(True) == desktop.gtkrc2_default()


# --- the live-flip helpers behave -------------------------------------------

def test_retheme_openbox_swaps_the_theme_name(tmp_path, monkeypatch):
    # _retheme_openbox rewrites the <theme><name> in the user's rc.xml between the dark and
    # light Az'arch theme names. Point the CLI's home at a temp dir with a seed rc.xml.
    cli = _cli()
    rc_dir = tmp_path / ".config" / "openbox"
    rc_dir.mkdir(parents=True)
    (rc_dir / "rc.xml").write_text(
        "<openbox_config><theme><name>Azarch-Dark</name></theme>"
        "<desktops><names><name>one</name></names></desktops></openbox_config>"
    )
    monkeypatch.setattr(cli, "_THEME_HOME", str(tmp_path))
    monkeypatch.setattr(cli.os.environ, "get", lambda *a, **k: None)  # no DISPLAY -> no reconfigure
    cli._retheme_openbox(dark=False)
    out = (rc_dir / "rc.xml").read_text()
    assert "<name>Azarch</name>" in out
    assert "<name>Azarch-Dark</name>" not in out
    # the desktop <name>one</name> must be UNTOUCHED (only the theme name is swapped)
    assert "<name>one</name>" in out
    # and back to dark
    cli._retheme_openbox(dark=True)
    assert "<name>Azarch-Dark</name>" in (rc_dir / "rc.xml").read_text()


def test_retheme_vlc_flips_only_the_palette_line(tmp_path, monkeypatch):
    cli = _cli()
    vlc_dir = tmp_path / ".config" / "vlc"
    vlc_dir.mkdir(parents=True)
    (vlc_dir / "vlcrc").write_text("[qt]\nqt-privacy-ask=0\nqt-palette-mode=2\n[core]\n")
    monkeypatch.setattr(cli, "_THEME_HOME", str(tmp_path))
    cli._retheme_vlc(dark=False)
    out = (vlc_dir / "vlcrc").read_text()
    assert "qt-palette-mode=1" in out
    assert "qt-privacy-ask=0" in out           # untouched


def test_retheme_librewolf_flips_theme_prefs(tmp_path, monkeypatch):
    cli = _cli()
    lw_dir = tmp_path / ".config" / "librewolf" / "librewolf"
    lw_dir.mkdir(parents=True)
    (lw_dir / "librewolf.overrides.cfg").write_text(
        '// x\n'
        'defaultPref("ui.systemUsesDarkTheme", 1);\n'
        'defaultPref("browser.theme.content-theme", 0);\n'
        'defaultPref("browser.theme.toolbar-theme", 0);\n'
        'defaultPref("layout.css.prefers-color-scheme.content-override", 0);\n'
    )
    monkeypatch.setattr(cli, "_THEME_HOME", str(tmp_path))
    cli._retheme_librewolf(dark=False)
    out = (lw_dir / "librewolf.overrides.cfg").read_text()
    assert 'defaultPref("ui.systemUsesDarkTheme", 0);' in out
    assert 'defaultPref("browser.theme.content-theme", 1);' in out
    assert 'defaultPref("layout.css.prefers-color-scheme.content-override", 1);' in out


def test_current_theme_defaults_dark_when_no_signal(tmp_path, monkeypatch):
    # With no gsettings value and no settings.ini, current_theme() falls back to the Az'arch
    # default: dark.
    cli = _cli()
    monkeypatch.setattr(cli, "_THEME_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_gsettings_get", lambda *a: "")
    assert cli.current_theme() == "dark"
