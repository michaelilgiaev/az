"""Data model and text<->object (de)serialization for the password store.

On-disk plaintext format (one or more entries):

    ####
    title) <title>
    password) <secret>
    <key>) <value>          # zero or more extra single-line elements
    notes)                  # optional, normally last
        <indented line>     # zero or more note (random text) lines
    ####

Entries are wrapped by delimiter lines (canonically "####"). Parsing is lenient:
any non-indented line whose stripped form starts with "###" is a delimiter, and
any block of non-blank lines between two delimiters is one entry. This tolerates
the sloppy "###" / "###ww" delimiters that can appear in hand-written files.
"""

import re

# key) value  -- the space after ")" is optional so "notes)" parses too. The key
# is everything up to the first ")", so any key serialize() can emit (digits,
# "-", ".", spaces) parses back identically. Keys never contain ")" (clean_key
# strips it on input), so splitting on the first ")" is unambiguous.
KEY_RE = re.compile(r'^([^)\n]+)\) ?(.*)$')
DELIM = '####'
NOTE_INDENT = '    '
# Only the title is required to save an entry now; password is just another
# optional element. Kept as ('title',) so the editor still refuses to blank or
# remove the title while letting the password be edited/removed freely.
ESSENTIAL = ('title',)

# Leading URI scheme (http/https/ftp/...) plus optional "www.", stripped from a
# title so pasting "https://www.example.com" stores just "example.com". Matches a
# scheme "<letters>://" and/or a leading "www." at the very start, case-insensitive.
_SCHEME_RE = re.compile(r'^\s*(?:[a-zA-Z][a-zA-Z0-9+.-]*://)?(?:www\.)?', re.IGNORECASE)


def strip_scheme(title):
    """Strip a leading URI scheme and/or "www." from a title.

    "https://www.example.com" -> "example.com", "http://foo.io/x" -> "foo.io/x",
    "example.com" -> "example.com". Only the very start is touched; the rest of
    the string (path, query) is left intact. Leading whitespace is dropped too."""
    return _SCHEME_RE.sub('', title, count=1)


def clean_key(name):
    """Normalize a user-entered element name so it always round-trips: no ")"
    (which would split the line) and no newlines, trimmed at the edges."""
    return name.replace(')', '').replace('\n', '').replace('\r', '').strip()


def _is_delimiter(line):
    # Delimiters are never indented; note/content lines always are. This keeps an
    # indented note like "    ### heading" from being mistaken for a delimiter.
    return line[:1] not in (' ', '\t') and line.lstrip().startswith('###')


class Entry:
    def __init__(self, elements=None):
        # elements: ordered list of [key, value]; value may contain newlines (notes).
        self.elements = elements if elements is not None else []

    def get(self, key):
        for k, v in self.elements:
            if k == key:
                return v
        return None

    def set(self, key, value):
        for pair in self.elements:
            if pair[0] == key:
                pair[1] = value
                return
        self.elements.append([key, value])

    @property
    def title(self):
        return self.get('title') or ''

    @property
    def password(self):
        return self.get('password') or ''

    def non_title_elements(self):
        return [e for e in self.elements if e[0] != 'title']

    def element_names(self):
        return [e[0] for e in self.non_title_elements()]

    def copy_sequence(self):
        """Elements clipped by 'm' mode: everything except title and notes,
        in order (password is first)."""
        return [e for e in self.elements if e[0] not in ('title', 'notes')]

    def serialize(self):
        lines = [DELIM]
        for key, value in self.elements:
            if key == 'notes' or '\n' in value:
                lines.append('%s)' % key)
                if value != '':
                    for vline in value.split('\n'):
                        lines.append(NOTE_INDENT + vline)
            elif value == '':
                lines.append('%s)' % key)
            else:
                lines.append('%s) %s' % (key, value))
        lines.append(DELIM)
        return '\n'.join(lines)


class Store:
    def __init__(self, entries=None):
        self.entries = entries if entries is not None else []

    @classmethod
    def parse(cls, text):
        entries = []
        block = []
        for raw in text.splitlines():
            if _is_delimiter(raw):
                if any(l.strip() for l in block):
                    entries.append(cls._parse_block(block))
                block = []
            else:
                block.append(raw)
        if any(l.strip() for l in block):
            entries.append(cls._parse_block(block))
        return cls(entries)

    @staticmethod
    def _parse_block(lines):
        elements = []
        for raw in lines:
            if raw[:1] in (' ', '\t'):
                # Indented continuation -> append to the current element (notes).
                # Strip only one level of indentation (the NOTE_INDENT prefix, or
                # a leading tab as used by hand-written files) so any deeper
                # indentation inside the note survives the round-trip.
                if elements:
                    if raw.startswith(NOTE_INDENT):
                        text = raw[len(NOTE_INDENT):]
                    elif raw[:1] == '\t':
                        text = raw[1:]
                    else:
                        text = raw.lstrip()
                    if elements[-1][1] == '':
                        elements[-1][1] = text
                    else:
                        elements[-1][1] += '\n' + text
                continue
            if raw.strip() == '':
                continue
            m = KEY_RE.match(raw)
            if m:
                elements.append([m.group(1), m.group(2)])
            elif elements:
                # Non-indented, non-key line -> fold into the current value.
                elements[-1][1] += ('\n' if elements[-1][1] else '') + raw
        return Entry(elements)

    def serialize(self):
        if not self.entries:
            return ''
        return '\n\n'.join(e.serialize() for e in self.entries) + '\n'

    def filter(self, query):
        """Entries whose title contains query (case-insensitive). Empty query
        returns everything."""
        q = query.strip().lower()
        if not q:
            return list(self.entries)
        return [e for e in self.entries if q in e.title.lower()]
