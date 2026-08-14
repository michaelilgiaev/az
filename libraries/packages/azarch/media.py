#!/usr/bin/env python3
"""azarch guest command line interface -- `azarch volume` / `azarch brightness` (the FN media keys).

The FN keys change two things, and the OpenBox session binds the X "XF86" media keysyms to
these subcommands (see modifications/openbox rc.xml):

    azarch volume up        raise the volume by one step (7.5%)
    azarch volume down       lower the volume by one step (7.5%)
    azarch volume mute       toggle mute
    azarch volume get        print the current volume percent (0-100)

    azarch brightness up     raise screen brightness by one step (7.5%)  [LAPTOP ONLY]
    azarch brightness down   lower screen brightness by one step (7.5%)  [LAPTOP ONLY]
    azarch brightness get    print the current brightness percent (0-100)

STEP + RANGE. Both go 0..100% and every press moves 7.5% (the spec's step), so the scale is
100 -> 92.5 -> 85 -> ... A press is clamped to the range (you cannot go past 100 or below 0).

BRIGHTNESS IS LAPTOP-ONLY. A PC (desktop) has no integrated backlight to control -- its
monitor has its own buttons -- so `azarch brightness up/down` on a PC does NOTHING and says
so (and the FN keys that would dim a laptop's screen are the volume keys on a PC keyboard).
The gate is `machine.is_laptop()` (which honours the hard override), so forcing "Laptop" via
`azarch machine --laptop` turns the brightness controls on even on a desktop, and forcing
"PC" turns them off on a laptop -- exactly what the manual switch is for. `get` still prints a
reading regardless so a caller can query without tripping the gate.

THE ON-SCREEN UI. Each up/down (and mute) pops a small CENTERED on-screen display -- a cyan
bar (the Az'arch logo cyan) filling to the new percent, with a volume or brightness icon --
by launching the OSD indicator (osd_indicator.py, shipped to OSD_INDICATOR_BIN) detached and
feeding it one JSON line describing what to show. The OSD dismisses itself after a moment; a
second press just refreshes the same on-screen bar. This is the speech-to-text indicator's
approach (a real borderless top-most window), reused for the media keys.

BACKENDS (root-free where possible). Volume goes through PipeWire's `wpctl` on the default
audio sink (the ISO ships pipewire + wireplumber), falling back to ALSA `amixer` if wpctl is
absent. Brightness reads/writes the kernel backlight under /sys/class/backlight directly (no
brightnessctl dependency): reading is free, and writing the brightness file needs root, so the
brightness setters run that one write via sudo (the FN keybind runs `azarch brightness ...`,
and the live medium/user has passwordless sudo). All standard library; bundled into the single
/usr/local/bin/azarch script (see common.py).
"""

from __future__ import annotations

# BUNDLE_START

# The single step every FN press moves, as a PERCENT of the 0..100 range. The spec: "each
# decrease and increase should be 7.5%". Kept exact (float) so 100 -> 92.5 -> 85 -> ... .
MEDIA_STEP_PERCENT = 7.5
MEDIA_MIN_PERCENT = 0.0
MEDIA_MAX_PERCENT = 100.0

# The kernel backlight dir (mirrors machine.py). Brightness is read/written under the first
# backlight device found here: <dev>/brightness (current, writable by root) and
# <dev>/max_brightness (the raw ceiling the percent scales against).
_BACKLIGHT_DIR = "/sys/class/backlight"

# The shipped OSD indicator (a standalone tkinter script, osd_indicator.py). Installed next to
# the C terminal user interface binary in the azarch lib dir so the two travel together. Kept in lock-step with
# modifications/openbox (OSD_INDICATOR_SYSTEM_PATH) -- a test pins the two so they cannot drift.
OSD_INDICATOR_BIN = "/usr/local/lib/azarch/azarch-osd"


def _clamp_percent(p: float) -> float:
    """Clamp a percent into [0, 100]."""
    return max(MEDIA_MIN_PERCENT, min(MEDIA_MAX_PERCENT, p))


def _step_percent(current: float, direction: int) -> float:
    """Apply ONE 7.5% step to `current` in `direction` (+1 up, -1 down), clamped to 0..100.
    Pure -- unit-tested so the step/clamp behaviour can't silently drift."""
    return _clamp_percent(current + direction * MEDIA_STEP_PERCENT)


# --- the on-screen display ---------------------------------------------------
def _show_osd(kind: str, percent: float, muted: bool = False) -> None:
    """Pop the centered cyan OSD bar for `kind` ("volume"/"brightness") at `percent`, marking
    it muted when asked. Best-effort and non-blocking: the indicator is launched DETACHED with
    a single JSON line on its stdin, so the FN key returns instantly and a missing indicator (or
    no display) never makes the volume/brightness change itself fail. No DISPLAY => skip it."""
    if not os.environ.get("DISPLAY"):
        return
    if not (os.path.exists(OSD_INDICATOR_BIN) and os.access(OSD_INDICATOR_BIN, os.X_OK)):
        return
    payload = json.dumps({
        "kind": kind,
        "percent": round(_clamp_percent(percent), 1),
        "muted": bool(muted),
    }) + "\n"
    try:
        proc = subprocess.Popen(
            [OSD_INDICATOR_BIN],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        # Hand it the one message, then close stdin so it renders and self-dismisses. We do
        # not wait on it (fire-and-forget): the key press must feel instant.
        if proc.stdin:
            proc.stdin.write(payload.encode())
            proc.stdin.close()
    except OSError:
        pass


# --- volume (PipeWire wpctl, ALSA amixer fallback) --------------------------
_WPCTL_SINK = "@DEFAULT_AUDIO_SINK@"


def _wpctl_get() -> tuple[float, bool] | None:
    """Read (percent, muted) from wpctl for the default sink, or None if wpctl is unavailable
    or unparseable. `wpctl get-volume @DEFAULT_AUDIO_SINK@` prints e.g. "Volume: 0.75" or
    "Volume: 0.75 [MUTED]"; the float is 0.0..1.0 (can exceed 1.0, which we clamp)."""
    if not _have("wpctl"):
        return None
    r = subprocess.run(["wpctl", "get-volume", _WPCTL_SINK],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        return None
    out = r.stdout.decode("utf-8", "replace")
    muted = "MUTED" in out.upper()
    for tok in out.replace(",", ".").split():
        try:
            return _clamp_percent(float(tok) * 100.0), muted
        except ValueError:
            continue
    return None


def _wpctl_set(percent: float) -> bool:
    """Set the default sink to `percent` via wpctl (0..100 -> a 0..1 fraction). Returns True on
    success. `-l 1.0` caps the volume at 100% so a press can never push it into overdrive."""
    if not _have("wpctl"):
        return False
    frac = _clamp_percent(percent) / 100.0
    rc = subprocess.run(["wpctl", "set-volume", "-l", "1.0", _WPCTL_SINK, f"{frac:.4f}"],
                        stderr=subprocess.DEVNULL).returncode
    return rc == 0


def _wpctl_toggle_mute() -> bool:
    if not _have("wpctl"):
        return False
    rc = subprocess.run(["wpctl", "set-mute", _WPCTL_SINK, "toggle"],
                        stderr=subprocess.DEVNULL).returncode
    return rc == 0


def _amixer_get() -> tuple[float, bool] | None:
    """Fallback: read (percent, muted) from ALSA `amixer get Master`. The line carries
    "[42%]" and "[on]"/"[off]". None if amixer is unavailable/unparseable."""
    if not _have("amixer"):
        return None
    r = subprocess.run(["amixer", "get", "Master"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if r.returncode != 0:
        return None
    out = r.stdout.decode("utf-8", "replace")
    pct, muted = None, False
    import re
    m = re.search(r"\[(\d+)%\]", out)
    if m:
        pct = float(m.group(1))
    if "[off]" in out:
        muted = True
    return (pct, muted) if pct is not None else None


def _amixer_set(percent: float) -> bool:
    if not _have("amixer"):
        return False
    rc = subprocess.run(["amixer", "-q", "set", "Master", f"{int(round(_clamp_percent(percent)))}%"],
                        stderr=subprocess.DEVNULL).returncode
    return rc == 0


def _amixer_toggle_mute() -> bool:
    if not _have("amixer"):
        return False
    rc = subprocess.run(["amixer", "-q", "set", "Master", "toggle"],
                        stderr=subprocess.DEVNULL).returncode
    return rc == 0


def _volume_read() -> tuple[float, bool]:
    """Current (percent, muted), preferring wpctl (PipeWire) then amixer (ALSA); (0, False)
    if neither is available so the caller still has a number to step from."""
    return _wpctl_get() or _amixer_get() or (0.0, False)


def _volume_write(percent: float) -> bool:
    """Set the volume via wpctl, else amixer. True on success."""
    return _wpctl_set(percent) or _amixer_set(percent)


def _volume_toggle_mute() -> bool:
    return _wpctl_toggle_mute() or _amixer_toggle_mute()


def cmd_volume(args: list[str]) -> int:
    """Dispatch `azarch volume up|down|mute|get`. up/down step 7.5% and show the OSD; mute
    toggles and shows the OSD; get prints the percent. Unknown verb -> usage + rc 2."""
    verb = args[0] if args else "get"
    if verb in ("up", "down"):
        cur, _muted = _volume_read()
        new = _step_percent(cur, +1 if verb == "up" else -1)
        if not _volume_write(new):
            _err("azarch volume: no audio backend (wpctl/amixer) available")
            return 1
        _show_osd("volume", new, muted=False)
        print(f"Volume: {int(round(new))}%")
        return 0
    if verb in ("mute", "toggle", "togglemute"):
        if not _volume_toggle_mute():
            _err("azarch volume: no audio backend (wpctl/amixer) available")
            return 1
        pct, muted = _volume_read()
        _show_osd("volume", pct, muted=muted)
        print(f"Volume: {'muted' if muted else 'unmuted'} ({int(round(pct))}%)")
        return 0
    if verb == "get":
        pct, muted = _volume_read()
        print(f"{int(round(pct))}{' muted' if muted else ''}")
        return 0
    if verb in ("--help", "-h", "help"):
        _media_usage("volume")
        return 0
    _err(f"azarch volume: unknown option: {verb}")
    _media_usage("volume")
    return 2


# --- brightness (kernel backlight sysfs, laptop-only) -----------------------
def _backlight_device() -> str | None:
    """The first backlight device dir under /sys/class/backlight (e.g. .../intel_backlight),
    or None when there is none (a desktop). Sorted so the choice is stable across calls."""
    try:
        names = sorted(e.name for e in os.scandir(_BACKLIGHT_DIR))
    except OSError:
        return None
    return os.path.join(_BACKLIGHT_DIR, names[0]) if names else None


def _brightness_read() -> float | None:
    """Current brightness as a 0..100 percent from the kernel backlight (brightness /
    max_brightness * 100), or None if there is no backlight or it is unreadable."""
    dev = _backlight_device()
    if not dev:
        return None
    try:
        with open(os.path.join(dev, "brightness"), encoding="utf-8") as fh:
            cur = int(fh.read().strip())
        with open(os.path.join(dev, "max_brightness"), encoding="utf-8") as fh:
            mx = int(fh.read().strip())
    except (OSError, ValueError):
        return None
    if mx <= 0:
        return None
    return _clamp_percent(cur / mx * 100.0)


def _brightness_write(percent: float) -> bool:
    """Set the backlight to `percent` (scaled to the device's raw max). Writing the brightness
    file needs root, so the write goes through `sudo tee` (the FN keybind runs `azarch
    brightness ...`, and the medium/user has passwordless sudo). A raw value of at least 1 is
    kept so a "down" step never blanks the panel to pure black. True on success."""
    dev = _backlight_device()
    if not dev:
        return False
    try:
        with open(os.path.join(dev, "max_brightness"), encoding="utf-8") as fh:
            mx = int(fh.read().strip())
    except (OSError, ValueError):
        return False
    if mx <= 0:
        return False
    raw = int(round(_clamp_percent(percent) / 100.0 * mx))
    raw = max(1, min(mx, raw))
    path = os.path.join(dev, "brightness")
    # Prefer a direct write if we can (already root); else `sudo tee` the one file.
    try:
        if os.access(path, os.W_OK):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(str(raw))
            return True
    except OSError:
        pass
    _sudo_write(path, str(raw))
    # Verify the write took (sudo tee is best-effort/silent), so we only claim success when it did.
    return _brightness_read() is not None


def cmd_brightness(args: list[str]) -> int:
    """Dispatch `azarch brightness up|down|get`. up/down step 7.5% and show the OSD, but ONLY
    on a laptop (a PC has no backlight -- brightness is not an option); get always prints a
    reading. Unknown verb -> usage + rc 2."""
    verb = args[0] if args else "get"
    if verb in ("up", "down"):
        # Brightness is a LAPTOP-ONLY control (honours the machine hard override).
        if not is_laptop():
            _err("azarch brightness: not a laptop -- brightness is a laptop-only control "
                 "(this machine is a PC). Use `azarch machine --laptop` to force it on.")
            return 1
        cur = _brightness_read()
        if cur is None:
            _err("azarch brightness: no backlight found under /sys/class/backlight")
            return 1
        new = _step_percent(cur, +1 if verb == "up" else -1)
        if not _brightness_write(new):
            _err("azarch brightness: could not set the backlight")
            return 1
        _show_osd("brightness", new)
        print(f"Brightness: {int(round(new))}%")
        return 0
    if verb == "get":
        cur = _brightness_read()
        if cur is None:
            print("n/a")     # no backlight (a PC) -- still exit 0 so a query never errors
            return 0
        print(f"{int(round(cur))}")
        return 0
    if verb in ("--help", "-h", "help"):
        _media_usage("brightness")
        return 0
    _err(f"azarch brightness: unknown option: {verb}")
    _media_usage("brightness")
    return 2


def _media_usage(which: str) -> None:
    if which == "volume":
        print(
            "Usage: azarch volume <up|down|mute|get>\n"
            "\n"
            "Change the system volume in 7.5% steps (0-100%), showing a centered cyan\n"
            "on-screen bar. Bound to the FN volume keys by the OpenBox session.\n"
            "\n"
            "  up      Raise the volume 7.5%.\n"
            "  down    Lower the volume 7.5%.\n"
            "  mute    Toggle mute.\n"
            "  get     Print the current volume percent.\n"
        )
    else:
        print(
            "Usage: azarch brightness <up|down|get>\n"
            "\n"
            "Change the screen brightness in 7.5% steps (0-100%), showing a centered cyan\n"
            "on-screen bar. LAPTOP ONLY -- a PC has no backlight to control (use\n"
            "`azarch machine --laptop` to force it on). Bound to the FN brightness keys.\n"
            "\n"
            "  up      Raise brightness 7.5%.\n"
            "  down    Lower brightness 7.5%.\n"
            "  get     Print the current brightness percent (n/a on a PC).\n"
        )
