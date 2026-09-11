"""packages.file_manager.icons -- the Azzio icon theme (folder / file / toolbar icons).

Why these tests matter: the file manager's folders, files and toolbar are resolved BY NAME through
the icon theme, and the session runs Adwaita -- which defines all those names and is searched
before hicolor. So the override MUST ship as a SEPARATE "Azzio" theme that Inherits Adwaita (our
names win, everything else falls through) AND gtk-icon-theme-name must point at it. A drift in the
name mapping, the theme's Inherits, or the gtk-icon-theme-name pointer silently reverts a folder
or toolbar icon back to Adwaita's. These pin: the SVG->name->context mapping, that each SVG is a
real on-brand asset, the emit_plan wiring (scalable + PNGs, root-owned, all under the theme dir),
a well-formed index.theme that Inherits Adwaita, the fold-in into fm.emit_plan(), that
gtk-icon-theme-name is "Azzio" everywhere it is written, and that the vendored C basename table
names the same azzio-* icons this module ships.
"""

from __future__ import annotations

import types
from pathlib import Path

from packages import file_manager as fm
from packages.file_manager import icons
from packages.azzio.bundle import bundle_source
import paths


def _azzio_command_line_interface():
    """Exec the bundled `azzio` command line interface in a fresh namespace (as shipped).

    theme.py starts with `# BUNDLE_START` and uses os/subprocess WITHOUT importing them --
    the bundler injects those at build time -- so importing it raw explodes. Driving the
    bundle is the sanctioned way to reach the real theme.py functions (matches
    tests/test_configuration_theme.py).
    """
    mod = types.ModuleType("azzio_cli_icons_test")
    exec(compile(bundle_source(), "azzio_command_line_interface", "exec"), mod.__dict__)
    return mod


def test_icon_name_mapping_is_the_spec():
    # The full SVG -> icon name -> context mapping. Standard freedesktop names override Adwaita;
    # the dirs with no standard name get an azzio-* name the vendored file manager maps by
    # basename; Shared + Mounts share the single mount-point symbol.
    mapping = {name: (svg, ctx) for svg, name, ctx in icons.ICONS}
    assert mapping["folder"] == ("folder.svg", "places")
    assert mapping["folder-documents"] == ("folder-documents.svg", "places")
    assert mapping["folder-download"] == ("folder-download.svg", "places")
    assert mapping["folder-music"] == ("folder-music.svg", "places")
    assert mapping["folder-pictures"] == ("folder-pictures.svg", "places")
    assert mapping["folder-videos"] == ("folder-videos.svg", "places")
    assert mapping["user-desktop"] == ("user-desktop.svg", "places")
    assert mapping["user-home"] == ("user-home.svg", "places")
    assert mapping["azzio-folder-projects"] == ("azzio-folder-projects.svg", "places")
    assert mapping["azzio-folder-vault"] == ("azzio-folder-vault.svg", "places")
    assert mapping["azzio-folder-ignore"] == ("azzio-folder-ignore.svg", "places")
    assert mapping["azzio-folder-mount"] == ("azzio-folder-mount.svg", "places")
    # The dot-location shortcut folders (Cache/Config/Trash/Local/SSH -> .cache/.config/...).
    assert mapping["azzio-folder-cache"] == ("azzio-folder-cache.svg", "places")
    assert mapping["azzio-folder-config"] == ("azzio-folder-config.svg", "places")
    assert mapping["azzio-folder-trash"] == ("azzio-folder-trash.svg", "places")
    assert mapping["azzio-folder-local"] == ("azzio-folder-local.svg", "places")
    assert mapping["azzio-folder-ssh"] == ("azzio-folder-ssh.svg", "places")
    assert mapping["text-x-generic"] == ("text-x-generic.svg", "mimetypes")
    # The symlink arrow emblem (its own "emblems" context), overlaid on symlinked folders/files.
    assert mapping["emblem-symbolic-link"] == ("emblem-symbolic-link.svg", "emblems")
    assert mapping["go-previous"] == ("go-previous.svg", "actions")
    assert mapping["go-next"] == ("go-next.svg", "actions")
    assert mapping["go-up"] == ("go-up.svg", "actions")
    assert mapping["system-search"] == ("system-search.svg", "actions")
    # No accidental extras / dupes.
    assert len(icons.ICONS) == 23
    assert len({name for _s, name, _c in icons.ICONS}) == 23


def test_every_icon_svg_asset_exists_and_is_on_brand():
    # Each icon SVG is a real file in the repo carrying the Azzio brand cyan (#06B8FD, the mid
    # gradient stop) so the whole set shares the house identity. A missing/off-brand asset would
    # ship a wrong or placeholder icon.
    assets_dir = Path(paths.ASSETSDIR)
    for svg, name, _ctx in icons.ICONS:
        p = assets_dir / icons.ASSET_DIR / svg
        assert p.is_file(), f"missing icon asset {svg}"
        text = p.read_text(encoding="utf-8")
        assert "<svg" in text and "</svg>" in text, f"{svg} is not SVG"
        assert "#06B8FD" in text, f"{svg} missing the Azzio brand cyan"
        # No double-hyphen inside XML comments (illegal -- rsvg refuses to parse it).
        for line in text.splitlines():
            if "<!--" in line or "--" in line:
                # crude but effective: a "--" is only legal as the comment open/close markers.
                stripped = line.replace("<!--", "").replace("-->", "")
                assert "--" not in stripped, f"{svg} has an illegal '--' inside an XML comment"


def test_emit_plan_ships_scalable_and_pngs_under_the_azzio_theme_root_owned():
    plan = icons.emit_plan()
    by_dest = {e["dest"]: e for e in plan}
    for svg, name, ctx in icons.ICONS:
        asset = f"{icons.ASSET_DIR}/{svg}"
        svg_dest = f"{icons.ICON_THEME_DIR}/scalable/{ctx}/{name}.svg"
        assert svg_dest in by_dest, f"scalable master not shipped for {name}"
        e = by_dest[svg_dest]
        assert e["asset"] == asset
        assert e["owner"] == "root" and e["mode"] == 0o644
        for size in icons.ICON_PNG_SIZES:
            png_dest = f"{icons.ICON_THEME_DIR}/{size}x{size}/{ctx}/{name}.png"
            assert png_dest in by_dest, f"missing {size}px PNG for {name}"
            r = by_dest[png_dest]
            assert r["render"] == {"asset": asset, "size": size}
            assert r["owner"] == "root"
    # Every icon dest lives under the Azzio theme dir (never hicolor -- Adwaita would win there).
    icon_dests = [d for d in by_dest if d.endswith((".svg", ".png"))]
    assert icon_dests and all(d.startswith(icons.ICON_THEME_DIR + "/") for d in icon_dests)


def test_index_theme_inherits_adwaita_and_declares_every_dir():
    idx = icons.index_theme()
    # It must inherit Adwaita (so every icon we do NOT override falls through) and be an override
    # theme hidden from pickers.
    assert "Name=Azzio" in idx
    assert "Inherits=Adwaita" in idx
    assert "Hidden=true" in idx
    # Every context/size dir our icons use is declared in Directories AND has its own section.
    contexts = {ctx for _s, _n, ctx in icons.ICONS}
    for ctx in contexts:
        assert f"scalable/{ctx}" in idx, ctx
        assert f"[scalable/{ctx}]" in idx, ctx
        for size in icons.ICON_PNG_SIZES:
            assert f"{size}x{size}/{ctx}" in idx, (size, ctx)
            assert f"[{size}x{size}/{ctx}]" in idx, (size, ctx)


def test_file_manager_folds_in_the_icon_theme():
    # fm.emit_plan() must carry every icon-theme entry (else the icons silently stop shipping).
    fm_dests = {e["dest"] for e in fm.emit_plan()}
    for e in icons.emit_plan():
        assert e["dest"] in fm_dests, e["dest"]
    # And the theme descriptor is in there.
    assert f"{icons.ICON_THEME_DIR}/index.theme" in fm_dests
    # The re-exports are wired.
    assert fm.ICON_THEME_NAME == "Azzio"
    assert fm.ICON_THEME_DIR == "/usr/share/icons/Azzio"


def test_gtk_icon_theme_name_points_at_azzio_everywhere():
    # The theme is only active if gtk-icon-theme-name is "Azzio" in every file that writes it:
    # the `azzio theme` builders (live toggle) AND the openbox shipped defaults. If any still says
    # "Adwaita", that surface reverts to Adwaita's icons.
    theme = _azzio_command_line_interface()
    from packages import openbox
    surfaces = [
        theme.gtk3_settings_ini(True), theme.gtk3_settings_ini(False),
        theme.gtk4_settings_ini(True), theme.gtk4_settings_ini(False),
        theme.gtkrc2(True), theme.gtkrc2(False),
        openbox.gtk3_settings_ini_default(), openbox.gtk4_settings_ini_default(),
        openbox.gtkrc2_default(),
    ]
    for s in surfaces:
        assert "gtk-icon-theme-name" in s
        assert "Azzio" in s, "an icon-theme surface does not point at Azzio"
        assert "icon-theme-name=Adwaita" not in s and 'icon-theme-name="Adwaita"' not in s, (
            "an icon-theme surface still points at Adwaita"
        )


def test_c_basename_table_names_match_the_shipped_azzio_icons():
    # The vendored file manager's basename->icon table (thunar-file.c azzio_folder_dirs) must name
    # icons this module actually ships -- otherwise a mapped folder resolves to a missing name and
    # falls back to the generic folder. Cross-check the azzio-* names appear in both.
    file_c = (fm.SOURCE_DIR / "thunar" / "thunar-file.c").read_text()
    shipped = {name for _s, name, _c in icons.ICONS}
    for icon in ("azzio-folder-projects", "azzio-folder-vault", "azzio-folder-ignore",
                 "azzio-folder-mount", "azzio-folder-cache", "azzio-folder-config",
                 "azzio-folder-trash", "azzio-folder-local", "azzio-folder-ssh"):
        assert icon in shipped, f"{icon} referenced by C but not shipped"
        assert f'"{icon}"' in file_c, f"{icon} shipped but not referenced by the C table"
