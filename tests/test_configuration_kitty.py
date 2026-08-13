"""patches.kitty -- the kitty terminal-icon patch (clean "> _" glyph).

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
from patches import kitty


def _asset_svg_text() -> str:
    return (paths.ASSETSDIR / kitty.ICON_ASSET).read_text(encoding="utf-8")


def test_emit_plan_has_four_entries():
    # SVG asset copy + two PNG removals + the titlebar PNG render. A dropped entry either
    # fails to replace the cat SVG, leaves a stale PNG that outranks it, or drops the
    # in-window titlebar icon.
    assert len(kitty.emit_plan()) == 4


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


def test_icon_asset_is_wellformed_xml():
    # A broken SVG makes the icon loader fall back to a generic icon; parse it to prove the
    # element tree is valid. (XML comments must not contain "--"; that gotcha raised during
    # authoring, exactly as this asserts against.)
    ET.fromstring(_asset_svg_text())


def test_icon_asset_is_a_clean_bw_terminal_not_a_cat():
    # The whole point (user's exact ask): a terminal-window mark -- a horizontal BLACK
    # rectangle (the window) with a WHITE "> _" prompt inside (a chevron stroked path + an
    # underscore cursor rect). Black and white ONLY, no color, no cat. Assert the structural
    # bits are present and nothing colored/mascot slipped in.
    svg = _asset_svg_text().lower()
    assert "<svg" in svg and "</svg>" in svg
    assert 'viewbox="0 0 256 256"' in svg
    assert svg.count("<rect") >= 2  # the black window rectangle + the "_" underscore cursor
    assert "<path" in svg           # the chevron ">"
    assert "cat" not in svg and "whisker" not in svg
    # Black and white only: a black window fill and a white prompt, and NO stray colors (the
    # old rejected icon used red/yellow/green titlebar dots + a green prompt).
    assert "#000000" in svg         # black background rectangle
    assert "#ffffff" in svg         # white prompt "> _"
    for banned in ("#e06c75", "#e5c07b", "#98c379", "#3fd07f", "#1b1f24", "#2b3038"):
        assert banned not in svg


def test_icon_asset_window_is_a_horizontal_rectangle():
    # The window must read as a terminal: a LANDSCAPE (wider-than-tall) rectangle, not a
    # square tile. Parse the background rect and assert width > height.
    root = ET.fromstring(_asset_svg_text())
    ns = "{http://www.w3.org/2000/svg}"
    rects = root.findall(f"{ns}rect")
    assert rects, "expected at least the background window rect"
    bg = rects[0]  # first rect is the window background
    assert float(bg.get("width")) > float(bg.get("height"))
