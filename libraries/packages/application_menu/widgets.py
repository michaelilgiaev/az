#!/usr/bin/env python3
"""Az'arch application menu -- reusable Tkinter widgets.

The visual building blocks of the menu, split out of ``menu.py`` so that file
stays a lean orchestrator. Everything here is styled to the Breeze-ish dark palette
in ``theme.py``:

  * :class:`AppRow` -- one application list row (icon + big name + type
    subtitle) whose hover / keyboard selection draws a rounded blue OUTLINE
    (not a full-bleed solid block), inset from the window edges.
  * :class:`PowerButton` -- a big bottom-bar session button (Breeze icon beside a
    label) that expands to share the bottom bar evenly and can render a keyboard
    FOCUS outline (the menu's TAB navigation drives it).
  * :class:`KickoffScrollBar` -- a canvas-drawn, arrow-less rounded scrollbar (a
    Plasma-Kickoff-style pill thumb).

(The old top-row Settings/pin controls -- and their :class:`IconButton`,
:class:`Tooltip` and ``dim_image`` helpers -- were REMOVED: the menu no longer has a
pin or a settings button, and the panel-icon :class:`HighlightBar` is gone with the
panel. The search box now spans the full top row.)
"""

from __future__ import annotations

import tkinter as tk

import theme as T


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
            font=(T.FONT_FAMILY, T.FONT_APP_NAME), anchor="w", justify="left",
        )
        self._name.pack(fill="x", anchor="w")
        self._type = tk.Label(
            text, text=entry.type_label, bg=T.BG_COLOR, fg=T.SUBTEXT_COLOR,
            font=(T.FONT_FAMILY, T.FONT_APP_TYPE), anchor="w", justify="left",
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


# --- Bottom power/session button ------------------------------------------
class PowerButton(tk.Frame):
    """A big bottom-bar session button: a Breeze icon beside its label, the whole
    thing highlighting on hover. The caller grids the four buttons into four EQUAL
    columns (``sticky="nsew"``) so each button fills its own equal slice of the
    bottom bar.

    The icon+label content is packed with the default CENTER anchor, so it sits
    centred WITHIN the button's cell -- giving 'each button centred in its own
    slice' rather than the whole group centred across the bar.

    KEYBOARD FOCUS: the power row is one of the menu's two TAB focus zones (the other
    is the search box + app list). When TAB moves focus onto the power row, the menu
    calls :meth:`set_focused` on one button to draw a blue selection OUTLINE (the same
    Breeze accent the app rows use), and Left/Right move that focus between buttons;
    Enter activates the focused one. ``set_focused`` is independent of mouse hover: a
    focused button stays outlined even when the pointer is elsewhere, and hover still
    tints on top so the pointer stays responsive.
    """

    def __init__(
        self,
        master: tk.Widget,
        image: tk.PhotoImage,
        label: str,
        command,
    ) -> None:
        # highlightthickness reserves 1px for the keyboard-focus outline (matched to
        # BG when unfocused so the geometry never shifts), like the app rows' card.
        super().__init__(
            master, bg=T.BG_COLOR, cursor="hand2",
            highlightthickness=1, highlightbackground=T.BG_COLOR,
            highlightcolor=T.BG_COLOR,
        )
        self._command = command
        self._focused = False

        inner = tk.Frame(self, bg=T.BG_COLOR)
        # Centre the icon+label within the button's (equal) cell. padx/pady are the
        # margin around the content; the default center anchor keeps the content
        # centred in its slice.
        inner.pack(padx=5, pady=10)

        self._icon = tk.Label(inner, image=image, bg=T.BG_COLOR)
        self._icon.image = image
        self._icon.pack(side="left", padx=(0, 8))
        self._text = tk.Label(
            inner, text=label, bg=T.BG_COLOR, fg=T.TEXT_COLOR,
            font=(T.FONT_FAMILY, T.FONT_POWER),
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

    def _restore(self) -> None:
        """Repaint to the button's resting look for its current focus state: a blue
        selection outline + faint fill when keyboard-focused, plain otherwise."""
        try:
            if self._focused:
                self._paint(T.SELECT_FILL)
                self.configure(
                    highlightbackground=T.SELECT_BORDER,
                    highlightcolor=T.SELECT_BORDER,
                )
            else:
                self._paint(T.BG_COLOR)
                self.configure(
                    highlightbackground=T.BG_COLOR, highlightcolor=T.BG_COLOR,
                )
        except tk.TclError:
            pass

    def set_focused(self, focused: bool) -> None:
        """Toggle the keyboard-focus outline (driven by the menu's TAB navigation)."""
        self._focused = bool(focused)
        self._restore()

    def activate(self) -> None:
        """Fire the button's command (used by Enter on a keyboard-focused button)."""
        if self._command is not None:
            self._command()

    def _on_enter(self, _e=None) -> None:
        # Hover tint sits ON TOP of the focus state (keep the blue outline if focused).
        self._paint(T.HOVER_COLOR)

    def _on_leave(self, _e=None) -> None:
        self._restore()

    def _press(self, _e=None) -> None:
        if self._command is not None:
            self._command()


# --- Kickoff-style scrollbar ----------------------------------------------
class KickoffScrollBar(tk.Canvas):
    """A pixel-faithful re-creation of Plasma Kickoff's scrollbar for a Tk
    scrollable canvas -- because the classic Tk scrollbar (3D bevels + arrow
    buttons) looks nothing like it.

    Kickoff's scrollbar (Breeze desktop theme) is:
      * ARROW-LESS -- just a slider, no up/down buttons.
      * a single ROUNDED (pill) thumb, translucent light grey, ~6px wide.
      * NO visible track at rest; on hover the thumb brightens and a faint
        groove fades in behind it.
      * hidden entirely when everything fits (nothing to scroll).

    It is wired exactly like a tk.Scrollbar: pass ``command=canvas.yview`` and set
    ``canvas.configure(yscrollcommand=self.set)``. Dragging the thumb (or pressing
    the groove) scrolls the target; the thumb tracks the view fraction.
    """

    def __init__(self, master: tk.Widget, command) -> None:
        super().__init__(
            master, width=T.SCROLL_TRACK_WIDTH, highlightthickness=0,
            borderwidth=0, bg=T.BG_COLOR, takefocus=0,
        )
        self._command = command          # canvas.yview
        self._first = 0.0                # top of the view (fraction)
        self._last = 1.0                 # bottom of the view (fraction)
        self._hover = False
        self._dragging = False
        self._drag_dy = 0.0              # grab offset within the thumb

        self.bind("<Configure>", lambda _e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    # -- scrollbar protocol (called by the canvas' yscrollcommand) ---------
    def set(self, first, last) -> None:
        """Receive the view fraction from the scrolled canvas and redraw. Hides
        the whole scrollbar when the content fits (first==0 and last==1)."""
        self._first = float(first)
        self._last = float(last)
        fits = self._first <= 0.0 and self._last >= 1.0
        try:
            if fits:
                # Nothing to scroll -> take the scrollbar out of the layout, just
                # like Kickoff hides it.
                if self.winfo_manager():
                    self.pack_forget()
            else:
                if not self.winfo_manager():
                    self.pack(side="right", fill="y")
        except tk.TclError:
            pass
        self._redraw()

    # -- geometry ----------------------------------------------------------
    def _thumb_span(self) -> tuple[int, int]:
        """Pixel (top, bottom) of the thumb for the current view fraction,
        clamped to a minimum grabbable length."""
        h = max(1, self.winfo_height())
        top = self._first * h
        bot = self._last * h
        if bot - top < T.SCROLL_THUMB_MIN:
            mid = (top + bot) / 2
            half = T.SCROLL_THUMB_MIN / 2
            top = mid - half
            bot = mid + half
            if top < 0:
                top, bot = 0, T.SCROLL_THUMB_MIN
            if bot > h:
                bot, top = h, h - T.SCROLL_THUMB_MIN
        return int(round(top)), int(round(bot))

    def _redraw(self) -> None:
        try:
            self.delete("all")
        except tk.TclError:
            return
        # Fully scrollable check: if content fits, draw nothing.
        if self._first <= 0.0 and self._last >= 1.0:
            return

        w = max(1, self.winfo_width())
        thumb_w = T.SCROLL_THUMB_WIDTH
        x0 = (w - thumb_w) / 2
        x1 = x0 + thumb_w
        r = thumb_w / 2                       # pill radius = half width
        top, bot = self._thumb_span()

        # Groove behind the thumb: hover-only, spanning the full track (like
        # Kickoff's background-vertical fading in on hover).
        if self._hover:
            gh = max(1, self.winfo_height())
            self.create_rectangle(
                x0, r, x1, gh - r, width=0, fill=T.SCROLL_GROOVE_COLOR,
            )
            self.create_oval(x0, 0, x1, thumb_w, width=0,
                             fill=T.SCROLL_GROOVE_COLOR)
            self.create_oval(x0, gh - thumb_w, x1, gh, width=0,
                             fill=T.SCROLL_GROOVE_COLOR)

        color = T.SCROLL_THUMB_HOVER if (self._hover or self._dragging) \
            else T.SCROLL_THUMB_COLOR

        # Pill thumb: round cap + body + round cap (all one colour).
        self.create_oval(x0, top, x1, top + thumb_w, width=0, fill=color)
        self.create_rectangle(x0, top + r, x1, bot - r, width=0, fill=color)
        self.create_oval(x0, bot - thumb_w, x1, bot, width=0, fill=color)

    # -- interaction -------------------------------------------------------
    def _on_enter(self, _e=None) -> None:
        self._hover = True
        self._redraw()

    def _on_leave(self, _e=None) -> None:
        self._hover = False
        self._redraw()

    def _hit_thumb(self, y: int) -> bool:
        top, bot = self._thumb_span()
        return top <= y <= bot

    def _on_press(self, e) -> None:
        top, bot = self._thumb_span()
        if self._hit_thumb(e.y):
            # Grab the thumb: remember where within it we grabbed.
            self._dragging = True
            self._drag_dy = e.y - top
        else:
            # Press on the empty track: jump so the thumb centres on the click,
            # then start dragging from there.
            self._dragging = True
            self._drag_dy = (bot - top) / 2
            self._scroll_to_pixel(e.y)
        self._redraw()

    def _on_drag(self, e) -> None:
        if self._dragging:
            self._scroll_to_pixel(e.y)

    def _on_release(self, _e=None) -> None:
        self._dragging = False
        self._redraw()

    def _scroll_to_pixel(self, y: int) -> None:
        """Move the view so the thumb's top lands at (y - grab offset)."""
        h = max(1, self.winfo_height())
        thumb_len = self._last - self._first
        new_top = (y - self._drag_dy) / h
        new_top = max(0.0, min(1.0 - thumb_len, new_top))
        try:
            self._command("moveto", new_top)
        except tk.TclError:
            pass
