"""pwlib - the working parts of the encrypted password manager.

Modules:
    config     - persisted store paths (no secrets)
    crypto     - GPG symmetric (AES256) encrypt/decrypt
    model      - Entry/Store data model + text (de)serialization
    clipboard  - xclip wrapper
    forms      - curses sub-screens (detail, edit, new, prompts, m-copy)
    tui        - the main search/select curses UI
    help       - shared help text
"""
