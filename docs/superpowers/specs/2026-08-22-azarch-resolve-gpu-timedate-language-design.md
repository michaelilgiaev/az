# Design: `azarch gpu --resolve`, `azarch timedate --resolve`, `azarch language --resolve`

Date: 2026-08-22

## 1. Goal

Give the booted Az'arch live ISO three **user-invoked** resolver commands, each also reachable
as a top-level entry in the `azarch` terminal user interface (TUI):

- `azarch gpu --resolve` — detect the machine's GPU(s) and install the matching missing GPU +
  developer drivers from the baked-in offline repo (offline-capable; `sudo pacman -Syu` handles
  staleness later).
- `azarch timedate --resolve` — pick one IP-geolocation server (shuffled), resolve the timezone,
  and apply it.
- `azarch language --resolve` — same geolocation, apply English (+ the region language/keyboard as
  a switchable second layout when the country is non-English).

**Explicitly user-triggered.** None of this runs on first boot. The ISO keeps shipping a generic
GPU stack that works everywhere and static English/`Asia/Jerusalem` defaults; the user opts into
resolution from the TUI or the command line.

## 2. Current state (what already exists — verified)

Two of the three already exist as flag-style guest commands, fully built and tested:

- `libraries/packages/azarch/resolver.py` — `resolve_via_server()` (5 shuffled servers:
  ipapi.co, ipquery.io, ip-api.com, ipinfo.io, ipwho.is), `apply_timezone(tz)`, `apply_language(country)`.
- `libraries/packages/azarch/command_line_interface.py` — dispatches `--resolve-date-time`,
  `--resolve-language`, `--resolve-region` (region = both, fail-fast on timezone error).
- `libraries/packages/azarch/country_table.py` — the country→(locale, xkb, keymap, english) table,
  regenerated at build time from the single source of truth `packages/calamares/locale.py` via
  `packages/openbox.azarch_command_line_interface()` (between the `# AZARCH_CC_TABLE_*` markers).
- The whole guest CLI is bundled into one `/usr/local/bin/azarch` script by
  `libraries/packages/azarch/bundle.py` (`MODULE_ORDER`).

What is **missing**:

- No `gpu` anything: detection, driver mapping, or install. The manifest
  (`libraries/packages/packages.x86_64`) bakes in only `mesa` for graphics — no `xf86-video-*`,
  no Vulkan, no `nvidia`, no `libva`/`vdpau`, no compute/developer drivers.
- No top-level TUI entries for GPU / Time & Date / Language. The TUI tree
  (`libraries/packages/azarch/model_tree.c`, `ROWS_MAIN` / `SCREENS[]`) has Network, Theme,
  Wallpaper, Volume, Brightness, Default Applications, Display, Machine Type, Backup — none of the three.
- The command names don't match the prompt: the prompt asks for the positional form
  `azarch <gpu|timedate|language> --resolve`; only flag-style `--resolve-*` exists today.

The offline install mechanism `gpu --resolve` needs already exists: the ISO bakes a local pacman
repo at `/root/azarch/pacstrap-azarch-repo/` (built by `libraries/downloader.py`;
`installer.py` copies it to `/mnt/pacstrap-azarch-repo/` for on-disk installs). A `file://` repo
pointed at it installs baked-in packages with no network. This is the same repo the installer uses
(`pacman.py: installer_pacstrap_conf()` → `Server = file:///mnt/pacstrap-azarch-repo/`).

## 3. Approach (chosen)

Positional subcommands `azarch gpu`, `azarch timedate`, `azarch language`, each taking `--resolve`,
**keeping** the existing `--resolve-date-time` / `--resolve-language` / `--resolve-region` flags as
hidden aliases (so every current test and `--resolve-region`'s "do both" stay green). This honors
the prompt's exact syntax, adds a real namespace each feature can grow into (`--status`, `--list`),
and is almost entirely additive. Rejected: renaming-and-deleting the old flags (harder break, loses
`--resolve-region` for no benefit) and keeping only the old flags (ignores the prompt, leaves the
surface inconsistent with `gpu --resolve`).

## 4. Components

### 4.1 GPU driver detection + install — new module `libraries/packages/azarch/gpu.py`

A new bundled module (added to `bundle.py` `MODULE_ORDER`, after `machine.py` — both are
sysfs/`lspci` hardware probes with no dependency on later modules).

**Detection.** Read GPU vendor IDs from PCI. Prefer parsing sysfs
(`/sys/bus/pci/devices/*/{class,vendor}` — class `0x03xxxx` is a display controller) so detection is
root-free and needs no extra tool; fall back to `lspci -nn` when present. Vendor IDs:
`0x10de` NVIDIA, `0x1002`/`0x1022` AMD, `0x8086` Intel. Returns the set of vendors present
(a VM/hypervisor with e.g. QXL/virtio-gpu/VMware resolves to "generic", meaning no vendor driver —
`mesa` already covers it).

**Driver map.** A static table from vendor → (base driver packages, developer/compute packages):

| Vendor | Base graphics | Developer / compute |
|---|---|---|
| Intel | `vulkan-intel lib32-vulkan-intel intel-media-driver libva-intel-driver` | `intel-compute-runtime` (OpenCL) |
| AMD | `xf86-video-amdgpu vulkan-radeon lib32-vulkan-radeon libva-mesa-driver mesa-vdpau` | `rocm-opencl-runtime rocm-hip-runtime opencl-mesa` |
| NVIDIA | `nvidia nvidia-utils lib32-nvidia-utils nvidia-settings` | `cuda opencl-nvidia` |
| (all) | `vulkan-icd-loader lib32-vulkan-icd-loader vulkan-mesa-layers libva vdpau` | `vulkan-tools clinfo vulkan-headers opencl-headers` |

(Exact package set finalized in the plan against the live Arch DB; the ISO bakes ALL of these so any
machine resolves offline.)

**Install.** For the detected vendors, compute the package list, then install **only the ones not
already present** via pacman against the baked-in offline repo, so it works with no network:

```
sudo pacman -Sy --needed --noconfirm \
  --config <transient conf with [pacstrap-azarch-repo] Server=file:///root/azarch/pacstrap-azarch-repo/> \
  <packages>
```

On the live ISO the repo is at `/root/azarch/pacstrap-azarch-repo/`; the module writes a transient
pacman.conf (reusing the exact stanza `pacman.py` already emits, `SigLevel = Never`) so it never
mutates the system `/etc/pacman.conf`. `--needed` makes it idempotent (already-installed baked-in
drivers are skipped). Outdated packages are explicitly out of scope — deferred to `pacman -Syu` as
the prompt says. If the offline repo is absent (e.g. installed system, not live ISO), fall back to
the normal configured repos so a networked machine still resolves.

Surface: `azarch gpu` (no args) prints detected GPUs + which driver packages are present/missing;
`azarch gpu --resolve` installs the missing ones; `azarch gpu --list` prints the full vendor→package
map. Needs root (installs packages) → the TUI row sets `.needs_root=1`.

### 4.2 Positional subcommands — `command_line_interface.py`

Add three dispatch branches that delegate to the existing resolver functions and the new gpu module:

- `azarch timedate [--resolve]` → `cmd_timedate()`: `--resolve` runs `resolve_via_server()` →
  `apply_timezone(tz)` (identical body to today's `--resolve-date-time`); no arg prints current zone
  (`timedatectl` / `/etc/localtime`).
- `azarch language [--resolve]` → `cmd_language()`: `--resolve` runs `resolve_via_server()` →
  `apply_language(country)` (identical to today's `--resolve-language`); no arg prints current
  `LANG` + keyboard layout.
- `azarch gpu [--resolve|--list]` → `cmd_gpu()` from `gpu.py`.

The old `--resolve-date-time` / `--resolve-language` / `--resolve-region` branches stay as-is
(hidden aliases). `usage()` documents the three new positional commands; the resolver logic is not
duplicated — the new handlers call the same `resolve_via_server` / `apply_*` functions.

### 4.3 TUI integration — `model_tree.c` (+ status probes in `model.c`, decls in the `.h`)

Add three top-level `ROWS_MAIN` entries and three `SCREENS[]` entries, each `AZ_ACT_APPLY` rows that
run the new `azarch` subcommands (exactly the existing pattern — the C TUI only ever shells out to
`azarch <subcommand>`, output captured in the overlay):

- **GPU** screen: `Detect & resolve GPU drivers` → `azarch gpu --resolve` (`.needs_root=1`,
  `.show_output=1`); `Show detected GPU / drivers` → `azarch gpu` (`.show_output=1`); `List driver
  map` → `azarch gpu --list` (`.show_output=1`). Base command: `lspci | grep -i vga`. Placed after
  Display (hardware group).
- **Time & Date** screen: `Resolve timezone (pick a server)` → `azarch timedate --resolve`. Base:
  `timedatectl set-timezone <tz>`.
- **Language** screen: `Resolve language (pick a server)` → `azarch language --resolve`. Base:
  `localectl set-locale`.

Interactive-server-prompt note: `resolve_via_server()` reads a `1-5` choice from stdin. The other
interactive TUI rows (Backup enable) use `AZ_ACT_PROMPT`, but that only injects a single trailing
token. The server picker is a full stdin menu, so — mirroring how Backup's genuinely interactive
`rclone config` is documented — the Time & Date / Language screen subtitles state that resolving asks
you to choose a server in the terminal. (If the capture overlay cannot host the prompt, the plan's
manual-verification step falls back to running the command from a shell; TUI wiring still lands.)

New status probes `az_status_gpu` / `az_status_timedate` / `az_status_language` in `model.c` show the
"Current:" line (detected GPU vendor; system timezone; `LANG` + layout), declared in
`terminal_user_interface.h`, following the existing `az_status_machine` probe pattern.

### 4.4 Bake every vendor driver into the ISO — `libraries/packages/packages.x86_64`

Add all packages from the §4.1 map to the AZ'ARCH ADDITIONS section, grouped under a clear
`# GPU drivers (all vendors) + GPU developer/compute stacks` comment block. This is what makes
`gpu --resolve` work offline for any machine: every driver is already in the baked-in repo, so
resolution is a local install, never a download. `lib32-*` packages require multilib, which the
build already enables. Size cost (CUDA/ROCm are large) is accepted per the prompt ("EVERY single
driver ... also every single developer driver").

## 5. Data flow

```
User (TUI row or shell)
        │
        ▼
azarch <gpu|timedate|language> --resolve        (/usr/local/bin/azarch, bundled)
        │
        ├── timedate/language ──► resolve_via_server()  ─► pick 1 of 5 shuffled servers ─► HTTP JSON
        │                                   │
        │                                   ▼
        │                         apply_timezone(tz) / apply_language(cc)  ─► timedatectl / locale.gen / xkb
        │
        └── gpu ──► detect vendors (sysfs PCI class 0x03, vendor id) 
                          │
                          ▼
                    map vendors → driver+dev packages → filter to missing
                          │
                          ▼
                    sudo pacman -Sy --needed --config <file:///root/azarch/pacstrap-azarch-repo/>  (offline)
```

## 6. Error handling

- **No network (timedate/language):** `resolve_via_server()` already returns `None` and prints a
  clear stderr message; the command exits non-zero without touching the system. Unchanged.
- **Unknown timezone / unmapped country:** existing `apply_timezone` returns 1 on a zone missing from
  `/usr/share/zoneinfo`; `apply_language` falls back to English-only. Unchanged.
- **GPU: offline repo missing:** fall back to the configured network repos; if that also fails,
  pacman's own error is surfaced (the command shows output). Non-zero exit.
- **GPU: no vendor GPU (VM/hypervisor):** report "generic GPU (mesa) — no vendor driver needed" and
  exit 0. The generic stack already works, matching the ISO's promise.
- **GPU: already resolved:** `--needed` skips installed packages; the command reports "nothing to do".
- All installs are non-interactive (`--noconfirm`) and time-bounded by the TUI's `timeout 30`
  wrapper when run from a row; from a shell they run unbounded (long CUDA/ROCm installs).

## 7. Testing

Python (pytest, matching the existing `test_configuration_openbox.py` resolver tests):

- `gpu.py` unit tests: vendor detection from a faked sysfs tree (Intel/AMD/NVIDIA/none/multi);
  vendor→package mapping correctness; `--resolve` builds the expected `pacman` argv against the
  offline `file://` repo and filters already-installed packages; `--needed`/`--noconfirm` present;
  never mutates `/etc/pacman.conf`.
- CLI dispatch tests: `azarch timedate --resolve` / `azarch language --resolve` call the same
  resolver functions as the old flags (stub `resolve_via_server`/`apply_*`, assert calls + rc),
  no-arg status paths; old `--resolve-*` flags still dispatch; `usage()` advertises the three
  positional commands.
- Manifest test: every driver package in the §4.1 map is present in `packages.x86_64` (guards the
  "baked in for offline resolve" contract, like the existing manifest/gap tests).
- Bundle test: `gpu.py` is in `MODULE_ORDER` and the emitted `/usr/local/bin/azarch` defines
  `cmd_gpu`.

C TUI (the existing C test harness under `tests/`, e.g. `test_terminal_user_interface_model.c`):
assert the three new screen ids resolve, the rows carry the right `azarch ...` targets and
`needs_root`/`show_output` flags, and `ROWS_MAIN` contains the three entries — mirroring how Machine
Type / Backup rows are pinned.

Manual verification (per repo standard, timeouts on every run): build-free run of the bundled
`azarch gpu` on this machine to confirm detection; dispatch-level checks for timedate/language.

## 8. Out of scope

- Updating drivers to the latest version (deferred to `sudo pacman -Syu`, per the prompt).
- Wayland-specific driver bits (the distro is X11).
- Auto-running any resolver on boot (explicitly user-invoked only).
- GPU overclocking / power / fan control.

## 9. Files touched

New:
- `libraries/packages/azarch/gpu.py`
- `tests/test_configuration_gpu.py`

Edited:
- `libraries/packages/azarch/bundle.py` (add `gpu.py` to `MODULE_ORDER`)
- `libraries/packages/azarch/command_line_interface.py` (positional `gpu`/`timedate`/`language`; usage)
- `libraries/packages/azarch/model_tree.c` (three `ROWS_*` + `SCREENS[]` + `ROWS_MAIN` entries)
- `libraries/packages/azarch/model.c` (three `az_status_*` probes)
- `libraries/packages/azarch/terminal_user_interface.h` (probe decls)
- `libraries/packages/packages.x86_64` (all vendor + developer GPU driver packages)
- `tests/test_configuration_openbox.py` (positional-subcommand assertions)
- C TUI model test (new screen/row assertions)
- Docs regenerated if the network-endpoints/localization sections drift.
