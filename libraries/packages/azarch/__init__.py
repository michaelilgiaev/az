"""The `azarch` guest command line interface, as a Python package.

Formerly a single module (libraries/packages/azarch.py). Split into small modules
(common, country_table, resolver, theme, sshd, command_line_interface) as the command line interface grows -- the `theme`
subcommand is the first of several planned. The single /usr/local/bin/azarch script that
ships to the guest is reassembled from these modules by bundle.bundle_source() (see
bundle.py); modifications.openbox.azarch_command_line_interface() calls it and re-injects the canonical country
table between the AZARCH_CC markers.

Importing this package for tests/dev exposes main() (from command_line_interface) so the command line interface can be driven
in-process; the shipped artifact is always the bundle, not this package.
"""

from __future__ import annotations
