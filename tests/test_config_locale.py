"""azarch.config.locale -- the static (English-only, Asia/Jerusalem) locale
setup plus the country->locale map retained as data for the deferred resolver.

As of the "no auto-resolve" change the emitted setup bash is STATIC: it must NOT
query the network (no curl / ipapi.co), must NOT match a country against
LANGUAGE_MAP, and must ship English (en_US.UTF-8), an English-only "us" keymap,
and the Asia/Jerusalem timezone unconditionally. The dynamic resolver is being
reimplemented as the user-invoked `azarch --resolve-*` commands (issue #46) and
is deliberately NOT part of the shipped setup scripts. LANGUAGE_MAP survives as
the single source of truth those future commands will consume.
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
    # The heredoc helper is retained for the deferred resolver (issue #46); it
    # still renders every entry, even though the static setup no longer embeds it.
    heredoc = locale._language_map_heredoc()
    lines = heredoc.splitlines()
    assert len(lines) == len(locale.LANGUAGE_MAP)
    for cc, (name, loc) in locale.LANGUAGE_MAP.items():
        assert f"{cc}|{name}|{loc}" in lines


def test_heredoc_lines_have_exactly_three_fields():
    for line in locale._language_map_heredoc().splitlines():
        assert line.count("|") == 2, line


def test_setup_locale_sh_is_a_bash_script_with_completion_marker():
    sh = locale.setup_locale_sh()
    assert sh.startswith("#!/bin/bash")
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


def test_no_auto_resolve_in_setup_block():
    # The whole point of the "no auto-resolve" change: the shipped setup bash must
    # NOT geolocate anything. No network call (curl / ipapi.co), no COUNTRY/TIMEZONE
    # capture, and NO embedding of the LANGUAGE_MAP the old country match grepped.
    block = locale._detect_and_apply_locale_block()
    assert "curl" not in block
    assert "ipapi.co" not in block
    assert "COUNTRY" not in block
    # The old geo-detected TIMEZONE variable is gone (the zone is now a literal).
    assert "TIMEZONE=" not in block
    # The country->locale map is NOT embedded in the static script anymore.
    assert "US|English|en_US.UTF-8" not in block
    assert locale._language_map_heredoc() not in block
    # No SECONDARY (2nd locale) machinery survives either.
    assert "SECONDARY_LANG" not in block


def test_language_is_english_only():
    # Display language is a fixed English (en_US.UTF-8) LANG -- no conditional.
    block = locale._detect_and_apply_locale_block()
    assert locale.DEFAULT_LANG == "en_US.UTF-8"
    assert 'PRIMARY_LANG="en_US.UTF-8"' in block
    assert 'echo "LANG=$PRIMARY_LANG" > /etc/locale.conf' in block


def test_keyboard_is_english_only():
    # Keyboard policy is English-only: a single "us" layout, no second layout, and
    # no group-toggle. The old SECONDARY_KB machinery (comma expansion + the
    # grp:alt_shift_toggle option) must be entirely gone from the emitted bash.
    block = locale._detect_and_apply_locale_block()
    assert locale.DEFAULT_KEYMAP == "us"
    assert 'PRIMARY_KB="us"' in block
    assert "SECONDARY_KB" not in block
    assert "grp:alt_shift_toggle" not in block
    # The X11 layout line carries only the primary (us) layout, no comma-joined 2nd.
    assert 'Option "XkbLayout" "$PRIMARY_KB"' in block


def test_default_timezone_is_asia_jerusalem_and_static():
    # Asia/Jerusalem is the shipped default timezone; with auto-resolve removed it
    # is now the ONLY zone -- symlinked unconditionally, with no geo override and
    # no fallback branch.
    assert locale.DEFAULT_TIMEZONE == "Asia/Jerusalem"
    block = locale._detect_and_apply_locale_block()
    assert 'ln -sf "/usr/share/zoneinfo/Asia/Jerusalem" /etc/localtime' in block
    # The old UTC fallback must be gone.
    assert "zoneinfo/UTC" not in block
    # And there is exactly one localtime symlink (no if/else geo branch).
    assert block.count("/etc/localtime") == 1


def test_setup_locale_single_shebang_and_marker():
    # setup_locale_sh() wraps the shared block; the shared block itself must NOT
    # carry a shebang or the completion marker, or the wrapper would emit two of
    # each. Exactly one shebang and one marker in the final script.
    out = locale.setup_locale_sh()
    assert out.count("#!/bin/bash") == 1
    assert out.count("touch /var/log/.locale_set") == 1
