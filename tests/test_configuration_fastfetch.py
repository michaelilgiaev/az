"""packages.fastfetch -- the fastfetch configuration + Az' logo.

The configuration's `source` MUST be an absolute path: fastfetch resolves a relative
source against the CWD, so a bare filename silently falls back to the stock Arch
logo (the documented bug this module exists to prevent).
"""

from __future__ import annotations

import json

from packages import fastfetch


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
    # module entries may be plain strings ("title") or objects ({"type": "custom", ...});
    # collect the type of each for the membership check.
    types = {m if isinstance(m, str) else m.get("type") for m in data["modules"]}
    for mod in ("title", "os", "kernel", "packages"):
        assert mod in types


def _edition_line(is_gui: bool) -> str:
    """The custom fastfetch module value that names the running edition, for the given line."""
    data = json.loads(fastfetch.config_jsonc(is_gui=is_gui))
    customs = [m for m in data["modules"]
               if isinstance(m, dict) and m.get("type") == "custom"]
    assert customs, "config must carry a custom module naming the edition"
    # exactly one edition module, keyed "Edition"
    edition = [m for m in customs if m.get("key") == "Edition"]
    assert len(edition) == 1, f"expected one Edition custom module, got {edition}"
    return edition[0]["format"]


def test_config_states_headed_edition():
    # NEW TASK B: fastfetch must say which edition is running. Headed -> "Headed".
    line = _edition_line(is_gui=True)
    assert "Headed" in line and "Headless" not in line, line
    assert "Az'arch" in line


def test_config_states_headless_edition():
    line = _edition_line(is_gui=False)
    assert "Headless" in line, line
    assert "Az'arch" in line


def test_edition_differs_between_lines():
    assert _edition_line(is_gui=True) != _edition_line(is_gui=False)


def test_config_jsonc_defaults_to_headed():
    # A bare config_jsonc() (no arg) is the historical default -> headed, so any existing
    # caller that does not pass is_gui keeps producing the graphical edition's config.
    assert fastfetch.config_jsonc() == fastfetch.config_jsonc(is_gui=True)


def test_both_editions_are_valid_json():
    for is_gui in (True, False):
        data = json.loads(fastfetch.config_jsonc(is_gui=is_gui))
        assert data["logo"]["type"] == "file-raw"
