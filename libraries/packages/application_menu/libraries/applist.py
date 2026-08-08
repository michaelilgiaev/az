#!/usr/bin/env python3
"""Az'arch application menu -- the scrollable application list, drawn as CANVAS
ITEMS (not embedded child widgets).

Why this exists
---------------
The list used to be a column of ``AppRow`` frames packed into a frame embedded in
the scroll canvas. Each row was a tree of ~7 real X windows (frame -> card -> pad
-> icon/text/name/type), so the whole list was ~100 X windows. Filtering
``pack``/``pack_forget``-ed those subtrees on every keystroke, which under a
compositing WM (KWin on a virtio GPU here) MAPS/UNMAPS ~100 child X windows per
keystroke. The compositor briefly presents those child windows before Tk repaints
them, so the list visibly FLICKERS -- items flashing in and out -- as the user
types. (A settled framebuffer grab can't catch it; the eye can.)

The fix is architectural and matches the spec ("preloaded and ready to be
filtered through"): every application is drawn ONCE as plain canvas items -- an
image plus two text items plus a selection rectangle -- directly on the list
canvas. There are NO per-row X windows. Filtering, selecting and scrolling then
only ever call ``itemconfigure`` / ``coords`` / ``yview`` on existing items, which
the canvas repaints from its own double-buffered expose. Nothing is ever mapped
or unmapped, so the list can never flicker or blank while typing.

Public surface used by menu.py::

    lst = CanvasAppList(parent, entries, icon_loader, on_activate)
    lst.set_entries(new_entries)        # after a resort
    lst.apply_filter(query)             # show/lay out matches, select first
    lst.move_selection(+1 / -1)         # keyboard nav
    lst.activate_selected()             # launch the selected app
    lst.selected_entry                  # AppEntry | None
    lst.visible_count                   # how many rows are shown
    lst.scroll_to_top()

Kept dependency-free: Tkinter + the shared theme only.
"""

from __future__ import annotations

import tkinter as tk

import theme as T
from widgets import KickoffScrollBar


class _RowItem:
    """The canvas item ids for one application row, plus its model entry. The
    items are created once and then only moved / recoloured / shown / hidden."""

    __slots__ = ("entry", "image", "rect", "icon", "name", "sub", "y", "shown")

    def __init__(self, entry, image) -> None:
        self.entry = entry
        self.image = image      # kept referenced so Tk won't collect the PhotoImage
        self.rect = None        # selection/hover outline rectangle
        self.icon = None        # create_image id
        self.name = None        # big name text id
        self.sub = None         # subtitle text id
        self.y = 0              # current top y (canvas coords) when shown
        self.shown = False


class CanvasAppList:
    """Draws the whole application list as canvas items and drives filtering,
    selection and scrolling without ever creating/destroying or mapping/unmapping
    a per-row widget (the old flicker source)."""

    # Row metrics (px). ROW_H is the full height of one row's hit box; the icon
    # and the two text lines are centred within it. Tuned to match the previous
    # AppRow look (40px icon + name + subtitle with padding).
    ROW_H = 56
    PAD_X = 8                 # left/right inset of the selection outline
    ICON_X = 20               # icon left edge inside the row
    TEXT_X = 72               # text left edge (icon width + gap)
    NAME_DY = 18              # name baseline offset from row top
    SUB_DY = 38               # subtitle baseline offset from row top

    def __init__(self, parent: tk.Widget, entries, icon_loader,
                 on_activate) -> None:
        self._parent = parent
        self._load_icon = icon_loader
        self._on_activate = on_activate
        self._entries = list(entries)
        self._rows: list[_RowItem] = []       # one per entry, canonical order
        self._visible: list[_RowItem] = []     # currently shown, in draw order
        self._selected = -1                    # index into self._visible
        self._width = 1

        wrap = tk.Frame(parent, bg=T.BG_COLOR)
        wrap.pack(fill="both", expand=True)
        self._wrap = wrap

        self.canvas = tk.Canvas(
            wrap, bg=T.BG_COLOR, highlightthickness=0, borderwidth=0,
        )
        self.canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = KickoffScrollBar(wrap, command=self.canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # A single reusable selection rectangle painted UNDER the row content,
        # moved to the selected/hovered row instead of recolouring per-row items.
        self._sel = self.canvas.create_rectangle(
            0, 0, 0, 0, width=1, outline=T.BG_COLOR, fill=T.BG_COLOR,
            state="hidden",
        )
        self._hover_index = -1

        self.canvas.bind("<Configure>", self._on_canvas_config)
        # Mouse-wheel scrolling (X11 delivers Button-4/5; Windows MouseWheel).
        self.canvas.bind_all("<Button-4>", lambda _e: self._wheel(-1))
        self.canvas.bind_all("<Button-5>", lambda _e: self._wheel(1))
        self.canvas.bind_all(
            "<MouseWheel>", lambda e: self._wheel(-1 if e.delta > 0 else 1)
        )
        # Hover + click are bound per-row via canvas item tags (see _build_rows).
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(-1))
        self.canvas.bind("<Button-1>", self._on_click)

        self._build_rows()

    # -- construction ------------------------------------------------------
    def _build_rows(self) -> None:
        """Create the canvas items for every entry ONCE. They start hidden and
        are positioned/shown by apply_filter. Rebuilt only when the entry set
        itself changes (set_entries)."""
        # Clear any previous items (set_entries rebuild).
        for r in self._rows:
            for iid in (r.rect, r.icon, r.name, r.sub):
                if iid is not None:
                    try:
                        self.canvas.delete(iid)
                    except tk.TclError:
                        pass
        self._rows = []
        for entry in self._entries:
            img = self._load_icon(entry.icon)
            row = _RowItem(entry, img)
            # Outline rectangle (invisible until selected/hovered); drawn first so
            # text/icon sit on top.
            row.rect = self.canvas.create_rectangle(
                0, 0, 0, 0, width=1,
                outline=T.BG_COLOR, fill=T.BG_COLOR, state="hidden",
            )
            row.icon = self.canvas.create_image(
                0, 0, image=img, anchor="w", state="hidden",
            )
            row.name = self.canvas.create_text(
                0, 0, text=entry.name, anchor="w", fill=T.TEXT_COLOR,
                font=("Noto Sans", 12), state="hidden",
            )
            row.sub = self.canvas.create_text(
                0, 0, text=entry.type_label, anchor="w", fill=T.SUBTEXT_COLOR,
                font=("Noto Sans", 9), state="hidden",
            )
            self._rows.append(row)

    # -- public API --------------------------------------------------------
    def set_entries(self, entries) -> None:
        """Replace the entry set (e.g. after a usage resort) and rebuild items in
        the new order. Caller re-applies the current filter afterwards."""
        self._entries = list(entries)
        self._selected = -1
        self._hover_index = -1
        self._build_rows()

    @property
    def selected_entry(self):
        if 0 <= self._selected < len(self._visible):
            return self._visible[self._selected].entry
        return None

    @property
    def visible_count(self) -> int:
        return len(self._visible)

    # -- introspection (used by tests) -------------------------------------
    @property
    def selected_index(self) -> int:
        return self._selected

    @property
    def all_entries(self) -> list:
        """Every entry in canonical (freq-then-alpha) order."""
        return [r.entry for r in self._rows]

    @property
    def visible_entries(self) -> list:
        """The entries currently shown, in on-screen (top-to-bottom) order."""
        return [r.entry for r in self._visible]

    def visible_tops(self) -> list:
        """Per-visible-row top y (canvas coords), in the same order as
        visible_entries -- the on-screen vertical order, for tests that used to
        read widget winfo_y()."""
        return [r.y for r in self._visible]

    def apply_filter(self, query: str) -> None:
        """Show exactly the rows whose name/type match ``query`` (empty -> all),
        laid out top-to-bottom in canonical order, and select the first. Only
        moves/shows/hides existing canvas items -- no window churn, so it can
        never flicker."""
        q = query.strip().casefold()
        matches = [r for r in self._rows if self._matches(r, q)]

        # Lay the matches out and show them; hide everything else. Because every
        # item already exists, this is pure itemconfigure/coords -- the canvas
        # repaints once from its own buffer.
        shown = set()
        y = 0
        text_x = self.TEXT_X
        icon_cx = self.ICON_X
        for r in matches:
            self._place_row(r, y, icon_cx, text_x)
            shown.add(id(r))
            r.y = y
            r.shown = True
            y += self.ROW_H
        for r in self._rows:
            if id(r) not in shown and r.shown:
                self._hide_row(r)
                r.shown = False

        self._visible = matches
        # Update the scrollregion to the laid-out height and scroll to the top.
        self._content_h = y
        try:
            self.canvas.configure(scrollregion=(0, 0, self._width, max(y, 1)))
            self.canvas.yview_moveto(0.0)
        except tk.TclError:
            pass

        # Select the first visible row so Enter launches something.
        self._selected = 0 if self._visible else -1
        self._hover_index = -1
        self._refresh_selection()

    def move_selection(self, delta: int) -> None:
        if not self._visible:
            return
        self._selected = max(
            0, min(len(self._visible) - 1, self._selected + delta)
        )
        self._refresh_selection()
        self._scroll_to_selected()

    def activate_selected(self) -> None:
        entry = self.selected_entry
        if entry is not None:
            self._on_activate(entry)

    def scroll_to_top(self) -> None:
        try:
            self.canvas.yview_moveto(0.0)
        except tk.TclError:
            pass

    # -- layout of a single row -------------------------------------------
    def _place_row(self, r: _RowItem, y: int, icon_cx: int, text_x: int) -> None:
        h = self.ROW_H
        w = max(self._width, 1)
        self.canvas.coords(
            r.rect, self.PAD_X, y + 2, w - self.PAD_X, y + h - 2
        )
        self.canvas.coords(r.icon, icon_cx, y + h / 2)
        self.canvas.coords(r.name, text_x, y + self.NAME_DY)
        self.canvas.coords(r.sub, text_x, y + self.SUB_DY)
        for iid in (r.icon, r.name, r.sub):
            self.canvas.itemconfigure(iid, state="normal")
        # rect stays hidden unless this row is the selected/hovered one; selection
        # is applied separately so we don't paint an outline on every row.

    def _hide_row(self, r: _RowItem) -> None:
        for iid in (r.rect, r.icon, r.name, r.sub):
            try:
                self.canvas.itemconfigure(iid, state="hidden")
            except tk.TclError:
                pass

    # -- selection / hover -------------------------------------------------
    def _refresh_selection(self) -> None:
        """Paint the selection outline on the selected row and reset the others
        to plain. Uses each row's own rect item (moved into place already) so the
        outline lands exactly on the row."""
        for i, r in enumerate(self._visible):
            selected = (i == self._selected)
            hovered = (i == self._hover_index)
            if selected or hovered:
                self.canvas.itemconfigure(
                    r.rect, state="normal",
                    outline=T.SELECT_BORDER, fill=T.SELECT_FILL,
                )
                self.canvas.itemconfigure(r.name, fill=T.SELECT_TEXT)
                self.canvas.itemconfigure(r.sub, fill=T.SELECT_TEXT)
                self.canvas.tag_raise(r.rect)
                for iid in (r.icon, r.name, r.sub):
                    self.canvas.tag_raise(iid)
            else:
                self.canvas.itemconfigure(r.rect, state="hidden")
                self.canvas.itemconfigure(r.name, fill=T.TEXT_COLOR)
                self.canvas.itemconfigure(r.sub, fill=T.SUBTEXT_COLOR)

    def _row_at(self, event_y: int) -> int:
        """Index into self._visible of the row under a canvas-y pixel, or -1."""
        y = self.canvas.canvasy(event_y)
        idx = int(y // self.ROW_H)
        if 0 <= idx < len(self._visible):
            return idx
        return -1

    def _set_hover(self, idx: int) -> None:
        if idx == self._hover_index:
            return
        self._hover_index = idx
        self._refresh_selection()

    def _on_motion(self, event) -> None:
        self._set_hover(self._row_at(event.y))

    def _on_click(self, event) -> None:
        idx = self._row_at(event.y)
        if 0 <= idx < len(self._visible):
            self._on_activate(self._visible[idx].entry)

    # -- filtering match (name or type label) ------------------------------
    @staticmethod
    def _matches(r: _RowItem, q: str) -> bool:
        if not q:
            return True
        e = r.entry
        return q in e.name.casefold() or q in e.type_label.casefold()

    # -- scrolling ---------------------------------------------------------
    def _on_canvas_config(self, event) -> None:
        self._width = event.width
        # Re-stretch every shown row's outline to the new width and keep the
        # scrollregion in sync. Positions (y) don't change on width resize.
        for r in self._visible:
            self.canvas.coords(
                r.rect, self.PAD_X, r.y + 2, event.width - self.PAD_X,
                r.y + self.ROW_H - 2,
            )
        try:
            self.canvas.configure(
                scrollregion=(0, 0, event.width,
                              max(getattr(self, "_content_h", 1), 1))
            )
        except tk.TclError:
            pass

    def _wheel(self, direction: int) -> None:
        try:
            self.canvas.yview_scroll(direction, "units")
        except tk.TclError:
            pass

    def _scroll_to_selected(self) -> None:
        if not (0 <= self._selected < len(self._visible)):
            return
        r = self._visible[self._selected]
        total = max(getattr(self, "_content_h", 1), 1)
        top = r.y
        bot = r.y + self.ROW_H
        try:
            view_top, view_bot = self.canvas.yview()
            frac_top = top / total
            frac_bot = bot / total
            if frac_top < view_top:
                self.canvas.yview_moveto(frac_top)
            elif frac_bot > view_bot:
                self.canvas.yview_moveto(frac_bot - (view_bot - view_top))
        except (tk.TclError, ZeroDivisionError):
            pass
