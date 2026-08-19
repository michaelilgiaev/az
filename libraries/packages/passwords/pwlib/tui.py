"""The main search/select curses UI.

Two input states resolve the conflict between "type letters to search" and
"single-letter commands":

  SEARCH state (default) - printable keys filter by title, live. the arrow keys
                           move into the result list; enter copies the password.
  SELECT state           - the highlight is on a result; the action keys act on
                           it. "/" drops back to the search box.

NAVIGATION mirrors the Az'arch terminal UI (packages/azarch/render.c): the same
WASD / HJKL / arrow movement, "/" for search. The bottom line is a plain,
left-aligned "KEY label   KEY label" nav bar built the same way azarch draws its
verbs (a keycap, a space, a dim label, a gap) -- NOT centred and NOT coloured,
just structured the same.

Because W/A/S/D and H/J/K/L are movement, the single-letter ACTIONS deliberately
avoid every movement key: v show, e edit, n new, x delete, m multi. ENTER copies
the password. There is no Tab. ESC never quits -- it jumps back to the START of
the UI (clears the query, highlight to the top) and is safe to spam. Only q / Q
quit.
"""

import curses

from . import clipboard, forms

SEARCH, SELECT = 0, 1

# Movement keys, mirroring azarch: WASD + HJKL + arrows all drive the vertical
# list (there is only a vertical axis here, exactly like azarch's own list, whose
# nav labels every one of these clusters simply "move"). Held as sets of the
# ordinals so the handlers can test membership cheaply.
_UP_KEYS = {curses.KEY_UP, ord('w'), ord('W'), ord('k'), ord('K'),
            ord('a'), ord('A'), ord('h'), ord('H'), curses.KEY_LEFT}
_DOWN_KEYS = {curses.KEY_DOWN, ord('s'), ord('S'), ord('j'), ord('J'),
              ord('d'), ord('D'), ord('l'), ord('L'), curses.KEY_RIGHT}
_MOVE_KEYS = _UP_KEYS | _DOWN_KEYS


def _nav(win, y, pairs):
    """Draw a left-aligned "KEY label   KEY label ..." nav bar on row y.

    Structured like azarch's draw_nav (packages/azarch/render.c): each verb is a
    keycap, a space, then a dim label, verbs separated by a 3-space gap. NOT
    centred and NOT coloured -- the keycap is drawn normal and the label A_DIM,
    matching the plain look the spec asks for. `pairs` is a list of (key, label)."""
    h, w = win.getmaxyx()
    x = 0
    gap = '   '
    for i, (key, label) in enumerate(pairs):
        if i:
            forms.addstr(win, y, x, gap, curses.A_DIM)
            x += len(gap)
        forms.addstr(win, y, x, key)
        x += len(key)
        if label:
            forms.addstr(win, y, x, ' ' + label, curses.A_DIM)
            x += 1 + len(label)
        if x >= w - 1:
            break


# The SELECT-mode nav: the packed movement cluster (one "cell" whose key glyphs
# read "WASD HJKL <arrows>" and whose label is "move"), then the verbs. Kept as
# data so the drawing and the tests share one definition.
_NAV_MOVE = ('WASD HJKL ←↑→↓', 'move')
_NAV_SELECT = [
    _NAV_MOVE,
    ('ENTER', 'copy'),
    ('v', 'show'),
    ('e', 'edit'),
    ('n', 'new'),
    ('x', 'delete'),
    ('m', 'multi'),
    ('/', 'search'),
    ('ESC', 'back'),
    ('Q', 'quit'),
]


class App:
    def __init__(self, stdscr, store):
        self.stdscr = stdscr
        self.store = store
        self.query = ''
        self.mode = SEARCH
        self.persistent = False
        self.dirty = False
        self.sel = 0
        self.status = ''
        self.results = []
        self.refilter()

    # ----- data -----

    def refilter(self):
        self.results = self.store.filter(self.query)
        if self.sel >= len(self.results):
            self.sel = max(0, len(self.results) - 1)

    def selected_entry(self):
        if 0 <= self.sel < len(self.results):
            return self.results[self.sel]
        return None

    def move(self, ch):
        if not self.results:
            return
        if ch in _UP_KEYS:
            self.sel = (self.sel - 1) % len(self.results)
        else:
            self.sel = (self.sel + 1) % len(self.results)

    def reset(self):
        """ESC: jump back to the START of the UI -- clear the search query, put
        the highlight at the top, and return to the search box. Spammable (a no-op
        once already at the start)."""
        self.query = ''
        self.sel = 0
        self.mode = SEARCH
        self.refilter()

    # ----- drawing -----

    def draw(self):
        s = self.stdscr
        s.erase()
        h, w = s.getmaxyx()
        header = ' passwords '
        if self.persistent:
            header += '[persistent] '
        forms.addstr(s, 0, 0, header + ' ' * max(0, w - len(header)),
                     curses.A_REVERSE)

        caret = ' _' if self.mode == SEARCH else ''
        forms.addstr(s, 1, 0, 'Search: ' + self.query + caret)
        forms.addstr(s, 2, 0, '-' * (w - 1))

        top = 3
        bottom = h - 1
        visible = max(1, bottom - top)
        start = 0
        if self.sel >= visible:
            start = self.sel - visible + 1
        row = top
        for idx in range(start, len(self.results)):
            if row >= bottom:
                break
            e = self.results[idx]
            names = e.element_names()
            meta = '(%d: %s)' % (len(names), ', '.join(names))
            marker = '> ' if idx == self.sel else '  '
            line = '%s%s   %s' % (marker, e.title, meta)
            if idx == self.sel:
                attr = curses.A_REVERSE if self.mode == SELECT else curses.A_BOLD
            else:
                attr = 0
            forms.addstr(s, row, 0, line, attr)
            row += 1
        if not self.results:
            forms.addstr(s, top, 0, '(no matches)', curses.A_DIM)

        if self.status:
            forms.addstr(s, h - 1, 0, self.status, curses.A_DIM)
        else:
            _nav(s, h - 1, _NAV_SELECT)
        self.status = ''
        s.refresh()

    # ----- input -----

    def run(self):
        curses.curs_set(0)
        while True:
            self.draw()
            try:
                ch = self.stdscr.getch()
            except KeyboardInterrupt:
                break
            if self.mode == SEARCH:
                if not self.handle_search(ch):
                    break
            else:
                if not self.handle_select(ch):
                    break
        return self.dirty

    def handle_search(self, ch):
        # Only q/Q quit. ESC never quits -- it resets to the start of the UI
        # (spammable): clears the query and puts the highlight back at the top.
        if ch in (ord('q'), ord('Q')):
            return False
        if ch == forms.ESC:
            self.reset()
            return True
        if ch in (curses.KEY_UP, curses.KEY_DOWN):
            # In SEARCH only the ARROWS move into the list -- letters are query
            # text here (WASD/HJKL become movement once in SELECT).
            if self.results:
                self.mode = SELECT
                self.move(ch)
            return True
        if ch in forms.ENTER_KEYS:
            if self.selected_entry() is None:
                return True
            self.copy_password()
            return self.persistent
        if ch in forms.BACKSPACE_KEYS:
            self.query = self.query[:-1]
            self.refilter()
            return True
        if ch == ord('n'):
            # 'n' creates a new entry from the search box too, so the first entry
            # can be added on an empty store (this used to need Tab, now removed).
            self.action_new()
            return True
        if 32 <= ch <= 126:
            self.query += chr(ch)
            self.refilter()
            return True
        return True

    def handle_select(self, ch):
        # Only q/Q quit. ESC never quits -- it resets to the start of the UI
        # (spammable); "/" drops back to the search box.
        if ch in (ord('q'), ord('Q')):
            return False
        if ch == forms.ESC:
            self.reset()
            return True
        if ch == ord('/'):
            self.mode = SEARCH
            return True
        if ch in _MOVE_KEYS:
            self.move(ch)
            return True
        if ch in forms.BACKSPACE_KEYS:
            self.mode = SEARCH
            self.query = self.query[:-1]
            self.refilter()
            return True
        if ch in forms.ENTER_KEYS:
            if self.selected_entry() is None:
                return True
            self.copy_password()
            return self.persistent
        c = chr(ch) if 32 <= ch <= 126 else ''
        if c == 'n':
            self.action_new()
            return True
        entry = self.selected_entry()
        if entry is None:
            return True
        if c == 'v':
            forms.show_detail(self.stdscr, entry)
        elif c == 'e':
            if forms.edit_entry(self.stdscr, entry):
                self.dirty = True
        elif c == 'x':
            if forms.confirm_delete(self.stdscr, entry):
                self.store.entries.remove(entry)
                self.dirty = True
                self.refilter()
                self.status = 'deleted'
        elif c == 'm':
            completed = forms.sequential_copy(self.stdscr, entry)
            if completed and not self.persistent:
                return False
        return True

    # ----- actions -----

    def copy_password(self):
        entry = self.selected_entry()
        if entry is None:
            return
        ok = clipboard.copy(entry.password)
        self.status = ('clipped password: ' if ok else 'clip FAILED: ') + entry.title

    def action_new(self):
        entry = forms.new_entry(self.stdscr)
        if entry is None:
            return
        self.store.entries.append(entry)
        self.dirty = True
        self.query = ''
        self.refilter()
        if entry in self.results:
            self.sel = self.results.index(entry)
        self.status = 'added: ' + entry.title


def run(store):
    """Run the UI over store. Returns True if the store was modified."""
    return curses.wrapper(lambda scr: App(scr, store).run())
