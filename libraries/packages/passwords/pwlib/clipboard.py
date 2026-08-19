"""Clipboard access through xclip (X11 clipboard selection)."""

import subprocess


def copy(text):
    """Put text on the clipboard. Returns True on success."""
    try:
        subprocess.run(['xclip', '-selection', 'clipboard'],
                       input=text.encode(), check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False
