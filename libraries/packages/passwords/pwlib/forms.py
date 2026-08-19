"""Curses sub-screens and primitives: line/multi-line prompts, the detail view,
the element editor, the new-entry wizard, delete confirmation, and the sequential
('m') copy flow. Kept apart from tui.py so each file stays small."""

import curses

from . import clipboard
from .model import Entry, ESSENTIAL, clean_key, strip_scheme

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


def nav_bar(win, y, pairs):
    """Draw a left-aligned "KEY label   KEY label ..." nav bar on row y.

    Structured like azarch's draw_nav: each verb is a keycap, a space, then a dim
    label, verbs separated by a 3-space gap. NOT centred and NOT coloured -- the
    keycap is drawn normal and the label A_DIM. `pairs` is a list of (key, label).
    Shared by the search UI (tui._nav) and the detail view so both bottom bars
    look identical."""
    _, w = win.getmaxyx()
    x = 0
    gap = '   '
    for i, (key, label) in enumerate(pairs):
        if i:
            addstr(win, y, x, gap, curses.A_DIM)
            x += len(gap)
        addstr(win, y, x, key)
        x += len(key)
        if label:
            addstr(win, y, x, ' ' + label, curses.A_DIM)
            x += 1 + len(label)
        if x >= w - 1:
            break


# Bottom navigation hints, one set per page. The bar at the bottom of every
# screen names exactly the keys that page answers to -- it is how the user learns
# the controls -- so each page passes its own set to nav_bar(). Nothing advertised
# here is a dead key on its page.
_NAV_DETAIL = [
    ('ESC', 'back'),
    ('Q', 'quit'),
]
# New-entry: typing the title (the header updates live as you type).
_NAV_NEW_TITLE = [
    ('ENTER', 'next'),
    ('ESC', 'back'),
]
# New-entry: the column picker. Type a number then ENTER to open that column;
# ESC finishes and saves the entry. (Empty ENTER just notes "no input" and stays.)
_NAV_PICK = [
    ('ENTER', 'continue'),
    ('ESC', 'done'),
]
# New-entry: entering one column's value (its own NEW ENTRY-style page).
_NAV_VALUE = [
    ('ENTER', 'add'),
    ('ESC', 'cancel'),
]
# Edit view (e): the element editor's key set, shown as a bottom bar like the
# rest of the app instead of a top hint line.
_NAV_EDIT = [
    ('↑↓', 'move'),
    ('e', 'edit'),
    ('k', 'rename'),
    ('a', 'add'),
    ('r', 'remove'),
    ('ESC', 'back'),
]
# Multi-copy (m): stepping through each element; ENTER advances, q/ESC stops.
_NAV_MULTI = [
    ('ENTER', 'next'),
    ('Q', 'stop'),
    ('ESC', 'stop'),
]


def prompt_line(win, label, initial='', y=None, on_change=None, nav=None):
    """Single-line input. Returns the string, or None on Esc.

    Drawn as plain text (no reverse-video highlight) so typing does not paint a
    white bar. By default it sits on the bottom row; pass `y` to place it on a
    specific row (used so the new-entry inputs sit right under their header).
    `on_change(text)`, if given, is called with the current buffer after every
    edit -- the new-entry wizard uses it to refresh its "NEW ENTRY <title>"
    header live as the user types. `nav`, if given, is a nav_bar() pairs list
    drawn on the bottom row while the prompt is live so the page keeps its
    contextual key hints (the cursor stays on the input row)."""
    buf = list(initial)
    curses.curs_set(1)
    try:
        while True:
            h, w = win.getmaxyx()
            row = h - 1 if y is None else y
            if nav is not None and row != h - 1:
                win.move(h - 1, 0)
                win.clrtoeol()
                nav_bar(win, h - 1, nav)
            win.move(row, 0)
            win.clrtoeol()
            text = label + ''.join(buf)
            addstr(win, row, 0, text)
            win.move(row, min(len(text), w - 1))
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
            else:
                continue
            if on_change is not None:
                on_change(''.join(buf))
    finally:
        curses.curs_set(0)


def prompt_multiline(win, label, start_row=None):
    """Collect note lines until an empty line is entered. Returns joined text.

    Default (start_row=None) is the standalone screen used by the editor: header
    on row 0, lines below. When start_row is given (the new-entry value page) the
    caller has already drawn the NEW ENTRY header + added list, so we render the
    prompt/lines from start_row down and keep the value-page key hints on the
    bottom row."""
    lines = []
    standalone = start_row is None
    top = 2 if standalone else start_row
    while True:
        if standalone:
            win.erase()
            addstr(win, 0, 0, label + ' (enter an empty line to finish):',
                   curses.A_BOLD)
        else:
            # Clear just the note region (header/added list drawn by the caller).
            h, _ = win.getmaxyx()
            for r in range(top, h - 1):
                win.move(r, 0)
                win.clrtoeol()
            addstr(win, top - 1, 0, 'add a note line; empty line finishes',
                   curses.A_DIM)
        for i, l in enumerate(lines):
            addstr(win, top + 1 + i, 2, l)
        input_row = None if standalone else top + 1 + len(lines)
        line = prompt_line(win, '> ', y=input_row,
                           nav=None if standalone else _NAV_VALUE)
        if line is None or line == '':
            break
        lines.append(line)
    return '\n'.join(lines)


def _label(key):
    """Display form of an element key. The built-in keys are stored lower-case and
    shown title-cased ("username" -> "Username"); a CUSTOM column is shown exactly
    as the user typed it (their capitalization stands -- we never re-case it)."""
    return _BUILTIN_LABELS.get(key, key)


def show_detail(win, entry):
    """Render one entry:

        Title) something.com

        Username) some_user
        Password) lol

    -- the title first, a blank line, then each other element as "Label) value"
    (multi-line notes indented under their label). The bottom row is the nav-hints
    bar, not a "press any key" line."""
    win.erase()
    h, _ = win.getmaxyx()
    addstr(win, 0, 0, 'Title) ' + entry.title, curses.A_BOLD)
    row = 2  # blank line 1 separates the title from the rest
    for key, value in entry.elements:
        if key == 'title':
            continue
        if row >= h - 1:
            break
        label = _label(key)
        if key == 'notes' or '\n' in value:
            addstr(win, row, 0, label + ')', curses.A_BOLD)
            row += 1
            for vline in (value.split('\n') if value else []):
                if row >= h - 1:
                    break
                addstr(win, row, 2, vline)
                row += 1
        else:
            addstr(win, row, 0, label + ') ', curses.A_BOLD)
            addstr(win, row, len(label) + 2, value)
            row += 1
    nav_bar(win, h - 1, _NAV_DETAIL)
    while True:
        ch = win.getch()
        if ch in (ord('q'), ord('Q')):
            return 'quit'          # q = FULL quit, propagated out of the app
        if ch in (ESC,) + ENTER_KEYS:
            return None            # ESC / ENTER = back to the list only


def confirm_delete(win, entry):
    win.erase()
    addstr(win, 0, 0, 'DELETE: ' + entry.title, curses.A_BOLD)
    addstr(win, 2, 0, 'This permanently removes the entry from the store.')
    ans = prompt_line(win, 'Type "yes" to confirm: ', y=4,
                      nav=[('yes+ENTER', 'delete'), ('ESC', 'cancel')])
    return ans is not None and ans.strip() == 'yes'


# The offered columns after a title is entered. Order is the menu order; the key
# is what gets stored (lower-case, matching the on-disk element keys). "Notes" is
# multi-line; everything else is a single line. The final "custom" slot lets the
# user name their own column.
_COLUMN_CHOICES = [
    ('Email', 'email', False),
    ('Username', 'username', False),
    ('Password', 'password', False),
    ('Notes', 'notes', True),
]

# Display labels for the built-in keys only (title-cased). Custom keys are NOT in
# here, so _label() shows them verbatim -- the user's own capitalization wins.
_BUILTIN_LABELS = {key: label for label, key, _ml in _COLUMN_CHOICES}


def _header_for_title(title):
    """The NEW ENTRY header text for a (possibly URL-ish) title: the scheme/www
    prefix is stripped so "NEW ENTRY https://www.x.com" reads "NEW ENTRY x.com"."""
    shown = strip_scheme(title).strip()
    return 'NEW ENTRY ' + shown if shown else 'NEW ENTRY'


def _draw_new_header(win, title):
    """Redraw the NEW ENTRY header row for the current title (called live as the
    title is typed, and again on each column-picker redraw)."""
    h, w = win.getmaxyx()
    win.move(0, 0)
    win.clrtoeol()
    addstr(win, 0, 0, _header_for_title(title)[:w - 1], curses.A_BOLD)


def _page_reset(win):
    """Erase AND force the next refresh to repaint every cell from scratch.

    The new-entry pages redraw a lot with per-row clrtoeol() (climbing note input,
    live header), which can leave ncurses' cell-diff optimizer convinced a stale
    glyph is still correct -- so a bare erase() sometimes leaves a leftover '>'
    from the previous page. clearok(True) makes the next refresh unconditional, so
    no stale cell can survive a page transition. Called at the top of each
    new-entry page draw."""
    win.erase()
    try:
        win.clearok(True)
    except curses.error:
        pass


def _draw_added(win, elements, start_row):
    """Draw the columns added so far, one per line, starting at start_row. These
    populate ABOVE the "Add a column" menu so the entry grows on screen as the
    user fills it in. Returns the next free row. Title is skipped (it is already
    in the header). Values are shown inline; notes are shown as "(N lines)"."""
    row = start_row
    h, _ = win.getmaxyx()
    for key, value in elements:
        if key == 'title':
            continue
        if row >= h - 2:
            break
        if key == 'notes' or '\n' in value:
            n = len([l for l in value.split('\n') if l]) if value else 0
            shown = '(%d line%s)' % (n, '' if n == 1 else 's')
        else:
            shown = value
        addstr(win, row, 0, _label(key) + ') ', curses.A_BOLD)
        addstr(win, row, len(_label(key)) + 2, shown)
        row += 1
    return row


def _add_columns(win, elements, title):
    """Column picker page. Shows the NEW ENTRY header, the columns added so far
    (populating above the menu), then "Add a column:" with a numbered menu whose
    input sits one line under it. Loops until the user is done. Mutates `elements`.

    Type a number then ENTER to open that column's value page; a column already
    present is tagged "(added)" and re-picking it edits its value. ENTER on an
    EMPTY input just notes that nothing was typed and stays. ESC finishes and
    saves the entry."""
    custom_n = len(_COLUMN_CHOICES) + 1
    note = ''  # transient message under the input (e.g. "no input provided")
    while True:
        _page_reset(win)
        _draw_new_header(win, title)
        present = {k for k, _ in elements}
        # Added columns populate directly under the header (row 1 down); then one
        # blank line, then the menu.
        row = _draw_added(win, elements, 1)
        row += 1  # single blank line between the added list and the menu
        addstr(win, row, 0, 'Add a column:', curses.A_BOLD)
        row += 1
        for i, (label, key, _ml) in enumerate(_COLUMN_CHOICES, 1):
            tag = '  (added)' if key in present else ''
            addstr(win, row, 2, '%d) %s%s' % (i, label, tag))
            row += 1
        addstr(win, row, 2, '%d) <CUSTOM COLUMN>' % custom_n)
        row += 2  # single blank line between the menu and the input

        # A transient hint (e.g. "no input provided") sits just below the input.
        if note:
            addstr(win, row + 1, 0, note, curses.A_DIM)
        choice = prompt_line(win, '> ', y=row, nav=_NAV_PICK)
        note = ''
        if choice is None:
            break                    # ESC = done (save and leave)
        choice = choice.strip()
        if choice == '':
            note = '(no input provided -- type a number, or ESC to finish)'
            continue
        if not choice.isdigit():
            note = '(not a number -- pick 1-%d)' % custom_n
            continue
        n = int(choice)
        if 1 <= n <= len(_COLUMN_CHOICES):
            label, key, multiline = _COLUMN_CHOICES[n - 1]
            _set_column(win, elements, title, key, label, multiline)
        elif n == custom_n:
            name = _prompt_custom_name(win, title, elements)
            if name:
                _set_column(win, elements, title, name, name, False)
        else:
            note = '(no such option -- pick 1-%d)' % custom_n


def _column_page_header_row(win, title, elements):
    """Draw a value page's top (NEW ENTRY header + added list) and return the row
    for the column's own heading -- one blank line under the added list."""
    _page_reset(win)
    _draw_new_header(win, title)
    return _draw_added(win, elements, 1) + 1


def _prompt_custom_name(win, title, elements):
    """Value-page for a custom column's NAME (its own "NEW COLUMN" heading + input
    right under it). Returns the cleaned name, or '' if cancelled/empty. The name
    is stored verbatim -- we never change its capitalization."""
    row = _column_page_header_row(win, title, elements)
    addstr(win, row, 0, 'NEW COLUMN', curses.A_BOLD)
    name = prompt_line(win, '', y=row + 1, nav=_NAV_VALUE)
    if name is None:
        return ''
    return clean_key(name)


def _set_column(win, elements, title, key, label, multiline):
    """Open a column's own value page (mirrors the NEW ENTRY title screen: a
    heading naming the column, the input right under it, contextual hints at the
    bottom) and store the value under `key`, replacing any existing value so
    re-picking a column edits it. Notes use the multi-line prompt.

    The heading shows the label as-is (built-ins title-cased, a custom name kept
    exactly as the user typed it -- never force-uppercased)."""
    heading = _label(label)
    if multiline:
        row = _column_page_header_row(win, title, elements)
        addstr(win, row, 0, heading, curses.A_BOLD)
        # +2 so prompt_multiline's own "add a note line" hint (drawn one row above
        # its region) lands below this heading rather than on top of it.
        value = prompt_multiline(win, heading, start_row=row + 2)
    else:
        existing = next((v for k, v in elements if k == key), '')
        row = _column_page_header_row(win, title, elements)
        addstr(win, row, 0, heading, curses.A_BOLD)
        value = prompt_line(win, '', existing, y=row + 1, nav=_NAV_VALUE)
        if value is None:
            return
    for pair in elements:
        if pair[0] == key:
            pair[1] = value
            return
    elements.append([key, value])


def new_entry(win):
    """Wizard: title (only requirement) -> numbered column picker.

    Only a title is needed to save. Pressing ENTER on an empty title is the same
    as ESC -- it goes back (returns None). The title input sits directly under the
    NEW ENTRY header, which updates live to show the title with any URL scheme /
    www. prefix stripped."""
    _page_reset(win)
    _draw_new_header(win, '')
    title = prompt_line(win, '', y=1, nav=_NAV_NEW_TITLE,
                        on_change=lambda t: _draw_new_header(win, t))
    if title is None:
        return None
    title = strip_scheme(title).strip()
    if title == '':
        # No title -> ENTER behaves like ESC: back, nothing saved.
        return None
    elements = [['title', title]]
    _add_columns(win, elements, title)
    return Entry(elements)


def edit_entry(win, entry):
    """Interactive element editor.

    Returns (changed, quit): `changed` is True if any element changed; `quit` is
    True only if the user pressed q (a FULL quit that the caller propagates out of
    the app). ESC just leaves the editor (back), quit stays False."""
    changed = False
    sel = 0
    while True:
        win.erase()
        h, _ = win.getmaxyx()
        addstr(win, 0, 0, 'EDIT: ' + entry.title, curses.A_BOLD)
        row = 2
        for i, (key, value) in enumerate(entry.elements):
            if row >= h - 1:
                break
            marker = '> ' if i == sel else '  '
            shown = value.replace('\n', ' / ')
            attr = curses.A_REVERSE if i == sel else 0
            addstr(win, row, 0, '%s%s) %s' % (marker, key, shown), attr)
            row += 1
        nav_bar(win, h - 1, _NAV_EDIT)   # bottom bar teaches the keys
        ch = win.getch()
        if ch in (ord('q'), ord('Q')):
            return changed, True     # q = FULL quit
        if ch == ESC:
            return changed, False    # ESC = back to the list only
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


def sequential_copy(win, entry):
    """Clip each non-notes element in turn (password first). Enter advances,
    q aborts. Returns True if every element was clipped."""
    seq = entry.copy_sequence()
    h, _ = win.getmaxyx()
    if not seq:
        win.erase()
        addstr(win, 0, 0, 'nothing to copy (no elements besides title/notes).',
               curses.A_BOLD)
        nav_bar(win, h - 1, [('ESC', 'back'), ('any', 'back')])
        win.getch()
        return False
    for i, (key, value) in enumerate(seq):
        ok = clipboard.copy(value)
        win.erase()
        addstr(win, 0, 0, 'MULTI-COPY: ' + entry.title, curses.A_BOLD)
        verb = 'clipped' if ok else 'clip FAILED'
        addstr(win, 2, 0, '%s [%d/%d]  %s' % (verb, i + 1, len(seq), key),
               curses.A_BOLD)
        addstr(win, 3, 0, 'paste it, then advance to the next.', curses.A_DIM)
        nav_bar(win, h - 1, _NAV_MULTI)   # bottom bar teaches the keys
        while True:
            ch = win.getch()
            if ch in ENTER_KEYS:
                break
            if ch in (ord('q'), ESC):
                return False
    return True
