#!/usr/bin/env python3
"""azarch guest CLI -- IP-geolocation resolver (region / date-time / language).

The ONLY part of Az'arch that pings an external server to geolocate the machine and
update its region settings (everything else is static/user-chosen). Presents 5 SHUFFLED
IP-geolocation servers; the user picks one, it is queried for the country code + timezone,
and the system is updated. Pure standard library (urllib + json). See the package README in
common.py for how these modules are bundled into the single /usr/local/bin/azarch script.
"""

from __future__ import annotations

# BUNDLE_START

# The 5 IP-geolocation servers offered (shuffled before display). Each entry is
# (label, url, country_path, timezone_path) -- the country_path/timezone_path are
# dotted JSON paths into that server's response.
RESOLVER_SERVERS: list[tuple[str, str, str, str]] = [
    ("ipapi.co", "https://ipapi.co/json/", "country_code", "timezone"),
    ("ipquery.io", "https://api.ipquery.io/?format=json",
     "location.country_code", "location.timezone"),
    ("ip-api.com", "http://ip-api.com/json/", "countryCode", "timezone"),
    ("ipinfo.io", "https://ipinfo.io/json", "country", "timezone"),
    ("ipwho.is", "https://ipwho.is/", "country_code", "timezone"),
]


def _dig(data: dict, path: str):
    """Follow a dotted path (e.g. 'location.country_code') into nested JSON."""
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def resolve_via_server() -> tuple[str, str] | None:
    """Prompt the user to choose one of the 5 shuffled servers, query it, and return
    (COUNTRY, TIMEZONE) with the country uppercased. Returns None on any failure (no
    network, bad/empty response). Prompts/errors go to stderr."""
    servers = list(RESOLVER_SERVERS)
    random.shuffle(servers)
    _err("Pick a server to geolocate this machine (1-5):")
    for i, (label, *_rest) in enumerate(servers, 1):
        _err(f"  {i}) {label}")
    sys.stderr.write("Server number: ")
    sys.stderr.flush()
    try:
        choice = input()
    except EOFError:
        _err("azarch: invalid selection")
        return None
    if choice not in ("1", "2", "3", "4", "5"):
        _err(f"azarch: invalid selection {choice}")
        return None
    label, url, cpath, tpath = servers[int(choice) - 1]
    _err(f"Querying {label} ...")
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        _err(f"azarch: could not reach {label}")
        return None
    country = _dig(payload, cpath)
    tz = _dig(payload, tpath)
    country = str(country).upper() if country else ""
    tz = str(tz) if tz else ""
    if not country or not tz:
        _err(f"azarch: {label} did not return a country + timezone")
        return None
    return country, tz


def apply_timezone(tz: str) -> int:
    """Apply a timezone to the running system (via timedatectl when present, so the
    change is live; else the /etc/localtime symlink)."""
    if not os.path.exists(f"/usr/share/zoneinfo/{tz}"):
        _err(f"azarch: unknown timezone {tz}")
        return 1
    live = (subprocess.run(["timedatectl", "set-timezone", tz],
                           stderr=subprocess.DEVNULL).returncode == 0
            if _have("timedatectl") else False)
    if not live:
        _sudo("ln", "-sf", f"/usr/share/zoneinfo/{tz}", "/etc/localtime", check=False)
    print(f"Timezone set to {tz}")
    return 0


def apply_language(country: str) -> int:
    """Apply the language for a country code: English + the region's language as a
    second keyboard layout (Alt+Shift) and the region format locale -- or English
    ONLY if the country is English-speaking. Mirrors the Calamares region-keyboard
    behaviour (LANG stays English; only LC_* follow the region)."""
    row = COUNTRY_TABLE.get(country.upper())
    if row is None:
        _err(f"azarch: no language mapping for {country}; keeping English only")
        loc, layout, keymap, english = "en_US.UTF-8", "us", "us", 1
    else:
        loc, layout, keymap, english = row

    # Enable + generate the needed locales (English always; the region locale too
    # when non-English).
    _sudo("sed", "-i", r"s/^#\s*en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/",
          "/etc/locale.gen", check=False)
    if english == 0:
        _sudo("sed", "-i", rf"s/^#\s*{loc} UTF-8/{loc} UTF-8/",
              "/etc/locale.gen", check=False)
        # Anchored line check, mirroring the shell's `grep -q "^${loc} UTF-8"`: the
        # entry counts as present only if a LINE STARTS with it (an unanchored
        # substring could match a commented "#<loc> UTF-8" and wrongly skip the append).
        try:
            already = any(line.startswith(f"{loc} UTF-8")
                          for line in open("/etc/locale.gen").read().splitlines())
        except OSError:
            already = False
        if not already:
            _sudo_write_append("/etc/locale.gen", f"{loc} UTF-8\n")
    _sudo("locale-gen", check=False)

    # /etc/locale.conf: English UI, region format locale (LC_*) when non-English.
    conf = "LANG=en_US.UTF-8\n"
    if english == 0:
        for k in ("LC_NUMERIC", "LC_TIME", "LC_MONETARY", "LC_PAPER", "LC_MEASUREMENT"):
            conf += f"{k}={loc}\n"
    _sudo_write("/etc/locale.conf", conf)

    # Keyboard: English ("us") first/active; the region layout as a switchable SECOND
    # (Alt+Shift) when non-English. English-speaking -> "us" only.
    if english == 0 and layout != "us":
        xkb_layout = f"us,{layout}"
        xkb_opts = '    Option "XkbOptions" "grp:alt_shift_toggle"'
        vconsole_map = keymap
        live_layout = f"us,{layout}"
    else:
        xkb_layout = "us"
        xkb_opts = ""
        vconsole_map = "us"
        live_layout = "us"
    _sudo("mkdir", "-p", "/etc/X11/xorg.conf.d", check=False)
    kb = (
        'Section "InputClass"\n'
        '    Identifier "system-keyboard"\n'
        '    MatchIsKeyboard "on"\n'
        f'    Option "XkbLayout" "{xkb_layout}"\n'
        + (f"{xkb_opts}\n" if xkb_opts else "")
        + "EndSection\n"
    )
    _sudo_write("/etc/X11/xorg.conf.d/00-keyboard.conf", kb)
    _sudo_write("/etc/vconsole.conf", f"KEYMAP={vconsole_map}\n")

    # Apply the keyboard to the LIVE X11 session too, when an X server + setxkbmap
    # are available (so it takes effect now, not just after re-login).
    if os.environ.get("DISPLAY") and _have("setxkbmap"):
        if live_layout == "us":
            subprocess.run(["setxkbmap", "-layout", "us"],
                           stderr=subprocess.DEVNULL, check=False)
        else:
            subprocess.run(["setxkbmap", "-layout", live_layout,
                            "-option", "grp:alt_shift_toggle"],
                           stderr=subprocess.DEVNULL, check=False)

    if english == 0:
        print(f"Language set to English + {layout} (Alt+Shift to switch layouts)")
    else:
        print("Language set to English only")
    return 0
