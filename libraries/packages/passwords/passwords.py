#!/usr/bin/env python3
"""The `passwords` command.

Unlocks the encrypted store (master password = GPG passphrase), decrypts it to a
session plaintext file under ~/Archive, runs the search/select UI, then on quit
re-encrypts only if something changed and always deletes the session plaintext.

The session plaintext is removed on every exit path: normal quit, exceptions,
KeyboardInterrupt (atexit), and SIGTERM/SIGHUP (signal handlers). Only SIGKILL
and power loss -- uncatchable -- can leave it behind.
"""

import atexit
import getpass
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pwlib import config, crypto, tui
from pwlib.help import HELP
from pwlib.keyboard import keyboard_status_line
from pwlib.model import Store


def _make_cleanup(path):
    state = {'done': False}

    def cleanup(*_):
        if state['done']:
            return
        state['done'] = True
        try:
            os.remove(path)
        except OSError:
            pass

    return cleanup


def main(argv):
    if any(a in ('-h', '-help', '--help') for a in argv):
        print(HELP)
        return 0

    cfg = config.load()
    enc = cfg['encrypted_path']
    plain = cfg['session_path']

    if not os.path.exists(enc):
        here = os.path.dirname(os.path.abspath(__file__))
        print('No encrypted store at: %s' % enc)
        print('Run first:  python3 %s' %
              os.path.join(here, 'encrypt_passwords_text_tile.py'))
        return 1

    # Register cleanup BEFORE the plaintext can exist so any later exit (incl. a
    # KeyboardInterrupt between decrypt and the try block) still removes it.
    cleanup = _make_cleanup(plain)
    atexit.register(cleanup)
    for sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(sig, lambda *_: (cleanup(), os._exit(1)))
        except (ValueError, OSError):
            pass

    pw = None
    for _ in range(3):
        print(keyboard_status_line())
        attempt = getpass.getpass('Master password: ')
        try:
            crypto.decrypt_to_file(enc, plain, attempt)
            pw = attempt
            break
        except crypto.CryptoError:
            print('Wrong master password.')
    if pw is None:
        return 1

    try:
        with open(plain) as f:
            store = Store.parse(f.read())
        dirty = tui.run(store)
        if dirty:
            with open(plain, 'w') as f:
                f.write(store.serialize())
            os.chmod(plain, 0o600)
            crypto.encrypt(plain, enc, pw)
            print('changes saved and re-encrypted -> %s' % enc)
        else:
            print('no changes.')
    finally:
        cleanup()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
