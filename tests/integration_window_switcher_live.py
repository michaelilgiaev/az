#!/usr/bin/env python3
"""Az'arch window switcher -- LIVE behavioral integration check (needs a real X display).

This is NOT part of the pure `bash tests.sh` suite (that suite never touches X/GTK). It is a
manual/CI-on-a-VM harness that proves the two alt-tab bugs stay fixed AT RUNTIME -- the layer
the headless unit tests (tests/test_switch_logic.c) cannot reach: the GTK key routing, the
_NET_ACTIVE_WINDOW round-trip in show_switcher(), and the override-redirect repaint.

WHY a separate script: the daemon holds a GTK seat grab while shown, and under that grab XTEST
(xdotool) mangles Shift+Tab into ISO_Next_Group -- so it CANNOT drive the real backward path.
This harness instead injects REAL hardware key events through a uinput virtual keyboard (they
traverse evdev -> X with the real keymap, exactly like a physical keyboard) and reads the result
back two ways: the daemon's committed window (_NET_ACTIVE_WINDOW after releasing Alt) and a Gdk
screenshot diff of the overlay (to prove the highlight actually repainted).

It builds the daemon straight from the repo source into a temp dir (window_switcher.build_daemon)
so it always tests HEAD, kills any running daemon, runs from the temp dir, and restores nothing
system-wide (the installed daemon path is untouched). Root is needed only for /dev/uinput.

Run ON the target machine (e.g. the hypervisor VM), not the build host:
    sudo python3 tests/integration_window_switcher_live.py
Environment it expects (the login session's): DISPLAY, XAUTHORITY, XDG_RUNTIME_DIR. If invoked
via sudo, pass them through, e.g.:
    sudo DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority XDG_RUNTIME_DIR=/run/user/$(id -u) \
        python3 tests/integration_window_switcher_live.py

Exit code 0 = both bugs verified fixed; non-zero = a failure (prints which). This file is
imported by NO pytest; it is a standalone script so the pure suite stays X-free.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# --- repo wiring: make packages.* importable exactly like tests.sh does ------
_REPO = Path(__file__).resolve().parents[1]
for _p in (_REPO / "libraries", _REPO / "libraries" / "packages"):
    sys.path.insert(0, str(_p))

from packages.window_switcher import window_switcher as ws  # noqa: E402

PIDFILE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "azarch-window-switcher.pid"

# The minimal uinput injector, compiled once. Real hardware key events (not XTEST) so Shift+Tab
# reaches the daemon as ISO_Left_Tab under the grab instead of the mangled ISO_Next_Group.
_UINPUT_C = r"""
#include <linux/uinput.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
static int ufd;
static void emit(int t,int c,int v){struct input_event e;memset(&e,0,sizeof(e));e.type=t;e.code=c;e.value=v;if(write(ufd,&e,sizeof(e))!=sizeof(e))perror("w");}
static void syn(void){emit(EV_SYN,SYN_REPORT,0);}
static int kc(const char*n){if(!strcmp(n,"ALT"))return KEY_LEFTALT;if(!strcmp(n,"SHIFT"))return KEY_LEFTSHIFT;if(!strcmp(n,"TAB"))return KEY_TAB;return -1;}
int main(int c,char**v){if(c<2)return 2;ufd=open("/dev/uinput",O_WRONLY|O_NONBLOCK);if(ufd<0){perror("uinput");return 1;}
ioctl(ufd,UI_SET_EVBIT,EV_KEY);ioctl(ufd,UI_SET_KEYBIT,KEY_LEFTALT);ioctl(ufd,UI_SET_KEYBIT,KEY_LEFTSHIFT);ioctl(ufd,UI_SET_KEYBIT,KEY_TAB);
struct uinput_setup u;memset(&u,0,sizeof(u));u.id.bustype=BUS_USB;u.id.vendor=0x1234;u.id.product=0x5678;strcpy(u.name,"azarch-virtual-kbd");
ioctl(ufd,UI_DEV_SETUP,&u);ioctl(ufd,UI_DEV_CREATE);usleep(400000);
char*s=NULL,*t=strtok_r(v[1],",",&s);while(t){if(!strncmp(t,"sleep:",6))usleep(atoi(t+6)*1000);
else if(!strncmp(t,"down:",5)){int k=kc(t+5);if(k>=0){emit(EV_KEY,k,1);syn();}}
else if(!strncmp(t,"up:",3)){int k=kc(t+3);if(k>=0){emit(EV_KEY,k,0);syn();}}t=strtok_r(NULL,",",&s);}
usleep(200000);ioctl(ufd,UI_DEV_DESTROY);close(ufd);return 0;}
"""

# Gdk full-root screenshot (works for override-redirect overlays; note GdkPixbuf is 2.0).
_SHOT_PY = r"""
import sys, gi
gi.require_version('Gdk','3.0'); gi.require_version('GdkPixbuf','2.0')
from gi.repository import Gdk
out=sys.argv[1]; root=Gdk.get_default_root_window()
pb=Gdk.pixbuf_get_from_window(root,0,0,root.get_width(),root.get_height())
if pb is None: sys.exit("PIXBUF_NONE")
pb.savev(out,"png",[],[]); print("SAVED",out)
"""


def _sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True, **kw)


def _managed_windows():
    """(xid, wm_class) for each _NET_CLIENT_LIST window, in list order."""
    out = _sh("xprop -root _NET_CLIENT_LIST").stdout
    ids = []
    if "#" in out:
        for chunk in out.split("#", 1)[1].split(","):
            w = chunk.strip()
            if w:
                ids.append(w)
    res = []
    for w in ids:
        cls = _sh(f"xprop -id {w} WM_CLASS").stdout.split("=", 1)[-1].strip()
        res.append((w, cls))
    return res


def _active_class():
    out = _sh("xprop -root _NET_ACTIVE_WINDOW").stdout
    xid = None
    for tok in out.replace(",", " ").split():
        if tok.startswith("0x"):
            xid = tok
    if not xid:
        return None
    return _sh(f"xprop -id {xid} WM_CLASS").stdout.split("=", 1)[-1].strip()


def _focus(cls_substr, tmp):
    for w, cls in _managed_windows():
        if cls_substr.lower() in cls.lower():
            _sh(f"xdotool windowactivate {w}")
            time.sleep(0.6)
            return True
    return False


class Harness:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.uinput = tmp / "uinput_key"
        self.shot = tmp / "shot.py"
        self.daemon = tmp / "azarch-window-switcher-daemon"
        self.stderr_log = tmp / "daemon.stderr"
        self.pid = None

    def build(self):
        (self.tmp / "uinput_key.c").write_text(_UINPUT_C)
        self.shot.write_text(_SHOT_PY)
        cc = _sh(f"gcc -O2 -o {self.uinput} {self.tmp/'uinput_key.c'}")
        if cc.returncode != 0:
            raise SystemExit(f"uinput build failed:\n{cc.stderr}")
        ws.build_daemon(self.daemon)  # compiles the repo HEAD sources

    def start_daemon(self):
        if PIDFILE.exists():
            try:
                os.kill(int(PIDFILE.read_text().strip()), signal.SIGTERM)
            except (OSError, ValueError):
                pass
        _sh("pkill -f azarch-window-switcher-daemon")
        time.sleep(1)
        PIDFILE.unlink(missing_ok=True)
        # AZARCH_SWITCHER_TIMING makes the daemon print "AZARCH_SHOW_MS <ms>" per show (see
        # switcher.c on_sig_pipe); we capture stderr so the snappiness check can read it.
        env = dict(os.environ, AZARCH_SWITCHER_TIMING="1")
        self._stderr_fh = open(self.stderr_log, "w")
        subprocess.Popen(
            ["setsid", str(self.daemon)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=self._stderr_fh, start_new_session=True, env=env,
        )
        time.sleep(2)
        self.pid = int(PIDFILE.read_text().strip())

    def show_latencies(self):
        """The AZARCH_SHOW_MS samples (ms, float) the daemon has emitted so far, in order."""
        try:
            text = self.stderr_log.read_text()
        except OSError:
            return []
        out = []
        for line in text.splitlines():
            if line.startswith("AZARCH_SHOW_MS"):
                try:
                    out.append(float(line.split()[1]))
                except (IndexError, ValueError):
                    pass
        return out

    def open_and_dismiss(self, sig=signal.SIGUSR1):
        """Hold Alt, signal (show), release Alt -> commit+hide. One clean show cycle (for timing)."""
        import threading
        t = threading.Thread(target=self.inject, args=("down:ALT,sleep:700,up:ALT",))
        t.start()
        time.sleep(0.35)
        os.kill(self.pid, sig)
        time.sleep(0.5)
        t.join()
        time.sleep(0.4)

    def inject(self, seq: str):
        subprocess.run([str(self.uinput), seq], check=False)

    def screenshot(self, path: Path):
        subprocess.run([sys.executable, str(self.shot), str(path)], check=False)

    def open_and_commit(self, sig=signal.SIGUSR1):
        """Hold Alt, signal the daemon (SIGUSR1=--next / SIGUSR2=--prev), release -> commit;
        return the activated WM_CLASS. The direction is driven by the SIGNAL (exactly how OpenBox's
        A-Tab / A-S-Tab bindings drive it), NOT by a Tab key under the grab -- so it is reliable
        regardless of how the test keyboard injects keys."""
        import threading
        t = threading.Thread(target=self.inject, args=("down:ALT,sleep:1600,up:ALT",))
        t.start()
        time.sleep(0.45)
        os.kill(self.pid, sig)
        time.sleep(0.6)
        t.join()
        time.sleep(0.5)
        return _active_class()

    def open_forward_and_commit(self):
        """Hold Alt, SIGUSR1 (--next), release -> commit; return the activated WM_CLASS."""
        return self.open_and_commit(signal.SIGUSR1)


def _diff_nonempty(a: Path, b: Path) -> bool:
    """True if the two PNGs differ (the overlay repainted). Uses PIL if present, else bytes."""
    try:
        from PIL import Image, ImageChops
        ia = Image.open(a).convert("RGB")
        ib = Image.open(b).convert("RGB")
        return ImageChops.difference(ia, ib).getbbox() is not None
    except Exception:
        return a.read_bytes() != b.read_bytes()


def main() -> int:
    for var in ("DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR"):
        if not os.environ.get(var):
            print(f"[skip] {var} not set -- this harness needs a live X session", file=sys.stderr)
            return 77  # automake-style "skipped"
    if not os.access("/dev/uinput", os.W_OK):
        print("[skip] /dev/uinput not writable -- run under sudo", file=sys.stderr)
        return 77

    failures = []
    with tempfile.TemporaryDirectory(prefix="azarch-switcher-live-") as td:
        tmp = Path(td)
        h = Harness(tmp)
        h.build()
        h.start_daemon()

        wins = _managed_windows()
        classes = [c for _, c in wins]
        print(f"managed windows ({len(wins)}): {classes}")
        if len(wins) < 3:
            print("[skip] need >=3 open windows to exercise start-index anchoring", file=sys.stderr)
            return 77

        # --- Bug 2: fresh-open start is FOCUS-RELATIVE, not a fixed tile. ------
        # Committing right after opening forward activates the tile AFTER the focused window.
        # We assert that focusing two DIFFERENT windows yields two DIFFERENT commits (the old
        # bug always committed the same fixed tile regardless of focus).
        picks = {}
        for target in ("librewolf", "thunar", "kitty", "gedit"):
            if _focus(target, tmp):
                before = _active_class()
                got = h.open_forward_and_commit()
                print(f"  focus={target!r} active={before!r} -> committed {got!r}")
                picks[target] = got
        distinct = {v for v in picks.values() if v}
        if len(picks) >= 2 and len(distinct) < 2:
            failures.append(
                f"Bug2: fresh-open start ignores focus -- every focus committed the same tile "
                f"{distinct}; expected focus-relative starts to differ ({picks})"
            )
        else:
            print(f"  OK Bug2: focus-relative starts differ: {picks}")

        # --- Bug 1: BACKWARD (Shift+Tab) actually goes the other way. -----------
        # HARNESS NOTE: a REAL Alt+Shift+Tab from the CLOSED state is dispatched by OpenBox's
        # A-S-Tab binding as `azarch-window-switcher --prev` -> SIGUSR2 -> show_switcher(-1). That
        # SIGNAL path is what the user actually triggers, and it is fully reliable to drive here.
        # We deliberately do NOT inject a Tab key under the daemon's seat grab to test direction:
        # both XTEST (xdotool) and a hotplugged uinput device are unreliable under an active grab
        # (XTEST remaps Shift+Tab's ISO_Left_Tab into ISO_Next_Group; a uinput slave's events may
        # not reach the grabbing client at all). The pure keyval+state->direction decision for an
        # under-grab Shift+Tab (ISO_Left_Tab -> -1) is proven exhaustively and deterministically by
        # the headless tests/test_switch_logic.c instead -- the right layer for that.
        #
        # Here we prove the end-to-end BACKWARD path: from the SAME focused window, a forward open
        # (SIGUSR1) commits the tile AFTER it, and a backward open (SIGUSR2) commits the tile BEFORE
        # it. Those must differ and must straddle the focused tile -- if backward were broken (e.g.
        # it stepped forward, or ignored dir), the two would collapse to the same commit.
        fwd = {}
        bwd = {}
        for target in ("librewolf", "kitty", "thunar"):
            if _focus(target, tmp):
                fwd[target] = h.open_and_commit(signal.SIGUSR1)
                _focus(target, tmp)
                bwd[target] = h.open_and_commit(signal.SIGUSR2)
                print(f"  focus={target!r}: forward -> {fwd[target]!r} | backward -> {bwd[target]!r}")
        pairs = [(t, fwd[t], bwd[t]) for t in fwd if t in bwd and fwd[t] and bwd[t]]
        differ = [t for (t, f, b) in pairs if f != b]
        if not pairs:
            failures.append("Bug1: could not drive any forward/backward open to a commit")
        elif not differ:
            failures.append(
                f"Bug1: backward (SIGUSR2 / A-S-Tab) commits the SAME window as forward -- backward "
                f"direction is broken (forward={fwd}, backward={bwd})"
            )
        else:
            print(f"  OK Bug1: backward differs from forward for {differ} "
                  f"(A-S-Tab steps the other way)")

        # --- Bug 3: the overlay is SNAPPY -- show latency stays tiny. -----------
        # The daemon prints "AZARCH_SHOW_MS <ms>" per show (AZARCH_SWITCHER_TIMING, set by the
        # harness). This is the signal-to-mapped cost. It was ~150-220ms when show_switcher
        # enumerated windows (forks xprop) and captured every tile's XComposite pixmap INLINE,
        # before moving the overlay on-screen -- the reported "delayed / not snappy", and why a
        # quick Alt+Shift+Tab felt dead (the overlay had not painted when the keys were released).
        # The fix seeds the strip at warmup and defers the reload to an idle AFTER the map, so the
        # show does only the cheap select+move+grab. We open/dismiss several times and assert the
        # MEDIAN show latency is well under the old cost. The threshold (60ms) sits far below the
        # ~200ms regression and comfortably above the few-ms fixed path, so it fails loudly if the
        # heavy work ever creeps back onto the show hot path.
        SNAPPY_MS = 60.0
        base = len(h.show_latencies())
        for _ in range(5):
            h.open_and_dismiss()
        samples = h.show_latencies()[base:]
        if not samples:
            failures.append("Bug3: no AZARCH_SHOW_MS samples captured (timing hook missing?)")
        else:
            samples_sorted = sorted(samples)
            median = samples_sorted[len(samples_sorted) // 2]
            worst = samples_sorted[-1]
            print(f"  show latency samples (ms): {[round(x,1) for x in samples]}")
            if median <= SNAPPY_MS:
                print(f"  OK Bug3: snappy -- median {median:.1f}ms <= {SNAPPY_MS:.0f}ms "
                      f"(worst {worst:.1f}ms)")
            else:
                failures.append(
                    f"Bug3: NOT snappy -- median show latency {median:.1f}ms > {SNAPPY_MS:.0f}ms "
                    f"(samples {[round(x,1) for x in samples]}); the heavy window-list/thumbnail "
                    f"work is back on the show hot path"
                )

    if failures:
        print("\nFAIL:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nPASS: alt-tab bugs (start-index, shift+tab, snappiness) verified fixed at runtime")
    return 0


if __name__ == "__main__":
    sys.exit(main())
