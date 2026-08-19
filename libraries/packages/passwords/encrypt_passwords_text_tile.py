#!/usr/bin/env python3
"""Set up the encrypted store.

Asks where the plaintext password file is (default ~/Archive/passwords.txt), what
the encrypted output file should be called, and the master password. Encrypts
with GPG (AES256), VERIFIES the ciphertext decrypts back to the exact source,
saves the paths to the config, and only then offers to delete the original
plaintext. After this, use the `passwords` command.
"""

import getpass
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pwlib import config, crypto
from pwlib.keyboard import keyboard_status_line


def ask(prompt, default):
    val = input('%s (ENTER = %s): ' % (prompt, default)).strip()
    return os.path.expanduser(val or default)


def _verify_roundtrip(enc_path, src_path, passphrase):
    """Decrypt enc_path and byte-compare against src_path. Returns True on match.
    Guarantees the store is recoverable before any plaintext is deleted."""
    fd, tmp = tempfile.mkstemp(prefix='.pwverify-')
    os.close(fd)
    try:
        crypto.decrypt_to_file(enc_path, tmp, passphrase)
        with open(tmp, 'rb') as a, open(src_path, 'rb') as b:
            return a.read() == b.read()
    except crypto.CryptoError:
        return False
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def main():
    print('Encrypt password text file (GPG AES256).')

    src = ask('Unencrypted text file to encrypt', config.DEFAULT_SOURCE)
    if not os.path.exists(src):
        print('Not found: %s' % src)
        return 1

    # The encrypted store is just the source name + ".gpg" (no prompt).
    out = src + '.gpg'

    print(keyboard_status_line())
    pw = getpass.getpass('Master password: ')
    if not pw:
        print('Empty password, aborting.')
        return 1
    print(keyboard_status_line())
    if pw != getpass.getpass('Confirm master password: '):
        print('Passwords do not match.')
        return 1

    try:
        crypto.encrypt(src, out, pw)
    except crypto.CryptoError as e:
        print('Encryption failed: %s' % e)
        return 1

    if not _verify_roundtrip(out, src, pw):
        print('Verification FAILED: the encrypted file did not decrypt back to '
              'the source. Leaving the plaintext in place. (%s removed)' % out)
        try:
            os.remove(out)
        except OSError:
            pass
        return 1

    config.save({'encrypted_path': out, 'session_path': config.DEFAULT_SESSION})
    print('Encrypted and verified -> %s' % out)

    ans = input('Delete the original plaintext "%s"? [Y/n]: ' % src).strip().lower()
    if ans in ('', 'y', 'yes'):
        os.remove(src)
        print('Deleted plaintext.')
    elif os.path.abspath(src) == os.path.abspath(config.DEFAULT_SESSION):
        print('Note: each `passwords` session decrypts to and then deletes "%s", '
              'so this kept copy will be replaced and removed by the next run. '
              'Your data stays safe in the encrypted store.' % src)

    print('Config saved. Open a new shell (or run "source ~/.bashrc"), '
          'then use:  passwords')
    return 0


if __name__ == '__main__':
    sys.exit(main())
