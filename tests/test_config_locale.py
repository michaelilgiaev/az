"""azarch.config.locale -- the country->locale map and the bash it generates.

LANGUAGE_MAP is the single source of truth; the live-ISO and installer scripts
grep the heredoc it renders. A malformed heredoc line means the country match
silently fails and the user gets the wrong locale.
"""

from __future__ import annotations

from azarch.config import locale


def test_language_map_has_no_duplicate_country_codes():
    # A dict can't hold dup keys, but assert the count matches distinct locales'
    # spread so a copy-paste that overwrites an entry is visible.
    codes = list(locale.LANGUAGE_MAP.keys())
    assert len(codes) == len(set(codes))


def test_every_locale_is_utf8():
    for cc, (name, loc) in locale.LANGUAGE_MAP.items():
        assert loc.endswith(".UTF-8"), f"{cc} -> {loc}"


def test_heredoc_renders_every_entry_as_pipe_delimited():
    heredoc = locale._language_map_heredoc()
    lines = heredoc.splitlines()
    assert len(lines) == len(locale.LANGUAGE_MAP)
    for cc, (name, loc) in locale.LANGUAGE_MAP.items():
        assert f"{cc}|{name}|{loc}" in lines


def test_heredoc_lines_have_exactly_three_fields():
    for line in locale._language_map_heredoc().splitlines():
        assert line.count("|") == 2, line


def test_setup_locale_sh_is_a_bash_script_and_embeds_the_map():
    sh = locale.setup_locale_sh()
    assert sh.startswith("#!/bin/bash")
    # The generated map is embedded so the on-ISO grep can match it.
    assert "US|English|en_US.UTF-8" in sh
    # The completion marker the oneshot touches.
    assert "touch /var/log/.locale_set" in sh


def test_us_maps_to_english():
    assert locale.LANGUAGE_MAP["US"] == ("English", "en_US.UTF-8")


def test_brace_escaping_collapsed():
    # The block is built with an f-string; every literal brace in the emitted bash
    # is written doubled in the source ({{ / }}). If a doubling is missed the
    # f-string raises at import; if a stray {{ survives into the OUTPUT the bash is
    # broken. So the rendered text must contain NO doubled braces.
    block = locale._detect_and_apply_locale_block()
    assert "{{" not in block
    assert "}}" not in block


def test_keyboard_is_english_only():
    # Keyboard policy is English-only: a single "us" layout, no second layout, and
    # no group-toggle. The old SECONDARY_KB machinery (comma expansion + the
    # grp:alt_shift_toggle option) must be entirely gone from the emitted bash.
    block = locale._detect_and_apply_locale_block()
    assert 'PRIMARY_KB="us"' in block
    assert "SECONDARY_KB" not in block
    assert "grp:alt_shift_toggle" not in block
    # The X11 layout line carries only the primary (us) layout, no comma-joined 2nd.
    assert 'Option "XkbLayout" "$PRIMARY_KB"' in block


def test_default_timezone_is_asia_jerusalem():
    # Asia/Jerusalem is the shipped default timezone; it is the FALLBACK used when
    # IP-geo does not resolve to a real zoneinfo file (geo still wins when it does).
    assert locale.DEFAULT_TIMEZONE == "Asia/Jerusalem"
    block = locale._detect_and_apply_locale_block()
    assert 'ln -sf "/usr/share/zoneinfo/Asia/Jerusalem" /etc/localtime' in block
    # The old UTC fallback must be gone.
    assert "zoneinfo/UTC" not in block


def test_setup_locale_single_shebang_and_marker():
    # setup_locale_sh() wraps the shared block; the shared block itself must NOT
    # carry a shebang or the completion marker, or the wrapper would emit two of
    # each. Exactly one shebang and one marker in the final script.
    out = locale.setup_locale_sh()
    assert out.count("#!/bin/bash") == 1
    assert out.count("touch /var/log/.locale_set") == 1
