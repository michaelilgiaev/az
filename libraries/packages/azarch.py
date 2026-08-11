#!/usr/bin/env python3
"""azarch -- guest-side helper CLI (pure Python).

Installed to /usr/local/bin/azarch on the live ISO and the installed system.
Subcommands:

  azarch --sshd-hypervisor
    Installs the host's public key from ~/shared/authorized_keys (staged there by
    the hypervisor) into ~/.ssh/authorized_keys, then enables and starts sshd. Safe
    to run more than once. (Named --sshd-hypervisor because it wires the guest sshd
    up for the hypervisor's forwarded host->guest SSH port.)

  azarch --resolve-region / --resolve-date-time / --resolve-language
    The ONLY things that ping an external server to geolocate the machine and update
    its region settings (everything else in Az'arch is static/user-chosen). Each
    presents a list of 5 SHUFFLED IP-geolocation servers; the user picks one, it is
    queried for the country code + timezone, and the system is updated:
      --resolve-date-time  set the timezone to match the IP.
      --resolve-language   set the language to English + the region's language
                           (English ONLY if the region is English-speaking), i.e. a
                           second keyboard layout with Alt+Shift + the locale.
      --resolve-region     do both.

The country -> (locale, layout, keymap, english) map is embedded below from
patches/calamares/locale locale.RESOLVER_COUNTRY_TABLE (the single source of truth); the
compiler regenerates the block between the AZARCH_CC markers at build time.

Pure standard library: no curl/jq, no pip packages. The geolocation query uses
urllib + json; the privileged steps shell out via sudo exactly as the old CLI did.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import urllib.request

# --- resolver: country -> locale + keyboard layout table --------------------
# CC -> (locale, xkb_layout, vconsole_keymap, english). `english` 1 means the
# country is English-speaking -> English ONLY (no second layout/locale). The
# compiler REGENERATES everything between the two AZARCH_CC markers from
# configuration/locale.RESOLVER_COUNTRY_TABLE, so this literal stays in lock-step.
# AZARCH_CC_TABLE_START
COUNTRY_TABLE: dict[str, tuple[str, str, str, int]] = {
    'US': ('en_US.UTF-8', 'us', 'us', 1),
    'GB': ('en_GB.UTF-8', 'us', 'us', 1),
    'AU': ('en_AU.UTF-8', 'us', 'us', 1),
    'NZ': ('en_NZ.UTF-8', 'us', 'us', 1),
    'IE': ('en_IE.UTF-8', 'us', 'us', 1),
    'ZA': ('en_ZA.UTF-8', 'us', 'us', 1),
    'CA': ('en_CA.UTF-8', 'us', 'us', 1),
    'SV': ('es_SV.UTF-8', 'latam', 'la-latin1', 0),
    'MX': ('es_MX.UTF-8', 'latam', 'la-latin1', 0),
    'AR': ('es_AR.UTF-8', 'latam', 'la-latin1', 0),
    'CO': ('es_CO.UTF-8', 'latam', 'la-latin1', 0),
    'CL': ('es_CL.UTF-8', 'latam', 'la-latin1', 0),
    'PE': ('es_PE.UTF-8', 'latam', 'la-latin1', 0),
    'VE': ('es_VE.UTF-8', 'latam', 'la-latin1', 0),
    'EC': ('es_EC.UTF-8', 'latam', 'la-latin1', 0),
    'GT': ('es_GT.UTF-8', 'latam', 'la-latin1', 0),
    'BO': ('es_BO.UTF-8', 'latam', 'la-latin1', 0),
    'CR': ('es_CR.UTF-8', 'latam', 'la-latin1', 0),
    'PY': ('es_PY.UTF-8', 'latam', 'la-latin1', 0),
    'PA': ('es_PA.UTF-8', 'latam', 'la-latin1', 0),
    'UY': ('es_UY.UTF-8', 'latam', 'la-latin1', 0),
    'HN': ('es_HN.UTF-8', 'latam', 'la-latin1', 0),
    'NI': ('es_NI.UTF-8', 'latam', 'la-latin1', 0),
    'DO': ('es_DO.UTF-8', 'latam', 'la-latin1', 0),
    'CU': ('es_CU.UTF-8', 'latam', 'la-latin1', 0),
    'ES': ('es_ES.UTF-8', 'es', 'es', 0),
    'FR': ('fr_FR.UTF-8', 'fr', 'fr', 0),
    'DE': ('de_DE.UTF-8', 'de', 'de', 0),
    'AT': ('de_AT.UTF-8', 'de', 'de', 0),
    'CH': ('de_CH.UTF-8', 'ch', 'de_CH-latin1', 0),
    'IT': ('it_IT.UTF-8', 'it', 'it', 0),
    'PT': ('pt_PT.UTF-8', 'pt', 'pt-latin1', 0),
    'BR': ('pt_BR.UTF-8', 'br', 'br-abnt2', 0),
    'NL': ('nl_NL.UTF-8', 'nl', 'nl', 0),
    'PL': ('pl_PL.UTF-8', 'pl', 'pl', 0),
    'SE': ('sv_SE.UTF-8', 'se', 'sv-latin1', 0),
    'NO': ('nb_NO.UTF-8', 'no', 'no-latin1', 0),
    'DK': ('da_DK.UTF-8', 'dk', 'dk-latin1', 0),
    'FI': ('fi_FI.UTF-8', 'fi', 'fi', 0),
    'CZ': ('cs_CZ.UTF-8', 'cz', 'cz-lat2', 0),
    'HU': ('hu_HU.UTF-8', 'hu', 'hu', 0),
    'TR': ('tr_TR.UTF-8', 'tr', 'trq', 0),
    'RO': ('ro_RO.UTF-8', 'ro', 'ro', 0),
    'HR': ('hr_HR.UTF-8', 'hr', 'croat', 0),
    'SK': ('sk_SK.UTF-8', 'sk', 'sk-qwerty', 0),
    'SI': ('sl_SI.UTF-8', 'si', 'slovene', 0),
    'EE': ('et_EE.UTF-8', 'ee', 'et', 0),
    'LV': ('lv_LV.UTF-8', 'lv', 'lv', 0),
    'LT': ('lt_LT.UTF-8', 'lt', 'lt', 0),
    'IS': ('is_IS.UTF-8', 'is', 'is-latin1', 0),
    'VN': ('vi_VN.UTF-8', 'vn', 'us', 0),
    'IL': ('he_IL.UTF-8', 'il', 'il', 0),
    'RU': ('ru_RU.UTF-8', 'ru', 'ruwin_alt_sh-UTF-8', 0),
    'UA': ('uk_UA.UTF-8', 'ua', 'ua-utf', 0),
    'BY': ('be_BY.UTF-8', 'by', 'by', 0),
    'BG': ('bg_BG.UTF-8', 'bg', 'bg_bds-utf8', 0),
    'RS': ('sr_RS.UTF-8', 'rs', 'sr-cy', 0),
    'MK': ('mk_MK.UTF-8', 'mk', 'mk-utf', 0),
    'GR': ('el_GR.UTF-8', 'gr', 'gr', 0),
    'GE': ('ka_GE.UTF-8', 'ge', 'ge', 0),
    'AM': ('hy_AM.UTF-8', 'am', 'us', 0),
    'IR': ('fa_IR.UTF-8', 'ir', 'us', 0),
    'PK': ('ur_PK.UTF-8', 'pk', 'us', 0),
    'IN': ('hi_IN.UTF-8', 'in', 'us', 0),
    'TH': ('th_TH.UTF-8', 'th', 'us', 0),
    'KH': ('km_KH.UTF-8', 'kh', 'us', 0),
    'LA': ('lo_LA.UTF-8', 'la', 'us', 0),
    'MM': ('my_MM.UTF-8', 'mm', 'us', 0),
    'LK': ('si_LK.UTF-8', 'lk', 'us', 0),
    'JP': ('ja_JP.UTF-8', 'jp', 'jp106', 0),
    'KR': ('ko_KR.UTF-8', 'kr', 'us', 0),
    'CN': ('zh_CN.UTF-8', 'cn', 'us', 0),
    'TW': ('zh_TW.UTF-8', 'tw', 'us', 0),
    'MN': ('mn_MN.UTF-8', 'mn', 'us', 0),
    'SA': ('ar_SA.UTF-8', 'ara', 'us', 0),
    'AE': ('ar_AE.UTF-8', 'ara', 'us', 0),
    'EG': ('ar_EG.UTF-8', 'ara', 'us', 0),
    'IQ': ('ar_IQ.UTF-8', 'ara', 'us', 0),
    'JO': ('ar_JO.UTF-8', 'ara', 'us', 0),
    'KW': ('ar_KW.UTF-8', 'ara', 'us', 0),
    'LB': ('ar_LB.UTF-8', 'ara', 'us', 0),
    'LY': ('ar_LY.UTF-8', 'ara', 'us', 0),
    'OM': ('ar_OM.UTF-8', 'ara', 'us', 0),
    'QA': ('ar_QA.UTF-8', 'ara', 'us', 0),
    'SY': ('ar_SY.UTF-8', 'ara', 'us', 0),
    'YE': ('ar_YE.UTF-8', 'ara', 'us', 0),
    'BH': ('ar_BH.UTF-8', 'ara', 'us', 0),
    'DZ': ('ar_DZ.UTF-8', 'ara', 'us', 0),
    'MA': ('ar_MA.UTF-8', 'ara', 'us', 0),
    'TN': ('ar_TN.UTF-8', 'ara', 'us', 0),
    'SD': ('ar_SD.UTF-8', 'ara', 'us', 0),
}
# AZARCH_CC_TABLE_END

# The 5 IP-geolocation servers offered (shuffled before display). Each entry is
# (label, url, country_path, timezone_path) -- the country_path/timezone_path are
# dotted JSON paths into that server's response (the pure-Python equivalent of the
# old jq filters). ipapi.co and ipquery.io were called out in issue #46; the rest
# are well-known free equivalents.
RESOLVER_SERVERS: list[tuple[str, str, str, str]] = [
    ("ipapi.co", "https://ipapi.co/json/", "country_code", "timezone"),
    ("ipquery.io", "https://api.ipquery.io/?format=json",
     "location.country_code", "location.timezone"),
    ("ip-api.com", "http://ip-api.com/json/", "countryCode", "timezone"),
    ("ipinfo.io", "https://ipinfo.io/json", "country", "timezone"),
    ("ipwho.is", "https://ipwho.is/", "country_code", "timezone"),
]


def _err(msg: str) -> None:
    """Print to stderr (stdout stays result-only, matching the old CLI)."""
    print(msg, file=sys.stderr)


def _sudo(*args: str, check: bool = True) -> int:
    """Run a command under sudo (or directly if already root). Returns the exit
    code; raises subprocess.CalledProcessError when check and the command fails."""
    prefix: list[str] = [] if os.geteuid() == 0 else ["sudo"]
    return subprocess.run([*prefix, *args], check=check).returncode


def usage() -> None:
    print(
        "Usage: azarch <command>\n"
        "\n"
        "Commands:\n"
        "  --sshd-hypervisor    Install host pubkey from ~/shared/authorized_keys "
        "and start sshd\n"
        "  --resolve-region     Geolocate by IP (pick a server) and set BOTH "
        "timezone and language\n"
        "  --resolve-date-time  Geolocate by IP (pick a server) and set the timezone\n"
        "  --resolve-language   Geolocate by IP (pick a server) and set English + "
        "the region language"
    )


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


def _have(prog: str) -> bool:
    return any(os.access(os.path.join(d, prog), os.X_OK)
               for d in os.environ.get("PATH", "").split(os.pathsep) if d)


def _sudo_write(path: str, content: str) -> None:
    """Write `content` to a root-owned file via `sudo tee` (works unprivileged)."""
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    subprocess.run([*prefix, "tee", path], input=content.encode(),
                   stdout=subprocess.DEVNULL, check=False)


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


def _sudo_write_append(path: str, content: str) -> None:
    """Append `content` to a root-owned file via `sudo tee -a`."""
    prefix = [] if os.geteuid() == 0 else ["sudo"]
    subprocess.run([*prefix, "tee", "-a", path], input=content.encode(),
                   stdout=subprocess.DEVNULL, check=False)


def sshd_hypervisor() -> int:
    """Install the host pubkey from ~/shared/authorized_keys into the TARGET user's
    ~/.ssh/authorized_keys and start sshd. Resolves the REAL login user via SUDO_USER
    (the documented invocation is `sudo azarch --sshd-hypervisor`), refuses a bare-root
    target, mounts the 9p `shared` folder, and opens the firewall before starting
    sshd."""
    target_user = os.environ.get("SUDO_USER") or _current_user()
    if target_user == "root":
        _err("azarch --sshd-hypervisor: run as a normal user via sudo (got root); "
             "cannot stage a login key for root")
        return 1
    try:
        import pwd
        target_home = pwd.getpwnam(target_user).pw_dir
    except KeyError:
        target_home = ""
    if not target_home:
        _err(f"azarch --sshd-hypervisor: could not resolve home for user {target_user}")
        return 1
    shared = os.path.join(target_home, "shared")
    key = os.path.join(shared, "authorized_keys")
    if not _is_mountpoint(shared):
        os.makedirs(shared, exist_ok=True)
        rc = _sudo("mount", "-t", "9p", "-o",
                   "trans=virtio,version=9p2000.L,msize=104857600",
                   "shared", shared, check=False)
        if rc != 0:
            _err("azarch --sshd-hypervisor: could not mount shared folder (is the VM "
                 "running with shared_directory=true?)")
            return 1
    if not os.path.isfile(key):
        _err(f"azarch --sshd-hypervisor: {key} not found -- stage a host pubkey there "
             "first")
        return 1
    # Install the key into the TARGET user's ~/.ssh and hand ownership to them
    # (root-owned authorized_keys trips sshd StrictModes). Each privileged step is
    # FAIL-FAST, mirroring the old shell CLI's `set -e`: if a step fails, bail with its
    # exit code and do NOT print the success line (so a failed sshd never reports
    # "enabled and started"). _sudo returns the child's exit code.
    ssh_dir = os.path.join(target_home, ".ssh")
    rc = _sudo("install", "-d", "-m", "700", "-o", target_user, "-g", target_user,
               ssh_dir, check=False)
    if rc != 0:
        return rc
    rc = _sudo("install", "-m", "600", "-o", target_user, "-g", target_user,
               key, os.path.join(ssh_dir, "authorized_keys"), check=False)
    if rc != 0:
        return rc
    print(f"Installed pubkey -> {target_home}/.ssh/authorized_keys")
    rc = _sudo("ssh-keygen", "-A", check=False)
    if rc != 0:
        return rc
    # setup-pkgs.sh sets 'ufw default reject incoming', so open :22 BEFORE starting
    # sshd (so the forwarded host->guest port is reachable the moment it listens).
    rc = _sudo("ufw", "allow", "ssh", check=False)
    if rc != 0:
        return rc
    rc = _sudo("systemctl", "enable", "--now", "sshd", check=False)
    if rc != 0:
        return rc
    print(f"sshd enabled and started -- ssh in as {target_user}.")
    return 0


def _current_user() -> str:
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except KeyError:
        return os.environ.get("USER", "")


def _is_mountpoint(path: str) -> bool:
    return subprocess.run(["mountpoint", "-q", path],
                          stderr=subprocess.DEVNULL).returncode == 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""

    if cmd == "--sshd-hypervisor":
        return sshd_hypervisor()
    if cmd == "--resolve-date-time":
        result = resolve_via_server()
        if result is None:
            return 1
        country, tz = result
        print(f"Resolved: country={country} timezone={tz}")
        return apply_timezone(tz)
    if cmd == "--resolve-language":
        result = resolve_via_server()
        if result is None:
            return 1
        country, _tz = result
        print(f"Resolved: country={country}")
        return apply_language(country)
    if cmd == "--resolve-region":
        result = resolve_via_server()
        if result is None:
            return 1
        country, tz = result
        print(f"Resolved: country={country} timezone={tz}")
        # FAIL-FAST like the old shell (`set -e`): if the timezone can't be applied
        # (e.g. unknown zone), bail WITHOUT touching the keyboard/locale, so a bad
        # geolocation result never half-applies the region.
        rc = apply_timezone(tz)
        if rc != 0:
            return rc
        return apply_language(country)
    if cmd in ("-h", "--help", "help"):
        usage()
        return 0
    if cmd == "":
        usage()
        return 1
    _err(f"azarch: unknown command: {cmd}")
    usage_err()
    return 2


def usage_err() -> None:
    """Same as usage() but on stderr (for the unknown-command path)."""
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        usage()
    sys.stderr.write(buf.getvalue())


if __name__ == "__main__":
    sys.exit(main())
