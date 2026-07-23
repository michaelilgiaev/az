"""azarch.config.fastfetch -- the fastfetch config + Az' logo.

The config's `source` MUST be an absolute path: fastfetch resolves a relative
source against the CWD, so a bare filename silently falls back to the stock Arch
logo (the documented bug this module exists to prevent).
"""

from __future__ import annotations

import json

from azarch.config import fastfetch


def test_config_jsonc_is_valid_json():
    # ".jsonc" but this file carries no comments/trailing commas -> parseable as JSON.
    data = json.loads(fastfetch.config_jsonc())
    assert data["logo"]["type"] == "file-raw"


def test_logo_source_is_absolute_path():
    data = json.loads(fastfetch.config_jsonc())
    src = data["logo"]["source"]
    assert src.startswith("/"), src
    assert src == fastfetch.LOGO_PATH


def test_logo_path_matches_filename_constant():
    assert fastfetch.LOGO_PATH.endswith("/" + fastfetch.LOGO_FILENAME)


def test_logo_txt_reads_the_repo_asset():
    # Verbatim read of the pre-colored .ansi asset; it exists and is non-empty.
    art = fastfetch.logo_txt()
    assert art.strip() != ""


def test_config_includes_expected_modules():
    data = json.loads(fastfetch.config_jsonc())
    for mod in ("title", "os", "kernel", "packages"):
        assert mod in data["modules"]
