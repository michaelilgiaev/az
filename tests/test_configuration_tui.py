"""The bare-`azarch` TERMINAL UI (Theme / Wallpaper / Network).

Running `azarch` with NO arguments opens a full-screen text UI so a developer new to Linux
can tune the three things a fresh machine needs -- Theme, Wallpaper, Network -- with arrow
keys and a live status readout, a search box at the top and nav hints at the bottom.

These tests pin, against the BUNDLED shipped script (packages.azarch.bundle.bundle_source --
the exact /usr/local/bin/azarch artifact):

  * that bare `azarch` dispatches to the TUI (run_tui) and the top-level usage advertises it;
  * the MODEL that drives every screen -- build_menu() gives exactly Theme/Wallpaper/Network
    at the top, each screen's rows, and the search box (filter_items) -- with NO tty needed;
  * that the spec's specifics hold: the Wallpaper screen shows the wallpaper DIRECTORY path,
    the nav hints list arrows/enter/esc and `/` for search, and only the three subsystems
    are configurable;
  * that the network rows reuse the real command helpers (an action either descends to a
    sub-screen or, for an apply, calls the same function the subcommand calls);
  * graceful degradation: with no terminal, run_tui prints a pointer and returns 0 instead
    of trying to start curses (so `azarch </dev/null` / a pipe never throws).

The curses DRAWING itself is exercised separately by an interactive smoke run; here we keep
to the tty-free model so the suite stays deterministic.
"""

from __future__ import annotations

import types

from packages.azarch.bundle import bundle_source
from modifications import openbox as desktop


def _cli():
    """Exec the bundled azarch CLI in a fresh module namespace (as shipped)."""
    mod = types.ModuleType("azarch_cli_tui_test")
    exec(compile(bundle_source(), "azarch_cli", "exec"), mod.__dict__)
    return mod


def _menu():
    cli = _cli()
    return cli, cli.build_menu()


# --- dispatch wiring --------------------------------------------------------

def test_bare_azarch_dispatches_to_the_tui():
    """No-argument azarch must route to run_tui, and the top-level usage must mention the UI."""
    src = desktop.azarch_cli()
    assert 'cmd == ""' in src
    assert "return run_tui(argv)" in src
    assert "full-screen UI" in src  # advertised in usage()


def test_tui_is_bundled_before_cli():
    """tui.py must be bundled (so run_tui exists) and ordered before cli.py."""
    from packages.azarch.bundle import MODULE_ORDER
    assert "tui.py" in MODULE_ORDER
    assert MODULE_ORDER.index("tui.py") < MODULE_ORDER.index("cli.py")
    # And every module tui.py leans on is bundled ahead of it.
    for dep in ("theme.py", "wallpaper.py", "network.py"):
        assert MODULE_ORDER.index(dep) < MODULE_ORDER.index("tui.py")


# --- the menu model: exactly the three subsystems at the top ----------------

def test_top_level_is_theme_wallpaper_network_only():
    cli, menu = _menu()
    title, items, _sub = menu["main"]
    labels = [it.label for it in items]
    assert labels == ["Theme", "Wallpaper", "Network"]


def test_every_screen_reachable_and_no_extra_subsystems():
    """The only descendable screens are the three subsystems and the network sub-screens --
    nothing else creeps into the configurable surface."""
    cli, menu = _menu()
    assert set(menu.keys()) == {
        "main",
        "theme",
        "wallpaper",
        "network",
        "network.wifi",
        "network.wired",
        "network.bluetooth",
        "network.airplane",
        "network.firewall",
    }


def test_theme_screen_offers_dark_and_white():
    cli, menu = _menu()
    _t, items, _s = menu["theme"]
    assert [it.label for it in items] == ["Dark", "White"]
    # Both are applies (callables), not sub-screens.
    assert all(callable(it.action) for it in items)


# --- the spec's specifics ---------------------------------------------------

def test_wallpaper_screen_shows_the_directory_path():
    """PROMPT.md: 'Make sure wallpaper shows the directory path of where the wallpapers are
    saved.' The Wallpaper screen subtitle carries the wallpaper dir."""
    cli, menu = _menu()
    _t, _items, subtitle = menu["wallpaper"]
    assert cli.WALLPAPERS_SYSTEM_DIR in subtitle
    assert "/usr/share/wallpapers" in subtitle


def test_nav_hints_list_the_expected_keys():
    """The bottom nav hints must name arrows, enter, escape and `/` for search."""
    cli = _cli()
    scr = cli._Screen.__new__(cli._Screen)   # no curses needed to read the footer text
    scr.stack = ["main"]
    scr.searching = False
    foot = scr._footer()
    for token in ("up/down", "enter", "esc", "/ search"):
        assert token in foot
    # In the search box the footer explains how to leave it.
    scr.searching = True
    assert "filter" in scr._footer()


def test_search_filters_rows():
    """filter_items is the search box: case-insensitive match over label + status."""
    cli, menu = _menu()
    _t, items, _s = menu["network"]
    got = [it.label for it in cli.filter_items(items, "fire")]
    assert got == ["Firewall"]
    # empty query returns everything; a miss returns nothing.
    assert len(cli.filter_items(items, "")) == len(items)
    assert cli.filter_items(items, "nonesuch") == []


# --- rows reuse the real command helpers ------------------------------------

def test_network_rows_descend_into_subscreens():
    cli, menu = _menu()
    _t, items, _s = menu["network"]
    for it in items:
        assert isinstance(it.action, str)
        assert it.action in menu           # points at a real screen


def test_firewall_apply_row_calls_the_real_helper(monkeypatch):
    """Selecting 'Enable firewall' in the UI runs the SAME _firewall_enable the subcommand
    runs (the action is a thin wrapper over it)."""
    cli, menu = _menu()
    calls = []
    monkeypatch.setattr(cli, "_firewall_enable", lambda on: (calls.append(on) or 0))
    _t, items, _s = menu["network.firewall"]
    enable = next(it for it in items if it.label == "Enable firewall")
    result = enable.action()               # invoke the apply
    assert calls == [True]
    assert isinstance(result, str)


def test_theme_apply_row_calls_apply_theme(monkeypatch):
    cli, menu = _menu()
    calls = []
    monkeypatch.setattr(cli, "apply_theme", lambda dark: (calls.append(dark) or 0))
    _t, items, _s = menu["theme"]
    white = next(it for it in items if it.label == "White")
    white.action()
    assert calls == [False]


def test_status_probe_never_raises(monkeypatch):
    """A status callable that blows up must degrade to a readable cell, not crash the draw."""
    cli = _cli()
    def boom():
        raise RuntimeError("nope")
    it = cli._Item("X", "main", boom)
    assert "unavailable" in it.status_text()


# --- graceful degradation with no terminal ----------------------------------

def test_run_tui_without_tty_prints_pointer(monkeypatch, capsys):
    """No usable terminal -> run_tui must NOT start curses; it prints a pointer and rc 0."""
    cli = _cli()
    monkeypatch.setattr(cli, "_tty_ok", lambda: False)
    assert cli.run_tui([]) == 0
    out = capsys.readouterr().out
    assert "no interactive terminal" in out
    for sub in ("azarch theme", "azarch wallpaper", "azarch network"):
        assert sub in out


def test_bare_main_uses_run_tui(monkeypatch):
    """cli.main([]) must call run_tui (bare azarch == the UI)."""
    cli = _cli()
    called = {}
    monkeypatch.setattr(cli, "run_tui", lambda argv=None: (called.setdefault("hit", True), 0)[1])
    assert cli.main([]) == 0
    assert called.get("hit") is True
