"""pwlib - the working parts of the encrypted password manager.

Modules:
    config          - persisted store paths (no secrets)
    crypto          - GPG symmetric (AES256) encrypt/decrypt
    model           - Entry/Store data model + text (de)serialization
    clipboard       - launches the paste-once clipboard owner (xclip fallback)
    clipboard_owner - the detached X CLIPBOARD owner (paste once, then clear)
    forms           - curses primitives + the entry view (columns/copy/edit)
    newentry        - the new-entry wizard and the column-reorder screen
    tui             - the main search/select curses UI
    help            - shared help text
"""
