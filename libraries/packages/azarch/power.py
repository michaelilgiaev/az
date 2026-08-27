#!/usr/bin/env python3
"""azarch guest command line interface -- `azarch power` (shutdown / restart / sleep / lock, with timers).

Plain wrappers over the confusing raw session/power tools, matching the rest of the azarch
CLI (base command vs azarch wrapper). Four verbs:

  shutdown  -> systemctl poweroff
  restart   -> systemctl reboot
  sleep     -> systemctl suspend
  lock      -> lock the screen (loginctl lock-session, with an xdg/light-locker fallback)

The first three take TIMER flags so an action can be scheduled, inspected, and cancelled:

  --in <DURATION>   run after a delay (e.g. 30m, 1h, 90s, or a bare number = minutes)
  --at <HH:MM>      run at a wall-clock time today (or tomorrow if already past)
  --status          show whether this action has a pending timer (and when)
  --cancel          cancel this action's pending timer

TIMER MECHANISM. All three scheduled actions use a TRANSIENT systemd timer created with
`systemd-run --on-active=/--on-calendar=`, named `azarch-<action>` (so
`azarch-shutdown.timer` etc.). One mechanism covers poweroff, reboot AND suspend uniformly
(plain `shutdown(8)` cannot schedule a suspend), and `--status`/`--cancel` just inspect and
stop that transient unit. No separate on-disk state file to drift: the timer IS the state.

lock has no timer (locking on a delay is niche); it always locks now.

Everything below lands in the single bundled /usr/local/bin/azarch namespace, so it calls
the shared helpers (_err, _have) by bare name and uses os/subprocess from the bundle header.
See common.py / bundle.py.
"""

from __future__ import annotations

# BUNDLE_START

# The transient systemd units are named azarch-<action>{,.timer}. Keeping a single prefix
# means --status/--cancel can find them without any bookkeeping file.
_POWER_UNIT_PREFIX = "azarch-"

# The scheduled actions (lock is excluded -- it has no timer) mapped to the systemctl verb
# the timer ultimately runs.
_POWER_ACTIONS = {
    "shutdown": "poweroff",
    "restart": "reboot",
    "sleep": "suspend",
}


def _power_unit(action: str) -> str:
    """The transient unit BASENAME for an action (systemd-run appends .service/.timer)."""
    return f"{_POWER_UNIT_PREFIX}{action}"


def parse_duration(token: str) -> int | None:
    """Parse a human duration into SECONDS, or None if it is not a valid duration.

    Accepts `90s`, `30m`, `2h`, `1d`, a combo like `1h30m`, or a BARE number which -- to
    match the `shutdown` convention users expect -- is MINUTES (`30` == 30 minutes). Zero
    and negatives are rejected (a timer must be in the future). Pure (string in, int out)
    so it is trivially unit-testable."""
    token = token.strip().lower()
    if not token:
        return None
    # Bare number -> minutes (the `shutdown +N` convention). isascii() guards the int():
    # str.isdigit() accepts non-ASCII digit characters (superscripts, circled digits) that
    # int() then REJECTS with ValueError, so `isdigit()` alone would crash on e.g. "²".
    if token.isascii() and token.isdigit():
        n = int(token)
        return n * 60 if n > 0 else None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    total = 0
    num = ""
    for ch in token:
        # ASCII digits only: str.isdigit() also matches non-ASCII "digit" chars ("²", "①")
        # that int() cannot parse -- treat those as stray chars, not digits, so int(num)
        # below can never raise.
        if ch.isascii() and ch.isdigit():
            num += ch
        elif ch in units and num:
            total += int(num) * units[ch]
            num = ""
        else:
            return None  # stray char, or a unit with no preceding number
    if num:  # trailing digits with no unit are invalid in the unit form
        return None
    return total if total > 0 else None


def _valid_hhmm(token: str) -> str | None:
    """Validate an HH:MM wall-clock token; return it normalised (zero-padded) or None.
    Used for --at, which maps straight onto systemd's OnCalendar `HH:MM` form."""
    parts = token.split(":")
    # isascii() guards the int() below: str.isdigit() accepts non-ASCII digit characters
    # (e.g. "²") that int() then rejects with ValueError, so a bare isdigit() would crash.
    if len(parts) != 2 or not all(p.isascii() and p.isdigit() for p in parts):
        return None
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def _schedule_power(action: str, when_args: list[str]) -> int:
    """Create the transient timer for a scheduled action from its --in/--at args.

    Builds a `systemd-run --unit=azarch-<action> --on-active=<secs> / --on-calendar=<HH:MM>
    systemctl <verb>` invocation. A pre-existing timer for the same action is cleared first
    (--cancel semantics) so re-scheduling replaces rather than stacks."""
    verb = _POWER_ACTIONS[action]
    on_active_secs: int | None = None
    on_calendar: str | None = None
    i = 0
    while i < len(when_args):
        a = when_args[i]
        if a == "--in":
            if i + 1 >= len(when_args):
                _err(f"azarch power {action}: --in needs a duration (e.g. 30m, 1h, 90s).")
                return 2
            on_active_secs = parse_duration(when_args[i + 1])
            if on_active_secs is None:
                _err(f"azarch power {action}: invalid duration '{when_args[i + 1]}' "
                     "(use e.g. 30m, 1h, 90s, or a plain number of minutes).")
                return 2
            i += 2
            continue
        if a.startswith("--in="):
            on_active_secs = parse_duration(a.split("=", 1)[1])
            if on_active_secs is None:
                _err(f"azarch power {action}: invalid duration in '{a}'.")
                return 2
            i += 1
            continue
        if a == "--at":
            if i + 1 >= len(when_args):
                _err(f"azarch power {action}: --at needs a time (HH:MM).")
                return 2
            on_calendar = _valid_hhmm(when_args[i + 1])
            if on_calendar is None:
                _err(f"azarch power {action}: invalid time '{when_args[i + 1]}' (use HH:MM).")
                return 2
            i += 2
            continue
        if a.startswith("--at="):
            on_calendar = _valid_hhmm(a.split("=", 1)[1])
            if on_calendar is None:
                _err(f"azarch power {action}: invalid time in '{a}' (use HH:MM).")
                return 2
            i += 1
            continue
        _err(f"azarch power {action}: unknown option '{a}'.")
        return 2

    if on_active_secs is None and on_calendar is None:
        _err(f"azarch power {action}: --in <DURATION> or --at <HH:MM> is required to "
             "schedule.")
        return 2

    if not _have("systemd-run"):
        _err("azarch power: systemd-run not found (systemd is required to schedule).")
        return 1

    # Replace any existing timer for this action so scheduling is idempotent.
    _cancel_power(action, quiet=True)

    unit = _power_unit(action)
    cmd = ["systemd-run", f"--unit={unit}"]
    if on_active_secs is not None:
        cmd.append(f"--on-active={on_active_secs}s")
        human = f"in {on_active_secs // 60} min" if on_active_secs >= 60 \
            else f"in {on_active_secs}s"
    else:
        cmd.append(f"--on-calendar=*-*-* {on_calendar}:00")
        human = f"at {on_calendar}"
    cmd += ["systemctl", verb]
    rc = _sudo(*cmd, check=False)
    if rc != 0:
        _err(f"azarch power {action}: could not schedule the timer.")
        return 1
    print(f"Scheduled {action} ({verb}) {human}. Cancel with "
          f"`azarch power {action} --cancel`.")
    return 0


def _cancel_power(action: str, quiet: bool = False) -> int:
    """Stop this action's transient timer (and its pending service), if any. Best-effort;
    returns 0 whether or not a timer existed (cancelling nothing is not an error)."""
    unit = _power_unit(action)
    had = _power_pending(action)
    _sudo("systemctl", "stop", f"{unit}.timer", check=False)
    _sudo("systemctl", "stop", f"{unit}.service", check=False)
    # A transient unit lingers as 'failed'/'dead'; reset so a later --status is clean.
    _sudo("systemctl", "reset-failed", f"{unit}.timer", check=False)
    _sudo("systemctl", "reset-failed", f"{unit}.service", check=False)
    if not quiet:
        print(f"{'Cancelled pending ' + action if had else 'No pending ' + action}.")
    return 0


def _power_pending(action: str) -> str:
    """The next-elapse description of this action's pending timer, or '' if none. Reads
    `systemctl list-timers` for the action's unit (a read; no root needed)."""
    unit = _power_unit(action)
    r = subprocess.run(
        ["systemctl", "list-timers", "--all", "--no-legend", f"{unit}.timer"],
        capture_output=True, text=True, check=False,
    )
    for line in r.stdout.splitlines():
        if f"{unit}.timer" in line:
            return line.strip()
    return ""


def _status_power(action: str) -> int:
    """Print whether this action has a pending timer (and its schedule). Returns 0 when a
    timer is pending, 1 when none -- so a probe/TUI can branch on the exit code."""
    pending = _power_pending(action)
    if pending:
        print(f"{action}: scheduled -- {pending}")
        return 0
    print(f"{action}: no timer scheduled")
    return 1


def _do_power_now(action: str) -> int:
    """Run the action immediately via systemctl (poweroff/reboot/suspend)."""
    verb = _POWER_ACTIONS[action]
    if not _have("systemctl"):
        _err("azarch power: systemctl not found (systemd is required).")
        return 1
    rc = _sudo("systemctl", verb, check=False)
    if rc != 0:
        _err(f"azarch power {action}: `systemctl {verb}` failed.")
        return 1
    return 0


def _power_verb(action: str, args: list[str]) -> int:
    """Shared handler for shutdown/restart/sleep: dispatch the timer flags, else act now.

      --status  -> show pending timer
      --cancel  -> cancel pending timer
      --in/--at -> schedule
      (none)    -> do it now
    """
    if args and args[0] in ("-h", "--help", "help"):
        verb = _POWER_ACTIONS[action]
        print(f"Usage: azarch power {action} [--in <DURATION> | --at <HH:MM> | "
              "--status | --cancel]\n"
              "\n"
              f"  (no option)      {action.capitalize()} now (systemctl {verb}).\n"
              "  --in <DURATION>  Schedule after a delay (30m, 1h, 90s, or N minutes).\n"
              "  --at <HH:MM>     Schedule at a wall-clock time.\n"
              "  --status         Show any pending timer for this action.\n"
              "  --cancel         Cancel the pending timer for this action.")
        return 0
    if "--status" in args:
        return _status_power(action)
    if "--cancel" in args:
        return _cancel_power(action)
    if any(a == "--in" or a.startswith("--in=") or a == "--at" or a.startswith("--at=")
           for a in args):
        return _schedule_power(action, args)
    if args:
        _err(f"azarch power {action}: unknown option '{args[0]}' "
             "(try --in, --at, --status, --cancel).")
        return 2
    return _do_power_now(action)


def cmd_lock(args: list[str]) -> int:
    """`azarch lock` -- lock the screen NOW. Tries loginctl lock-session first (the
    session-manager way, works under any DE), then a couple of common lockers as a
    fallback. No timer (locking on a delay is not useful)."""
    if args and args[0] in ("-h", "--help", "help"):
        print("Usage: azarch lock\n\n  Lock the screen now.")
        return 0
    # loginctl lock-session: asks the session manager to lock; the running locker (if any)
    # picks it up. No root needed for one's own session.
    if _have("loginctl"):
        if subprocess.run(["loginctl", "lock-session"], check=False).returncode == 0:
            print("Screen locked.")
            return 0
    for locker in (["light-locker-command", "-l"], ["xdg-screensaver", "lock"],
                   ["betterlockscreen", "-l"], ["i3lock"]):
        if _have(locker[0]):
            if subprocess.run(locker, check=False).returncode == 0:
                print("Screen locked.")
                return 0
    _err("azarch lock: no screen locker available (tried loginctl, light-locker, "
         "xdg-screensaver, betterlockscreen, i3lock).")
    return 1


def cmd_power(args: list[str]) -> int:
    """`azarch power <shutdown|restart|sleep|lock> [timer flags]` -- the grouped entry
    point. The individual verbs are also exposed at the top level (azarch shutdown, etc.)
    by command_line_interface.main, which calls the same handlers."""
    if not args or args[0] in ("-h", "--help", "help"):
        print("Usage: azarch power <shutdown|restart|sleep|lock> [options]\n"
              "\n"
              "  shutdown [--in D|--at T|--status|--cancel]  Power off (with optional "
              "timer).\n"
              "  restart  [--in D|--at T|--status|--cancel]  Reboot (with optional timer).\n"
              "  sleep    [--in D|--at T|--status|--cancel]  Suspend (with optional "
              "timer).\n"
              "  lock                                        Lock the screen now.\n"
              "\n"
              "Durations: 30m, 1h, 90s, or a plain number of minutes. Times: HH:MM.")
        return 0
    verb = args[0]
    rest = args[1:]
    if verb == "shutdown":
        return _power_verb("shutdown", rest)
    if verb == "restart":
        return _power_verb("restart", rest)
    if verb == "sleep":
        return _power_verb("sleep", rest)
    if verb == "lock":
        return cmd_lock(rest)
    _err(f"azarch power: unknown command: {verb} "
         "(use shutdown|restart|sleep|lock).")
    return 2
