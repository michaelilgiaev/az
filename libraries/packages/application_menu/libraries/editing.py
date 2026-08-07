#!/usr/bin/env python3
"""Az'arch application menu -- standard text-editing for a Tk Entry.

A bare Tk ``Entry`` behaves emacs-ish (Ctrl+A jumps to line start, no undo), not
like a normal desktop text field. The search box must behave EXACTLY like a
standard editor's input (gedit): select-all, cut/copy/paste, undo/redo, word
navigation and word delete, all with the X clipboard. :func:`enable_standard_
editing` installs that behaviour on any Entry backed by a ``StringVar``.

Only the standard library is used. Undo/redo is implemented here because Tk's
``Entry`` (unlike ``Text``) has no built-in undo.
"""

from __future__ import annotations

import tkinter as tk


class _UndoStack:
    """A minimal coalescing undo/redo history for a StringVar-backed Entry.

    Snapshots (text, cursor) are pushed as the user types. Consecutive plain-typing
    edits coalesce into one undo step (like a real editor) until a boundary
    (space, delete, paste, cut, or an explicit undo/redo) forces a new step.
    """

    def __init__(self, entry: tk.Entry, var: tk.StringVar) -> None:
        self._entry = entry
        self._var = var
        self._undo: list[tuple[str, int]] = [(var.get(), 0)]
        self._redo: list[tuple[str, int]] = []
        self._suspend = False        # ignore var-trace while we drive it
        self._coalesce = False       # merge the next typed edit into the top
        self._trace = var.trace_add("write", self._on_change)

    def _cursor(self) -> int:
        try:
            return self._entry.index("insert")
        except tk.TclError:
            return len(self._var.get())

    def _on_change(self, *_a) -> None:
        if self._suspend:
            return
        self._redo.clear()
        snap = (self._var.get(), self._cursor())
        if self._coalesce and self._undo:
            self._undo[-1] = snap
        else:
            self._undo.append(snap)
        # Coalesce further single-character edits until break_coalescing().
        self._coalesce = True

    def break_coalescing(self) -> None:
        """Force the next edit to start a fresh undo step (call on space, paste,
        cut, delete, or when focus/selection changes materially)."""
        self._coalesce = False

    def _apply(self, text: str, cursor: int) -> None:
        self._suspend = True
        try:
            self._var.set(text)
            self._entry.icursor(min(cursor, len(text)))
            self._entry.selection_clear()
        except tk.TclError:
            pass
        finally:
            self._suspend = False
        self._coalesce = False

    def undo(self) -> str:
        if len(self._undo) > 1:
            cur = self._undo.pop()
            self._redo.append(cur)
            text, cursor = self._undo[-1]
            self._apply(text, cursor)
        return "break"

    def redo(self) -> str:
        if self._redo:
            text, cursor = self._redo.pop()
            self._undo.append((text, cursor))
            self._apply(text, cursor)
        return "break"


def enable_standard_editing(entry: tk.Entry, var: tk.StringVar) -> _UndoStack:
    """Give ``entry`` the full set of standard editor key bindings and return the
    undo stack (kept referenced by the caller so its var-trace stays alive).

    Bindings installed (matching a normal desktop text field / gedit):
      Ctrl+A            select all
      Ctrl+C / X / V    copy / cut / paste (X clipboard)
      Ctrl+Z           undo
      Ctrl+Y, Ctrl+Shift+Z   redo
      Ctrl+Backspace    delete previous word
      Ctrl+Delete       delete next word
    (Home/End, Shift+navigation selection and Ctrl+Left/Right word jumps are
    already provided by Tk's default Entry bindings and are left intact.)
    """
    undo = _UndoStack(entry, var)

    def select_all(_e=None) -> str:
        try:
            entry.selection_range(0, "end")
            entry.icursor("end")
        except tk.TclError:
            pass
        return "break"  # stop Tk's default Ctrl+A (go to line start)

    def copy(_e=None) -> str:
        try:
            if entry.selection_present():
                entry.event_generate("<<Copy>>")
        except tk.TclError:
            pass
        return "break"

    def cut(_e=None) -> str:
        try:
            if entry.selection_present():
                # Break BEFORE the edit so the cut is its own undo step, not
                # merged with prior typing.
                undo.break_coalescing()
                entry.event_generate("<<Cut>>")
                undo.break_coalescing()
        except tk.TclError:
            pass
        return "break"

    def paste(_e=None) -> str:
        # Replace any selection with the clipboard text, then insert. Doing it by
        # hand (rather than <<Paste>>) gives consistent behaviour across Tk
        # builds and keeps the undo history correct.
        try:
            clip = entry.clipboard_get()
        except tk.TclError:
            clip = ""
        if clip:
            try:
                # Break BEFORE mutating so the paste starts a fresh undo step
                # (otherwise it coalesces into the previous typing run and a
                # single undo would wrongly remove both).
                undo.break_coalescing()
                if entry.selection_present():
                    entry.delete("sel.first", "sel.last")
                entry.insert("insert", clip)
                undo.break_coalescing()
            except tk.TclError:
                pass
        return "break"

    def del_prev_word(_e=None) -> str:
        try:
            pos = entry.index("insert")
            text = var.get()
            i = pos
            # Skip whitespace immediately left, then the word.
            while i > 0 and text[i - 1].isspace():
                i -= 1
            while i > 0 and not text[i - 1].isspace():
                i -= 1
            if i < pos:
                undo.break_coalescing()
                entry.delete(i, pos)
                undo.break_coalescing()
        except tk.TclError:
            pass
        return "break"

    def del_next_word(_e=None) -> str:
        try:
            pos = entry.index("insert")
            text = var.get()
            n = len(text)
            j = pos
            while j < n and text[j].isspace():
                j += 1
            while j < n and not text[j].isspace():
                j += 1
            if j > pos:
                undo.break_coalescing()
                entry.delete(pos, j)
                undo.break_coalescing()
        except tk.TclError:
            pass
        return "break"

    def on_space(_e=None) -> None:
        # A space is a natural undo boundary (word-by-word undo, like editors).
        undo.break_coalescing()

    # Bind on both cases so it works regardless of Caps/Shift state.
    for seq in ("<Control-a>", "<Control-A>"):
        entry.bind(seq, select_all)
    for seq in ("<Control-c>", "<Control-C>"):
        entry.bind(seq, copy)
    for seq in ("<Control-x>", "<Control-X>"):
        entry.bind(seq, cut)
    for seq in ("<Control-v>", "<Control-V>"):
        entry.bind(seq, paste)
    for seq in ("<Control-z>", "<Control-Z>"):
        entry.bind(seq, lambda _e: undo.undo())
    for seq in ("<Control-y>", "<Control-Y>",
                "<Control-Shift-z>", "<Control-Shift-Z>"):
        entry.bind(seq, lambda _e: undo.redo())
    entry.bind("<Control-BackSpace>", del_prev_word)
    entry.bind("<Control-Delete>", del_next_word)
    entry.bind("<space>", on_space, add="+")

    # Expose the operations on the returned object so they can be invoked
    # directly (tests, or programmatic edits) without depending on synthetic
    # key-event delivery, which is unreliable headless.
    undo.select_all = select_all
    undo.copy = copy
    undo.cut = cut
    undo.paste = paste
    undo.del_prev_word = del_prev_word
    undo.del_next_word = del_next_word

    return undo
