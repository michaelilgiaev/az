"""Weighted, pinned-to-bottom progress bar.

Ported from the bash bar in the old compile.sh but simplified: because the whole
build now runs in ONE python process, we don't need the CR->LF log-tailing reader
subshell the bash version used to scrape pacman/mkarchiso progress out of a shared
PTY. Instead the long steps (package cache, mkarchiso) call ``bar.sub(permille)``
directly from the same process that parses their live output line-by-line
(see steps.py), which is both simpler and race-free.

Layout: ``[####----]  50%  Label`` pinned to the last terminal row via a DECSTBM
scroll region, so build output scrolls in the rows above it. On a non-TTY (piped
to a file / docker logs without -t) it degrades to plain milestone lines, so no
escape codes leak into logs.
"""

from __future__ import annotations

import os
import shutil
import sys

from . import paths


class ProgressBar:
    def __init__(self, weights: list[int], tty: bool | None = None):
        # weights[i] is the weight of step i (1-indexed; index 0 unused).
        self.weights = weights
        self.total_steps = len(weights) - 1
        self.total_weight = sum(weights)
        self.accum = [0] * len(weights)
        acc = 0
        for i in range(1, len(weights)):
            acc += weights[i]
            self.accum[i] = acc
        self.current = 0
        self.label = ""
        self.done_weight = 0
        self.cur_weight = 0
        self.subfrac = 0  # 0..1000 within the current step
        # The bar paints ONLY to the raw terminal (the pristine PTY stdout), never
        # through the stdout tee build.py installs -- so its ANSI escapes and █/░
        # glyphs are seen live by the human but never written into full.log.
        self.term = sys.__stdout__
        if tty is None:
            tty = self.term.isatty()
        self.tty = tty
        # steps.log gets each milestone/phase line in real time (compile.sh already
        # truncated it at launch; append + flush so `tail -f` shows checkpoints live).
        self.steps_log = paths.STEPS_LOG.open("a", encoding="utf-8", errors="replace")
        self._armed = False
        self._armed_rows = None  # terminal height the scroll region was last armed to
        self._base_label = ""    # current step's label, prefixed onto phase() sub-labels

    def _log_step(self, line: str) -> None:
        """Append a milestone/phase line to steps.log in real time."""
        try:
            self.steps_log.write(line + "\n")
            self.steps_log.flush()
        except (ValueError, OSError):
            pass

    def _emit(self, term_line: str, log_line: str, lead: str = "") -> None:
        """Scroll a milestone/phase line: the width-CLIPPED copy to the terminal (so
        a long label does not wrap and break the pinned bar's scroll region) and the
        FULL copy to full.log. sys.stdout is the build's stdout tee, whose write_split
        keeps the two independent -- writing the clipped copy through plain write (an
        earlier bug) truncated these lines in the log too. Fall back to a plain
        clipped write when stdout is not the tee (logging not installed)."""
        writer = getattr(sys.stdout, "write_split", None)
        if writer is not None:
            writer(lead + term_line + "\n", lead + log_line + "\n")
        else:
            sys.stdout.write(lead + term_line + "\n")
            sys.stdout.flush()

    # -- geometry ------------------------------------------------------------
    def _size(self) -> tuple[int, int]:
        try:
            cols, rows = shutil.get_terminal_size((80, 24))
        except Exception:
            cols, rows = 80, 24
        return cols, rows

    def _clip(self, text: str) -> str:
        """Truncate a scrolling line to the terminal width so long labels/output do
        not wrap onto a second row (which desyncs the pinned scroll region and looks
        like text 'escaping' the screen). Non-TTY: no clipping (logs keep full text)."""
        if not self.tty:
            return text
        cols, _ = self._size()
        if cols > 1 and len(text) > cols:
            return text[: cols - 1] + "…"
        return text

    def _layout(self, cols: int) -> str:
        # Left-aligned, hard-clamped to `cols`: [bar] pct% label. Every visible-width
        # term is budgeted from `cols` up front and the label is truncated to whatever
        # room is left, so the printed line NEVER exceeds the terminal width (no
        # centering pad that could push the tail off the right edge). Color codes are
        # added last and are zero-width, so they don't affect the budget.
        cols = max(cols, 1)
        eff = self.done_weight * 1000 + self.cur_weight * min(max(self.subfrac, 0), 1000)
        pct = min(eff // 10 // self.total_weight, 100) if self.total_weight else 0
        pctstr = f" {pct:3d}% "                       # e.g. "  24% " -> 6 visible cols
        # Reserve the pct field; give the bar ~45% of what's left, rest to the label.
        room = max(cols - len(pctstr), 0)
        barw = min(room, max(0, room * 45 // 100))
        barw = min(barw, max(0, cols - len(pctstr)))  # never let bar+pct exceed cols
        filled = (eff * barw // (1000 * self.total_weight)) if self.total_weight else 0
        filled = min(max(filled, 0), barw)
        bar = "█" * filled + "░" * (barw - filled)
        # Remaining columns for the label (after one separating space).
        budget = cols - barw - len(pctstr) - 1
        label = self.label
        if budget <= 0:
            sep, field = "", ""
        else:
            if len(label) > budget:
                label = (label[: budget - 1] + "…") if budget >= 2 else label[:budget]
            sep = " " if label else ""
            # Center the label within its remaining field (bar + % stay put; only the
            # text is pushed toward the middle of the space it has).
            pad = max(budget - len(label), 0)
            left = pad // 2
            field = " " * left + label
        return f"\033[36m{bar}\033[0m\033[1m{pctstr}\033[0m{sep}{field}"

    # -- pinning -------------------------------------------------------------
    def _arm(self) -> None:
        if not self.tty:
            return
        _, rows = self._size()
        # Set the DECSTBM scroll region to rows 1..rows-1, reserving the last row for
        # the pinned bar. Setting the region homes the cursor (a DECSTBM side effect),
        # which would make the next scrolling write land at the TOP; immediately place
        # the cursor at the bottom of the region so build output appends above the bar.
        self.term.write(f"\033[1;{rows - 1}r\033[{rows - 1};1H")
        self.term.flush()
        self._armed = True
        self._armed_rows = rows

    def draw(self) -> None:
        if not self.tty:
            return
        cols, rows = self._size()
        # If the terminal was resized since the region was armed, the old scroll region
        # and bar row are stale -- the bar would paint on the wrong row and unstick. The
        # giant steps drive many draw()s over a long span, so a resize mid-step is likely;
        # re-arm to the new height before painting. (\033[u below restores to a saved
        # position that re-arming would clobber, so re-arm BEFORE saving the cursor.)
        if getattr(self, "_armed_rows", None) != rows:
            self._arm()
        line = self._layout(cols)
        # save cursor, jump to last row, clear, paint, restore cursor
        self.term.write(f"\033[s\033[{rows};1H\033[K{line}\033[u")
        self.term.flush()

    def init(self) -> None:
        if self.tty:
            self._arm()
            self.draw()

    # -- step / sub ----------------------------------------------------------
    def step(self, label: str) -> None:
        self.current += 1
        self.label = label
        self.done_weight = self.accum[self.current - 1]
        self.cur_weight = self.weights[self.current]
        self.subfrac = 0
        self._base_label = label  # phase() prefixes sub-phase labels with this
        self._arm()
        # milestone line: full (unclipped) text to steps.log in real time; a
        # width-clipped copy scrolls on the terminal (and into full.log via the
        # stdout tee) so a long label does not wrap and break the scroll region.
        milestone = f"[ {self.current:2d}/{self.total_steps} ] {label}"
        self._log_step(milestone)
        self._emit(self._clip(milestone), milestone, lead="\n")
        self.draw()

    def sub(self, permille: int) -> None:
        """Set intra-step progress (0..1000) and repaint. Monotonic within a step."""
        permille = min(max(permille, 0), 1000)
        if permille > self.subfrac:
            self.subfrac = permille
            self.draw()

    def phase(self, sublabel: str) -> None:
        """Update the pinned bar's label to a sub-phase of the current step WITHOUT
        advancing the step counter, and drop a scrolling milestone line. Lets the two
        giant steps (package cache, mkarchiso) narrate their internal phases so the
        bar reports fine-grained progress instead of one static label for minutes."""
        text = f"{self._base_label} › {sublabel}" if getattr(self, "_base_label", "") else sublabel
        self.label = text
        line = f"    -> {sublabel}"
        self._log_step(line)   # sub-checkpoint to steps.log, real time
        self._emit(self._clip(line), line)
        self.draw()

    def sub_done(self) -> None:
        """Snap the current step to 100% of its slice."""
        self.subfrac = 1000
        self.draw()

    # -- teardown ------------------------------------------------------------
    def finalize(self) -> None:
        """Print a permanent full bar as a scrolled line (the 'done' state)."""
        self.subfrac = 1000
        if self.tty:
            # The final █/░ bar is bar glyphs -> terminal only (never the log).
            self.term.write("\033[r")  # unpin
            cols, _ = self._size()
            self.term.write("\r\033[K" + self._layout(cols) + "\n")
            self.term.flush()
        else:
            # Non-tty (piped / docker logs): a plain #/. bar, no escapes -> it is
            # fine (and useful) for this completion line to land in full.log via
            # the stdout tee. Matches the pre-change non-tty behaviour.
            eff = self.done_weight * 1000 + self.cur_weight * 1000
            pct = min(eff // 10 // self.total_weight, 100)
            barw = 40
            filled = min(eff * barw // (1000 * self.total_weight), barw)
            bar = "#" * filled + "." * (barw - filled)
            sys.stdout.write(f"[{bar}] {pct:3d}%  {self.label}\n")
            sys.stdout.flush()

    def cleanup(self) -> None:
        """Restore the terminal on any exit (unpin scroll region, clear bar line)."""
        if self.tty:
            try:
                self.term.write("\r\033[K\033[r\033[0m")
                self.term.flush()
            except Exception:
                pass
        try:
            self.steps_log.close()
        except (ValueError, OSError):
            pass
