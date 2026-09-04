"""Contract tests for tests.sh: the test-mode toggles, --help, marker registration, and the
env-export wiring the isolated log runs depend on. Mirrors the sibling Coder suite's
test_tests_sh.py so both distributions enforce the same standard."""
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TESTS_SH = REPO / "tests.sh"
MODESCONF = REPO / "tests" / "test_modes.conf"
CALAMARES = REPO / "tests" / "test_configuration_calamares.py"


def test_tests_sh_exists_and_parses():
    assert TESTS_SH.exists()
    r = subprocess.run(["bash", "-n", str(TESTS_SH)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# --- test-mode toggles: `tests.sh --online/--offline` and `--user/--root` -------------------
# These flags flip tests/test_modes.conf and EXIT without running pytest. Each test here restores
# the file afterwards so the toggle tests never leave the repo's committed default (both false)
# mutated.

@pytest.fixture
def _preserve_modesconf():
    saved = MODESCONF.read_text() if MODESCONF.exists() else None
    try:
        yield
    finally:
        if saved is None:
            MODESCONF.unlink(missing_ok=True)
        else:
            MODESCONF.write_text(saved)


def _run_toggle(*flags, timeout=30):
    """Run `bash tests.sh <flags>` with a HARD timeout. A toggle must return quickly (no venv, no
    pytest); if it ever fell through to the suite this would trip the timeout and fail loudly."""
    return subprocess.run(["bash", str(TESTS_SH), *flags],
                          capture_output=True, text=True, cwd=str(REPO), timeout=timeout)


def _conf_dict():
    out = {}
    for line in MODESCONF.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip().lower()] = v.strip().lower()
    return out


def test_offline_flag_writes_config_and_does_not_run_pytest(_preserve_modesconf):
    r = _run_toggle("--offline")
    assert r.returncode == 0, r.stderr
    assert _conf_dict()["network"] == "false"
    # It must have EXITED on the toggle, not launched the suite.
    combined = r.stdout + r.stderr
    assert "network=false" in combined
    assert "passed" not in combined and "collected" not in combined


def test_online_flag_writes_config(_preserve_modesconf):
    r = _run_toggle("--online")
    assert r.returncode == 0, r.stderr
    assert _conf_dict()["network"] == "true"
    assert "network=true" in (r.stdout + r.stderr)


def test_root_flag_writes_config_and_does_not_run_pytest(_preserve_modesconf):
    r = _run_toggle("--root")
    assert r.returncode == 0, r.stderr
    assert _conf_dict()["root"] == "true"
    combined = r.stdout + r.stderr
    assert "root=true" in combined
    assert "passed" not in combined and "collected" not in combined


def test_user_flag_writes_config(_preserve_modesconf):
    r = _run_toggle("--user")
    assert r.returncode == 0, r.stderr
    assert _conf_dict()["root"] == "false"
    assert "root=false" in (r.stdout + r.stderr)


def test_toggling_one_pair_preserves_the_other(_preserve_modesconf):
    # Turn network on, then flip only root: network must STAY on.
    assert _run_toggle("--online").returncode == 0
    assert _conf_dict()["network"] == "true"
    assert _run_toggle("--root").returncode == 0
    d = _conf_dict()
    assert d["network"] == "true" and d["root"] == "true"


def test_both_pairs_toggle_in_one_invocation(_preserve_modesconf):
    MODESCONF.write_text("network = false\nroot = false\n")
    r = _run_toggle("--online", "--root")
    assert r.returncode == 0, r.stderr
    d = _conf_dict()
    assert d["network"] == "true" and d["root"] == "true"


def test_online_and_offline_are_mutually_exclusive(_preserve_modesconf):
    before = MODESCONF.read_text() if MODESCONF.exists() else None
    r = _run_toggle("--online", "--offline")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "mutually exclusive" in r.stderr
    after = MODESCONF.read_text() if MODESCONF.exists() else None
    assert after == before


def test_user_and_root_are_mutually_exclusive(_preserve_modesconf):
    before = MODESCONF.read_text() if MODESCONF.exists() else None
    r = _run_toggle("--user", "--root")
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "mutually exclusive" in r.stderr
    after = MODESCONF.read_text() if MODESCONF.exists() else None
    assert after == before


def test_help_prints_usage_and_does_not_run_pytest():
    for flag in ("--help", "-h"):
        r = _run_toggle(flag)
        assert r.returncode == 0, r.stderr
        out = r.stdout + r.stderr
        assert "Usage:" in out
        assert "--offline" in out and "--online" in out
        assert "--user" in out and "--root" in out
        assert "passed" not in out and "collected" not in out


def test_committed_modes_conf_default_is_both_false():
    # The checked-in default must be both false: a fresh clone / CI then never hangs on the network
    # and never needs sudo.
    assert MODESCONF.exists(), "tests/test_modes.conf must be committed"
    d = _conf_dict()
    assert d.get("network") == "false", "committed network mode must default to false (offline)"
    assert d.get("root") == "false", "committed root mode must default to false (user)"


def test_tests_sh_exports_both_modes_for_isolated_runs():
    # The isolated log-copy runs don't get the conf file (it's outside their copy), so tests.sh must
    # export BOTH mode env vars for them to inherit the modes.
    s = TESTS_SH.read_text()
    assert "export AZARCH_TESTS_NETWORK" in s
    assert "export AZARCH_TESTS_ROOT" in s


def test_markers_are_registered():
    # --strict-markers is on, so `network` and `root` must be declared in pyproject or collection
    # errors.
    pp = (REPO / "pyproject.toml").read_text()
    assert "network:" in pp, "the `network` marker must be registered in pyproject.toml"
    assert "root:" in pp, "the `root` marker must be registered in pyproject.toml"


def test_root_marker_gates_the_two_calamares_tests():
    # The two btrfs loop-mount desparse tests are the ONLY root-requiring tests, and each must carry
    # @pytest.mark.root so the conftest hook / --user policy skip catches them.
    src = CALAMARES.read_text()
    for fn in ("test_desparse_actually_yields_uncompressed_boot_on_zstd_btrfs",
               "test_desparse_full_chain_yields_grub_readable_kernel_on_zstd_btrfs"):
        idx = src.index(f"def {fn}(")
        # The decorator sits on the line(s) immediately above the def; look back a small window.
        preamble = src[max(0, idx - 120):idx]
        assert "@pytest.mark.root" in preamble, f"{fn} must be decorated @pytest.mark.root"


def test_tests_sh_deletes_pytest_cache_on_exit():
    s = TESTS_SH.read_text()
    assert ".pytest_cache" in s
    assert "trap" in s and "EXIT" in s
    assert "no:cacheprovider" in s


@pytest.mark.parametrize("key,value", [
    ("network", "online"),      # legacy word: enables network
    ("network", "offline"),     # legacy word: disables network
    ("root", "online"),         # legacy word is NOT valid for root -> must stay false
    ("root", "offline"),        # ditto
    ("network", "true"), ("network", "false"),
    ("root", "true"), ("root", "false"),
    ("network", "TRUE"), ("root", "  yes  "),   # case-fold + edge-trim
    ("root", "t rue"),          # interior space -> unrecognized -> false (fail closed)
    ("network", "on line"),     # ditto
    ("network", "1"), ("root", "0"), ("root", "on"), ("network", "off"),
    ("root", "garbage"), ("network", ""),
])
def test_bash_and_python_parsers_agree(tmp_path, key, value):
    """The bash conf_bool in tests.sh and the Python parser in _testmodes.py MUST read an identical
    file identically -- otherwise `bash tests.sh` and a bare `pytest` disagree on which tiers run,
    and (worse) a toggle of one pair rewrites the OTHER pair to the bash reading. This guards the
    exact divergences an earlier review found: `online` wrongly enabling `root`, and interior-space
    values (`t rue`) failing OPEN in bash while Python fails closed."""
    import re
    conf = tmp_path / "test_modes.conf"
    conf.write_text(f"{key} = {value}\n")

    # Extract the canonical conf_bool() function body from tests.sh and run it against this conf.
    sh = TESTS_SH.read_text()
    m = re.search(r"^conf_bool\(\) \{.*?^\}", sh, re.MULTILINE | re.DOTALL)
    assert m, "conf_bool() must be defined in tests.sh"
    script = f'MODESCONF="{conf}"\n{m.group(0)}\nconf_bool {key}\n'
    bash_out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=15)
    bash_res = bash_out.stdout.strip()
    assert bash_res in ("true", "false"), (bash_out.stdout, bash_out.stderr)

    # Python side: point _testmodes at this conf and read the same key. Env vars must NOT interfere.
    import _testmodes
    old = _testmodes.CONFIG_PATH
    env_keys = (_testmodes.ENV_NETWORK, _testmodes.ENV_ROOT)
    saved_env = {k: __import__("os").environ.pop(k, None) for k in env_keys}
    try:
        _testmodes.CONFIG_PATH = conf
        py_res = "true" if (_testmodes.network_enabled() if key == "network"
                            else _testmodes.root_enabled()) else "false"
    finally:
        _testmodes.CONFIG_PATH = old
        for k, v in saved_env.items():
            if v is not None:
                __import__("os").environ[k] = v
    assert bash_res == py_res, f"parser divergence on {key}={value!r}: bash={bash_res} python={py_res}"


def _bash_conf_bool(conf_path, key):
    """Run the canonical conf_bool() extracted from tests.sh against a conf file, return true/false."""
    import re
    sh = TESTS_SH.read_text()
    m = re.search(r"^conf_bool\(\) \{.*?^\}", sh, re.MULTILINE | re.DOTALL)
    assert m, "conf_bool() must be defined in tests.sh"
    script = f'MODESCONF="{conf_path}"\n{m.group(0)}\nconf_bool {key}\n'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=15)
    assert out.stdout.strip() in ("true", "false"), (out.stdout, out.stderr)
    return out.stdout.strip()


def _py_read(conf_path, key):
    """Read one mode from _testmodes pointed at conf_path, isolated from env overrides."""
    import os as _os
    import _testmodes
    old = _testmodes.CONFIG_PATH
    saved = {k: _os.environ.pop(k, None) for k in (_testmodes.ENV_NETWORK, _testmodes.ENV_ROOT)}
    try:
        _testmodes.CONFIG_PATH = conf_path
        return "true" if (_testmodes.network_enabled() if key == "network"
                          else _testmodes.root_enabled()) else "false"
    finally:
        _testmodes.CONFIG_PATH = old
        for k, v in saved.items():
            if v is not None:
                _os.environ[k] = v


@pytest.mark.parametrize("key,raw,label", [
    # Exotic-whitespace / encoding cases an earlier review used to break parser agreement. Written as
    # RAW BYTES so we can inject NBSP (U+00A0), form-feed, vertical tab, CRLF, and a stray non-UTF-8
    # byte -- the exact inputs where Python's Unicode str.strip()/splitlines() diverged from bash's
    # ASCII [[:space:]] + line-oriented grep. All must AGREE, and none may crash the Python parser.
    ("network", b"network = \xc2\xa0true\n", "nbsp-leading"),
    ("network", b"network = true\xc2\xa0\n", "nbsp-trailing"),
    ("root",    b"root = \xc2\xa0yes\n", "nbsp-root"),
    ("network", b"network = \x0ctrue\n", "form-feed"),
    ("network", b"network = \x0btrue\n", "vertical-tab"),
    ("network", b"network = true\r\n", "crlf"),
    ("network", b"network = true\n\xa0", "invalid-utf8-trailing-byte"),
    ("root",    b"root = true\n\xff\xfe", "invalid-utf8-bom-ish"),
])
def test_bash_and_python_parsers_agree_on_exotic_bytes(tmp_path, key, raw, label):
    """Guards the second divergence class the review found: byte-level / exotic-whitespace inputs.
    A stray non-UTF-8 byte must fail CLOSED in Python (errors='replace'), never raise
    UnicodeDecodeError and take down pytest collection. bash and Python must read identically."""
    conf = tmp_path / "test_modes.conf"
    conf.write_bytes(raw)
    bash_res = _bash_conf_bool(conf, key)
    py_res = _py_read(conf, key)   # must not raise
    assert bash_res == py_res, f"parser divergence on {label} ({key}): bash={bash_res} python={py_res}"


def test_isolated_log_copies_exclude_bulk_dirs():
    # The off-screen log-copy runs mirror the repo into /tmp. output/ (built ISOs) and cache/ (the
    # package cache) are tens of GB; copying them once filled /tmp (a 16G tmpfs), the copy failed on
    # ENOSPC, and the swallow-errors log run left the log EMPTY. Guard that both bulk dirs stay in
    # the exclude list (rsync flags) so that regression can't silently return.
    s = TESTS_SH.read_text()
    assert "--exclude output" in s, "isolated log copies must exclude output/ (multi-GB ISOs)"
    assert "--exclude cache" in s, "isolated log copies must exclude cache/ (multi-GB package cache)"
    # The cp fallback must skip them too (a copy-then-delete would still transit the bulk).
    assert "venv|.git|logs|output|cache)" in s, "cp fallback must also skip the bulk dirs"
