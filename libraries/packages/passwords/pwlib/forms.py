"""Curses sub-screens and primitives: line/multi-line prompts, the detail view,
the element editor, the new-entry wizard, delete confirmation, and the sequential
('m') copy flow. Kept apart from tui.py so each file stays small."""

import curses

from . import clipboard
from .model import Entry, ESSENTIAL, clean_key

ENTER_KEYS = (curses.KEY_ENTER, 10, 13)
BACKSPACE_KEYS = (curses.KEY_BACKSPACE, 127, 8)
ESC = 27


def addstr(win, y, x, text, attr=0):
    """Write text clipped to the window; never raises on edges/small terminals."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = text[:max(0, w - x - 1)]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def prompt_line(win, label, initial=''):
    """Single-line input on the bottom row. Returns the string, or None on Esc."""
    buf = list(initial)
    curses.curs_set(1)
    try:
        while True:
            h, w = win.getmaxyx()
            y = h - 1
            win.move(y, 0)
            win.clrtoeol()
            text = label + ''.join(buf)
            addstr(win, y, 0, text, curses.A_REVERSE)
            win.move(y, min(len(text), w - 1))
            ch = win.getch()
            if ch in ENTER_KEYS:
                return ''.join(buf)
            if ch == ESC:
                return None
            if ch in BACKSPACE_KEYS:
                if buf:
                    buf.pop()
            elif 32 <= ch <= 126:
                buf.append(chr(ch))
    finally:
        curses.curs_set(0)


def prompt_multiline(win, label):
    """Collect note lines until an empty line is entered. Returns joined text."""
    lines = []
    while True:
        win.erase()
        addstr(win, 0, 0, label + ' (enter an empty line to finish):',
               curses.A_BOLD)
        for i, l in enumerate(lines):
            addstr(win, 2 + i, 2, l)
        line = prompt_line(win, '> ')
        if line is None or line == '':
            break
        lines.append(line)
    return '\n'.join(lines)


def show_detail(win, entry):
    win.erase()
    h, _ = win.getmaxyx()
    addstr(win, 0, 0, 'DETAIL: ' + entry.title, curses.A_BOLD)
    row = 2
    for key, value in entry.elements:
        if key == 'title':
            continue
        if row >= h - 1:
            break
        if key == 'notes' or '\n' in value:
            addstr(win, row, 0, key + ')', curses.A_BOLD)
            row += 1
            for vline in (value.split('\n') if value else []):
                if row >= h - 1:
                    break
                addstr(win, row, 2, vline)
                row += 1
        else:
            addstr(win, row, 0, key + ') ', curses.A_BOLD)
            addstr(win, row, len(key) + 2, value)
            row += 1
    addstr(win, h - 1, 0, 'press any key to go back', curses.A_DIM)
    win.getch()


def confirm_delete(win, entry):
    win.erase()
    addstr(win, 0, 0, 'DELETE: ' + entry.title, curses.A_BOLD)
    addstr(win, 2, 0, 'This permanently removes the entry from the store.')
    ans = prompt_line(win, 'Type "yes" to confirm: ')
    return ans is not None and ans.strip() == 'yes'


def new_entry(win):
    """Wizard: title -> password -> extra elements -> optional notes."""
    win.erase()
    addstr(win, 0, 0, 'NEW ENTRY (esc to cancel)', curses.A_BOLD)
    title = prompt_line(win, 'Title: ')
    if title is None or title.strip() == '':
        return None
    # Password is essential: re-prompt until non-empty (esc cancels the wizard).
    while True:
        password = prompt_line(win, 'Password: ')
        if password is None:
            return None
        if password != '':
            break
        addstr(win, 2, 0, 'password cannot be empty', curses.A_BOLD)
    elements = [['title', title.strip()], ['password', password]]
    while True:
        name = prompt_line(win, 'Add element name (empty = done): ')
        if name is None or clean_key(name) == '':
            break
        key = clean_key(name)
        value = prompt_line(win, key + ': ')
        if value is None:
            continue
        elements.append([key, value])
    ans = prompt_line(win, 'Add notes? (y/N): ')
    if ans is not None and ans.strip().lower().startswith('y'):
        notes = prompt_multiline(win, 'Notes')
        if notes:
            elements.append(['notes', notes])
    return Entry(elements)


def edit_entry(win, entry):
    """Interactive element editor. Returns True if anything changed."""
    changed = False
    sel = 0
    while True:
        win.erase()
        h, _ = win.getmaxyx()
        addstr(win, 0, 0, 'EDIT: ' + entry.title, curses.A_BOLD)
        addstr(win, 1, 0,
               '↑↓ move   e edit   k rename   a add   r remove   ESC back',
               curses.A_DIM)
        row = 3
        for i, (key, value) in enumerate(entry.elements):
            if row >= h - 1:
                break
            marker = '> ' if i == sel else '  '
            shown = value.replace('\n', ' / ')
            attr = curses.A_REVERSE if i == sel else 0
            addstr(win, row, 0, '%s%s) %s' % (marker, key, shown), attr)
            row += 1
        ch = win.getch()
        if ch in (ord('q'), ESC):
            break
        if not entry.elements:
            continue
        if ch == curses.KEY_UP:
            sel = (sel - 1) % len(entry.elements)
        elif ch == curses.KEY_DOWN:
            sel = (sel + 1) % len(entry.elements)
        elif ch in (ord('e'),) + ENTER_KEYS:
            key, value = entry.elements[sel]
            if key == 'notes':
                new = prompt_multiline(win, 'Notes')
            else:
                new = prompt_line(win, key + ': ', value)
            if new is not None:
                if key in ESSENTIAL and new == '':
                    continue  # title/password must not be blanked
                entry.elements[sel][1] = new
                changed = True
        elif ch == ord('k'):
            key = entry.elements[sel][0]
            if key in ESSENTIAL:
                continue
            new = prompt_line(win, 'Rename element: ', key)
            if new and clean_key(new):
                entry.elements[sel][0] = clean_key(new)
                changed = True
        elif ch == ord('a'):
            name = prompt_line(win, 'New element name: ')
            if name and clean_key(name):
                key = clean_key(name)
                value = prompt_line(win, key + ': ') or ''
                idx = len(entry.elements)
                for j, (k, _) in enumerate(entry.elements):
                    if k == 'notes':
                        idx = j
                        break
                entry.elements.insert(idx, [key, value])
                changed = True
                sel = idx
        elif ch in (ord('r'), ord('x'), curses.KEY_DC):
            if entry.elements[sel][0] in ESSENTIAL:
                continue  # title/password are essential, cannot be removed
            del entry.elements[sel]
            changed = True
            sel = min(sel, len(entry.elements) - 1)
    return changed


def sequential_copy(win, entry):
    """Clip each non-notes element in turn (password first). Enter advances,
    q aborts. Returns True if every element was clipped."""
    seq = entry.copy_sequence()
    if not seq:
        win.erase()
        addstr(win, 0, 0, 'nothing to copy (no elements besides title/notes).',
               curses.A_BOLD)
        addstr(win, 2, 0, 'press any key.', curses.A_DIM)
        win.getch()
        return False
    for i, (key, value) in enumerate(seq):
        ok = clipboard.copy(value)
        win.erase()
        addstr(win, 0, 0, 'MULTI-COPY: ' + entry.title, curses.A_BOLD)
        verb = 'clipped' if ok else 'clip FAILED'
        addstr(win, 2, 0, '%s [%d/%d]  %s' % (verb, i + 1, len(seq), key),
               curses.A_BOLD)
        addstr(win, 3, 0, 'paste it, then enter for the next. q to stop.',
               curses.A_DIM)
        while True:
            ch = win.getch()
            if ch in ENTER_KEYS:
                break
            if ch in (ord('q'), ESC):
                return False
    return True
