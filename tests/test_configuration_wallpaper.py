"""The `azarch wallpaper` desktop-wallpaper picker + the session's pointer-aware paint.

Az'arch ships two wallpapers ("years" the default, "decades") under /usr/share/wallpapers.
`azarch wallpaper` switches between them, applies the choice to the running session with feh
immediately, and persists it to a per-user pointer file the OpenBox session reads on the next
login. These tests pin:

  * the `azarch wallpaper` subcommand surface (--years.png / --decades.png / --help / bare
    status) as it is BUNDLED into the shipped /usr/local/bin/azarch script;
  * the wallpaper image paths, which MUST stay in lock-step with modifications/openbox
    (WALLPAPERS_SYSTEM_DIR / WALLPAPER_IMAGE_RES / the ids) so the CLI and the emitted images
    cannot drift;
  * that applying persists the chosen image to the pointer file AND (with a stubbed feh)
    would repaint live;
  * that the OpenBox session (xinitrc + autostart) READS that pointer, falling back to the
    "years" default -- the mechanism that makes the choice survive a re-login.

The CLI is exercised via its bundle (packages.azarch.bundle.bundle_source) executed in one
namespace -- exactly the artifact the compiler ships -- so tests drive the real functions.
"""

from __future__ import annotations

import os
import types

from packages.azarch.bundle import bundle_source
from modifications import openbox as desktop


def _cli():
    """Exec the bundled azarch CLI in a fresh module namespace (as shipped)."""
    mod = types.ModuleType("azarch_cli_wallpaper_test")
    exec(compile(bundle_source(), "azarch_cli", "exec"), mod.__dict__)
    return mod


# --- the `azarch wallpaper` subcommand surface ------------------------------

def test_wallpaper_is_a_dispatch_branch_in_main():
    # `azarch wallpaper ...` must be a real top-level dispatch branch, and the top-level
    # usage must advertise it.
    src = desktop.azarch_cli()
    assert 'cmd == "wallpaper"' in src
    assert "return cmd_wallpaper(argv[1:])" in src
    assert "wallpaper [--years.png|--decades.png]" in src  # advertised in usage()


def test_wallpaper_help_prints_usage_and_exits_zero(capsys):
    cli = _cli()
    rc = cli.main(["wallpaper", "--help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Usage: azarch wallpaper" in out
    assert "--years.png" in out and "--decades.png" in out


def test_wallpaper_unknown_option_is_rc_two(capsys):
    cli = _cli()
    rc = cli.main(["wallpaper", "--bogus.png"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown option" in err


def test_wallpaper_options_map_to_the_two_ids():
    # --years.png / --decades.png are the two selectors; each maps to its wallpaper id.
    cli = _cli()
    assert cli._OPTION_TO_ID == {
        "--years.png": "years",
        "--decades.png": "decades",
    }


# --- lock-step with the shipped images (modifications/openbox) ---------------

def test_wallpaper_paths_match_openbox_constants():
    # The CLI's wallpaper dir/res/ids MUST equal what modifications/openbox emits, or the
    # CLI would point feh at a non-existent file.
    cli = _cli()
    assert cli.WALLPAPERS_SYSTEM_DIR == desktop.WALLPAPERS_SYSTEM_DIR
    assert cli.WALLPAPER_IMAGE_RES == desktop.WALLPAPER_IMAGE_RES
    assert cli.WALLPAPER_DEFAULT_ID == desktop.WALLPAPER_DEFAULT_ID
    assert set(cli.WALLPAPER_IDS) == {p["id"] for p in desktop.WALLPAPER_PACKAGES}
    # The default resolves to the SAME inner PNG openbox paints.
    assert cli._wallpaper_image("years") == desktop.WALLPAPER_IMAGE_FILE


def test_wallpaper_state_file_matches_openbox_pointer():
    # The pointer file the CLI writes and the pointer file the session reads must be the
    # SAME path, or a saved choice would never be honoured on the next login.
    cli = _cli()
    # _state_file() resolves off ~; compare against openbox's constant with ~ expanded to
    # the same home the session uses (/home/main).
    expected = desktop.WALLPAPER_POINTER_FILE  # /home/main/.config/azarch/wallpaper
    assert expected.endswith("/.config/azarch/wallpaper")
    # The CLI builds it under $HOME/.config/azarch/wallpaper.
    got = cli._state_file()
    assert got.endswith("/.config/azarch/wallpaper")


# --- applying: persist + (stubbed) live paint -------------------------------

def _point_home(cli, monkeypatch, home):
    """Point the CLI's ~ resolution at `home` without touching os.path.exists (mocking
    exists globally breaks os.makedirs). Only expanduser("~") is redirected."""
    real_expanduser = cli.os.path.expanduser
    monkeypatch.setattr(
        cli.os.path, "expanduser",
        lambda p: str(home) if p == "~" else real_expanduser(p))


def test_apply_persists_pointer_and_paints_live(tmp_path, monkeypatch):
    cli = _cli()
    _point_home(cli, monkeypatch, tmp_path)
    # Make the chosen image a REAL file so apply's existence check passes (no global
    # exists() stub, which would break os.makedirs).
    img = tmp_path / "decades.png"
    img.write_bytes(b"\x89PNG")
    monkeypatch.setattr(cli, "_wallpaper_image",
                        lambda wp_id: str(img) if wp_id == "decades" else "/nope")
    # Capture the live paint instead of shelling feh.
    painted = []
    monkeypatch.setattr(cli, "_apply_live", lambda image: painted.append(image))
    rc = cli.apply_wallpaper("decades")
    assert rc == 0
    # Pointer file written with the decades image path.
    pointer = tmp_path / ".config" / "azarch" / "wallpaper"
    assert pointer.is_file()
    assert pointer.read_text().strip() == str(img)
    # Live paint happened with the same image.
    assert painted == [str(img)]


def test_apply_missing_image_warns_but_persists(tmp_path, monkeypatch, capsys):
    cli = _cli()
    _point_home(cli, monkeypatch, tmp_path)
    # Point the image at a path that does NOT exist (real check, no exists() stub).
    missing = tmp_path / "does_not_exist.png"
    monkeypatch.setattr(cli, "_wallpaper_image", lambda wp_id: str(missing))
    monkeypatch.setattr(cli, "_apply_live", lambda image: (_ for _ in ()).throw(
        AssertionError("must not paint a missing image")))
    rc = cli.apply_wallpaper("years")
    assert rc == 1
    err = capsys.readouterr().err
    assert "image not found" in err
    # Still persisted so a later-installed image is honoured.
    pointer = tmp_path / ".config" / "azarch" / "wallpaper"
    assert pointer.read_text().strip() == str(missing)


def test_bare_wallpaper_prints_current_status(tmp_path, monkeypatch, capsys):
    # `azarch wallpaper` with no args prints the current wallpaper. With no pointer file it
    # reports the "years" default.
    cli = _cli()
    _point_home(cli, monkeypatch, tmp_path)
    rc = cli.main(["wallpaper"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Wallpaper: years" in out


def test_current_id_reflects_a_saved_decades_choice(tmp_path, monkeypatch):
    cli = _cli()
    _point_home(cli, monkeypatch, tmp_path)
    cfg = tmp_path / ".config" / "azarch"
    cfg.mkdir(parents=True)
    (cfg / "wallpaper").write_text(cli._wallpaper_image("decades") + "\n")
    assert cli._current_id() == "decades"
    assert cli._current_image() == cli._wallpaper_image("decades")


# --- the session reads the pointer (persistence across re-login) -------------

def test_xinitrc_and_autostart_read_the_pointer_with_years_fallback():
    # Both the no-flash pre-paint (xinitrc) and the autostart repaint read the per-user
    # pointer and fall back to the shipped "years" default.
    for out in (desktop.xinitrc(), desktop.openbox_autostart(),
                desktop.openbox_autostart_installed()):
        assert 'cat "$HOME/.config/azarch/wallpaper"' in out
        assert "|| _azwp='" + desktop.WALLPAPER_IMAGE_FILE + "'" in out
        assert 'feh --no-fehbg --bg-fill "$_azwp"' in out
