"""The FN media controls -- `azarch volume` / `azarch brightness` / `azarch machine`, the
centered cyan OSD bar, and the OpenBox FN keybinds that drive them.

The PROMPT: add volume + brightness FN controls to the `azarch` command line interface. Resolve the machine's FN
mapping (a PC's FN+F2/F3 are volume; a laptop's are brightness), make BRIGHTNESS a laptop-only
option (a PC has no backlight), add a "Machine Type" surface that displays PC/Laptop and lets
the user HARD-SWITCH it, and show a centered cyan (the Az'arch logo cyan) on-screen bar at 100%
with 7.5% steps when volume/brightness change -- reusing the speech-to-text indicator's UI.

These tests pin, against the BUNDLED command line interface (the /usr/local/bin/azarch artifact) + the standalone
OSD script + the OpenBox wiring:

  * machine-type detection (backlight, then DMI chassis) and the persistent hard override;
  * the 7.5% step + 0..100 clamp for volume and brightness;
  * brightness is gated to laptops (honouring the override), volume is not;
  * the OSD is centered, draws a cyan bar + a volume/brightness icon, self-dismisses;
  * the OpenBox rc.xml binds the XF86 audio/brightness keysyms to the subcommands, and the OSD
    script ships (executable, pinned) next to the terminal user interface binary.

The command line interface is exercised via its bundle (packages.azarch.bundle.bundle_source) executed in one
namespace -- exactly the artifact the compiler ships -- so the tests drive the real functions.
"""

from __future__ import annotations

import json
import subprocess
import types

import pytest

from packages.azarch.bundle import bundle_source, MODULE_ORDER
from modifications import openbox as desktop
import paths
import profile as profiledef


def _command_line_interface():
    """Exec the bundled azarch command line interface in a fresh module namespace (as shipped)."""
    mod = types.ModuleType("azarch_cli_media_test")
    exec(compile(bundle_source(), "azarch_command_line_interface", "exec"), mod.__dict__)
    return mod


# --- the modules are bundled in a working order -----------------------------

def test_machine_and_media_are_bundled_before_the_cli():
    """machine.py + media.py must be in the bundle, and BEFORE command_line_interface.py (whose main()
    dispatches to them). machine.py must precede media.py (media's brightness gate calls
    machine.is_laptop() by bare name)."""
    for mod in ("machine.py", "media.py"):
        assert mod in MODULE_ORDER, f"{mod} not bundled"
        assert MODULE_ORDER.index(mod) < MODULE_ORDER.index("command_line_interface.py")
    assert MODULE_ORDER.index("machine.py") < MODULE_ORDER.index("media.py")


def test_dispatch_branches_exist_in_main():
    """`azarch volume|brightness|machine ...` must be real top-level dispatch branches, and the
    top-level usage must advertise them."""
    src = desktop.azarch_command_line_interface()
    assert 'cmd == "volume"' in src and "return cmd_volume(argv[1:])" in src
    assert 'cmd == "brightness"' in src and "return cmd_brightness(argv[1:])" in src
    assert 'cmd == "machine"' in src and "return cmd_machine(argv[1:])" in src
    # advertised in usage()
    assert "volume <up|down|mute|get>" in src
    assert "brightness <up|down|get>" in src
    assert "machine [--pc|--laptop|--auto]" in src


# --- machine-type detection + the hard switch -------------------------------

def test_machine_default_is_pc_with_no_signals(monkeypatch):
    """With no backlight and no DMI chassis, autodetection falls back to PC (a machine with no
    backlight has no brightness to control)."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_has_backlight", lambda: False)
    monkeypatch.setattr(cli, "_chassis_is_laptop", lambda: None)
    monkeypatch.setattr(cli, "_read_override", lambda: None)
    assert cli._detect_machine_type() == "PC"
    assert cli.machine_type() == "PC"
    assert cli.is_laptop() is False


def test_machine_backlight_means_laptop(monkeypatch):
    """A real backlight under /sys/class/backlight => Laptop (it can control its own screen),
    and it wins over a (contradicting) desktop chassis code."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_has_backlight", lambda: True)
    monkeypatch.setattr(cli, "_chassis_is_laptop", lambda: False)   # DMI says desktop...
    monkeypatch.setattr(cli, "_read_override", lambda: None)
    assert cli._detect_machine_type() == "Laptop"                  # ...backlight still wins
    assert cli.is_laptop() is True


def test_machine_chassis_laptop_codes(monkeypatch):
    """When there is no backlight, the DMI chassis code decides: 9/10 (laptop/notebook) =>
    Laptop, 3 (desktop) => PC."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_has_backlight", lambda: False)
    monkeypatch.setattr(cli, "_read_override", lambda: None)
    for code in ("8", "9", "10", "11", "14", "30", "31", "32"):
        assert code in cli._LAPTOP_CHASSIS_CODES
    # a laptop code -> Laptop
    monkeypatch.setattr(cli, "_chassis_is_laptop", lambda: True)
    assert cli._detect_machine_type() == "Laptop"
    # a desktop code -> PC
    monkeypatch.setattr(cli, "_chassis_is_laptop", lambda: False)
    assert cli._detect_machine_type() == "PC"


def test_machine_hard_override_persists_and_wins(tmp_path, monkeypatch):
    """`azarch machine --pc/--laptop` writes ~/.config/azarch/machine-type and that override
    WINS over autodetection; `--auto` clears it. Point the pointer file at a temp home."""
    cli = _command_line_interface()
    state = tmp_path / ".config" / "azarch" / "machine-type"
    monkeypatch.setattr(cli, "_machine_state_file", lambda: str(state))
    # autodetect would say PC (no backlight, no/という chassis) -- stub it so the test is host-free
    monkeypatch.setattr(cli, "_detect_machine_type", lambda: "PC")

    # force Laptop -> file written, effective type flips, brightness gate opens
    assert cli.cmd_machine(["--laptop"]) == 0
    assert state.read_text().strip() == "Laptop"
    assert cli.machine_type() == "Laptop"
    assert cli.is_laptop() is True

    # force PC
    assert cli.cmd_machine(["--pc"]) == 0
    assert state.read_text().strip() == "PC"
    assert cli.machine_type() == "PC"

    # --auto clears the override -> back to autodetection (PC)
    assert cli.cmd_machine(["--auto"]) == 0
    assert not state.exists()
    assert cli.machine_type() == "PC"


def test_machine_status_and_unknown_option(tmp_path, monkeypatch, capsys):
    """Bare `azarch machine` prints the recognised type; an unknown option is rc 2."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_machine_state_file", lambda: str(tmp_path / "mt"))
    monkeypatch.setattr(cli, "_detect_machine_type", lambda: "Laptop")
    assert cli.cmd_machine([]) == 0
    out = capsys.readouterr().out
    assert "Machine type: Laptop" in out
    assert "autodetected" in out
    assert cli.cmd_machine(["--bogus"]) == 2
    assert "unknown option" in capsys.readouterr().err


# --- the 7.5% step + 0..100 clamp -------------------------------------------

def test_step_is_seven_and_a_half_percent():
    """The spec: each increase/decrease is 7.5%, over a 0..100 range."""
    cli = _command_line_interface()
    assert cli.MEDIA_STEP_PERCENT == 7.5
    assert cli.MEDIA_MIN_PERCENT == 0.0
    assert cli.MEDIA_MAX_PERCENT == 100.0
    # 100 -> 92.5 -> 85 stepping down; and back up
    assert cli._step_percent(100.0, -1) == 92.5
    assert cli._step_percent(92.5, -1) == 85.0
    assert cli._step_percent(85.0, +1) == 92.5


def test_step_clamps_at_the_edges():
    """A press can never push past 100 or below 0."""
    cli = _command_line_interface()
    assert cli._step_percent(97.0, +1) == 100.0     # 97 + 7.5 clamps to 100
    assert cli._step_percent(100.0, +1) == 100.0
    assert cli._step_percent(3.0, -1) == 0.0        # 3 - 7.5 clamps to 0
    assert cli._step_percent(0.0, -1) == 0.0


# --- volume: steps, mutes, shows the OSD ------------------------------------

def test_volume_up_steps_and_shows_osd(monkeypatch, capsys):
    """`azarch volume up` reads the current level, writes current+7.5 (clamped), and pops the
    OSD. Backends + OSD are stubbed so the test is host-free."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_volume_read", lambda: (50.0, False))
    written = {}
    monkeypatch.setattr(cli, "_volume_write", lambda p: (written.__setitem__("p", p), True)[1])
    osd = {}
    monkeypatch.setattr(cli, "_show_osd", lambda kind, pct, muted=False: osd.update(kind=kind, pct=pct))
    assert cli.cmd_volume(["up"]) == 0
    assert written["p"] == 57.5
    assert osd == {"kind": "volume", "pct": 57.5}
    assert "Volume: 58%" in capsys.readouterr().out   # rounded for display


def test_volume_down_and_mute(monkeypatch):
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_volume_read", lambda: (30.0, False))
    seen = {}
    monkeypatch.setattr(cli, "_volume_write", lambda p: (seen.__setitem__("p", p), True)[1])
    monkeypatch.setattr(cli, "_show_osd", lambda *a, **k: None)
    assert cli.cmd_volume(["down"]) == 0
    assert seen["p"] == 22.5
    # mute toggles via the backend and shows the OSD with the muted flag
    toggled = {}
    monkeypatch.setattr(cli, "_volume_toggle_mute", lambda: (toggled.__setitem__("t", True), True)[1])
    monkeypatch.setattr(cli, "_volume_read", lambda: (22.5, True))
    shown = {}
    monkeypatch.setattr(cli, "_show_osd", lambda kind, pct, muted=False: shown.update(muted=muted))
    assert cli.cmd_volume(["mute"]) == 0
    assert toggled.get("t") is True
    assert shown.get("muted") is True


def test_volume_no_backend_is_error(monkeypatch, capsys):
    """With neither wpctl nor amixer, a volume change reports an error (rc 1), not a crash."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_volume_read", lambda: (0.0, False))
    monkeypatch.setattr(cli, "_volume_write", lambda p: False)
    monkeypatch.setattr(cli, "_show_osd", lambda *a, **k: None)
    assert cli.cmd_volume(["up"]) == 1
    assert "no audio backend" in capsys.readouterr().err


def test_volume_get_prints_percent(monkeypatch, capsys):
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_volume_read", lambda: (42.0, False))
    assert cli.cmd_volume(["get"]) == 0
    assert capsys.readouterr().out.strip() == "42"


# --- brightness: LAPTOP ONLY, steps, shows the OSD --------------------------

def test_brightness_is_laptop_only(monkeypatch, capsys):
    """On a PC (is_laptop False), `azarch brightness up/down` does NOTHING and says so (rc 1) --
    brightness is a laptop-only control. The backlight setter is never called."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "is_laptop", lambda: False)
    called = {"write": False}
    monkeypatch.setattr(cli, "_brightness_write", lambda p: called.__setitem__("write", True) or True)
    assert cli.cmd_brightness(["up"]) == 1
    assert called["write"] is False
    err = capsys.readouterr().err
    assert "laptop-only" in err


def test_brightness_up_on_laptop_steps_and_shows_osd(monkeypatch, capsys):
    """On a laptop, `azarch brightness up` steps 7.5% off the current backlight reading and pops
    the OSD."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "is_laptop", lambda: True)
    monkeypatch.setattr(cli, "_brightness_read", lambda: 40.0)
    written = {}
    monkeypatch.setattr(cli, "_brightness_write", lambda p: (written.__setitem__("p", p), True)[1])
    osd = {}
    monkeypatch.setattr(cli, "_show_osd", lambda kind, pct, muted=False: osd.update(kind=kind, pct=pct))
    assert cli.cmd_brightness(["up"]) == 0
    assert written["p"] == 47.5
    assert osd == {"kind": "brightness", "pct": 47.5}
    assert "Brightness: 48%" in capsys.readouterr().out


def test_brightness_get_is_na_on_a_pc(monkeypatch, capsys):
    """`azarch brightness get` always exits 0; on a PC (no backlight) it prints n/a rather than
    erroring, so a caller can query without tripping the laptop gate."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli, "_brightness_read", lambda: None)
    assert cli.cmd_brightness(["get"]) == 0
    assert capsys.readouterr().out.strip() == "n/a"


def test_brightness_step_never_blanks_the_panel(monkeypatch):
    """The backlight write keeps a raw value of at least 1 so a "down" step never drives the
    panel to pure black (unrecoverable without the keys). Drive _brightness_write against a fake
    sysfs device and assert the written raw is >= 1 even at 0%."""
    cli = _command_line_interface()
    writes = []

    class _FakeWritable:
        """A tiny file stand-in that records everything written to it, and survives the
        `with open(...) as fh` close (a StringIO would raise once closed)."""
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def write(self, s):
            writes.append(s)

        def read(self):
            return "100"

    monkeypatch.setattr(cli, "_backlight_device", lambda: "/sys/class/backlight/fake")

    real_open = open

    def fake_open(path, *a, **k):
        if path.endswith("max_brightness") or path.endswith("brightness"):
            return _FakeWritable()
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", fake_open)
    monkeypatch.setattr(cli.os, "access", lambda p, m: True)   # pretend we can write directly
    assert cli._brightness_write(0.0) is True
    assert writes, "nothing was written to the backlight"
    assert int(writes[-1]) >= 1                                # never a raw 0 (black panel)


# --- the OSD is centered, cyan, iconed, self-dismissing ---------------------

def _osd_src() -> str:
    return (paths.AZARCH_COMMAND_LINE_INTERFACE_DIR / "osd_indicator.py").read_text(encoding="utf-8")


def test_osd_uses_the_logo_cyan_for_the_bar():
    """The spec: use the Az'arch logo colour, cyan, for the bars. The OSD's accent is #06B8FD."""
    src = _osd_src()
    assert "#06B8FD" in src
    assert 'ACCENT = "#06B8FD"' in src


def test_osd_is_centered_on_the_primary_monitor():
    """The spec: put it in the middle. The OSD centers on the primary monitor (parsed from
    xrandr, like the speech-to-text indicator)."""
    src = _osd_src()
    assert "primary_geometry" in src
    assert "xrandr" in src and "listmonitors" in src
    # centered: (mw - WIN_W)//2, (mh - WIN_H)//2
    assert "(mw - WIN_W) // 2" in src
    assert "(mh - WIN_H) // 2" in src


def test_osd_draws_simple_volume_and_brightness_icons():
    """The spec: create simple icons for volume and brightness. They are DRAWN on the canvas
    (a speaker for volume, a sun for brightness) -- simple primitives, no image files."""
    src = _osd_src()
    assert "_draw_speaker" in src        # the volume icon
    assert "_draw_sun" in src            # the brightness icon
    # it chooses the icon by kind
    assert 'self.kind == "brightness"' in src
    # a muted state is representable (the speaker shows an x)
    assert "self.muted" in src


def test_osd_scale_is_full_range_and_self_dismisses():
    """The spec: give me 100% (a full-range bar). The OSD bar is a 0..100 percent fill, and it
    fades out / closes on its own after a hold so a keypress just flashes it."""
    src = _osd_src()
    assert "self.percent / 100.0" in src         # a 0..100 percent fill
    assert "_start_fade" in src and "-alpha" in src
    assert "override_redirect" not in src        # (spelled overrideredirect)
    assert "overrideredirect(True)" in src
    assert "-topmost" in src


def test_osd_never_steals_focus():
    """Inherited from the speech-to-text indicator: the OSD must never steal focus (no
    focus_set/force, no key bindings) so typing is never interrupted."""
    src = _osd_src()
    # No focus-grabbing CALLS (the words may appear in the design-notes docstring explaining the
    # constraint; what must be absent is an actual .focus_force()/.focus_set() invocation).
    assert ".focus_force(" not in src
    assert ".focus_set(" not in src


# --- the launcher (media.py) wires to the shipped OSD, non-blocking ----------

def test_media_launches_the_shipped_osd_detached():
    """media.py launches the OSD DETACHED (start_new_session) with one JSON line, so the FN key
    returns instantly; and it targets the same path the ISO ships the OSD to."""
    cli = _command_line_interface()
    assert cli.OSD_INDICATOR_BIN == desktop.AZARCH_OSD_SYSTEM_PATH == "/usr/local/lib/azarch/azarch-osd"
    src = bundle_source()
    # the OSD is launched via Popen, detached, fed a JSON payload
    assert "start_new_session=True" in src
    assert '"kind": kind' in src and '"percent"' in src and '"muted"' in src


def test_media_osd_is_a_noop_without_display(monkeypatch):
    """No DISPLAY (or a missing OSD binary) must make _show_osd a clean no-op -- the FN key still
    changes the volume/brightness, it just shows no bar. It must NOT spawn a process."""
    cli = _command_line_interface()
    monkeypatch.setattr(cli.os.environ, "get", lambda *a, **k: None)   # DISPLAY unset
    monkeypatch.setattr(cli.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("must not spawn the OSD without a display"))
    cli._show_osd("volume", 50.0)   # returns cleanly


# --- the OpenBox FN keybinds + the OSD shipping ------------------------------

def test_openbox_binds_the_fn_media_keysyms():
    """The FN keys are wired by BINDING the XF86 media keysyms (not a fixed FN+F2/F3, which
    differs per machine) to the `azarch` subcommands."""
    rc = desktop.openbox_rc_xml()
    assert "XF86AudioRaiseVolume" in rc and "/usr/local/bin/azarch volume up" in rc
    assert "XF86AudioLowerVolume" in rc and "/usr/local/bin/azarch volume down" in rc
    assert "XF86AudioMute" in rc and "/usr/local/bin/azarch volume mute" in rc
    assert "XF86MonBrightnessUp" in rc and "/usr/local/bin/azarch brightness up" in rc
    assert "XF86MonBrightnessDown" in rc and "/usr/local/bin/azarch brightness down" in rc


def test_openbox_documents_the_per_machine_fn_mapping():
    """The rc.xml comment must explain WHY we bind keysyms: the physical FN+F2/F3 mapping differs
    between a PC (volume) and a laptop (brightness), so binding the keysyms makes each 'just
    work' -- and brightness self-gates on a PC."""
    rc = desktop.openbox_rc_xml()
    assert "keysym" in rc.lower()
    assert "brightness" in rc.lower() and "volume" in rc.lower()


def test_osd_ships_executable_and_pinned():
    """The OSD script ships (root-owned, executable) next to the terminal user interface binary, and is pinned
    0755 in the ISO file_permissions (archiso would otherwise ship it 0644 and the launcher's
    X_OK guard would silently skip the bar)."""
    # a PLAN entry emits it to the lib dir, executable, root-owned
    entry = next(e for e in desktop.emit_plan()
                 if e["dest"] == "/usr/local/lib/azarch/azarch-osd")
    assert entry["owner"] == "root"
    assert entry["mode"] == desktop._EXEC
    # the builder emits the indicator source verbatim (with its python3 shebang)
    body = entry["builder"]()
    assert body.startswith("#!/usr/bin/env python3")
    # pinned executable in the ISO
    perms = profiledef.FILE_PERMISSIONS
    assert perms["/usr/local/lib/azarch/azarch-osd"] == "0:0:755"


def test_osd_is_not_bundled_into_the_fast_cli():
    """The OSD is a SEPARATE GUI process (it imports tkinter); it must NOT be bundled into the
    `azarch` script, whose fast path must not pay a tkinter import."""
    assert "osd_indicator.py" not in MODULE_ORDER
    assert "import tkinter" not in bundle_source()


def test_osd_never_lingers_on_empty_or_bad_stdin():
    """REGRESSION: the OSD must self-terminate even when stdin closes with NO usable message
    (the launcher died before writing, or wrote only blanks/garbage). A stuck, process-alive
    window on that path would wedge on every FN press whose payload failed to arrive. The window
    starts WITHDRAWN and closes on an empty EOF, and a hard MAX_LIFETIME backstop bounds every
    path. Drive the real script under a timeout and assert it exits promptly, not on the kill.

    Skipped without a DISPLAY or without tkinter (headless CI): the script exits 2 immediately
    when tkinter is unavailable, which is itself non-lingering, but we only assert the
    interesting path where a window could actually be mapped."""
    import os
    import shutil

    if not os.environ.get("DISPLAY"):
        pytest.skip("no DISPLAY: the OSD cannot map a window to linger")
    try:
        import tkinter  # noqa: F401
    except Exception:
        pytest.skip("no tkinter available")

    osd = paths.AZARCH_COMMAND_LINE_INTERFACE_DIR / "osd_indicator.py"
    py = shutil.which("python3") or shutil.which("python")
    assert py, "no python interpreter to run the OSD"
    # A generous timeout, but well ABOVE the ~1.35s normal flash and the 4s hard backstop, so a
    # clean exit lands far inside it while a genuine hang trips the timeout (returncode != 0).
    # The payloads cover EVERY no-usable-message shape: nothing, blanks, non-JSON garbage, AND
    # JSON that DECODES but is not a dict (null / a list / a number / a string) -- the last group
    # is the subtle case an adversary found hanging under load, because such a payload looks like
    # input but reveals no window; the pump now treats a non-dict as "no message" and exits
    # deterministically on EOF.
    for stdin_text in ("", "   \n\n", "not-json\n", "null\n", "[1,2,3]\n", "42\n", '"hi"\n'):
        proc = subprocess.run(
            [py, str(osd)], input=stdin_text.encode(),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=12,
        )
        # subprocess.run raises TimeoutExpired if it hung; reaching here means it self-exited.
        assert proc.returncode == 0, (
            f"OSD exited {proc.returncode} on stdin={stdin_text!r} (expected a clean 0)"
        )


def test_osd_starts_withdrawn_and_closes_on_empty_eof():
    """The source contract behind the regression above: the window is created WITHDRAWN (revealed
    only in show() on the first real message); the EOF handler exits DETERMINISTICALLY (os._exit,
    keyed off a synchronously-set `dispatched` flag, so a non-dict payload cannot wedge it and a
    just-queued real message is not killed early); and a hard max-lifetime backstop runs on its
    OWN THREAD (immune to Tk event-loop starvation under many concurrent OSDs)."""
    src = _osd_src()
    # withdrawn until a message arrives (no unconditional deiconify in __init__)
    assert "self._shown = False" in src
    assert "self.root.deiconify()" in src            # present -- but inside show(), guarded by _shown
    # the EOF teardown keys off `dispatched` (set synchronously in the pump) and hard-exits, so a
    # non-dict payload (null / list / number) that reveals no window cannot leave it lingering.
    assert "dispatched" in src
    assert "if not dispatched" in src
    assert "os._exit(0)" in src
    assert "isinstance(msg, dict)" in src            # non-dict decoded payloads don't count as input
    # the hard-lifetime backstop is a WATCHDOG THREAD (not a Tk `after` timer, which could starve)
    assert "_start_watchdog" in src
    assert "MAX_LIFETIME_S" in src
    assert "threading.Thread(target=watchdog" in src
