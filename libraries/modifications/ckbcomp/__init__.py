"""ckbcomp - vendored keyboard-layout compiler (a modification directory module).

`ckbcomp` translates an XKB layout to loadkeys/kbdcontrol format. This is a self-contained
Python 3 port of the upstream (Debian/Manjaro) Perl `ckbcomp`, byte-identical in output, so
no Perl is in the tree. Arch does not package it, yet Calamares' keyboard-preview page shells
out to `ckbcomp` by name, so we vendor it and copy it to /usr/bin/ckbcomp at build time.

The vendored script is the sibling file `ckbcomp.py` (kept under its upstream command name);
it is COPIED VERBATIM to /usr/bin/ckbcomp (no .py suffix there -- it is an executable the
keyboard page runs by name), never imported as a Python module. This __init__.py only marks
the directory as a modification package so the modifications loader discovers it like the
rest; there is nothing to import here.
"""
