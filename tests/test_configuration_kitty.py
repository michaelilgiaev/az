"""modifications.kitty -- the kitty terminal-icon patch (clean "> _" glyph).

Why these tests matter: compiler._emit_apps never inspects builder CONTENT for kitty; it
iterates emit_plan() and copies/renders/removes each dest by its keys (asset/render/remove)
and mode/owner. So the plan IS the contract:
  * the scalable SVG entry must COPY our repo asset (assets/icons/kitty.svg) to the system
    scalable path -- the single source of truth for the icon;
  * the two PNG entries MUST carry "remove": True (or the stale cat PNGs outrank our SVG
    and the cat comes back);
  * the titlebar entry must RENDER that same asset to ~/.config/kitty/kitty.app.png (owner
    "home") so the open kitty window's titlebar icon is the clean glyph too.
The asset itself must be a well-formed, black-and-white "> _" SVG (no color, no window
chrome, no cat). These tests pin the plan shape, the asset path/wiring, and the asset SVG.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import paths
from modifications import kitty


def _asset_svg_text() -> str:
    return (paths.ASSETSDIR / kitty.ICON_ASSET).read_text(encoding="utf-8")


def test_emit_plan_has_five_entries():
    # SVG asset copy + two PNG removals + the titlebar PNG render + the kitty.conf font
    # config. A dropped entry either fails to replace the cat SVG, leaves a stale PNG that
    # outranks it, drops the in-window titlebar icon, or drops the font-size config.
    assert len(kitty.emit_plan()) == 5


def test_emit_plan_entries_have_expected_keys():
    for entry in kitty.emit_plan():
        # Every entry has the four base keys; extras (asset/render/remove) are per-entry.
        assert {"builder", "dest", "mode", "owner"} <= set(entry)


def test_icon_asset_exists_and_is_the_single_source_of_truth():
    # The icon lives as a real repo asset (git-tracked), referenced by path like fastfetch's
    # assets -- not inlined in the module. It must exist on disk.
    assert kitty.ICON_ASSET == "icons/kitty.svg"
    assert (paths.ASSETSDIR / kitty.ICON_ASSET).is_file()


def test_svg_entry_copies_the_asset_to_scalable_apps():
    # The scalable system icon is our asset SVG, copied verbatim (asset entry, no builder).
    entry = next(e for e in kitty.emit_plan() if e["dest"] == kitty.ICON_SVG_PATH)
    assert entry["dest"] == "/usr/share/icons/hicolor/scalable/apps/kitty.svg"
    assert entry["builder"] is None
    assert entry.get("asset") == kitty.ICON_ASSET
    assert entry["mode"] == 0o644
    assert entry["owner"] == "root"


def test_png_entries_are_removals_of_the_two_stale_icons():
    removals = [e for e in kitty.emit_plan() if e.get("remove")]
    assert len(removals) == 2
    dests = {e["dest"] for e in removals}
    assert dests == {kitty.ICON_PNG_HICOLOR_PATH, kitty.ICON_PNG_PIXMAP_PATH}
    # Removal entries have no builder (nothing to write) and stay root-owned system paths.
    for e in removals:
        assert e["builder"] is None
        assert e["owner"] == "root"


def test_titlebar_icon_is_rendered_from_the_asset_into_home():
    # The in-window titlebar icon (kitty.app.png) is rasterized from the SAME asset and is a
    # HOME file (owner "home") so it is chowned + skel-mirrored for the installed user.
    entry = next(e for e in kitty.emit_plan() if e["dest"] == kitty.KITTY_APP_ICON_PATH)
    assert entry["dest"] == "/home/main/.config/kitty/kitty.app.png"
    assert entry["dest"].startswith(kitty.HOME + "/")
    assert entry["builder"] is None
    assert entry.get("render") == {"asset": kitty.ICON_ASSET, "size": kitty.KITTY_APP_ICON_SIZE}
    # X11 caps the OS-window icon at 128x128: kitty REFUSES a larger one ("window icon is
    # too large (256x256). On X11 max window icon size is: 128x128") and the WM then shows a
    # broken/default icon -- exactly the titlebar bug reported. So the render MUST be 128px.
    assert kitty.KITTY_APP_ICON_SIZE == 128
    assert entry["owner"] == "home"


def test_kitty_conf_sets_font_size_in_home():
    # A partial kitty.conf (owner "home", so chowned + skel-mirrored) sets ONLY font_size,
    # to the STOCK baseline from the single scale source (matching gedit's editor font size).
    # kitty renders a pt font at the screen DPI, so the GLOBAL SCALE's Xft.dpi channel bumps it
    # (at 1.35 it renders ~= the old hardcoded 18pt). kitty.conf syntax is `<name> <value>`.
    from modifications import scale
    entry = next(e for e in kitty.emit_plan() if e["dest"] == kitty.KITTY_CONF_PATH)
    assert entry["dest"] == "/home/main/.config/kitty/kitty.conf"
    assert entry["dest"].startswith(kitty.HOME + "/")
    assert entry["builder"] is kitty.kitty_conf
    assert entry["owner"] == "home"
    assert entry["mode"] == 0o644
    # DERIVES from scale (not a raw 18 -- that would be a second hardcoded size).
    assert kitty.KITTY_FONT_SIZE == scale.TERMINAL_EDITOR_FONT_STOCK
    assert kitty.KITTY_FONT_SIZE != 18
    out = kitty.kitty_conf()
    assert f"font_size {kitty.KITTY_FONT_SIZE}" in out
    # kitty.conf uses space-separated options, not INI '=' assignments.
    assert "font_size=" not in out


def test_kitty_conf_font_size_matches_gedit():
    # The whole point of pinning both: the terminal and the editor render at the same size.
    from modifications import gedit
    assert kitty.KITTY_FONT_SIZE == gedit.GEDIT_FONT_SIZE


def test_icon_asset_is_wellformed_xml():
    # A broken SVG makes the icon loader fall back to a generic icon; parse it to prove the
    # element tree is valid. (XML comments must not contain "--"; that gotcha raised during
    # authoring, exactly as this asserts against.)
    ET.fromstring(_asset_svg_text())


def test_icon_asset_is_a_clean_bw_terminal_not_a_cat():
    # The whole point (user's exact ask): a terminal-window mark -- a BLACK window shape with
    # a WHITE "> _" prompt inside (a chevron ">" and an underscore "_" cursor). The icon is
    # drawn as filled <path>s (converted to FontForge geometry): a black window path plus the
    # white prompt paths. Black and white ONLY, no color, no cat. Assert the structural bits
    # are present and nothing colored/mascot slipped in.
    svg = _asset_svg_text().lower()
    assert "<svg" in svg and "</svg>" in svg
    assert 'viewbox="0 0 256 256"' in svg
    # The glyph is path-based: the black window + the white chevron ">" + the white
    # underscore "_" cursor are three filled paths.
    assert svg.count("<path") >= 3
    assert "cat" not in svg and "whisker" not in svg
    # Black and white only: a black window fill and a white prompt, and NO stray colors (the
    # old rejected icon used red/yellow/green titlebar dots + a green prompt).
    assert "#000000" in svg         # black window path
    assert "#ffffff" in svg         # white prompt "> _"
    for banned in ("#e06c75", "#e5c07b", "#98c379", "#3fd07f", "#1b1f24", "#2b3038"):
        assert banned not in svg


def _path_bbox(d: str) -> tuple[float, float, float, float]:
    """Rough bounding box (min_x, min_y, max_x, max_y) of an SVG path's on-curve points.

    Walks the M/L/C/H/V commands (absolute and relative) tracking the current point and
    recording each segment endpoint. Control points are ignored, which is fine for an
    aspect-ratio (wider-vs-taller) check on these closed glyph outlines."""
    import re as _re
    toks = _re.findall(r"[A-Za-z]|-?\d*\.?\d+", d)
    xs: list[float] = []
    ys: list[float] = []
    i = 0
    cx = cy = 0.0
    cmd = None

    def take(n: int) -> list[float]:
        nonlocal i
        vals = [float(toks[i + k]) for k in range(n)]
        i += n
        return vals

    while i < len(toks):
        t = toks[i]
        if _re.match(r"[A-Za-z]$", t):
            cmd = t
            i += 1
            continue
        if cmd in ("M", "L"):
            cx, cy = take(2)
        elif cmd in ("m", "l"):
            dx, dy = take(2); cx += dx; cy += dy
        elif cmd == "C":
            _x1, _y1, _x2, _y2, cx, cy = take(6)
        elif cmd == "c":
            _dx1, _dy1, _dx2, _dy2, dx, dy = take(6); cx += dx; cy += dy
        elif cmd == "H":
            cx, = take(1)
        elif cmd == "h":
            dx, = take(1); cx += dx
        elif cmd == "V":
            cy, = take(1)
        elif cmd == "v":
            dy, = take(1); cy += dy
        elif cmd in ("Z", "z"):
            continue
        else:
            take(1)  # unknown command's operand -- consume one to avoid an infinite loop
            continue
        xs.append(cx); ys.append(cy)
    return min(xs), min(ys), max(xs), max(ys)


def test_icon_asset_window_is_a_horizontal_shape():
    # The window must read as a terminal: a LANDSCAPE (wider-than-tall) shape, not a square
    # tile. The window is the FIRST <path> (the black #000000 fill); assert its bounding box
    # is wider than tall. (It used to be a <rect>; the icon is now path-based.)
    root = ET.fromstring(_asset_svg_text())
    ns = "{http://www.w3.org/2000/svg}"
    paths = root.findall(f".//{ns}path")
    assert paths, "expected at least the window path"
    window = paths[0]  # first path is the black window background
    assert window.get("fill") == "#000000"
    min_x, min_y, max_x, max_y = _path_bbox(window.get("d"))
    assert (max_x - min_x) > (max_y - min_y)
