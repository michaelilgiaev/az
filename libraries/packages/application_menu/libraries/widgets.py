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
  * :class:`KickoffScrollBar` -- a canvas-drawn, arrow-less rounded scrollbar
    that reproduces Plasma Kickoff's scrollbar exactly.
"""

from __future__ import annotations

import tkinter as tk

import theme as T


# --- Image helpers --------------------------------------------------------
def dim_image(image: tk.PhotoImage, mix: float = T.DISABLED_ICON_MIX,
              toward: str = T.DISABLED_ICON_COLOR) -> tk.PhotoImage:
    """Return a greyed-out copy of ``image`` for a disabled control.

    Each opaque pixel is blended ``mix`` of the way toward ``toward`` (the Breeze
    disabled-foreground grey), leaving fully transparent pixels transparent so the
    icon's shape is preserved but faded -- the standard "this control is inactive"
    look. Used for the Settings (gear) button, which is not wired up yet.

    Pure Tk: we read the source with ``get`` and write the blend with ``put``.
    The top buttons are tiny (POWER_ICON_SIZE px), so the per-pixel loop is cheap
    and runs once at build time. Returns the original image unchanged if anything
    goes wrong (a dim glyph is cosmetic; never break the menu over it)."""
    try:
        w = image.width()
        h = image.height()
    except tk.TclError:
        return image
    tr, tg, tb = _hex_rgb(toward)
    # Start from a full copy so transparency + any pixels we skip are preserved,
    # then repaint only the opaque pixels with their blended-toward-grey colour.
    out = tk.PhotoImage(width=w, height=h)
    try:
        out.tk.call(out, "copy", image)
        for y in range(h):
            for x in range(w):
                # A transparent source pixel stays transparent (shape preserved).
                if image.transparency_get(x, y):
                    continue
                r, g, b = image.get(x, y)[:3]
                r = int(r + (tr - r) * mix)
                g = int(g + (tg - g) * mix)
                b = int(b + (tb - b) * mix)
                out.put(f"#{r:02x}{g:02x}{b:02x}", to=(x, y))
    except tk.TclError:
        return image
    return out


def _hex_rgb(color: str) -> tuple[int, int, int]:
    """Parse a #rrggbb string into an (r, g, b) int triple."""
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


# --- Hover tooltip --------------------------------------------------------
class Tooltip:
    """A tiny borderless hover hint attached to a widget.

    Shows ``text`` in a small Breeze-styled popup the INSTANT the mouse enters the
    widget, and hides it the instant the mouse leaves (or on press / when the
    widget goes away). There is NO dwell delay -- the hint tracks the pointer 1:1
    so the greyed-out Settings button explains itself immediately on hover. Works
    even on a DISABLED control (the button binds no hover-paint handlers, but we
    bind our own <Enter>/<Leave> here so the hint still appears).

    Pure Tkinter, dependency-free and crash-proof, like the rest of the menu: the
    popup is an ``overrideredirect`` Toplevel (no window chrome), positioned just
    below-right of the pointer. Any Tk error while showing/placing it is swallowed
    -- a missing tooltip must never break the button.
    """

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        # Bind on the widget AND (if it has children, e.g. the icon label inside a
        # button frame) so hovering the glyph counts too. add="+" keeps any
        # existing bindings intact. <Enter> shows the hint immediately (no
        # after()-based dwell) so it appears the moment the pointer arrives.
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Button-1>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _show(self, _e=None) -> None:
        if self._tip is not None:
            return
        try:
            if not self._widget.winfo_exists():
                return
            # Position just below-right of the widget's bottom-left corner.
            x = self._widget.winfo_rootx() + 8
            y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
            tip = tk.Toplevel(self._widget)
            tip.wm_overrideredirect(True)
            tip.configure(
                bg=T.TOOLTIP_BORDER, highlightthickness=0
            )
            # A 1px border via an outer frame coloured the border colour, with the
            # label inset by 1px so the border shows as a thin blue outline.
            inner = tk.Label(
                tip, text=self._text, bg=T.TOOLTIP_BG, fg=T.TOOLTIP_FG,
                font=(T.FONT_FAMILY, T.FONT_APP_TYPE), justify="left",
                padx=8, pady=4,
            )
            inner.pack(padx=1, pady=1)
            tip.wm_geometry(f"+{x}+{y}")
            tip.lift()
            self._tip = tip
        except tk.TclError:
            self._tip = None

    def _hide(self, _e=None) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


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


# --- Flat icon button (top settings / pin) --------------------------------
class IconButton(tk.Frame):
    """A borderless square button showing a rasterised Breeze icon that
    highlights on hover. Used for the top-row settings and pin controls.

    Supports an "active" look (a blue outline + tinted fill, like the pinned pin
    in rough-design.png) toggled via :meth:`set_active`, so the pin button can
    show whether the menu is pinned.

    ``disabled=True`` renders a GREYED-OUT, inert button: the glyph is dimmed
    (see :func:`dim_image`), the pointer stays a normal arrow (no ``hand2``),
    hover does not highlight, and clicks are ignored (``command`` is never
    called). This is used for the Settings (gear) button, which is not wired up
    yet -- greying it out tells the user it is inactive instead of leaving them
    wondering why pressing it does nothing.
    """

    def __init__(
        self,
        master: tk.Widget,
        image: tk.PhotoImage,
        command,
        *,
        pad: int = 7,
        disabled: bool = False,
        tooltip: str | None = None,
    ) -> None:
        self._disabled = disabled
        super().__init__(
            master, bg=T.BG_COLOR,
            cursor="arrow" if disabled else "hand2",
            highlightthickness=1, highlightbackground=T.BG_COLOR,
            highlightcolor=T.BG_COLOR,
        )
        self._command = command
        self._active = False
        # A disabled button shows a dimmed copy of the glyph; keep a reference so
        # Tk does not garbage-collect the derived image out from under the label.
        shown = dim_image(image) if disabled else image
        self._label = tk.Label(self, image=shown, bg=T.BG_COLOR)
        self._label.image = shown
        self._label.pack(padx=pad, pady=pad)

        # A disabled button binds NO hover-paint/click handlers, so it neither
        # highlights on hover nor fires on click -- it is completely inert.
        if not disabled:
            for w in (self, self._label):
                w.bind("<Enter>", self._on_enter)
                w.bind("<Leave>", self._on_leave)
                w.bind("<Button-1>", self._press)

        # A hover tooltip (independent of the hover-paint above) is attached even
        # when the button is disabled -- e.g. the greyed-out Settings button tells
        # the user its screen is not built yet. Keep the Tooltip referenced so it
        # is not garbage-collected. Attach it to both the frame and its glyph label
        # so resting on the icon itself still triggers the hint.
        self._tooltips: list[Tooltip] = []
        if tooltip:
            self._tooltips.append(Tooltip(self, tooltip))
            self._tooltips.append(Tooltip(self._label, tooltip))

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
        """Toggle the pinned/active blue-outline look. No-op while disabled (a
        disabled button never changes state)."""
        if self._disabled:
            return
        self._active = active
        self._restore()

    def _press(self, _e=None) -> None:
        # Disabled buttons bind no handlers, but guard anyway so a stray
        # programmatic call can never fire the (unwired) command.
        if self._disabled:
            return
        if self._command is not None:
            self._command()


# --- Bottom power/session button ------------------------------------------
class PowerButton(tk.Frame):
    """A big bottom-bar session button: a Breeze icon beside its label, the whole
    thing highlighting on hover. The caller grids the four buttons into four EQUAL
    columns (``sticky="nsew"``) so each button fills its own equal slice of the
    bottom bar.

    The icon+label content is packed with the default CENTER anchor, so it sits
    centred WITHIN the button's cell -- giving 'each button centred in its own
    slice' rather than the whole group centred across the bar.
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

    def _on_enter(self, _e=None) -> None:
        self._paint(T.HOVER_COLOR)

    def _on_leave(self, _e=None) -> None:
        self._paint(T.BG_COLOR)

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
