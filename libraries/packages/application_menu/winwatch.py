#!/usr/bin/env python3
"""Az'arch application menu -- system-wide "app opened" detection.

The menu orders apps by how often each is *opened* (most-used first). The
spec is literal: "as each software is opened, it counts that" -- so an open
must be counted no matter HOW the user launched it (our menu, the taskbar, a
desktop icon, a terminal, a file association, autostart). Counting only the
clicks that go through our own menu (the old behaviour) misses the vast
majority of real launches, which is why the order looked frozen/random.

This module watches the X11 window list and records one launch each time a new
top-level *application* window appears, mapping that window back to the
``.desktop`` id it came from. It talks to the running WM through EWMH
properties (``_NET_CLIENT_LIST``, ``_NET_WM_PID``, ``WM_CLASS``,
``_NET_WM_WINDOW_TYPE``) via the ``xprop`` tool -- no extra Python deps, no
python-xlib. KWin on this system advertises full EWMH support.

Design / safety:
  * Pure polling on the Tk main loop (``after``); cheap -- one ``xprop`` to
    read the client list, then one per *newly appeared* window only (steady
    state: zero spawns). No threads (Tk is not thread-safe).
  * Best-effort and crash-proof: any xprop/parse/OS error is swallowed. A
    watcher that cannot read a window simply does not count it; it must never
    take the daemon down or block the menu.
  * De-duplication on TWO axes so one launch counts exactly once:
      - by window id: a window already seen is never re-counted, so raising /
        refocusing an existing window does nothing.
      - by pid burst: an app that opens several windows at once (splash +
        main, or a multi-window app) is collapsed to a single count within a
        short window, keyed on the owning process pid.
  * Only real application windows count: ``_NET_WM_WINDOW_TYPE`` of DESKTOP /
    DOCK / TOOLBAR / MENU / UTILITY / SPLASH / NOTIFICATION / etc. is skipped,
    so plasmashell's panel and the desktop itself never register. Our own menu
    is override-redirect (unmanaged) so it never appears in the client list at
    all, but we also skip our own pid defensively.

Mapping a window -> desktop id (first match wins):
  1. ``StartupWMClass``  -- when the .desktop declares it, it is authoritative.
  2. ``WM_CLASS``        -- either of the two strings, matched case-folded to a
                            desktop's StartupWMClass, exec-binary basename, or
                            desktop-id stem.
  3. ``_NET_WM_PID``     -- resolve /proc/<pid>/exe + cmdline and match the
                            binary basename to a desktop's exec basename. This
                            is what catches the ~98% of apps that declare no
                            StartupWMClass (kitty, vlc, systemsettings, ...).
"""

from __future__ import annotations

import os
import shlex
import subprocess


# Window types that are NOT "an application the user opened". Anything whose
# _NET_WM_WINDOW_TYPE is (only) one of these is ignored. NORMAL, DIALOG, or an
# absent type all count as a real window.
_SKIP_WINDOW_TYPES: frozenset[str] = frozenset(
    {
        "_NET_WM_WINDOW_TYPE_DESKTOP",
        "_NET_WM_WINDOW_TYPE_DOCK",
        "_NET_WM_WINDOW_TYPE_TOOLBAR",
        "_NET_WM_WINDOW_TYPE_MENU",
        "_NET_WM_WINDOW_TYPE_UTILITY",
        "_NET_WM_WINDOW_TYPE_SPLASH",
        "_NET_WM_WINDOW_TYPE_DROPDOWN_MENU",
        "_NET_WM_WINDOW_TYPE_POPUP_MENU",
        "_NET_WM_WINDOW_TYPE_TOOLTIP",
        "_NET_WM_WINDOW_TYPE_NOTIFICATION",
        "_NET_WM_WINDOW_TYPE_COMBO",
        "_NET_WM_WINDOW_TYPE_DND",
    }
)

# Collapse a burst of windows from the same process opening at once into one
# launch (splash + main window, or an app that maps several top-levels). Two
# windows from the same pid within this many poll ticks count once.
_PID_BURST_TICKS = 8  # at ~400ms/poll ≈ 3.2s


def _run_xprop(args: list[str]) -> str:
    """Run ``xprop`` and return stdout ('' on any failure). Short timeout so a
    hung X call can never wedge the poll."""
    try:
        proc = subprocess.run(
            ["xprop"] + args,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return proc.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _client_list() -> list[str]:
    """Current top-level managed window ids (hex strings), or [] on failure."""
    out = _run_xprop(["-root", "_NET_CLIENT_LIST"])
    _, sep, rest = out.partition("#")
    if not sep:
        return []
    return [w.strip() for w in rest.split(",") if w.strip()]


def _win_props(win: str) -> dict[str, str]:
    """Read the handful of properties we need for one window in a single xprop
    call. Returns a dict with any of: wm_class, wm_pid, wm_types, wm_command."""
    out = _run_xprop(
        [
            "-id",
            win,
            "WM_CLASS",
            "_NET_WM_PID",
            "_NET_WM_WINDOW_TYPE",
            "WM_COMMAND",
        ]
    )
    props: dict[str, str] = {}
    for line in out.splitlines():
        if line.startswith("WM_CLASS"):
            props["wm_class"] = line
        elif line.startswith("_NET_WM_PID"):
            props["wm_pid"] = line
        elif line.startswith("_NET_WM_WINDOW_TYPE"):
            props["wm_types"] = line
        elif line.startswith("WM_COMMAND"):
            props["wm_command"] = line
    return props


def _parse_wm_class(line: str) -> list[str]:
    """Extract the (instance, class) strings from an xprop WM_CLASS line.

    ``WM_CLASS(STRING) = "dolphin", "dolphin"`` -> ['dolphin', 'dolphin'].
    """
    _, _, rhs = line.partition("=")
    out: list[str] = []
    for chunk in rhs.split(","):
        chunk = chunk.strip().strip('"').strip()
        if chunk:
            out.append(chunk)
    return out


def _parse_pid(line: str) -> int | None:
    """Extract the integer pid from an xprop _NET_WM_PID line."""
    _, _, rhs = line.partition("=")
    rhs = rhs.strip()
    try:
        return int(rhs)
    except ValueError:
        return None


def _parse_window_types(line: str) -> list[str]:
    """Extract the atom names from an xprop _NET_WM_WINDOW_TYPE line."""
    _, _, rhs = line.partition("=")
    return [t.strip() for t in rhs.split(",") if t.strip()]


def _proc_exe_basename(pid: int) -> str | None:
    """Basename of /proc/<pid>/exe (the real executable), or None."""
    try:
        target = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None
    base = os.path.basename(target)
    # Strip a trailing " (deleted)" the kernel appends for updated binaries.
    if base.endswith(" (deleted)"):
        base = base[: -len(" (deleted)")]
    return base or None


def _proc_cmdline_bins(pid: int) -> list[str]:
    """Candidate binary basenames from /proc/<pid>/cmdline: the argv[0]
    basename, plus (for wrappers/interpreters) the basename of the first later
    arg that looks like a path. Best-effort, [] on failure."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            raw = fh.read()
    except OSError:
        return []
    parts = [p.decode(errors="replace") for p in raw.split(b"\x00") if p]
    bins: list[str] = []
    for i, p in enumerate(parts[:4]):
        b = os.path.basename(p)
        if b and (i == 0 or "/" in p):
            bins.append(b)
    return bins


def _exec_binary(exec_str: str) -> str | None:
    """The launched binary's basename from a .desktop Exec= line (field codes
    already irrelevant -- we only look at argv[0])."""
    try:
        parts = shlex.split(exec_str)
    except ValueError:
        parts = exec_str.split()
    # Skip a leading env/wrapper so the *real* program is matched
    # (e.g. `env FOO=1 kitty`, `/usr/bin/env kitty`).
    idx = 0
    while idx < len(parts):
        tok = parts[idx]
        base = os.path.basename(tok)
        if base == "env" or "=" in tok:
            idx += 1
            continue
        break
    if idx >= len(parts):
        return None
    return os.path.basename(parts[idx]) or None


class DesktopIndex:
    """Lookup tables mapping a window's identity to a ``.desktop`` id.

    Built once from the same visible-app set the menu shows (so it never
    records an app the menu deliberately hides), and refreshable cheaply.
    """

    def __init__(self, entries) -> None:
        # entry.desktop_id -> entry, plus the reverse indices we match on.
        self.by_startup_wmclass: dict[str, str] = {}
        self.by_exec_bin: dict[str, str] = {}
        self.by_id_stem: dict[str, str] = {}
        self._build(entries)

    def _build(self, entries) -> None:
        for e in entries:
            did = e.desktop_id
            swc = getattr(e, "startup_wmclass", "") or ""
            if swc:
                self.by_startup_wmclass.setdefault(swc.casefold(), did)
            exec_bin = _exec_binary(" ".join(e.exec_argv)) if e.exec_argv else None
            if exec_bin:
                self.by_exec_bin.setdefault(exec_bin.casefold(), did)
            stem = did[:-8] if did.endswith(".desktop") else did
            # Reverse-DNS ids (org.kde.dolphin) -> last dotted component too.
            self.by_id_stem.setdefault(stem.casefold(), did)
            if "." in stem:
                self.by_id_stem.setdefault(stem.rsplit(".", 1)[-1].casefold(), did)

    def resolve(self, wm_classes: list[str], pid: int | None) -> str | None:
        """Return the best desktop id for a window, or None if unmatched."""
        # 1) StartupWMClass -- authoritative when the window's class matches one.
        for cls in wm_classes:
            hit = self.by_startup_wmclass.get(cls.casefold())
            if hit:
                return hit
        # 2) WM_CLASS matched to an exec basename or desktop-id stem.
        for cls in wm_classes:
            cf = cls.casefold()
            hit = self.by_exec_bin.get(cf) or self.by_id_stem.get(cf)
            if hit:
                return hit
        # 3) PID -> executable basename / cmdline, matched to an exec basename.
        if pid is not None:
            base = _proc_exe_basename(pid)
            if base:
                hit = self.by_exec_bin.get(base.casefold()) or self.by_id_stem.get(
                    base.casefold()
                )
                if hit:
                    return hit
            for b in _proc_cmdline_bins(pid):
                hit = self.by_exec_bin.get(b.casefold()) or self.by_id_stem.get(
                    b.casefold()
                )
                if hit:
                    return hit
        return None


class WindowWatcher:
    """Polls the X11 client list and records a launch per newly-opened app
    window. Wire it to the Tk root and the shared UsageStore.

    Usage::

        w = WindowWatcher(root, usage_store, index_provider)
        w.start()   # begins polling on the Tk loop
    """

    def __init__(
        self,
        root,
        usage,
        index_provider,
        interval_ms: int = 400,
        own_pid: int | None = None,
    ) -> None:
        self.root = root
        self.usage = usage
        # A zero-arg callable returning a fresh DesktopIndex, so newly-installed
        # apps become matchable without restarting the daemon (rebuilt lazily,
        # not every poll).
        self._index_provider = index_provider
        self.interval_ms = interval_ms
        self.own_pid = own_pid if own_pid is not None else os.getpid()

        self._index: DesktopIndex | None = None
        # Windows we've already accounted for (by id), so an existing window
        # being raised/refocused is never re-counted.
        self._seen: set[str] = set()
        # pid -> tick when we last counted it, to collapse multi-window bursts.
        self._pid_last_tick: dict[int, int] = {}
        self._tick = 0
        self._after_id = None
        self._primed = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Prime the seen-set with windows already open (so pre-existing windows
        are NOT counted as fresh opens), then begin polling."""
        try:
            self._seen = set(_client_list())
        except Exception:
            self._seen = set()
        self._primed = True
        self._schedule()

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _schedule(self) -> None:
        try:
            self._after_id = self.root.after(self.interval_ms, self._poll)
        except Exception:
            self._after_id = None

    # -- the poll ----------------------------------------------------------
    def _poll(self) -> None:
        try:
            self._tick += 1
            self._scan_once()
        except Exception:
            # Never let a poll error kill the daemon; just try again next tick.
            pass
        finally:
            self._schedule()

    def _index_now(self) -> DesktopIndex:
        if self._index is None:
            self._index = self._index_provider()
        return self._index

    def refresh_index(self) -> None:
        """Drop the cached desktop index so the next resolve rebuilds it (call
        after apps may have been installed/removed)."""
        self._index = None

    def _scan_once(self) -> None:
        current = _client_list()
        if not current:
            return
        current_set = set(current)
        # Forget windows that have closed, so a window id reused later still
        # counts as a fresh open.
        self._seen &= current_set

        new_ids = [w for w in current if w not in self._seen]
        if not new_ids:
            return

        idx = self._index_now()
        for win in new_ids:
            self._seen.add(win)
            self._consider(win, idx)

    def _consider(self, win: str, idx: DesktopIndex) -> None:
        props = _win_props(win)

        # Filter out non-application windows (panels, the desktop, menus, ...).
        types = _parse_window_types(props.get("wm_types", ""))
        if types and all(t in _SKIP_WINDOW_TYPES for t in types):
            return

        pid = _parse_pid(props.get("wm_pid", ""))
        # Never count our own menu/daemon window (defensive: it's unmanaged and
        # shouldn't be in the list, but be safe).
        if pid is not None and pid == self.own_pid:
            return

        wm_classes = _parse_wm_class(props.get("wm_class", ""))
        desktop_id = idx.resolve(wm_classes, pid)
        if not desktop_id:
            return

        # Collapse a burst of windows from the same process into one launch.
        if pid is not None:
            last = self._pid_last_tick.get(pid)
            if last is not None and (self._tick - last) <= _PID_BURST_TICKS:
                self._pid_last_tick[pid] = self._tick
                return
            self._pid_last_tick[pid] = self._tick

        self.usage.record(desktop_id)
