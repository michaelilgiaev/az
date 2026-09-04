"""Contract tests for tests.sh: the test-mode toggles, --help, marker registration, and the
env-export wiring the isolated log runs depend on. Mirrors the sibling Coder suite's
test_tests_sh.py so both distributions enforce the same standard."""
import re
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


# --- Local (gitignored) conf: auto-create-if-missing, never-clobber -------------------------
# tests/test_modes.conf is LOCAL per-machine state (gitignored, NOT committed). tests.sh must
# CREATE it (both false) on first run when it is missing, and otherwise leave it byte-identical.
# We exercise the actual auto-create block extracted from tests.sh against a TEMP path, so the
# real repo's conf is never touched and no venv/pytest is built.

def _autocreate_snippet(conf_path):
    """The verbatim 'create the conf if missing' block from tests.sh, retargeted at conf_path.

    Extracted (not reimplemented) so this test breaks if the real block's behavior drifts. The
    block is anchored between the `MODESCONF=` assignment and the `conf_bool()` definition."""
    sh = TESTS_SH.read_text()
    m = re.search(r'^if \[ ! -f "\$MODESCONF" \]; then\n(?:.*\n)*?^fi$', sh, re.MULTILINE)
    assert m, "the auto-create `if [ ! -f \"$MODESCONF\" ]` block must exist in tests.sh"
    return f'MODESCONF="{conf_path}"\n{m.group(0)}\n'


def test_missing_conf_is_created_with_both_false(tmp_path):
    conf = tmp_path / "sub" / "test_modes.conf"   # parent missing too: block must mkdir -p
    assert not conf.exists()
    r = subprocess.run(["bash", "-c", _autocreate_snippet(conf)],
                       capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, r.stderr
    assert conf.exists(), "a missing conf must be auto-created"
    assert conf.read_text() == "network = false\nroot = false\n"


def test_existing_conf_is_not_clobbered(tmp_path):
    conf = tmp_path / "test_modes.conf"
    original = "network = true\nroot = true\n"   # a NON-default value the block must preserve
    conf.write_text(original)
    r = subprocess.run(["bash", "-c", _autocreate_snippet(conf)],
                       capture_output=True, text=True, timeout=15)
    assert r.returncode == 0, r.stderr
    assert conf.read_text() == original, "an existing conf must be left byte-identical"


def test_modes_conf_is_gitignored_not_tracked():
    # The conf is local state now: it must NOT be a tracked file, and git must ignore it.
    import subprocess as sp
    tracked = sp.run(["git", "ls-files", "--error-unmatch", "tests/test_modes.conf"],
                     cwd=str(REPO), capture_output=True, text=True)
    assert tracked.returncode != 0, "tests/test_modes.conf must NOT be tracked by git (it is local state)"
    ignored = sp.run(["git", "check-ignore", "tests/test_modes.conf"],
                     cwd=str(REPO), capture_output=True, text=True)
    assert ignored.returncode == 0 and ignored.stdout.strip(), \
        "tests/test_modes.conf must be gitignored"


# --- Root tier demands sudo -----------------------------------------------------------------
# With the root tier ENABLED, a plain `bash tests.sh` (non-root) must STOP and ask for sudo,
# instead of quietly skipping the root-marked tests. We drive the ACTUAL guard block extracted
# from tests.sh (needs conf_bool too), so the test tracks the real logic and needs no venv. The
# pytest process is non-root, so the `id -u != 0` arm holds naturally; the AZARCH_ALLOW_NONROOT
# escape hatch is the seam that lets a non-root run proceed past the guard.

# The mode env vars the guard consults. A guard test must run in a HERMETIC environment: when
# this suite itself is launched via `bash tests.sh`, the parent EXPORTS AZARCH_TESTS_ROOT (and
# friends), which would otherwise leak in and override the temp conf the test wrote. _run_guard
# strips all three and re-applies only what the test asks for.
_GUARD_ENV_VARS = ("AZARCH_TESTS_ROOT", "AZARCH_TESTS_NETWORK", "AZARCH_ALLOW_NONROOT")


def _guard_snippet(conf_path, args=""):
    """conf_bool() + the root-sudo guard block from tests.sh, retargeted at conf_path. The mode
    env vars are supplied by the caller via a sanitized env (see _run_guard), NOT exported here,
    so an inherited AZARCH_TESTS_ROOT cannot leak in. Echoes PASSED_GUARD if the guard let the
    run continue (so a test can distinguish 'passed' from 'refused with exit 1')."""
    sh = TESTS_SH.read_text()
    cb = re.search(r"^conf_bool\(\) \{.*?^\}", sh, re.MULTILINE | re.DOTALL)
    assert cb, "conf_bool() must be defined in tests.sh"
    guard = re.search(r'^# --- Root tier demands sudo\..*?^fi$', sh, re.MULTILINE | re.DOTALL)
    assert guard, "the root-sudo guard block must exist in tests.sh"
    prelude = f'MODESCONF="{conf_path}"\nset --{(" " + args) if args else ""}\n'
    return prelude + cb.group(0) + "\n" + guard.group(0) + '\necho PASSED_GUARD\n'


def _run_guard(tmp_path, conf_text, root_env=None, allow_nonroot=None, args=""):
    """Write conf_text to a temp conf and run the extracted guard against it in a HERMETIC env
    (all inherited mode vars stripped). root_env sets AZARCH_TESTS_ROOT; allow_nonroot sets
    AZARCH_ALLOW_NONROOT -- only when the test passes them, so the conf is the sole other input."""
    import os
    conf = tmp_path / "test_modes.conf"
    conf.write_text(conf_text)
    env = {k: v for k, v in os.environ.items() if k not in _GUARD_ENV_VARS}
    if root_env is not None:
        env["AZARCH_TESTS_ROOT"] = root_env
    if allow_nonroot is not None:
        env["AZARCH_ALLOW_NONROOT"] = allow_nonroot
    return subprocess.run(["bash", "-c", _guard_snippet(conf, args=args)],
                          capture_output=True, text=True, timeout=15, env=env)


@pytest.mark.skipif(__import__("os").geteuid() == 0,
                    reason="guard's refusal path is for NON-root; this process is root")
def test_root_mode_without_sudo_is_refused(tmp_path):
    r = _run_guard(tmp_path, "network = false\nroot = true\n")
    assert r.returncode == 1, (r.stdout, r.stderr)
    assert "PASSED_GUARD" not in r.stdout, "the guard must STOP the run, not fall through"
    assert "not root" in r.stderr and "sudo bash tests.sh" in r.stderr
    assert "bash tests.sh --user" in r.stderr, "the refusal must point at the --user off-switch"


# Every truthy spelling the Python reader (_testmodes._as_bool, which lowercases) accepts must
# ALSO trip the guard -- otherwise the guard reads the env value as false and waves the run
# through while pytest's conftest, reading the SAME var, selects the root tier and the tests
# silently self-skip. The mixed/upper-case entries (TRUE, Yes, ON) are the exact regression an
# adversarial review found: the guard's `case` did not case-fold while Python does.
@pytest.mark.skipif(__import__("os").geteuid() == 0,
                    reason="guard's refusal path is for NON-root; this process is root")
@pytest.mark.parametrize("root_env", [
    "true", "TRUE", "True", "tRuE", "1", "yes", "Yes", "YES", "on", "ON",
    " true ", "\ttrue\t", "true\n",   # surrounding ASCII whitespace: Python _ascii_strip trims it
])                                     # truthy, so the guard MUST too (a `$(cmd)` capture yields \n)
def test_root_env_truthy_without_sudo_is_refused(tmp_path, root_env):
    # Env override alone (conf says root=false) must also trigger the demand -- env wins, and it
    # must do so for ANY casing/spelling/whitespace-padding Python treats as truthy, not just a
    # bare lowercase "true". Both the case-fold and the edge-trim in tests.sh's guard are covered.
    r = _run_guard(tmp_path, "network = false\nroot = false\n", root_env=root_env)
    assert r.returncode == 1, (repr(root_env), r.stdout, r.stderr)
    assert "sudo bash tests.sh" in r.stderr


@pytest.mark.parametrize("root_env", ["false", "FALSE", "no", "off", "online", "garbage", ""])
def test_root_env_non_truthy_never_demands_sudo(tmp_path, root_env):
    # The falsey/unrecognized spellings (incl. the network-only word `online`, which must NOT
    # enable root) must leave the guard inert WHEN THE CONF IS ALSO false -- mirroring Python's
    # fail-closed default. (Unrecognized values fall through to the conf; here the conf is false.)
    r = _run_guard(tmp_path, "network = false\nroot = false\n", root_env=root_env)
    assert r.returncode == 0, (root_env, r.stdout, r.stderr)
    assert "PASSED_GUARD" in r.stdout


# The env var must win ONLY when it parses to a real boolean. An UNRECOGNIZED env value (empty,
# whitespace-only, junk, or the network-only word `online`) must ABSTAIN and let the CONF decide --
# exactly as _testmodes.root_enabled() does. The whitespace-only-with-conf-true case is the precise
# divergence an adversarial review found: bash's old `[ -n ]` test treated a blank-but-nonempty
# value as "set" and skipped the conf (reading false), while Python fell through to the conf (true),
# silently skipping the enabled tier. Both engines must now fall through.
@pytest.mark.skipif(__import__("os").geteuid() == 0,
                    reason="guard's refusal path is for NON-root; this process is root")
@pytest.mark.parametrize("root_env", ["", "  ", "\t", "\n", "online", "garbage", "maybe"])
def test_unrecognized_env_falls_through_to_conf_true(tmp_path, root_env):
    # conf says root=true; an unrecognized env value must NOT override it to false -- the guard
    # must still refuse, matching Python (which reads the env as None and falls to the true conf).
    r = _run_guard(tmp_path, "network = false\nroot = true\n", root_env=root_env)
    assert r.returncode == 1, (repr(root_env), r.stdout, r.stderr)
    assert "sudo bash tests.sh" in r.stderr


@pytest.mark.parametrize("root_env", ["", "  ", "\t", "online", "garbage"])
def test_unrecognized_env_falls_through_to_conf_false(tmp_path, root_env):
    # Mirror: conf says root=false; an unrecognized env value falls through to the false conf, so
    # the guard stays inert.
    r = _run_guard(tmp_path, "network = false\nroot = false\n", root_env=root_env)
    assert r.returncode == 0, (repr(root_env), r.stdout, r.stderr)
    assert "PASSED_GUARD" in r.stdout


def test_root_mode_with_escape_hatch_proceeds(tmp_path):
    # AZARCH_ALLOW_NONROOT=1 is the test seam: even root=true + non-root must fall THROUGH the
    # guard (the hermetic suite relies on this). Works whether or not the process is root.
    r = _run_guard(tmp_path, "network = false\nroot = true\n", allow_nonroot="1")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "PASSED_GUARD" in r.stdout, "the escape hatch must let the run continue"
    assert "not root" not in r.stderr


def test_user_mode_never_demands_sudo(tmp_path):
    # root=false: the guard must be inert regardless of UID.
    r = _run_guard(tmp_path, "network = false\nroot = false\n")
    assert r.returncode == 0, (r.stdout, r.stderr)
    assert "PASSED_GUARD" in r.stdout


def test_root_toggle_flag_never_demands_sudo(_preserve_modesconf):
    # Flipping the switch (`--root`) must ALWAYS work, even as a non-root user -- the demand is
    # only for actually RUNNING the suite. The toggle exits 0 well before the guard.
    r = _run_toggle("--root")
    assert r.returncode == 0, r.stderr
    combined = r.stdout + r.stderr
    assert "root=true" in combined
    assert "needs administrator rights" not in combined and "not root" not in combined


def test_help_never_demands_sudo_even_with_root_enabled(_preserve_modesconf):
    # `--help` short-circuits before any mode resolution, so even root=true must not gate it.
    MODESCONF.write_text("network = false\nroot = true\n")
    r = _run_toggle("--help")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "Usage:" in out
    assert "not root" not in out and "needs administrator rights" not in out


def test_usage_documents_the_root_sudo_demand():
    # The house rule: --help must EXPLAIN the sudo behavior so it is discoverable.
    r = _run_toggle("--help")
    out = r.stdout + r.stderr
    assert "sudo" in out, "usage must mention the root tier's sudo requirement"


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
