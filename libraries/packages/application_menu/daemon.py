#!/usr/bin/env python3
"""Az'arch application menu -- resident daemon for INSTANT open.

Spawning a fresh Python+Tk process on every click costs ~120-280ms (interpreter
start, tkinter import, X connection, building the window + loading an icon per
app). That is the delay the user sees. This module removes it entirely: ONE
long-lived process builds the whole window ONCE at login, then WARMS IT UP -- maps
it a single time OFF-SCREEN and forces a full render, paying the one expensive first
map (~600ms, re-exposing the whole widget tree) invisibly at login. It thereafter
keeps the window MAPPED but parked off-screen; showing it just MOVES it on-screen and
hiding it moves it back off (never a re-map, ~10-40ms), so it appears the instant the
Super key is pressed. (Under X the map/unmap -- withdraw()/deiconify() -- is the slow
part, not the content; keeping the window mapped is what makes the open instant. See
menu.warmup_menu / hide_menu / show_menu.)

Control is by Unix signal from the tiny launcher (/usr/local/bin/azarch-
application-menu):

    SIGUSR1 -> toggle (show if hidden, hide if shown)   <- the panel icon
    SIGUSR2 -> show   (force-show; used right after the daemon is auto-started)
    SIGTERM/SIGINT -> quit cleanly

Signals cannot safely touch Tk from the handler (they fire between bytecodes
while Tk blocks in C), so we use the self-pipe trick: the handler writes one byte
to a pipe and Tk's file handler (or a tiny poll fallback) dispatches the real
show/hide/quit on the main loop.

State is a single pidfile under XDG_RUNTIME_DIR so the launcher can find us and
so a second daemon never starts. Kept dependency-free (standard library only).
"""

from __future__ import annotations

import os
import signal
import sys
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import menu as M  # noqa: E402
from apps import scan_applications  # noqa: E402
from winwatch import DesktopIndex, WindowWatcher  # noqa: E402


RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
PID_FILE = os.path.join(RUNTIME_DIR, "azarch-application-menu.pid")

# Debounce window (seconds) for the toggle after a hide. Closing the menu with a Super
# TAP makes xcape inject a Menu keysym that arrives here as a toggle a moment later; a
# toggle landing within this window of a hide is treated as that echo and swallowed so
# the close is not immediately undone.
#
# CRITICAL sizing invariant: the debounce clock starts when the menu is hidden, which
# happens on the Super_L *press* (the grab delivers the physical KeyPress to the window;
# hide_menu stamps az_last_hidden there). xcape only injects the Menu echo on the *release*,
# and its -t timeout (see openbox.py, currently 500ms) lets a solo Super be held up to that
# long and STILL emit the tap. So the echo can arrive as late as (xcape -t) + a little
# signal-dispatch latency after the stamp. This window MUST therefore exceed the xcape
# timeout, or a slow (~0.4-0.5s) close-tap re-opens the menu -- the exact "buggy close" this
# guards. Keep TOGGLE_DEBOUNCE_S > the xcape -t (0.5s) with margin; do not lower it below
# the xcape timeout when tuning either value.
TOGGLE_DEBOUNCE_S = 0.6


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # signal 0 = existence check
        return True
    except OSError:
        return False


def _claim_pidfile() -> bool:
    """Atomically claim the single-instance pidfile. Returns True if WE now own
    it (safe to run), False if another LIVE daemon already holds it (we should
    bow out).

    Uses O_CREAT|O_EXCL so that when two daemons start at once (autostart racing
    the launcher's first click, say), exactly ONE wins the create -- closing the
    check-then-write race where both could pass an existence check during the
    ~200ms window before either wrote the file. A stale pidfile (owner dead) is
    removed and the claim retried once."""
    for _ in range(3):
        try:
            fd = os.open(PID_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            # Someone holds it. Read the owner PID -- but the winner may have
            # created the file microseconds ago and not yet WRITTEN its pid, so
            # an empty/unparseable read means "another daemon is starting", NOT
            # "stale". Re-read a few times before concluding it is dead; only an
            # unlink-on-genuinely-stale is safe (unlinking a just-created-empty
            # file would let BOTH racers think they won).
            other = -1
            for _try in range(20):  # ~200ms max
                try:
                    with open(PID_FILE, encoding="utf-8") as fh:
                        txt = fh.read().strip()
                except OSError:
                    txt = ""
                if txt:
                    try:
                        other = int(txt)
                    except ValueError:
                        other = -1
                    break
                time.sleep(0.01)
            if other == os.getpid():
                return True
            if other > 0 and _pid_alive(other):
                return False  # a live daemon owns it -> bow out
            if other <= 0:
                # Still empty after waiting -> the "winner" never wrote a pid
                # (it likely died); treat as stale.
                pass
            # Stale -> remove and retry the atomic create.
            try:
                os.unlink(PID_FILE)
            except OSError:
                pass
            continue
        except OSError:
            return True  # can't lock (e.g. no runtime dir) -> run anyway
        else:
            # We won the create. Write our pid IMMEDIATELY (before any slow work)
            # so a racing loser reads it and bows out.
            try:
                os.write(fd, str(os.getpid()).encode("ascii"))
            finally:
                os.close(fd)
            return True
    return True


def _remove_pidfile() -> None:
    try:
        # Only remove if it still points at us (avoid clobbering a newer daemon).
        with open(PID_FILE, encoding="utf-8") as fh:
            if fh.read().strip() == str(os.getpid()):
                os.unlink(PID_FILE)
    except OSError:
        pass


# Commands received by the EARLY signal handlers (installed before the window is
# built). Because _claim_pidfile() publishes our PID before the ~200ms build,
# the launcher may fire SIGUSR2 while we are still building. SIGUSR1/2's default
# action is to TERMINATE the process -- so we must install handlers before the
# build to (a) not die, and (b) remember the request. The Daemon replays these
# once it is ready.
_early_pending: list[str] = []


def _early_handler(signum, _frame) -> None:
    if signum == signal.SIGUSR1:
        _early_pending.append("1")
    elif signum == signal.SIGUSR2:
        _early_pending.append("2")
    # SIGTERM/SIGINT during startup: exit promptly (nothing to clean but the
    # pidfile, released by main()'s except).
    elif signum in (signal.SIGTERM, signal.SIGINT):
        raise SystemExit(0)


def _install_early_handlers() -> None:
    for sig in (signal.SIGUSR1, signal.SIGUSR2, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _early_handler)


class Daemon:
    """Owns the persistent window and the signal-driven show/hide/quit loop."""

    def __init__(self) -> None:
        # Build the full window (chrome + all rows) up front, then warm it up so the
        # first real open is instant. Withdraw FIRST -- before any update -- so the
        # window never flashes on screen during daemon startup.
        self.root = M.build_window(persistent=True)
        try:
            self.root.withdraw()
        except tk.TclError:
            pass
        # Warm-up: map the window ONCE, OFF-SCREEN, and force a full render. This pays the
        # expensive first map (~600ms -- re-exposing the whole widget tree, worst of all
        # opens) HERE, at login, while the window is invisible. After this the window
        # stays mapped off-screen; every user open just MOVES it on-screen (~10-40ms, no
        # re-map/re-expose), which is what makes the menu open instantly and snappily
        # instead of stalling on the first Super press. (az_warmup populates the rows,
        # so the separate az_populate call is no longer needed.)
        try:
            self.root.az_warmup()
        except tk.TclError:
            pass

        # --- system-wide "app opened" counting ----------------------------
        # The menu is ordered most-USED first, and the spec is literal: an open
        # is counted however the user launched the app, not only via our menu.
        # This watcher polls the X11 window list and records one launch each
        # time a new application WINDOW appears, into the SAME usage store the
        # menu sorts by (root.az_menu.usage). It shares the menu's visible-app
        # set so it never counts an app the menu hides. Best-effort: if it can't
        # start (no xprop / odd WM), the menu still works, just without
        # auto-counting.
        self._watcher: WindowWatcher | None = None
        try:
            usage = self.root.az_menu.usage
            self._watcher = WindowWatcher(
                self.root,
                usage,
                index_provider=lambda: DesktopIndex(scan_applications()),
                own_pid=os.getpid(),
            )
            self._watcher.start()
        except Exception:
            self._watcher = None

        # Self-pipe wakeup. CRITICAL: Tk blocks inside its C event loop, and a
        # pure-Python signal handler only runs when the interpreter regains
        # control -- which never happens while blocked, so a handler that wrote
        # the pipe itself would deadlock (Tcl won't wake because nothing wrote;
        # nothing wrote because Python can't run). signal.set_wakeup_fd() solves
        # this: the C-level signal trampoline writes the signal NUMBER to the
        # pipe the instant the signal lands, which wakes Tcl's notifier and
        # dispatches _drain on the main loop. The Python handlers below just
        # enqueue the intended action; _drain (woken by the fd) executes it.
        self._rd, self._wr = os.pipe()
        os.set_blocking(self._rd, False)
        os.set_blocking(self._wr, False)
        # Inherit anything the early handlers captured during the build (e.g. the
        # launcher's SIGUSR2 "show" fired before we were ready).
        self._pending: list[str] = list(_early_pending)
        _early_pending.clear()

        for sig in (signal.SIGUSR1, signal.SIGUSR2):
            signal.signal(sig, self._on_signal)
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._on_quit_signal)
        # Route the wakeup byte to our pipe (C writes the signum here).
        self._old_wakeup = signal.set_wakeup_fd(self._wr)
        # If an early signal already asked us to show, honour it as soon as the
        # loop starts.
        if self._pending:
            try:
                self.root.after_idle(self._drain)
            except tk.TclError:
                pass

        # Prefer Tk's file handler (zero-latency, no polling). Fall back to a
        # short poll if this Tk build lacks createfilehandler.
        self._use_filehandler = False
        try:
            self.root.tk.createfilehandler(
                self._rd, tk.READABLE, self._drain
            )
            self._use_filehandler = True
        except (tk.TclError, AttributeError, TypeError):
            self._poll()

    # -- signal side (async-signal-safe: only append + the C wakeup fires) --
    def _on_signal(self, signum, _frame) -> None:
        self._pending.append("1" if signum == signal.SIGUSR1 else "2")

    def _on_quit_signal(self, _signum, _frame) -> None:
        self._pending.append("q")

    # -- main-loop side (safe to touch Tk) ---------------------------------
    def _drain(self, *_a) -> None:
        # Consume the wakeup bytes (their values -- signal numbers -- don't
        # matter; the intent is in self._pending, set by the Python handlers).
        try:
            os.read(self._rd, 4096)
        except OSError:
            pass
        if not self._pending:
            return
        cmds, self._pending = self._pending, []
        if "q" in cmds:
            self.quit()
            return
        # Collapse rapid repeats to the LAST command so a burst of toggles
        # doesn't flip-flop; a trailing show wins.
        last = cmds[-1]
        if last == "1":
            self.toggle()
        elif last == "2":
            self.show()

    def _poll(self) -> None:
        # Fallback path when createfilehandler is unavailable: check the pipe
        # every 15ms (imperceptible) on the Tk loop.
        self._drain()
        try:
            self.root.after(15, self._poll)
        except tk.TclError:
            pass

    # -- actions -----------------------------------------------------------
    def show(self) -> None:
        try:
            self.root.az_show()
        except tk.TclError:
            pass
        # az_show() re-scanned the .desktop files (menu.reset_view -> refresh_apps),
        # so a package installed since login now appears in the LIST. The
        # WindowWatcher keeps its OWN cached desktop index (to map a new window back
        # to a .desktop for launch counting); drop it so it rebuilds from the fresh
        # scan and can count launches of the newly-installed app too. Best-effort.
        if self._watcher is not None:
            try:
                self._watcher.refresh_index()
            except Exception:
                pass

    def hide(self) -> None:
        try:
            self.root.az_hide()
        except tk.TclError:
            pass

    def toggle(self) -> None:
        # Track true SHOWN state. The window stays MAPPED even when hidden (daemon mode
        # parks it off-screen instead of withdrawing it -- see menu.hide_menu -- so the
        # first show can be instant), which means winfo_viewable() is always True and can
        # no longer tell shown from hidden. az_shown is the source of truth; it is set
        # False by every close path (outside click / Escape / the Super binding all go
        # through hide_menu, which clears it) so a self-close is reflected here too.
        try:
            shown = bool(getattr(self.root, "az_shown", False))
        except tk.TclError:
            shown = False
        if shown:
            self.hide()
            return
        # Hidden -> normally show. BUT guard against the xcape echo of a Super
        # close-tap: closing with a Super TAP delivers Super_L to the (grabbed) window,
        # which moves it off-screen and releases the grab; xcape ALSO injects the Menu
        # keysym on that same tap's release, and once the grab is gone that Menu reaches
        # OpenBox -> the launcher -> here as a toggle, a few ms after the hide. Without this
        # guard
        # that echo would re-open the window the instant the user closed it (the "close is
        # buggy" symptom). If we were hidden within the debounce window, treat this toggle
        # as that echo and swallow it so the close sticks. A deliberate re-open a moment
        # later (well past the window) still works.
        try:
            since_hidden = time.monotonic() - float(
                getattr(self.root, "az_last_hidden", 0.0)
            )
        except (tk.TclError, TypeError, ValueError):
            since_hidden = TOGGLE_DEBOUNCE_S + 1.0
        if 0.0 <= since_hidden < TOGGLE_DEBOUNCE_S:
            return
        self.show()

    def quit(self) -> None:
        if self._watcher is not None:
            try:
                self._watcher.stop()
            except Exception:
                pass
        try:
            signal.set_wakeup_fd(self._old_wakeup)
        except (ValueError, OSError):
            pass
        try:
            if self._use_filehandler:
                self.root.tk.deletefilehandler(self._rd)
        except (tk.TclError, AttributeError):
            pass
        _remove_pidfile()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        # The pidfile was already claimed (atomically) in main() before we built
        # the window, so the launcher can find us. Just run, then release it.
        try:
            self.root.mainloop()
        finally:
            _remove_pidfile()


def main() -> None:
    # Order matters (spec Gotcha 4): install the early signal handlers BEFORE
    # claiming the pidfile. _claim_pidfile() publishes our PID (what the launcher
    # polls for) and the launcher fires SIGUSR2 the instant it sees the file --
    # possibly before the ~200ms window build finishes. SIGUSR1/2's default
    # disposition is TERMINATE, so if the pidfile were published before the
    # handlers existed a signal landing in that gap would kill the daemon. Arming
    # the handlers first closes the gap by construction: any early signal is
    # recorded into _early_pending and replayed once the window + Tk wiring are
    # ready.
    _install_early_handlers()
    # Single instance, race-free: atomically claim the pidfile BEFORE building
    # the window. If another live daemon already owns it (autostart racing the
    # launcher's first click), bow out without wasting a build.
    if not _claim_pidfile():
        return
    try:
        Daemon().run()
    except BaseException:
        # If building/running blew up after we claimed the pidfile, release it so
        # the next launch can start cleanly rather than seeing a stale lock.
        _remove_pidfile()
        raise


if __name__ == "__main__":
    main()
