#!/usr/bin/env python3
"""Unit tests for the `passwords` app's non-curses logic.

Curses UI flows (prompt_line, new_entry, show_detail) need a live terminal and
are not exercised here; instead we test the pure pieces they lean on -- URL
scheme stripping, the title-only save rule, element (de)serialization round-trips,
and the small display/label helpers in pwlib.forms. Run: python3 test_passwords.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pwlib import forms, model, tui
from pwlib.model import Entry, Store, clean_key, strip_scheme


class StripSchemeTests(unittest.TestCase):
    def test_https_www(self):
        self.assertEqual(strip_scheme('https://www.example.com').strip(),
                         'example.com')

    def test_http_www(self):
        self.assertEqual(strip_scheme('http://www.example.com').strip(),
                         'example.com')

    def test_scheme_without_www(self):
        self.assertEqual(strip_scheme('https://example.com').strip(),
                         'example.com')

    def test_www_without_scheme(self):
        self.assertEqual(strip_scheme('www.github.com').strip(), 'github.com')

    def test_path_and_query_kept(self):
        self.assertEqual(strip_scheme('http://foo.io/path?q=1').strip(),
                         'foo.io/path?q=1')

    def test_other_scheme(self):
        self.assertEqual(strip_scheme('ftp://files.x.org').strip(),
                         'files.x.org')

    def test_leading_whitespace_dropped(self):
        self.assertEqual(strip_scheme('  https://www.spaced.com').strip(),
                         'spaced.com')

    def test_case_insensitive(self):
        self.assertEqual(strip_scheme('HTTPS://WWW.CAPS.COM').strip(),
                         'CAPS.COM')

    def test_plain_title_untouched(self):
        self.assertEqual(strip_scheme('My Bank').strip(), 'My Bank')
        self.assertEqual(strip_scheme('example.com').strip(), 'example.com')

    def test_www_not_a_prefix(self):
        # "wwwsomething" does not start with "www." -> left alone.
        self.assertEqual(strip_scheme('wwwsomething').strip(), 'wwwsomething')

    def test_scheme_only(self):
        self.assertEqual(strip_scheme('http://').strip(), '')


class EssentialRuleTests(unittest.TestCase):
    def test_only_title_is_essential(self):
        # Password is no longer required to save -- only the title is essential.
        self.assertEqual(model.ESSENTIAL, ('title',))
        self.assertIn('title', model.ESSENTIAL)
        self.assertNotIn('password', model.ESSENTIAL)


class RoundTripTests(unittest.TestCase):
    def test_title_only_round_trip(self):
        e = Entry([['title', 'example.com']])
        text = Store([e]).serialize()
        back = Store.parse(text)
        self.assertEqual(back.entries[0].title, 'example.com')
        self.assertEqual(back.entries[0].password, '')  # absent -> ''

    def test_columns_round_trip(self):
        e = Entry([['title', 'something.com'],
                   ['username', 'some_user'],
                   ['password', 'lol']])
        text = Store([e]).serialize()
        back = Store.parse(text).entries[0]
        self.assertEqual([k for k, _ in back.elements],
                         ['title', 'username', 'password'])
        self.assertEqual(back.get('username'), 'some_user')
        self.assertEqual(back.get('password'), 'lol')

    def test_notes_round_trip(self):
        e = Entry([['title', 'x'], ['notes', 'line one\nline two']])
        text = Store([e]).serialize()
        back = Store.parse(text).entries[0]
        self.assertEqual(back.get('notes'), 'line one\nline two')


class CleanKeyTests(unittest.TestCase):
    def test_strips_paren_and_newlines(self):
        self.assertEqual(clean_key(' Foo)\n'), 'Foo')

    def test_empty(self):
        self.assertEqual(clean_key('   '), '')


class FormsHelperTests(unittest.TestCase):
    def test_label_capitalizes_builtins(self):
        # The four built-in keys are stored lower-case and shown title-cased.
        self.assertEqual(forms._label('username'), 'Username')
        self.assertEqual(forms._label('email'), 'Email')
        self.assertEqual(forms._label('password'), 'Password')
        self.assertEqual(forms._label('notes'), 'Notes')

    def test_label_custom_key_verbatim(self):
        # A CUSTOM column keeps the user's exact capitalization -- never re-cased.
        self.assertEqual(forms._label('recovery code'), 'recovery code')
        self.assertEqual(forms._label('MyBank'), 'MyBank')
        self.assertEqual(forms._label('API key'), 'API key')

    def test_header_strips_scheme(self):
        self.assertEqual(forms._header_for_title('https://www.x.com'),
                         'NEW ENTRY x.com')

    def test_header_empty_title(self):
        self.assertEqual(forms._header_for_title(''), 'NEW ENTRY')
        self.assertEqual(forms._header_for_title('http://'), 'NEW ENTRY')

    def test_column_choices_present(self):
        keys = [k for _, k, _ in forms._COLUMN_CHOICES]
        self.assertEqual(keys, ['email', 'username', 'password', 'notes'])
        # Notes is the only multi-line column.
        multiline = [k for _, k, ml in forms._COLUMN_CHOICES if ml]
        self.assertEqual(multiline, ['notes'])


class _FakeWin:
    """Minimal no-op curses window so form helpers that draw can run headless."""
    def getmaxyx(self):
        return (24, 80)

    def erase(self):
        pass

    def move(self, *a):
        pass

    def clrtoeol(self):
        pass

    def clrtobot(self):
        pass

    def clearok(self, *a):
        pass

    def addstr(self, *a, **k):
        pass


class SetColumnTests(unittest.TestCase):
    """_set_column drives one column's value page; with the value prompt stubbed
    and a no-op window it is testable headless. It must store under the key and
    replace (not duplicate) an existing value when the column is re-picked."""

    def test_adds_then_edits_in_place(self):
        win = _FakeWin()
        elements = [['title', 'x']]
        seq = iter(['some_user', 'edited_user'])
        orig = forms.prompt_line
        forms.prompt_line = lambda *a, **k: next(seq)
        try:
            forms._set_column(win, elements, 'x', 'username', 'Username', False)
            self.assertEqual(elements[-1], ['username', 'some_user'])
            # Re-picking the same column edits in place -- no duplicate key.
            forms._set_column(win, elements, 'x', 'username', 'Username', False)
            self.assertEqual(elements[-1], ['username', 'edited_user'])
            self.assertEqual([k for k, _ in elements], ['title', 'username'])
        finally:
            forms.prompt_line = orig

    def test_cancel_value_leaves_elements_unchanged(self):
        win = _FakeWin()
        elements = [['title', 'x']]
        orig = forms.prompt_line
        forms.prompt_line = lambda *a, **k: None   # ESC on the value page
        try:
            forms._set_column(win, elements, 'x', 'email', 'Email', False)
            self.assertEqual(elements, [['title', 'x']])
        finally:
            forms.prompt_line = orig


class QuitVsBackTests(unittest.TestCase):
    """The whole-app rule: q is a FULL quit (handlers return False -> run() ends);
    ESC is only "back" (never quits). Driven headless through App.handle_* with a
    no-op stdscr, so we assert the control-flow contract without a terminal.

    handle_search / handle_select return False to end the app, True to keep going.
    """

    def _app(self):
        store = Store([Entry([['title', 'example.com'],
                              ['username', 'u'], ['password', 'p']])])
        app = tui.App(_FakeWin(), store)
        app.results = list(store.entries)
        app.sel = 0
        return app

    def test_q_quits_from_search(self):
        app = self._app()
        self.assertFalse(app.handle_search(ord('q')))
        self.assertFalse(app.handle_search(ord('Q')))

    def test_q_quits_from_select(self):
        app = self._app()
        app.mode = tui.SELECT
        self.assertFalse(app.handle_select(ord('q')))
        self.assertFalse(app.handle_select(ord('Q')))

    def test_esc_does_not_quit(self):
        app = self._app()
        # ESC returns True (stays in the app) and resets to the search box.
        self.assertTrue(app.handle_search(forms.ESC))
        self.assertEqual(app.mode, tui.SEARCH)
        app.mode = tui.SELECT
        self.assertTrue(app.handle_select(forms.ESC))

    def test_q_in_detail_view_quits_app(self):
        # show_detail returns 'quit' on q; handle_select must propagate that as a
        # FULL quit (return False), not a mere "back".
        app = self._app()
        app.mode = tui.SELECT
        orig = forms.show_detail
        forms.show_detail = lambda *a, **k: 'quit'
        try:
            self.assertFalse(app.handle_select(ord('v')))
        finally:
            forms.show_detail = orig

    def test_back_from_detail_view_keeps_app(self):
        app = self._app()
        app.mode = tui.SELECT
        orig = forms.show_detail
        forms.show_detail = lambda *a, **k: None   # ESC/back inside detail
        try:
            self.assertTrue(app.handle_select(ord('v')))
        finally:
            forms.show_detail = orig

    def test_q_in_edit_quits_app(self):
        app = self._app()
        app.mode = tui.SELECT
        orig = forms.edit_entry
        forms.edit_entry = lambda *a, **k: (False, True)   # (changed, quit)
        try:
            self.assertFalse(app.handle_select(ord('e')))
        finally:
            forms.edit_entry = orig

    def test_edit_change_marks_dirty_without_quitting(self):
        app = self._app()
        app.mode = tui.SELECT
        orig = forms.edit_entry
        forms.edit_entry = lambda *a, **k: (True, False)   # changed, no quit
        try:
            self.assertTrue(app.handle_select(ord('e')))
            self.assertTrue(app.dirty)
        finally:
            forms.edit_entry = orig


if __name__ == '__main__':
    unittest.main(verbosity=2)
