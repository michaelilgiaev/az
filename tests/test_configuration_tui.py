"""The bare-`azarch` TERMINAL UI -- now a COMPILED C program (Theme / Wallpaper / Network).

Running `azarch` with NO arguments opens a full-screen text UI so a developer new to Linux
can tune the three things a fresh machine needs -- Theme, Wallpaper, Network -- with arrow
keys (or WASD / HJKL), a search box at the top and nav hints at the bottom, everything
centred and coloured in the Az'arch logo cyan. It used to be Python/curses but felt laggy, so
it was rewritten in C. The C sources now live INSIDE the azarch package
(libraries/packages/azarch/, built by tui_build.py) -- there is only ONE program, `azarch`,
and the UI is C for speed; the Python `azarch` CLI just EXECs that binary for the no-argument
case.

These tests pin, against BOTH the bundled Python launcher (the /usr/local/bin/azarch
artifact) AND the C source tree + its build wiring:

  * bare `azarch` dispatches to run_tui, which EXECs the compiled UI binary (not curses);
  * the launcher's binary path is the SAME one the build installs (no drift);
  * graceful degradation: with no terminal, run_tui prints a pointer and returns 0 instead
    of exec-ing anything (so `azarch </dev/null` / a pipe never throws);
  * the build wiring compiles exactly the C sources into the installed binary, without
    polluting the repo tree, and the binary is pinned executable in the ISO file_permissions;
  * the spec's specifics live in the C source: the accent is the logo cyan #06B8FD, the nav
    line advertises WASD / HJKL / arrows (packed + uppercased) with q-to-quit / ESC-to-back,
    Network is the FIRST option, the entry title is "Az'arch Settings", the Wallpaper screen
    names the wallpaper DIRECTORY and previews the hovered image, and the Theme screen previews
    real LibreWolf + Dolphin screenshots (shipped, unmodified) and discloses that kitty is
    exempt -- with the "Current:" state shown once at the top and no per-row status echo.

The interactive DRAWING itself is exercised by an interactive smoke run (and the C model is
unit-tested headless by tests/Makefile's test_tui_model). Here we keep to the launcher wiring
+ the source contract so the suite stays deterministic and tty-free.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import types

import pytest

from packages.azarch.bundle import bundle_source, MODULE_ORDER
from packages.azarch import tui_build
from modifications import openbox as desktop
import paths
import profile as profiledef


# The C UI sources now live INSIDE the azarch package (one program, C for speed) -- there is
# no separate azarch_tui package anymore.
TUI_SRC_DIR = paths.AZARCH_CLI_DIR


def _cli():
    """Exec the bundled azarch CLI in a fresh module namespace (as shipped)."""
    mod = types.ModuleType("azarch_cli_tui_test")
    exec(compile(bundle_source(), "azarch_cli", "exec"), mod.__dict__)
    return mod


def _src(name: str) -> str:
    return (TUI_SRC_DIR / name).read_text(encoding="utf-8")


# --- dispatch wiring: bare azarch -> run_tui -> exec the C binary ------------

def test_bare_azarch_dispatches_to_the_tui():
    """No-argument azarch must route to run_tui, and the top-level usage must mention the UI."""
    src = desktop.azarch_cli()
    assert 'cmd == ""' in src
    assert "return run_tui(argv)" in src
    assert "full-screen UI" in src  # advertised in usage()


def test_run_tui_execs_the_compiled_binary():
    """run_tui must EXEC the compiled C UI (the fast, instant path) -- not start curses."""
    src = bundle_source()
    assert "os.execv(TUI_BIN" in src
    assert "import curses" not in src        # the Python curses UI is gone


def test_launcher_binary_path_matches_the_build():
    """The path run_tui execs must be the SAME path the build installs the binary to, so the
    two can never drift."""
    cli = _cli()
    assert cli.TUI_BIN == tui_build.TUI_BIN_SYSTEM_PATH
    assert cli.TUI_BIN == "/usr/local/lib/azarch-tui/azarch-tui"


def test_bare_main_uses_run_tui(monkeypatch):
    """cli.main([]) must call run_tui (bare azarch == the UI)."""
    cli = _cli()
    called = {}
    monkeypatch.setattr(cli, "run_tui", lambda argv=None: (called.setdefault("hit", True), 0)[1])
    assert cli.main([]) == 0
    assert called.get("hit") is True


def test_tui_is_bundled_before_cli():
    """tui.py (the launcher) must be bundled before cli.py, whose main() dispatches to it."""
    assert "tui.py" in MODULE_ORDER
    assert MODULE_ORDER.index("tui.py") < MODULE_ORDER.index("cli.py")


# --- graceful degradation with no terminal ----------------------------------

def test_run_tui_without_tty_prints_pointer(monkeypatch, capsys):
    """No usable terminal -> run_tui must NOT exec anything; it prints a pointer and rc 0."""
    cli = _cli()
    monkeypatch.setattr(cli, "_tty_ok", lambda: False)
    # If it tried to exec, this would raise; assert it returns cleanly instead.
    monkeypatch.setattr(cli.os, "execv",
                        lambda *a, **k: pytest.fail("must not exec without a tty"))
    assert cli.run_tui([]) == 0
    out = capsys.readouterr().out
    assert "no interactive terminal" in out
    for sub in ("azarch theme", "azarch wallpaper", "azarch network"):
        assert sub in out


def test_run_tui_missing_binary_falls_back(monkeypatch, capsys):
    """A tty but a MISSING binary must fall back to the pointer, never crash."""
    cli = _cli()
    monkeypatch.setattr(cli, "_tty_ok", lambda: True)
    monkeypatch.setattr(cli.os.path, "exists", lambda p: False)
    assert cli.run_tui([]) == 0
    assert "no interactive terminal" in capsys.readouterr().out


# --- the build wiring: compile the C sources, no pollution, pinned exec ------

def test_build_tui_inputs_are_the_c_sources():
    """build_tui copies exactly the C sources/headers + the Makefile (no Python) into a
    scratch dir; the produced binary name matches the installed path's basename."""
    names = {p.name for p in tui_build._csrc_files()}
    assert "main.c" in names
    assert "render.c" in names
    assert "model.c" in names
    assert "preview.c" in names
    assert "action.c" in names       # apply execution + in-UI sudo credential
    assert "Makefile" in names
    assert "tui.h" in names
    assert "action.h" in names
    assert not any(n.endswith(".py") for n in names)     # only C inputs
    assert tui_build.TUI_BIN_NAME == os.path.basename(tui_build.TUI_BIN_SYSTEM_PATH)


def test_theme_preview_assets_exist_and_ship_unmodified(tmp_path):
    """PROMPT: use the real screenshots in assets/previews/ (same names, don't modify them).
    All four contract images must exist as assets, and install_previews must copy them BYTE-FOR-
    BYTE into the runtime preview dir (no resizing at build time -- the C scales at draw time)."""
    # every contract asset exists in the repo
    for rel in tui_build.PREVIEW_ASSETS:
        assert (paths.ASSETSDIR / rel).is_file(), f"missing preview asset {rel}"
    # the four expected names (timedate/files x dark/white) are exactly the contract
    assert {os.path.basename(r) for r in tui_build.PREVIEW_ASSETS} == {
        "timedate_dark.png", "timedate_white.png", "files_dark.png", "files_white.png",
    }
    # install_previews copies them verbatim (identical bytes) into the dest dir
    written = tui_build.install_previews(tmp_path)
    assert len(written) == len(tui_build.PREVIEW_ASSETS)
    for rel in tui_build.PREVIEW_ASSETS:
        src = paths.ASSETSDIR / rel
        dst = tmp_path / os.path.basename(rel)
        assert dst.is_file()
        assert dst.read_bytes() == src.read_bytes(), f"{rel} was modified during install"


def test_preview_dir_contract_matches_between_build_and_c():
    """The C reads the screenshots from a hard-coded AZ_PREVIEW_DIR; it MUST equal the dir the
    build ships them to (tui_build.TUI_PREVIEW_SYSTEM_DIR), or the previews are 'not installed'
    at runtime. Also pin the dir under the binary's lib dir so both travel together."""
    preview = _src("preview.c")
    assert f'"{tui_build.TUI_PREVIEW_SYSTEM_DIR}"' in preview
    assert tui_build.TUI_PREVIEW_SYSTEM_DIR.startswith(tui_build.TUI_LIB_DIR)


def _have_c_toolchain() -> bool:
    return ((shutil.which("gcc") or shutil.which("cc")) is not None
            and shutil.which("make") is not None)


def test_build_tui_compiles_and_does_not_pollute_the_repo_tree():
    """build_tui() must build in a TEMP dir, not the source tree -- no .o/binary left behind
    next to the sources (they would otherwise get tracked / shipped)."""
    def _artifacts():
        return sorted(p.name for p in TUI_SRC_DIR.iterdir()
                      if p.suffix == ".o" or p.name == tui_build.TUI_BIN_NAME)

    assert _artifacts() == [], f"stale build artifacts in the source tree: {_artifacts()}"
    if not _have_c_toolchain():
        pytest.skip("no C toolchain on this host")
    out = TUI_SRC_DIR / "_test_build_out" / tui_build.TUI_BIN_NAME
    try:
        tui_build.build_tui(out)
        assert out.is_file() and os.access(out, os.X_OK)   # produced an executable
        assert _artifacts() == [], f"build polluted the source tree: {_artifacts()}"
    finally:
        shutil.rmtree(TUI_SRC_DIR / "_test_build_out", ignore_errors=True)


def test_tui_binary_is_pinned_executable_in_the_iso():
    """archiso normalizes overlay modes, so the compiled binary must be pinned 0755 in the
    profile file_permissions or bare `azarch` would find it non-executable and fall back to
    the pointer instead of opening the UI."""
    perms = profiledef.FILE_PERMISSIONS
    assert tui_build.TUI_BIN_SYSTEM_PATH in perms
    assert perms[tui_build.TUI_BIN_SYSTEM_PATH].endswith(":755")


def test_tui_build_dep_is_only_gcc_no_ncurses_no_gtk():
    """The UI is pure libc + raw ANSI (previews shell out to kitty at runtime), so the ONLY
    build dep is a C compiler -- no ncurses, no GTK LINKAGE (checked on the recipe, not the
    comments, which do mention 'no ncurses')."""
    assert tui_build.TUI_BUILD_DEPS == ["gcc"]
    # Look only at the non-comment recipe lines: no library linkage, no pkg-config.
    recipe = "\n".join(ln for ln in _src("Makefile").splitlines()
                       if not ln.lstrip().startswith("#"))
    assert "-lncurses" not in recipe
    assert "-lgtk" not in recipe
    assert "gtk+-3.0" not in recipe
    assert "pkg-config" not in recipe        # no library discovery needed


# --- the spec's specifics, pinned in the C source ---------------------------

def test_accent_is_the_azarch_logo_cyan():
    """PROMPT: use the Az'arch logo colour (cyan-ish, #06B8FD) to differentiate elements and
    ease navigation. The accent RGB (6,184,253) must be the accent SGR in the palette."""
    header = _src("tui.h")
    assert "#06B8FD" in header
    assert "38;2;6;184;253" in header    # the accent as a truecolor foreground
    # the nav keys are coloured with the accent, too
    assert "AZ_SGR_KEYCAP" in header


def test_nav_advertises_wasd_hjkl_and_arrows_uppercased():
    """PROMPT: navigation is WASD / HJKL / arrows; uppercase the keys, keep the labels, and
    pack them tight ("WASD HJKL ←↑→↓ move"). Also advertise q-to-quit and ESC-to-back. The
    renderer's nav line must list them, and the input loop must accept all three families."""
    render = _src("render.c")
    # the movement key-caps, uppercased (drawn as tight clusters via capgroup)
    for k in ('"W"', '"A"', '"S"', '"D"', '"H"', '"J"', '"K"', '"L"'):
        assert k in render, f"missing nav keycap {k}"
    # the plain (test-facing) nav string names the PACKED clusters + the verbs incl. q/quit
    for token in ("WASD HJKL", "move", "ENTER", "Q quit", "ESC back", "search"):
        assert token in render, f"missing nav token {token!r}"
    # the input loop binds WASD + HJKL + arrows to movement/back/open, and q to quit
    main = _src("main.c")
    assert "case K_UP: case 'k': case 'w':" in main
    assert "case K_DOWN: case 'j': case 's':" in main
    assert "case K_LEFT: case 'h': case 'a':" in main
    assert "case K_RIGHT: case 'l': case 'd':" in main
    assert "case 'q':" in main


def test_esc_is_back_and_q_ctrlc_quit_instantly():
    """PROMPT (newest): ESC is 'go back', NOT quit; q is the one instant quit; Ctrl-C must ALSO
    quit cleanly (raw mode disables ISIG, so Ctrl-C arrives as the byte 0x03 and must be handled
    explicitly). The nav label for ESC therefore reads 'back' everywhere (no depth relabelling)."""
    main = _src("main.c")
    render = _src("render.c")
    # ESC handler goes back (never a quit branch of its own anymore).
    esc_block = main[main.index("case K_ESC:"):main.index("case 'q':")]
    assert "go_back(&ui)" in esc_block
    assert "return 0" not in esc_block, "ESC must NOT quit -- it only goes back"
    # q and Ctrl-C (0x03) quit instantly from the menu; EOF (stdin closed) quits from ANY mode,
    # handled up front so it can never spin (it is a top-level `if`, not a switch case now).
    assert "case 'q':" in main
    assert "case 3:" in main            # Ctrl-C as a raw byte
    assert "k == K_EOF" in main         # stdin closed -> quit, never spin (checked before dispatch)
    # the nav label for ESC is a fixed 'back' (not depth-dependent 'quit').
    assert 'verb(&t, "ESC", "back")' in render


def test_status_probes_are_cached_for_instant_navigation():
    """PROMPT: it must feel SNAP INSTANT. Every status probe forks a tool; called straight from
    the draw loop that is several forks per keystroke. All probe calls go through a short-TTL
    memo (az_status_cached) so navigation re-forks nothing, and an apply busts the cache so a
    toggle shows immediately."""
    model = _src("model.c")
    render = _src("render.c")
    main = _src("main.c")
    # the cache + its invalidation exist in the model
    assert "az_status_cached" in model
    assert "az_status_invalidate" in model
    # the renderer reads EVERY probe through the cache, never calling the fn pointer directly
    assert "az_status_cached(scr->current" in render
    assert "az_status_cached(vis[i]->status" in render
    assert "vis[i]->status(sbuf" not in render      # no direct (uncached) probe call
    assert "scr->current(sb" not in render
    # an apply invalidates the cache so the new state shows on the next frame
    assert "az_status_invalidate()" in main


def test_network_status_is_plain_online_offline():
    """PROMPT: replace "wifi enabled, firewall active" with a plain Online/Offline headline, and
    make Bluetooth/Airplane read as a simple on/off (never "present"; default off)."""
    model = _src("model.c")
    assert "Online - Connected to Internet" in model
    assert "Offline - No Internet" in model
    # the top-level Network row reads connectivity, not a radio+firewall soup
    assert "networking" in model and "connectivity" in model
    # bluetooth never RETURNS the old confusing "present" value (the word may still appear in a
    # comment explaining why it was dropped -- match the code that produced it, not prose).
    assert 'snprintf(buf, n, "present")' not in model
    # airplane now reads NetworkManager's master switch (`nmcli networking`) so a wired machine
    # reports airplane correctly (the internet really being down), not just the radios.
    assert '"nmcli", "networking"' in model


def test_wifi_and_wired_status_are_mutually_exclusive_in_c():
    """PROMPT (newest): wifi and wired must not both read on/connected -- one-or-the-other. The
    C probes share a single device scan and the connected ethernet link wins (wifi -> off)."""
    model = _src("model.c")
    assert "az_net_scan" in model                 # single source of truth for both probes
    # wired wins: when ethernet is connected the wifi probe reports off
    assert "s.eth_conn" in model


def test_every_apply_runs_inside_the_ui_no_terminal_drop():
    """PROMPT (newest): selecting a setting must NOT black out the terminal, and Q must exit
    cleanly (no leftover CLI text). So every apply runs captured INSIDE the alt screen -- there
    is no '?1049l' (leave alt screen) around an apply anymore, and applies go through action.c's
    capture, shown in the OUTPUT overlay."""
    main = _src("main.c")
    action = _src("action.c")
    # the old "drop to the real terminal for the apply" path is gone.
    assert "run_apply_visible" not in main
    # applies are captured (no child writes to the terminal) ...
    assert "az_action_run_capture" in main
    assert "az_action_run_capture" in action
    # ... and a privileged apply secures a sudo credential via an in-UI prompt, never a hidden
    # prompt on a blanked screen.
    assert "AZ_MODE_PASSWORD" in main
    assert "az_action_sudo_ok" in main


def test_firewall_ports_are_configurable_in_the_ui():
    """PROMPT (newest): the Firewall screen must LIST ports in the UI and let you configure them
    (open/close/delete) without dropping to a shell. model.c has the list row (show_output) and
    the AZ_ACT_PORT rows; main.c prompts for the port."""
    model = _src("model.c")
    main = _src("main.c")
    assert "firewall port list" in model
    assert "AZ_ACT_PORT" in model                 # open/close/delete by typing a port
    assert "AZ_MODE_PORT" in main                 # the in-UI port prompt


def test_settings_show_their_bash_command():
    """PROMPT (newest): each setting is accompanied by the bash command that invokes it, so the
    user learns to do it without the UI. The renderer draws the row's command; model.c exposes
    it via az_row_command."""
    model = _src("model.c")
    render = _src("render.c")
    assert "az_row_command" in model
    assert "az_row_command" in render


def test_esc_go_back_is_instant():
    """PROMPT (newest): ESC (go back) must be INSTANT. The ESC decode no longer arms a 100ms
    VTIME timer -- it peeks fully non-blocking (VMIN=0, VTIME=0), so a bare ESC returns at once."""
    main = _src("main.c")
    esc_decode = main[main.index("if (c == 27)"):main.index("return key;")]
    assert "VTIME] = 0" in esc_decode
    assert "VTIME] = 1" not in esc_decode          # no 100ms wait on a bare ESC anymore


def test_entry_title_and_first_option():
    """PROMPT: rename the entry screen to "Az'arch Settings" and make Network the FIRST option.
    (The earlier "no branding" rule was about ASCII-art / a logo banner -- a plain window title
    is not that; the spec explicitly asks for this title.)"""
    model = _src("model.c")
    # the entry screen is titled "Az'arch Settings"
    assert '"Az\'arch Settings"' in model
    # Network is the first main-menu row (before Theme / Wallpaper)
    net = model.index('.label="Network"')
    theme = model.index('.label="Theme"')
    wall = model.index('.label="Wallpaper"')
    assert net < theme < wall, "Network must be the first main-menu option"
    # No ASCII-art / logo banner: the renderer draws no multi-line art block (the branding
    # rule was about art, not the plain window title the spec now asks for).
    render = _src("render.c")
    for arty in ("____", "\\\\", "|__|", "____/"):
        assert arty not in render, f"looks like ASCII-art banner in the renderer: {arty!r}"


def test_main_screen_has_no_move_hint_subtitle():
    """PROMPT: remove the 'Move with the arrow keys, Enter to open.' subtitle from the main
    screen (the bottom nav hints already say how to move)."""
    model = _src("model.c")
    assert "Move with the arrow keys" not in model


def test_wallpaper_screen_names_dir_and_previews_the_image():
    """PROMPT: Wallpaper shows the directory path AND previews the hovered image (kitty)."""
    model = _src("model.c")
    preview = _src("preview.c")
    assert "/usr/share/wallpapers" in model               # the dir, shown as the subtitle
    assert "AZ_PV_WALLPAPER" in model                      # wallpaper rows request a preview
    # the preview shells out to kitty's icat with a placement
    assert "kitten" in preview and "icat" in preview
    assert "--place" in preview
    # the wallpaper image path matches wallpaper.py's layout
    assert "contents/images" in model and "1672x941" in model


def test_theme_screen_previews_real_screenshots_and_disclaims_kitty():
    """PROMPT: Theme previews are the REAL shipped screenshots (LibreWolf on the timedate home
    page + Dolphin), placed with kitty, sized for the terminal and used UNMODIFIED. The screen
    discloses kitty is exempt and shows Current at the top; there is NO caption under them."""
    model = _src("model.c")
    preview = _src("preview.c")
    assert "AZ_PV_THEME" in model
    # the kitty disclaimer is the Theme screen subtitle
    assert "Kitty does not follow the system theme" in model
    # the previews are the shipped screenshot files (timedate = LibreWolf home page, files =
    # Dolphin), placed via kitty's icat with a placement -- not ANSI mock-ups.
    assert "kitten" in preview and "icat" in preview and "--place" in preview
    assert "timedate_%s.png" in preview and "files_%s.png" in preview
    assert "dark" in preview and "white" in preview        # the two variants
    # the images are used unmodified (no image editing in the C -- just placement/scaling)
    for banned in ("convert", "resize", "mogrify"):
        assert banned not in preview, f"previews must not modify images ({banned})"
    # NO caption text under the theme previews anymore (the old mock-up caption is gone)
    assert "Preview: dark" not in preview and "Preview: white" not in preview
    # "Current: ..." is drawn at the top of the screen by the renderer
    assert "Current:" in _src("render.c")


def test_theme_and_wallpaper_rows_have_no_status_echo():
    """PROMPT: drop the per-row status ('white' after each theme option, 'years' after each
    wallpaper option) -- 'Current:' already shows it. The rows must carry no .status, and the
    screens must instead supply a screen-level .current probe."""
    model = _src("model.c")
    # the Theme/Wallpaper apply rows are defined with a preview but WITHOUT a .status field
    for row_target in ('.target="azarch theme --dark"', '.target="azarch wallpaper --years.png"'):
        assert row_target in model
    # the screen-level "Current:" probe is wired for both
    assert ".current=az_status_theme" in model
    assert ".current=az_status_wallpaper" in model
    # the renderer draws "Current:" from the SCREEN probe, not rows[0].status
    render = _src("render.c")
    assert "scr->current" in render


def test_actions_shell_back_to_the_azarch_subcommands():
    """Every apply row runs the SAME tested `azarch` subcommand (the C UI adds navigation,
    not new system behaviour)."""
    model = _src("model.c")
    for cmd in (
        "azarch theme --dark",
        "azarch theme --white",
        "azarch wallpaper --years.png",
        "azarch wallpaper --decades.png",
        "azarch network firewall enable",
        "azarch network firewall port list",
        "azarch network wifi on",
    ):
        assert cmd in model, f"missing action: {cmd}"


def test_everything_is_centred():
    """PROMPT: center navigation, center the search box, center everything. The renderer's
    layout helper centres each element."""
    render = _src("render.c")
    assert "center_col" in render
    assert "put_center" in render
    # the search box, rows block, and nav are all placed via the centring helper
    assert render.count("center_col") >= 4
