"""Locale setup: a STATIC English-only, Asia/Jerusalem configuration plus the
country->locale map kept as data for the (deferred) dynamic resolver.

Both consumers -- setup-locale.sh (runs on the LIVE ISO) and the locale portion
of chroot-setup.sh (runs in the INSTALL chroot) -- share
``_detect_and_apply_locale_block()`` below. As of the "no auto-resolve" change it
does NOT query the network: the display language is English (en_US.UTF-8), the
keyboard is English-only ("us"), and the timezone is Asia/Jerusalem, all fixed.

The old behaviour -- IP-geolocating the timezone/country (curl ipapi.co) and
switching the display locale from LANGUAGE_MAP -- is intentionally gone. It is
being reimplemented as separate, user-invoked guest commands (`azarch
--resolve-date-time` / `--resolve-language` / `--resolve-region`) tracked in
issue #46; that work is deliberately NOT done here. LANGUAGE_MAP is retained as
the single source of truth those future commands will consume (adding a language
is still a one-line Python edit), but it is no longer embedded in the shipped
setup scripts.
"""

from __future__ import annotations

# country code -> (language name, locale). Order preserved (matches the original).
# NOTE: this is now DATA ONLY -- retained for the deferred `azarch --resolve-*`
# commands (issue #46). The static locale block below no longer reads it, so the
# live/installed systems ship English-only regardless of what is added here.
LANGUAGE_MAP: dict[str, tuple[str, str]] = {
    "US": ("English", "en_US.UTF-8"),
    "GB": ("English", "en_GB.UTF-8"),
    "FR": ("French", "fr_FR.UTF-8"),
    "DE": ("German", "de_DE.UTF-8"),
    "ES": ("Spanish", "es_ES.UTF-8"),
    "IT": ("Italian", "it_IT.UTF-8"),
    "UA": ("Ukrainian", "uk_UA.UTF-8"),
    "RU": ("Russian", "ru_RU.UTF-8"),
    "CN": ("Chinese", "zh_CN.UTF-8"),
    "JP": ("Japanese", "ja_JP.UTF-8"),
    "KR": ("Korean", "ko_KR.UTF-8"),
    "BR": ("Portuguese", "pt_BR.UTF-8"),
    "IN": ("Hindi", "hi_IN.UTF-8"),
    "IL": ("Hebrew", "he_IL.UTF-8"),
    "AR": ("Arabic", "ar_SA.UTF-8"),
    "TR": ("Turkish", "tr_TR.UTF-8"),
    "NL": ("Dutch", "nl_NL.UTF-8"),
    "PL": ("Polish", "pl_PL.UTF-8"),
    "SE": ("Swedish", "sv_SE.UTF-8"),
    "NO": ("Norwegian", "nb_NO.UTF-8"),
    "DK": ("Danish", "da_DK.UTF-8"),
    "FI": ("Finnish", "fi_FI.UTF-8"),
    "CZ": ("Czech", "cs_CZ.UTF-8"),
    "HU": ("Hungarian", "hu_HU.UTF-8"),
    "GR": ("Greek", "el_GR.UTF-8"),
    "TH": ("Thai", "th_TH.UTF-8"),
    "VN": ("Vietnamese", "vi_VN.UTF-8"),
}


def _language_map_heredoc() -> str:
    """Render LANGUAGE_MAP as the ``CC|Language|locale`` lines the (deferred)
    resolver will grep. Retained as a helper for issue #46; NOT used by the
    static setup block below."""
    return "\n".join(f"{cc}|{name}|{loc}" for cc, (name, loc) in LANGUAGE_MAP.items())


# Az'arch default/only display language and keyboard. English everywhere; the
# keymap is always "us" with no second layout and no group-toggle.
DEFAULT_LANG = "en_US.UTF-8"
DEFAULT_KEYMAP = "us"

# Az'arch default (and, since auto-resolve was removed, ONLY) timezone. Dynamic
# geo detection is deferred to `azarch --resolve-date-time` (issue #46).
DEFAULT_TIMEZONE = "Asia/Jerusalem"


# Shared bash block: apply the STATIC locale -- English display language, an
# English-only ("us") keyboard, and the Asia/Jerusalem timezone. NO network call.
# Both the live-ISO script and the installer chroot script start from this.
#
# Language policy: ENGLISH-ONLY. LANG is en_US.UTF-8, unconditionally.
# Keyboard policy: ENGLISH-ONLY. The layout is always "us" with no second layout
# and no group-toggle.
# Timezone policy: Asia/Jerusalem, unconditionally. (No IP geolocation -- that is
# reimplemented as the user-invoked `azarch --resolve-*` commands, issue #46.)
def _detect_and_apply_locale_block() -> str:
    return f"""\
# Static locale: English display language, English-only ("us") keyboard, and the
# Asia/Jerusalem timezone. Nothing here is auto-resolved from the network -- the
# dynamic resolver lives in the `azarch --resolve-*` commands (issue #46).
PRIMARY_LANG="{DEFAULT_LANG}"
PRIMARY_KB="{DEFAULT_KEYMAP}"

# Enable the single (English) locale.
sed -i "s/^#\\?\\s*$PRIMARY_LANG/$PRIMARY_LANG/" /etc/locale.gen

# Generate locales
locale-gen

# Set system locale
echo "LANG=$PRIMARY_LANG" > /etc/locale.conf

# Set console keyboard (English-only)
echo "KEYMAP=$PRIMARY_KB" > /etc/vconsole.conf
echo "FONT=lat2-16" >> /etc/vconsole.conf

# Set X11 keyboard layout (English-only: single "us" layout, no toggle)
mkdir -p /etc/X11/xorg.conf.d
cat <<EOF > /etc/X11/xorg.conf.d/00-keyboard.conf
Section "InputClass"
    Identifier "system-keyboard"
    MatchIsKeyboard "on"
    Option "XkbLayout" "$PRIMARY_KB"
EndSection
EOF

# Set timezone: Asia/Jerusalem (fixed; no geo detection).
ln -sf "/usr/share/zoneinfo/{DEFAULT_TIMEZONE}" /etc/localtime

hwclock --systohc"""


def setup_locale_sh() -> str:
    """The live-ISO oneshot: apply the static locale, then mark complete."""
    return f"""\
#!/bin/bash

{_detect_and_apply_locale_block()}

# Mark setup complete
touch /var/log/.locale_set
"""
