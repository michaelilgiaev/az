#!/usr/bin/env python3
"""Az'arch application menu -- icon resolution for Tkinter.

Tk's ``PhotoImage`` only understands PNG/GIF/PPM, but the live icon theme
(Breeze Dark) ships its app icons as SVG. This module bridges the gap: given an
``Icon=`` value from a .desktop file it finds the best matching icon on disk
and, if that file is an SVG, rasterises it to a PNG (via ``rsvg-convert``) in a
per-user cache so Tk can load it. Recognised PNGs are used directly.

Design goals:
  * Pure standard library + the ``rsvg-convert`` binary (already on the system).
    No Pillow, no cairosvg, no GTK bindings.
  * A freedesktop-ish theme lookup: honour the active theme and its parents
    (breeze-dark -> breeze -> hicolor), preferring the requested pixel size.
  * Cache rasterised PNGs under XDG cache so repeat opens are instant.
  * Always return SOMETHING usable: fall back to a generic app-icon SVG, and if
    even that fails, to a flat-colour placeholder PhotoImage drawn in-memory.

The Tk root must already exist before :meth:`IconResolver.load` is called
(PhotoImage needs an interpreter). Loaded images are cached and kept referenced
on the resolver so Tk does not garbage-collect them out from under the widgets.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tkinter as tk


# --- Theme + search-path configuration ------------------------------------
_ICON_ROOTS = ("/usr/local/share/icons", "/usr/share/icons")
_PIXMAPS = ("/usr/local/share/pixmaps", "/usr/share/pixmaps")

# Theme fallback chain. We read the user's configured theme but always end at
# hicolor (the spec's required fallback). breeze-dark inherits breeze.
_DEFAULT_THEME_CHAIN = ("breeze-dark", "breeze", "Adwaita", "hicolor")

_RASTER_EXTS = (".png",)          # directly loadable by Tk
_VECTOR_EXTS = (".svg", ".svgz")  # need rsvg-convert first

# freedesktop icon "contexts" (theme subdirectories). Application icons usually
# live in apps/, but .desktop Icon= values legitimately point at device, action,
# preference, place, status, category and mimetype icons too (e.g. Avahi uses
# network-wired from devices/, our own menu uses application-menu from actions/,
# the emoji picker uses preferences-desktop-emoticons from preferences/). Search
# them all, apps first so a real app icon always wins.
#
# `actions` comes SECOND (right after apps) on purpose: the session glyphs the
# bottom bar uses -- system-lock-screen / system-suspend / system-reboot /
# system-shutdown -- are the flat monochrome ones Kickoff's leave buttons use,
# and those live in actions/. Breeze also ships a busier COLOURED
# system-lock-screen under preferences/ (the "system settings" lock); putting
# actions ahead of preferences makes the flat one win, matching the design.
_CONTEXTS = (
    "apps",
    "actions",
    "preferences",
    "categories",
    "devices",
    "places",
    "status",
    "mimetypes",
    "apps/preferences",
)

_CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
    "azarch-application-menu",
    "icons",
)

# Generic icon used when a name cannot be resolved at all.
_GENERIC_NAMES = ("application-x-executable", "application-default-icon")


def _read_configured_theme() -> str | None:
    """Best-effort read of the active Plasma/Qt icon theme name from kdeglobals
    (``[Icons] Theme=``). Returns None if not found; the default chain is used."""
    path = os.path.expanduser("~/.config/kdeglobals")
    try:
        with open(path, encoding="utf-8") as fh:
            in_icons = False
            for line in fh:
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    in_icons = s == "[Icons]"
                    continue
                if in_icons and s.startswith("Theme="):
                    return s.split("=", 1)[1].strip() or None
    except OSError:
        pass
    return None


def _theme_chain() -> tuple[str, ...]:
    """The ordered list of theme dirs to search, configured-theme first."""
    configured = _read_configured_theme()
    chain: list[str] = []
    if configured:
        chain.append(configured)
    for t in _DEFAULT_THEME_CHAIN:
        if t not in chain:
            chain.append(t)
    return tuple(chain)


class IconResolver:
    """Resolves ``Icon=`` names/paths to Tk ``PhotoImage`` objects at a target
    pixel size, rasterising SVGs on demand and caching everything."""

    def __init__(self, size: int = 40) -> None:
        self.size = int(size)
        self._themes = _theme_chain()
        # name/path -> PhotoImage (kept referenced so Tk won't collect them).
        self._image_cache: dict[str, tk.PhotoImage] = {}
        os.makedirs(_CACHE_DIR, exist_ok=True)

    # -- public API --------------------------------------------------------
    def load(self, icon: str) -> tk.PhotoImage:
        """Return a PhotoImage for the given Icon= value (name or absolute
        path). Always returns an image -- a placeholder if nothing resolves."""
        key = icon or "<none>"
        cached = self._image_cache.get(key)
        if cached is not None:
            return cached

        png_path = self._resolve_to_png(icon)
        img = self._photo_from_png(png_path) if png_path else None
        if img is None:
            img = self._placeholder()
        self._image_cache[key] = img
        return img

    # -- resolution --------------------------------------------------------
    def _resolve_to_png(self, icon: str) -> str | None:
        """Find (or rasterise) a PNG on disk for this icon value, or None."""
        src = self._find_source(icon)
        if src is None and icon not in _GENERIC_NAMES:
            # Fall back to a generic executable icon.
            for gen in _GENERIC_NAMES:
                src = self._find_source(gen)
                if src:
                    break
        if src is None:
            return None
        ext = os.path.splitext(src)[1].lower()
        if ext in _RASTER_EXTS:
            return src
        if ext in _VECTOR_EXTS:
            return self._rasterise(src)
        return None

    def _find_source(self, icon: str) -> str | None:
        """Locate the best on-disk file for an Icon= value.

        Handles three cases: an absolute path (used as-is), a bare filename with
        an image extension found in pixmaps, or a themed icon name looked up
        across the theme chain preferring the target size.
        """
        if not icon:
            return None
        # Absolute or explicit path.
        if os.path.isabs(icon) and os.path.isfile(icon):
            return icon
        # Name may already include an extension.
        name, ext = os.path.splitext(icon)
        has_ext = ext.lower() in _RASTER_EXTS + _VECTOR_EXTS
        base = name if has_ext else icon

        candidates = self._themed_candidates(base)
        # Prefer raster over vector at the SAME size tier is handled by ordering
        # in _themed_candidates (size-sorted); just take the first that exists.
        for cand in candidates:
            if os.path.isfile(cand):
                return cand

        # Pixmaps (flat dir, no size) as a last resort.
        for pm in _PIXMAPS:
            for e in _RASTER_EXTS + _VECTOR_EXTS:
                p = os.path.join(pm, base + e)
                if os.path.isfile(p):
                    return p
        return None

    def _themed_candidates(self, base: str) -> list[str]:
        """Ordered candidate file paths for an icon name across the theme chain.

        Ordering priority:
          1. Themes in chain order (configured theme first).
          2. Within a theme, sizes closest to the target (>= target preferred,
             then largest available), plus 'scalable'.
          3. PNG before SVG at the same size (cheaper to load).
        """
        # Size directories commonly present in icon themes.
        numeric_sizes = [512, 256, 192, 128, 96, 64, 48, 44, 40, 36, 32, 24, 22, 16]
        # Rank sizes: closest-but->= target first, then remaining by proximity.
        target = self.size

        def size_rank(s: int) -> tuple[int, int]:
            # (0, delta) if >= target so upscaled-down looks crisp; else (1, delta).
            if s >= target:
                return (0, s - target)
            return (1, target - s)

        ordered_sizes = sorted(numeric_sizes, key=size_rank)

        out: list[str] = []
        for theme in self._themes:
            for root in _ICON_ROOTS:
                theme_dir = os.path.join(root, theme)
                if not os.path.isdir(theme_dir):
                    continue
                # Try each context (apps first). Two on-disk layouts exist:
                #   Breeze:  <theme>/<context>/<size>/<name>.svg
                #   hicolor: <theme>/<size>x<size>/<context>/<name>.png
                for context in _CONTEXTS:
                    for s in ordered_sizes:
                        for sub in (
                            os.path.join(context, str(s)),
                            os.path.join(f"{s}x{s}", context),
                            os.path.join(context, f"{s}x{s}"),
                        ):
                            d = os.path.join(theme_dir, sub)
                            # PNG first (cheap to load), then SVG.
                            out.append(os.path.join(d, base + ".png"))
                            out.append(os.path.join(d, base + ".svg"))
                    # Scalable dirs for this context.
                    for sub in (
                        os.path.join(context, "scalable"),
                        os.path.join("scalable", context),
                    ):
                        d = os.path.join(theme_dir, sub)
                        out.append(os.path.join(d, base + ".svg"))
        return out

    # -- rasterisation -----------------------------------------------------
    def _rasterise(self, svg_path: str) -> str | None:
        """Rasterise an SVG to a cached PNG at the target size. Returns the PNG
        path, or None if rsvg-convert is unavailable or fails."""
        st = os.stat(svg_path)
        digest = hashlib.sha1(
            f"{svg_path}:{st.st_mtime_ns}:{self.size}".encode("utf-8")
        ).hexdigest()[:16]
        out_png = os.path.join(_CACHE_DIR, f"{digest}-{self.size}.png")
        if os.path.isfile(out_png) and os.path.getsize(out_png) > 0:
            return out_png
        try:
            subprocess.run(
                [
                    "rsvg-convert",
                    "-w", str(self.size),
                    "-h", str(self.size),
                    "-o", out_png,
                    svg_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (
            FileNotFoundError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
            return None
        if os.path.isfile(out_png) and os.path.getsize(out_png) > 0:
            return out_png
        return None

    # -- PhotoImage helpers ------------------------------------------------
    def _photo_from_png(self, png_path: str) -> tk.PhotoImage | None:
        try:
            img = tk.PhotoImage(file=png_path)
        except tk.TclError:
            return None
        # Down-scale huge PNGs (e.g. a 128px librewolf) toward the target so
        # rows line up. PhotoImage.subsample only does integer factors; pick the
        # nearest that keeps it >= target so it stays legible.
        w = img.width()
        if w > self.size * 2:
            factor = max(1, round(w / self.size))
            if factor > 1:
                try:
                    img = img.subsample(factor, factor)
                except tk.TclError:
                    pass
        return img

    def _placeholder(self) -> tk.PhotoImage:
        """A flat rounded-ish square drawn in memory when all lookup fails, so
        the row still shows a consistent icon slot."""
        img = tk.PhotoImage(width=self.size, height=self.size)
        # Fill with a muted Breeze surface colour so it blends with the menu.
        img.put("#4d5359", to=(0, 0, self.size, self.size))
        return img


if __name__ == "__main__":
    # Smoke test: resolve a handful of names and report what was found.
    root = tk.Tk()
    root.withdraw()
    r = IconResolver(size=40)
    for nm in ("librewolf", "org.kde.dolphin", "preferences-system", "kitty",
               "definitely-not-a-real-icon"):
        src = r._find_source(nm)
        png = r._resolve_to_png(nm)
        print(f"{nm:32} src={src}  png={png}")
    root.destroy()
