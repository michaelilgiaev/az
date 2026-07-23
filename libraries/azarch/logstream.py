"""Own the build logs from Python instead of letting util-linux `script` do it.

Why this exists: compile.sh re-execs on a PTY so pacman/mkarchiso keep their live
progress redraws and so the process is a real terminal (the progress bar only
paints to a tty). Previously `script` also MIRRORED that whole PTY into
logs/full.log -- which meant the pinned progress bar's ANSI escapes and █/░
glyphs were copied straight into the log, where they do not belong (the bar is
for the human watching the terminal, not the log).

The fix: `script` now writes its capture to /dev/null (it is kept ONLY for the
PTY), and Python owns full.log itself. Every `print()` / `sys.stderr.write` in
the build funnels through the _Tee installed here, which writes to BOTH the real
terminal AND full.log, flushing each write (real-time, tail-able). The progress
bar deliberately bypasses this tee -- it writes to the raw terminal
(`sys.__stdout__`) only, so its escape codes never reach the log. See
progress.ProgressBar (self.term) and steps._drive_mkarchiso_progress.
"""

from __future__ import annotations

import sys
from typing import TextIO

from . import paths


class _Tee:
    """A minimal text stream that duplicates every write to a terminal stream and
    a log file, flushing both each time so the log stays real-time (tail -f works)
    and nothing is lost on a hard Ctrl-C exit."""

    def __init__(self, term: TextIO, logfile: TextIO) -> None:
        self._term = term
        self._log = logfile

    def write(self, text: str) -> int:
        n = self._term.write(text)
        self._term.flush()
        try:
            self._log.write(text)
            self._log.flush()
        except (ValueError, OSError):
            pass  # log closed/unwritable -> keep the terminal alive regardless
        return n

    def write_split(self, term_text: str, log_text: str) -> int:
        """Write DIFFERENT bytes to the terminal and the log in one call.

        Used by the mkarchiso driver: the terminal copy is width-clipped so a long
        pacstrap line does not wrap and desync the pinned progress bar's scroll
        region, but the log must keep the FULL untruncated line. Writing the clipped
        copy through plain write() (as a prior change did) silently cut the tail off
        every wide mkarchiso line in full.log. This keeps them independent."""
        n = self._term.write(term_text)
        self._term.flush()
        try:
            self._log.write(log_text)
            self._log.flush()
        except (ValueError, OSError):
            pass
        return n

    def flush(self) -> None:
        self._term.flush()
        try:
            self._log.flush()
        except (ValueError, OSError):
            pass

    # A few programs/libs probe these; delegate to the terminal stream.
    def isatty(self) -> bool:
        return self._term.isatty()

    def fileno(self) -> int:
        return self._term.fileno()


def install() -> TextIO:
    """Open full.log (append; compile.sh already truncated it at launch) and route
    sys.stdout + sys.stderr through a _Tee so all build output is mirrored into the
    log in real time. Returns the open log file handle so the caller can keep a
    reference (closed implicitly at process exit; every write is already flushed).

    The progress bar captures sys.__stdout__ BEFORE this swap is even relevant --
    it always uses the pristine terminal stream -- so bar escapes never enter the
    tee and never reach the log."""
    logfile = paths.FULL_LOG.open("a", encoding="utf-8", errors="replace")
    sys.stdout = _Tee(sys.__stdout__, logfile)
    sys.stderr = _Tee(sys.__stderr__, logfile)
    return logfile
