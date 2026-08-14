#!/usr/bin/env python3
"""Az'arch media OSD -- the centered on-screen bar shown when the FN keys change the volume
or the screen brightness.

This is a standalone, borderless, always-on-top desktop window (tkinter) that draws a single
CYAN bar (the Az'arch logo cyan #06B8FD) filling to a 0-100% level, next to a simple
volume-or-brightness ICON, and a percent readout. It is the media-key counterpart of the
speech-to-text REC indicator (~/.config/nvim/lua/local_plugins/speech-to-text.nvim's
indicator.py) -- same idea (a real top-most override-redirect window, never focus-stealing),
reused for the media keys and placed in the MIDDLE of the primary monitor instead of the
corner.

INVOCATION. `azarch volume/brightness` (media.py) launches this DETACHED and writes ONE JSON
line to its stdin, then closes the pipe:

    {"kind":"volume","percent":72.5,"muted":false}
    {"kind":"brightness","percent":50.0}

The window renders that state, holds briefly, fades out, and exits -- so a keypress flashes the
bar and it disappears on its own. If a second press launches a second copy while the first is
still up, that is fine (each is a short-lived flash); the newest sits on top. Extra lines on
stdin (a caller could stream several) refresh the SAME window instead of spawning more.

ICONS ARE DRAWN, NOT LOADED. The two icons the spec asks for ("simple icons please") are drawn
directly on the canvas with tkinter primitives in the logo cyan: a speaker (a filled trapezoid
cone) with sound waves for volume -- or an "off" cross when muted -- and a sun (a filled disc
with rays) for brightness. Drawing them means no image files to ship, no scaling, and they
stay crisp at any DPI. Kept deliberately minimal per the spec.

Design constraints (inherited from the speech-to-text indicator):
  - NEVER steal focus: override-redirect + no focus_set/force, no key bindings.
  - Always on top: -topmost, re-asserted on a tick.
  - CENTERED on the PRIMARY monitor (parsed from `xrandr --listmonitors`, since
    winfo_screenwidth returns the COMBINED width on a multi-head X11 setup).
  - No faster-whisper/CUDA/any heavy import: it must start from the SYSTEM python (which has
    tkinter) even where nothing else is installed.
"""
import json
import os
import subprocess
import sys
import threading
import time

try:
    import tkinter as tk
except Exception as e:  # pragma: no cover - the launcher points at a tk-capable python
    sys.stderr.write("azarch osd: tkinter unavailable: %s\n" % e)
    sys.exit(2)


# ── Look & feel ──────────────────────────────────────────────────────────────
ACCENT = "#06B8FD"        # the Az'arch logo cyan -- the bar fill + the icon
BAR_EMPTY = "#20303a"     # dim, unfilled bar track
BG_COLOR = "#0a0f14"      # near-black window background (a solid dark chip)
TEXT_COLOR = "#dee4ea"    # the percent readout
MUTED_COLOR = "#78828c"   # a muted grey for the "muted" state

# Window geometry -- a compact centered chip: an icon box on the left, a long bar, a percent.
WIN_W = 360
WIN_H = 84
ICON_BOX = 56             # the left square the icon is drawn in
PAD = 18                  # inner padding
BAR_H = 16                # the level bar thickness


def primary_geometry(root):
    """Return (x, y, w, h) of the PRIMARY monitor in root coords, parsed from
    `xrandr --listmonitors` (its primary line carries a '*'). Falls back to the whole screen
    (single-head safe) when xrandr is unavailable/unparseable. Mirrors the speech-to-text
    indicator's resolver so the OSD centers on the same monitor."""
    try:
        out = subprocess.run(
            ["xrandr", "--listmonitors"],
            capture_output=True, text=True, timeout=2,
        ).stdout
        for line in out.splitlines():
            line = line.strip()
            if "*" not in line:
                continue
            geom = line.split()[2]                       # "1920/527x1080/296+0+0"
            wpart, rest = geom.split("x", 1)
            w = int(wpart.split("/", 1)[0])
            hpart, offs = rest.split("+", 1)
            h = int(hpart.split("/", 1)[0])
            ox, oy = offs.split("+", 1)
            return int(ox), int(oy), w, h
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


class Osd:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        self.root.configure(bg=BG_COLOR)

        ox, oy, mw, mh = primary_geometry(self.root)
        # CENTER on the primary monitor (the spec: "put it in the middle").
        x = ox + (mw - WIN_W) // 2
        y = oy + (mh - WIN_H) // 2
        self.root.geometry("%dx%d+%d+%d" % (WIN_W, WIN_H, x, y))

        self.canvas = tk.Canvas(
            self.root, width=WIN_W, height=WIN_H,
            bg=BG_COLOR, highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.kind = "volume"       # "volume" | "brightness"
        self.percent = 0.0         # 0..100
        self.muted = False
        self._fade_after = None    # pending fade step id
        self._close_after = None   # pending close id
        self._shown = False        # has a real message rendered yet? (drives the EOF close)

        # Stay WITHDRAWN until the first message renders (show() deiconifies). An empty-stdin
        # invocation (the launcher died before writing, or wrote nothing) therefore never even
        # maps a window -- it just closes on EOF. This is the fix for a stuck, invisible/empty
        # centered chip lingering when no level ever arrives.
        self._tick_topmost()
        # HARD backstop, OWNED BY A WATCHDOG THREAD -- NOT a Tk `after` timer. A Tk timer for the
        # ceiling is not safe: it fires from the SAME event loop it is meant to rescue, so under
        # heavy X/CPU contention (many OSDs spawned by rapid FN presses -- the documented use
        # case) the loop starves and the timer never runs, and the process lingers. A plain
        # daemon thread that sleeps and then force-exits the whole process is immune to any
        # Tk-loop starvation: after MAX_LIFETIME_S the OSD is GONE, unconditionally. os._exit is
        # used deliberately (not sys.exit) so it cannot be swallowed by Tk's C mainloop; this is
        # a short-lived flash with nothing to flush, so a hard exit is correct and safe.
        self._start_watchdog()

    # The absolute maximum the OSD may stay alive, as a backstop against any lingering path.
    MAX_LIFETIME_S = 4.0

    def _start_watchdog(self):
        """Spawn the hard-lifetime watchdog: a daemon thread that force-exits the process after
        MAX_LIFETIME_S no matter what the Tk event loop is (or is not) doing. This is the
        ultimate guarantee the OSD can never linger -- independent of the fade timers, the EOF
        close, and any event-loop starvation."""
        def watchdog():
            time.sleep(self.MAX_LIFETIME_S)
            os._exit(0)
        threading.Thread(target=watchdog, daemon=True).start()

    # ── periodic topmost re-assert (some WMs drop it) ──────────────────────────
    def _tick_topmost(self):
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        self.root.after(500, self._tick_topmost)

    # ── icon drawing (simple, cyan, canvas primitives) ─────────────────────────
    def _draw_speaker(self, cx, cy):
        """A simple speaker: a small square body + a triangular cone, then two sound-wave
        arcs to its right -- or a red-grey 'x' over it when muted. Cyan, minimal."""
        c = self.canvas
        col = MUTED_COLOR if self.muted else ACCENT
        # body + cone (a filled polygon: box on the left, cone opening to the right)
        bx = cx - 16
        c.create_rectangle(bx, cy - 6, bx + 8, cy + 6, fill=col, outline="")
        c.create_polygon(bx + 8, cy - 6, bx + 8, cy + 6, bx + 20, cy + 14, bx + 20, cy - 14,
                         fill=col, outline="")
        if self.muted:
            # An 'x' to the right instead of sound waves.
            mx = cx + 8
            c.create_line(mx, cy - 8, mx + 14, cy + 8, fill=col, width=3)
            c.create_line(mx, cy + 8, mx + 14, cy - 8, fill=col, width=3)
        else:
            # Two concentric sound-wave arcs.
            c.create_arc(cx + 2, cy - 12, cx + 18, cy + 12, start=-60, extent=120,
                        style="arc", outline=col, width=2)
            c.create_arc(cx + 8, cy - 18, cx + 28, cy + 18, start=-60, extent=120,
                        style="arc", outline=col, width=2)

    def _draw_sun(self, cx, cy):
        """A simple sun: a filled disc with eight short rays radiating out. Cyan, minimal."""
        import math
        c = self.canvas
        r = 8
        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ACCENT, outline="")
        for k in range(8):
            a = math.pi * k / 4.0
            x0 = cx + math.cos(a) * (r + 3)
            y0 = cy + math.sin(a) * (r + 3)
            x1 = cx + math.cos(a) * (r + 9)
            y1 = cy + math.sin(a) * (r + 9)
            c.create_line(x0, y0, x1, y1, fill=ACCENT, width=2)

    # ── rendering ──────────────────────────────────────────────────────────────
    def render(self):
        c = self.canvas
        c.delete("all")
        icon_cx = PAD + ICON_BOX // 2
        icon_cy = WIN_H // 2
        if self.kind == "brightness":
            self._draw_sun(icon_cx, icon_cy)
        else:
            self._draw_speaker(icon_cx, icon_cy)

        # The bar: a dim track with a cyan fill to `percent`. Spans from just right of the
        # icon box to the right padding; the percent reads at the far right, above the bar.
        bx0 = PAD + ICON_BOX + PAD
        bx1 = WIN_W - PAD
        by0 = WIN_H // 2 - BAR_H // 2
        by1 = WIN_H // 2 + BAR_H // 2
        c.create_rectangle(bx0, by0, bx1, by1, fill=BAR_EMPTY, outline="")
        frac = max(0.0, min(1.0, self.percent / 100.0))
        fill_w = int(round((bx1 - bx0) * frac))
        if fill_w > 0:
            fill_col = MUTED_COLOR if self.muted else ACCENT
            c.create_rectangle(bx0, by0, bx0 + fill_w, by1, fill=fill_col, outline="")

        label = "muted" if self.muted else ("%d%%" % int(round(self.percent)))
        c.create_text(bx1, by0 - 6, text=label, anchor="se",
                     fill=(MUTED_COLOR if self.muted else TEXT_COLOR),
                     font=("TkDefaultFont", 11, "bold"))

    # ── show + auto-dismiss ────────────────────────────────────────────────────
    def show(self, kind, percent, muted):
        """Render a fresh state and (re)arm the hold-then-fade dismissal. A second message
        cancels the pending fade and restarts the timer, so rapid presses keep one bar up."""
        self.kind = kind if kind in ("volume", "brightness") else "volume"
        try:
            self.percent = max(0.0, min(100.0, float(percent)))
        except (TypeError, ValueError):
            self.percent = 0.0
        self.muted = bool(muted)
        # Reset opacity + cancel any in-flight fade/close so the bar is fully visible again.
        for attr in ("_fade_after", "_close_after"):
            aid = getattr(self, attr)
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)
        try:
            self.root.attributes("-alpha", 1.0)
        except Exception:
            pass
        # First real message: reveal the window (it starts withdrawn) and mark that something
        # has now been shown, so an EOF no longer means "close immediately".
        if not self._shown:
            self._shown = True
            try:
                self.root.deiconify()
            except Exception:
                pass
        self.render()
        # Hold fully visible ~900ms, then fade out over ~450ms, then close.
        self._close_after = self.root.after(900, self._start_fade)

    def _start_fade(self):
        STEPS = 15
        step_ms = 30

        def step(i):
            if i > STEPS:
                self.close()
                return
            alpha = max(0.0, 1.0 - i / STEPS)
            try:
                self.root.attributes("-alpha", alpha)
            except Exception:
                self.close()
                return
            self._fade_after = self.root.after(step_ms, lambda: step(i + 1))

        step(0)

    def close(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    # ── stdin pump ──────────────────────────────────────────────────────────────
    def apply(self, msg):
        if not isinstance(msg, dict):
            return
        if msg.get("cmd") == "close":
            self.close()
            return
        self.show(msg.get("kind", "volume"), msg.get("percent", 0), msg.get("muted", False))

    def run(self):
        def pump():
            dispatched = False   # did we hand at least one decoded message to the Tk thread?
            for raw in sys.stdin:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                # A message that decodes to a NON-dict (null / list / number / string) is not a
                # real payload -- apply() ignores it -- so it does NOT count as "dispatched".
                # This is exactly the earlier hang case: without this guard a `null` line looked
                # like input but never revealed a window, so the EOF check below would wrongly
                # wait on a Tk timer. We decide it HERE, synchronously, so EOF teardown is exact.
                if not isinstance(msg, dict):
                    continue
                dispatched = True
                try:
                    self.root.after(0, lambda m=msg: self.apply(m))
                except Exception:
                    return
            # stdin closed. Decide teardown on `dispatched` -- set SYNCHRONOUSLY in this thread
            # the instant a usable dict message was handed off -- NOT on self._shown, which the
            # MAIN thread sets later (so at EOF it may still be False for a message that has only
            # just been queued; keying off it would wrongly kill the normal one-line flash before
            # apply() runs). Normal path: dispatched is True, the fade timer set by show() owns
            # teardown -- do NOT force a close (the bar must still be seen; the launcher closes
            # stdin right after its single line). No usable message at all -- empty, blanks,
            # garbage, or a non-dict payload -- there is no window to tear down gracefully, so
            # exit the PROCESS immediately and DETERMINISTICALLY. os._exit from this pump thread
            # does not depend on the Tk event loop (which can be starved under many concurrent
            # OSDs), so this can never hang: the earlier bug where a `null`/list payload left the
            # process alive until killed is closed here, not left to a racing Tk timer.
            if not dispatched:
                os._exit(0)

        t = threading.Thread(target=pump, daemon=True)
        t.start()
        try:
            self.root.mainloop()
        except Exception:
            pass


def main():
    Osd().run()


if __name__ == "__main__":
    main()
