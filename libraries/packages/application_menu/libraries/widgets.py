#!/usr/bin/env python3
"""Az'arch application menu -- reusable Tkinter widgets.

The visual building blocks of the menu, split out of ``menu.py`` so that file
stays a lean orchestrator. Everything here is styled to the Breeze-ish palette
in ``theme.py`` and matched to ``rough-design.png``:

  * :class:`HighlightBar` -- the Breeze-blue accent stripe that pops in over our
    panel icon while the menu is open.
  * :class:`AppRow` -- one application list row (icon + big name + type
    subtitle) whose hover / keyboard selection draws a rounded blue OUTLINE
    (not a full-bleed solid block), inset from the window edges.
  * :class:`IconButton` -- a flat square button that shows a rasterised Breeze
    icon and highlights on hover; used for the top settings/pin controls. It can
    render an "active" (pinned) state as a blue-outlined box.
  * :class:`PowerButton` -- a big bottom-bar session button (Breeze icon over/
    beside a label) that expands to share the bottom bar evenly.
"""

from __future__ import annotations

import tkinter as tk

import theme as T


# --- Highlight bar over the panel icon ------------------------------------
class HighlightBar:
    """A borderless Breeze-blue accent stripe that POPS IN at full size over the
    panel icon while the menu is open (mirroring Plasma's "active applet"
    indicator), and is torn down when the menu closes. Idempotent close()."""

    def __init__(self, root: tk.Tk, screen_w: int, screen_h: int) -> None:
        self._root = root
        full_w = max(1, T.ICON_CELL_W - 2 * T.HIGHLIGHT_BAR_INSET)
        cell_left = T.ICON_CELL_X + T.HIGHLIGHT_BAR_INSET
        self._w = min(full_w, screen_w)
        self._x = cell_left
        self._y = screen_h - T.PANEL_HEIGHT

        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.configure(bg=T.HIGHLIGHT_COLOR)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        win.withdraw()
        self._win = win

    def show(self) -> None:
        if not self._alive():
            return
        self._win.geometry(
            f"{self._w}x{T.HIGHLIGHT_BAR_HEIGHT}+{self._x}+{self._y}"
        )
        self._win.deiconify()

    def _alive(self) -> bool:
        try:
            return bool(self._win.winfo_exists())
        except tk.TclError:
            return False

    def close(self) -> None:
        try:
            self._win.destroy()
        except tk.TclError:
            pass


# --- One application row ---------------------------------------------------
class AppRow(tk.Frame):
    """A clickable list row: [icon]  Big Name / small type subtitle.

    Hover / keyboard selection draws a rounded blue outline around the row (a
    highlight border on an inset frame with a faint tinted fill), matching the
    Kickoff/rough-design selection. A left click launches the app and asks the
    menu to close via the supplied callback.

    Structure (so the outline can inset from the window edges and the whole row
    reacts to hover uniformly -- Tk does not propagate <Enter>/<Button> from
    children to the parent):

        self (BG, horizontal padding)          <- outer, gives left/right inset
          card (highlightthickness border)     <- the rounded-ish outline
            pad (icon + text, internal padding)
    """

    def __init__(
        self,
        master: tk.Widget,
        entry,
        image: tk.PhotoImage,
        on_activate,
    ) -> None:
        super().__init__(master, bg=T.BG_COLOR, cursor="hand2")
        self.entry = entry
        self._on_activate = on_activate
        self._selected = False

        # The "card" carries the outline. highlightthickness draws a border that
        # we colour blue on select/hover and match to the fill otherwise (so it
        # is invisible but the geometry never shifts).
        self._card = tk.Frame(
            self, bg=T.BG_COLOR, highlightthickness=1,
            highlightbackground=T.BG_COLOR, highlightcolor=T.BG_COLOR,
        )
        self._card.pack(fill="x", padx=8, pady=2)

        pad = tk.Frame(self._card, bg=T.BG_COLOR)
        pad.pack(fill="x", padx=8, pady=5)

        self._icon = tk.Label(pad, image=image, bg=T.BG_COLOR)
        self._icon.image = image  # keep a ref so Tk doesn't collect it
        self._icon.pack(side="left", padx=(2, 12))

        text = tk.Frame(pad, bg=T.BG_COLOR)
        text.pack(side="left", fill="x", expand=True, anchor="w")

        self._name = tk.Label(
            text, text=entry.name, bg=T.BG_COLOR, fg=T.TEXT_COLOR,
            font=("Noto Sans", 12), anchor="w", justify="left",
        )
        self._name.pack(fill="x", anchor="w")
        self._type = tk.Label(
            text, text=entry.type_label, bg=T.BG_COLOR, fg=T.SUBTEXT_COLOR,
            font=("Noto Sans", 9), anchor="w", justify="left",
        )
        self._type.pack(fill="x", anchor="w")

        # Widgets whose background follows the row state (everything except the
        # card, whose *border* is what changes).
        self._bg_widgets = (self, pad, text, self._icon, self._name, self._type)
        for w in (self, self._card, pad, text, self._icon,
                  self._name, self._type):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_click)

    # -- appearance --------------------------------------------------------
    def _paint(self, fill: str, border: str, name_fg: str, sub_fg: str) -> None:
        try:
            for w in self._bg_widgets:
                w.configure(bg=fill)
            self._card.configure(
                bg=fill, highlightbackground=border, highlightcolor=border,
            )
            self._name.configure(fg=name_fg)
            self._type.configure(fg=sub_fg)
        except tk.TclError:
            # Widgets torn down (menu closing) -> nothing to recolour.
            pass

    def _plain(self) -> None:
        # Border matched to BG so it is invisible but reserves the same 1px.
        self._paint(T.BG_COLOR, T.BG_COLOR, T.TEXT_COLOR, T.SUBTEXT_COLOR)

    def _highlight(self) -> None:
        self._paint(
            T.SELECT_FILL, T.SELECT_BORDER, T.SELECT_TEXT, T.SELECT_TEXT
        )

    def _on_enter(self, _e=None) -> None:
        if not self._selected:
            self._highlight()

    def _on_leave(self, _e=None) -> None:
        if not self._selected:
            self._plain()

    def set_selected(self, selected: bool) -> None:
        """Keyboard selection highlight (Breeze selection outline)."""
        self._selected = selected
        if selected:
            self._highlight()
        else:
            self._plain()

    # -- activation --------------------------------------------------------
    def _on_click(self, _e=None) -> None:
        self.activate()

    def activate(self) -> None:
        self._on_activate(self.entry)


# --- Flat icon button (top settings / pin) --------------------------------
class IconButton(tk.Frame):
    """A borderless square button showing a rasterised Breeze icon that
    highlights on hover. Used for the top-row settings and pin controls.

    Supports an "active" look (a blue outline + tinted fill, like the pinned pin
    in rough-design.png) toggled via :meth:`set_active`, so the pin button can
    show whether the menu is pinned.
    """

    def __init__(
        self,
        master: tk.Widget,
        image: tk.PhotoImage,
        command,
        *,
        pad: int = 7,
    ) -> None:
        super().__init__(
            master, bg=T.BG_COLOR, cursor="hand2",
            highlightthickness=1, highlightbackground=T.BG_COLOR,
            highlightcolor=T.BG_COLOR,
        )
        self._command = command
        self._active = False
        self._label = tk.Label(self, image=image, bg=T.BG_COLOR)
        self._label.image = image
        self._label.pack(padx=pad, pady=pad)

        for w in (self, self._label):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._press)

    def _fill(self, bg: str, border: str) -> None:
        try:
            self.configure(
                bg=bg, highlightbackground=border, highlightcolor=border
            )
            self._label.configure(bg=bg)
        except tk.TclError:
            pass

    def _on_enter(self, _e=None) -> None:
        if self._active:
            self._fill(T.SELECT_FILL, T.SELECT_BORDER)
        else:
            self._fill(T.HOVER_COLOR, T.HOVER_COLOR)

    def _on_leave(self, _e=None) -> None:
        self._restore()

    def _restore(self) -> None:
        if self._active:
            self._fill(T.SELECT_FILL, T.SELECT_BORDER)
        else:
            self._fill(T.BG_COLOR, T.BG_COLOR)

    def set_active(self, active: bool) -> None:
        """Toggle the pinned/active blue-outline look."""
        self._active = active
        self._restore()

    def _press(self, _e=None) -> None:
        if self._command is not None:
            self._command()


# --- Bottom power/session button ------------------------------------------
class PowerButton(tk.Frame):
    """A big bottom-bar session button: a Breeze icon beside its label, the
    whole thing highlighting on hover. Packed with ``expand=True`` by the caller
    so the four buttons share the bottom bar evenly and fill the window width.
    """

    def __init__(
        self,
        master: tk.Widget,
        image: tk.PhotoImage,
        label: str,
        command,
    ) -> None:
        super().__init__(master, bg=T.BG_COLOR, cursor="hand2")
        self._command = command

        inner = tk.Frame(self, bg=T.BG_COLOR)
        inner.pack(padx=6, pady=10)  # generous vertical pad -> fills the bar

        self._icon = tk.Label(inner, image=image, bg=T.BG_COLOR)
        self._icon.image = image
        self._icon.pack(side="left", padx=(0, 8))
        self._text = tk.Label(
            inner, text=label, bg=T.BG_COLOR, fg=T.TEXT_COLOR,
            font=("Noto Sans", 11),
        )
        self._text.pack(side="left")

        self._widgets = (self, inner, self._icon, self._text)
        for w in self._widgets:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._press)

    def _paint(self, bg: str) -> None:
        try:
            for w in self._widgets:
                w.configure(bg=bg)
        except tk.TclError:
            pass

    def _on_enter(self, _e=None) -> None:
        self._paint(T.HOVER_COLOR)

    def _on_leave(self, _e=None) -> None:
        self._paint(T.BG_COLOR)

    def _press(self, _e=None) -> None:
        if self._command is not None:
            self._command()
