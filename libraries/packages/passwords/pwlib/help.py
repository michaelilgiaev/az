"""Shared help text for `passwords -h` and the in-UI 'h' screen."""

HELP = """passwords - encrypted password manager

USAGE
  passwords             unlock and open the search UI
  passwords -h | -help  show this help

UNLOCK
  prompts for the master password set with encrypt_passwords_text_tile.py
  the store is decrypted to a temp plaintext file only for the session

SEARCH MODE  (default; cursor in the search box)
  type           filter entries by title, updates live
  up / down      move into the result list (switches to SELECT mode)
  tab            switch to SELECT mode (works even with no results, e.g. to
                 add the first entry with 'n')
  enter          copy the highlighted entry's password, then close
  esc            quit

SELECT MODE  (cursor on the result list)
  up / down      move the highlight
  enter          copy password, then close
  s              show all elements of the highlighted entry
  e              edit: change / rename / add / remove elements
  d              delete the entry (must type "yes")
  n              new entry (title, password, more elements, notes)
  m              multi-copy: clip each element in turn (notes excluded);
                 press enter for the next one, closes at the end
  o              persistent mode toggle: actions stop closing the UI
  h              this help
  / or esc       back to SEARCH mode
  backspace      back to SEARCH mode and delete the last query character
  q              quit

RESULT LINE
  > title   (N: name1, name2, ...)   N = count of non-title elements

ON QUIT
  no changes -> the temp plaintext is just deleted
  changes    -> re-encrypted to the store, then the temp plaintext is deleted
"""

HELP_LINES = HELP.splitlines()
