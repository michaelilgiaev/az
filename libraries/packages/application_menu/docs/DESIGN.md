# Az'arch Application Menu -- Design

## Goal

Pressing **Super** (or **Alt+F1**) opens **two** application menus together:

- **Left:** KDE's stock Kickoff (unchanged).
- **Right:** our own menu -- for now just a "Hello World" window, to be grown later.

Pressing the key **again closes both**. Behavior matches Kickoff: toggle open/closed,
never more than one of our windows on screen.

## Components

### 1. `libraries/menu.py` -- the persistent, single-instance menu

- Runs as ONE long-lived process. Holds a single Tkinter window, pinned to the
  right edge of the screen, showing "Hello World".
- Starts **hidden** (withdrawn). It does not steal focus or show until toggled.
- Listens on a **Unix domain socket** at
  `$XDG_RUNTIME_DIR/azarch-application-menu.sock` for one-line commands:
  - `toggle` -> if the window is visible, hide it; else show it (raised, on the right).
  - `show` / `hide` -> explicit variants (used internally/testing).
  - `ping` -> replies `ok` (used by the launcher to detect a running instance).
- **Single instance:** on startup it tries to bind the socket. If the socket is
  already in use (another instance is up), it sends `toggle` to that instance and
  exits immediately -- so launching the menu a second time toggles the existing
  one instead of opening a duplicate.
- Stale-socket safe: if the socket file exists but nothing answers `ping`, it is
  removed and this process takes over.

### 2. `libraries/azarch-application-menu.sh` -- the launcher (bound to Super)

On each press:
1. **Our menu:** send `toggle` to the socket. If no instance is running, start
   `menu.py` (which comes up and shows itself), so the first press opens it.
2. **Kickoff:** invoke Plasma's `activate application launcher` global-shortcut
   action (kglobalaccel) -- the same action Alt+F1 fires -- which toggles Kickoff.

Net: one press opens both; next press closes both.

### 3. `install.sh` / `uninstall.sh`

- `install.sh`: copy menu.py + launcher into place; write the `.desktop`
  (`X-KDE-Shortcuts=Meta`) that binds Super to the launcher; unbind Super from
  Kickoff's direct activation (Alt+F1 kept); **autostart the persistent menu** so
  it is already running (hidden) at login; reload the shortcut daemon.
- `uninstall.sh`: restore Kickoff's Super binding; remove the `.desktop`, the
  autostart entry, the installed files; stop any running menu instance.

## Why a persistent process + socket

Tkinter has no cross-process "toggle" primitive. A fresh `python3 menu.py` per
press cannot see or close a window opened by a previous press -- that is the
"our menu stacks up / never closes" bug. A single resident process that toggles
its own window on a socket command gives Kickoff-identical open/close with no
duplicates, and no third-party dependencies (socket + Tkinter are stdlib).

## Testing (on the hypervisor, headless-safe)

- Start menu.py; assert it binds the socket and starts hidden (window state
  `withdrawn`).
- Send `toggle` -> window becomes viewable; send `toggle` -> withdrawn again.
- Start a second `menu.py` -> it exits non-error and the first instance toggled
  (no second process remains).
- Launcher: with no instance, a call starts one; with an instance, a call toggles.
- Full install -> invoke Super action -> both our menu shows and Kickoff fires;
  invoke again -> both hidden. Uninstall -> Kickoff Super binding restored.
