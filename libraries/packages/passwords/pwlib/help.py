"""Shared help text for `passwords -h` (the in-UI 'h' help screen was removed --
navigation now mirrors the Az'arch terminal UI: ESC goes back, Q quits)."""

HELP = """passwords - encrypted password manager

USAGE
  passwords             unlock and open the search UI
  passwords -h | -help  show this help

UNLOCK
  first run       prompts you to CREATE a master password, then makes an empty
                  encrypted store at ~/Vault/passwords.txt.gpg
  after that      prompts for that master password to unlock the store
  the store is decrypted to a session plaintext only while the UI is open

NAVIGATION (mirrors the Az'arch terminal UI)
  WASD / HJKL / arrows   move the highlight
  /                      search
  ESC                    jump back to the start of the UI (never quits; spammable)
  q / Q                  quit

SEARCH MODE  (default; cursor in the search box)
  type           filter entries by title, updates live
  arrows         move into the result list (switches to SELECT mode)
  enter          copy the highlighted entry's password, then close
  n              new entry (works even with no results -- add the first entry);
                 only a title is required, and a leading http(s):// / www. is
                 stripped from it. ENTER on an empty title just goes back.
  esc            jump back to the start of the UI
  q              quit

SELECT MODE  (cursor on the result list)
  WASD/HJKL/arrows  move the highlight
  enter             copy password, then close
  v                 show all elements of the highlighted entry
  e                 edit: change / rename / add / remove elements
  x                 delete the entry (must type "yes")
  n                 new entry: enter a title (only requirement), then pick
                    columns from a numbered menu -- Email, Username, Password,
                    Notes, or a custom-named column
  m                 multi-copy: clip each element in turn (notes excluded);
                    press enter for the next one, closes at the end
  /                 drop back to the search box
  esc               jump back to the start of the UI
  backspace         back to the search box and delete the last query character
  q                 quit

RESULT LINE
  > title   (N: name1, name2, ...)   N = count of non-title elements

ON QUIT
  no changes -> the session plaintext is just deleted
  changes    -> saved and re-encrypted into the store, then the session
                plaintext is deleted (you are told the changes were saved)
"""
