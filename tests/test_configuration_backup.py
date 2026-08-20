"""packages.backup -- OUR home-directory backup (the `backup` command).

`backup` rolls the current user's top-level home folders into one timestamped,
GPG-encrypted archive at ~/backup_<date>.tar.gz.gpg. It SKIPS the ``Ignore``
directory and hidden dot files, and it keeps symlinks AS links (recording where they
point). The app is one flat directory; packages/backup/packaging.py is the ISO build
wiring.

Why these tests matter: like the passwords payload, compiler.py never inspects the
CONTENT of these builders -- it blindly iterates emit_plan() and calls emit.write_text
with the (dest, mode) each entry declares. So the declarative plan + the launcher text
ARE the build contract, and the SELECTION rules (what gets archived) + the symlink
handling ARE the behavioural contract. A wrong mode makes the launcher non-executable;
a launcher that does not cd into LIB_DIR breaks the entry's sibling imports; a
selection that follows symlinks or grabs dot files silently backs up the wrong bytes.
None of that raises on its own. These tests pin:

  * the emit_plan() dest/mode entries + that it does not mutate module state,
  * the launcher (execs `python backup.py "$@"` from the install dir, executable),
  * the flat-package ship contract (every runtime module installs into LIB_DIR; the
    build wiring does NOT ship, and the unit tests live in tests/ anyway),
  * the SELECTION rules from the distribution PROMPT (skip ``Ignore``, skip dot files,
    keep symlinks as links, resolve HOME dynamically, output name/location),
  * that gnupg (the app's system-binary dep) is in the manifest,
  * that the compiler actually wires the package in.
"""

from __future__ import annotations

import ast
import inspect
import os
import tarfile
import tempfile

import compiler
import pacman
import paths
import profile
from packages.backup import packaging as bk
from packages.backup import backup as app
from packages.backup import archive as arch


# --- emit_plan() contract ---------------------------------------------------
EXPECTED_KEY_PLAN = {
    "/usr/local/lib/azarch-backup/backup.py": 0o644,
    "/usr/local/lib/azarch-backup/unpack.py": 0o644,
    "/usr/local/lib/azarch-backup/archive.py": 0o644,
    "/usr/local/bin/backup": 0o755,
    "/usr/local/bin/unpack": 0o755,
}


def test_emit_plan_dest_mode_table():
    """The declarative (dest -> mode) entries compiler.py iterates. The launcher MUST be
    executable (0o755) so typing `backup` runs it; every module is plain data (0o644, run
    through the launcher's python). Pin the key entries + the two structural rules: every
    non-launcher entry is a 0o644 .py under LIB_DIR, and the build wiring never ships."""
    got = {e["dest"]: e["mode"] for e in bk.emit_plan()}
    launchers = {bk.LAUNCHER_SYSTEM_PATH, bk.UNPACK_LAUNCHER_SYSTEM_PATH}
    for dest, mode in EXPECTED_KEY_PLAN.items():
        assert got.get(dest) == mode, dest
    for dest, mode in got.items():
        if dest in launchers:
            assert mode == 0o755, dest
        else:
            assert dest.startswith(bk.LIB_DIR + "/") and dest.endswith(".py"), dest
            assert mode == 0o644, dest
    assert f"{bk.LIB_DIR}/packaging.py" not in got
    assert not any(d.rsplit("/", 1)[-1].startswith("test_") for d in got)


def test_emit_plan_builders_are_callable_and_nonempty():
    """Every entry's builder returns real content (compiler.py calls builder())."""
    for e in bk.emit_plan():
        content = e["builder"]()
        assert isinstance(content, str) and content.strip(), e["dest"]


def test_emit_plan_is_pure():
    """compiler.py may call emit_plan() more than once; it must not mutate module state or
    return aliased dicts a caller could mutate. Mirrors the passwords test."""
    a = bk.emit_plan()
    b = bk.emit_plan()
    assert a == b
    a[0]["mode"] = 0o000  # mutate the returned copy
    assert bk.emit_plan()[0]["mode"] == 0o644  # module PLAN unaffected


def test_dest_paths_are_absolute_system_paths():
    """All root-owned absolute paths under /usr/local (the OFFLINE install rsyncs the live
    rootfs, so no per-user home entry is needed -- the command is on PATH for every user)."""
    for e in bk.emit_plan():
        assert e["dest"].startswith("/usr/local/"), e["dest"]


def test_launcher_name_is_the_backup_command():
    """The command the user types is literally `backup`: the launcher installs to
    /usr/local/bin/backup (on PATH)."""
    assert bk.LAUNCHER_SYSTEM_PATH == "/usr/local/bin/backup"
    plan = {e["dest"]: e for e in bk.emit_plan()}
    assert bk.LAUNCHER_SYSTEM_PATH in plan
    assert plan[bk.LAUNCHER_SYSTEM_PATH]["mode"] == 0o755  # must be executable


# --- launcher ---------------------------------------------------------------
def test_launcher_execs_python_entry_from_install_dir():
    """The `backup` launcher cd's into the install dir (so the entry's sibling imports
    resolve) and execs the system python on backup.py, forwarding arguments so
    `backup --help` reaches the script. `exec` so the python process replaces the shell."""
    sh = bk.launcher_sh()
    assert sh.startswith("#!/bin/sh")
    assert f"cd '{bk.LIB_DIR}'" in sh
    assert 'exec python -u backup.py "$@"' in sh


def test_unpack_launcher_execs_python_entry_from_install_dir():
    """The `unpack` launcher is the twin of the `backup` one: same cd into LIB_DIR (so the
    shared `import archive` resolves) but execs unpack.py, forwarding the archive argument
    (`unpack backup.tar.gz.gpg`)."""
    sh = bk.unpack_launcher_sh()
    assert sh.startswith("#!/bin/sh")
    assert f"cd '{bk.LIB_DIR}'" in sh
    assert 'exec python -u unpack.py "$@"' in sh


def test_unpack_launcher_name_is_the_unpack_command():
    """The restore command the user types is literally `unpack`: its launcher installs to
    /usr/local/bin/unpack (on PATH), executable."""
    assert bk.UNPACK_LAUNCHER_SYSTEM_PATH == "/usr/local/bin/unpack"
    plan = {e["dest"]: e for e in bk.emit_plan()}
    assert bk.UNPACK_LAUNCHER_SYSTEM_PATH in plan
    assert plan[bk.UNPACK_LAUNCHER_SYSTEM_PATH]["mode"] == 0o755


# --- the flat-package ship contract -----------------------------------------
def test_flat_app_ships_every_module_beside_the_entry_script():
    """The app is one flat directory: the entry script (and any module it grows) install
    side by side in LIB_DIR. Pin that emit_plan() ships each source module into LIB_DIR,
    and that the entry script's own install dir is LIB_DIR."""
    shipped = {e["dest"] for e in bk.emit_plan()}
    for p in paths.BACKUP_DIR.iterdir():
        if p.is_file() and p.suffix == ".py" and p.name != "packaging.py":
            assert f"{bk.LIB_DIR}/{p.name}" in shipped, p.name
    assert bk.ENTRY_SYSTEM_PATH.startswith(bk.LIB_DIR + "/")


def test_shipped_modules_parse_as_python():
    """Defense-in-depth: every shipped module is syntactically valid Python (they are copied
    verbatim and run on the target, so a syntax error would only surface there)."""
    for e in bk.emit_plan():
        if e["dest"].endswith(".py"):
            ast.parse(e["builder"](), filename=e["dest"])


# --- the compiler actually WIRES the package in (seam coverage) -------------
def test_compiler_emit_desktop_wires_backup_in():
    """Guard the compiler-to-package SEAM: the package's contract can be perfect while
    compiler.py forgets to invoke it, shipping an ISO where `backup` is missing entirely."""
    src = inspect.getsource(compiler._emit_desktop)
    assert "backup.emit_plan()" in src
    assert "from packages.backup import packaging as backup" in inspect.getsource(compiler)


def test_backup_is_excluded_from_auto_app_discovery():
    """`backup` is emitted BY NAME in _emit_desktop, so it must be in _EXPLICIT_PACKAGES or
    the app-loop discovery would emit it a SECOND time (duplicate writes)."""
    assert "backup" in compiler._EXPLICIT_PACKAGES


# --- runtime dependency is in the manifest ----------------------------------
def test_gnupg_is_in_the_manifest():
    """The app shells out to `gpg` (gnupg) to encrypt the archive; it must be shipped or the
    command is installed but non-functional. Tokenize the manifest exactly as the build does."""
    text = paths.PACKAGES_FILE.read_text()
    toks = [tok for line in text.splitlines()
            if (tok := line.split("#", 1)[0].strip())]
    assert "gnupg" in toks


# --- the SELECTION rules (the distribution PROMPT's explicit requirements) ---
def _make_home(tmp_path):
    """Build a fake HOME with dirs, dot files, an Ignore dir, a Vault dir, and a symlink."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "Documents").mkdir()
    (home / "Documents" / "note.txt").write_text("hi")
    (home / "Pictures").mkdir()
    (home / "Ignore").mkdir()
    (home / "Ignore" / "junk.bin").write_text("junk")
    (home / "Vault").mkdir()            # holds the password store -> its own archive
    (home / "Vault" / "passwords.txt.gpg").write_text("ENCRYPTED")
    (home / ".config").mkdir()          # hidden dir -> skipped
    (home / ".bashrc").write_text("x")  # hidden file -> skipped
    (home / "Link").symlink_to(home / "Documents")  # symlink -> kept as a link
    return home


def test_select_entries_skips_ignore_and_dot_files_keeps_the_rest(tmp_path):
    """The PROMPT: back up all top-level home entries EXCEPT the ``Ignore`` directory and
    EXCEPT hidden dot files/dirs. Symlinks ARE included in the selection. The ``Vault``
    dir is also excluded -- the password store has its OWN archive (see below)."""
    home = _make_home(tmp_path)
    selected = app.select_entries(str(home))
    assert "Documents" in selected
    assert "Pictures" in selected
    assert "Link" in selected           # the symlink is selected...
    assert "Ignore" not in selected     # ...but the Ignore dir is not,
    assert "Vault" not in selected      # ...nor the Vault dir (own archive),
    assert ".config" not in selected    # ...and dot files/dirs are not.
    assert ".bashrc" not in selected


def test_vault_dir_is_excluded_from_the_home_archive(tmp_path):
    """The password store lives in ~/Vault and is archived SEPARATELY into
    ~/passwords.tar.gz.gpg, so ~/Vault must NOT be bundled into the home archive too
    (disjoint responsibilities; no double-archiving of the encrypted store). The excluded
    name is derived from VAULT_REL so it cannot drift."""
    assert app.VAULT_DIR_NAME == "Vault"
    assert app.VAULT_REL.split("/", 1)[0] == app.VAULT_DIR_NAME
    home = _make_home(tmp_path)
    assert "Vault" not in app.select_entries(str(home))


def test_ignore_dir_name_is_exactly_Ignore():
    """Pin the ignored directory name so it cannot silently drift (the PROMPT names it
    ``Ignore``)."""
    assert app.IGNORE_DIR_NAME == "Ignore"


def test_home_is_resolved_dynamically_not_hardcoded():
    """The PROMPT: save to ``~`` -- which is /home/main for this user, but 'you never know
    how the user might name their user'. So home_dir() must expand ``~`` at runtime and must
    NOT hard-code /home/main anywhere in the app source."""
    assert app.home_dir() == os.path.expanduser("~")
    src = (paths.BACKUP_DIR / "backup.py").read_text(encoding="utf-8")
    assert "/home/main" not in src


def test_archive_keeps_symlinks_as_links_and_records_target(tmp_path):
    """The PROMPT: 'save the symbolic links and where they point'. Build the real archive of
    a fake home and assert the symlink is stored AS a link (never dereferenced into a copy of
    its target) and that tar recorded its target path (linkname)."""
    home = _make_home(tmp_path)
    entries = app.select_entries(str(home))
    out = tmp_path / "out.tar.gz"
    # Bypass gpg for this test: write the tar stream straight to a file so we can inspect it.
    with tarfile.open(str(out), mode="w:gz") as tar:
        for name in entries:
            tar.add(os.path.join(str(home), name), arcname=name,
                    recursive=True, filter=app._tar_filter)
    with tarfile.open(str(out), mode="r:gz") as tar:
        members = {m.name: m for m in tar.getmembers()}
    link = members["Link"]
    assert link.issym(), "the symlink must be stored AS a symlink, not followed"
    assert link.linkname, "the symlink's target (linkname) must be recorded"


def test_tar_filter_drops_pycache_and_pyc(tmp_path):
    """__pycache__ and compiled Python are never archived (the user hates the clutter and it
    is regenerated). The per-entry filter returns None for them."""
    (tmp_path / "__pycache__").mkdir()
    info = tarfile.TarInfo(name="proj/__pycache__")
    assert app._tar_filter(info) is None
    assert app._tar_filter(tarfile.TarInfo(name="proj/mod.pyc")) is None
    assert app._tar_filter(tarfile.TarInfo(name="proj/mod.py")) is not None


# --- the deliverable: two encrypted archives named/located per the PROMPT ----
def test_output_archives_are_gpg_encrypted_tars_in_home():
    """The PROMPT (step two): `backup` writes TWO fixed-name GPG (AES256) archives into
    HOME -- backup.tar.gz.gpg (the home dirs) and passwords.tar.gz.gpg (the store) -- and
    the date stamp from step one is DROPPED (the deliverables are named exactly
    backup.tar.gz.gpg / passwords.tar.gz.gpg so `unpack` can recognise them)."""
    assert app.HOME_ARCHIVE_NAME == "backup.tar.gz.gpg"
    assert app.PASSWORDS_ARCHIVE_NAME == "passwords.tar.gz.gpg"
    src = (paths.BACKUP_DIR / "archive.py").read_text(encoding="utf-8")
    assert "--symmetric" in src and "AES256" in src   # GPG symmetric AES256 (shared helper)
    bsrc = (paths.BACKUP_DIR / "backup.py").read_text(encoding="utf-8")
    # Both outputs are joined onto the resolved HOME (os.path.join(home, ...)); no _<date>.
    assert "os.path.join(home, HOME_ARCHIVE_NAME)" in bsrc
    assert "os.path.join(home, PASSWORDS_ARCHIVE_NAME)" in bsrc
    assert "backup_" not in app.HOME_ARCHIVE_NAME     # the step-one date stamp is gone


def test_passphrase_is_never_passed_on_the_command_line():
    """Defense-in-depth: the passphrase must reach gpg over a private fd / stdin, never as
    an argv token (which would leak it into the process list). The gpg commands now live in
    the shared archive.py, so parse THAT source and inspect the actual argv list literals
    rather than substring-scanning prose (a mention of the flag in a comment can't trip or
    hide this). The safe fd form is allowed; the plaintext argv forms
    (`--passphrase <value>` / `--passphrase=<value>`) must be entirely absent from BOTH the
    helper and the two entry scripts."""
    for name in ("archive.py", "backup.py", "unpack.py"):
        src = (paths.BACKUP_DIR / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        argv_strings = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.List):
                for elt in node.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        argv_strings.add(elt.value)
        assert "--passphrase" not in argv_strings, name         # bare flag + value arg
        assert not any(s.startswith("--passphrase=") for s in argv_strings), name
    # The shared helper is where the safe fd form must actually appear.
    assert "--passphrase-fd" in (paths.BACKUP_DIR / "archive.py").read_text(encoding="utf-8")


# --- the two-archive behaviour + vault handling (the step-two contract) ------
# These build REAL gpg archives (gpg is the app's declared dep and is on the test host),
# so they exercise the actual encrypt/decrypt path, not just the source text.
import shutil  # noqa: E402  (local to the behavioural block below)

_PASS = "correct horse battery staple"


def _has_gpg():
    return shutil.which("gpg") is not None


def _make_vault(home, passphrase, plaintext="site\tsecret\n"):
    """Create a REAL gpg-encrypted ~/Vault/passwords.txt.gpg for `home`."""
    vault = os.path.join(str(home), "Vault")
    os.makedirs(vault, exist_ok=True)
    plain = os.path.join(vault, "passwords.txt")
    with open(plain, "w") as handle:
        handle.write(plaintext)
    store = os.path.join(vault, "passwords.txt.gpg")
    assert arch.gpg_encrypt_file(plain, store, passphrase), "vault setup failed"
    os.remove(plain)
    return store


def test_backup_produces_two_archives_when_vault_passphrase_matches(tmp_path):
    """The PROMPT (step two): one prompt, BOTH ~/backup.tar.gz.gpg and
    ~/passwords.tar.gz.gpg are produced when the entered passphrase unlocks the vault
    store. Uses the real gpg path via the module functions (no monkeypatched prompt)."""
    if not _has_gpg():
        import pytest
        pytest.skip("gpg not installed on the test host")
    home = _make_home(tmp_path)
    _make_vault(home, _PASS)
    entries = app.select_entries(str(home))

    home_out = os.path.join(str(home), app.HOME_ARCHIVE_NAME)
    assert app.build_home_archive(str(home), entries, home_out, _PASS)
    assert os.path.exists(home_out)

    pw_out = os.path.join(str(home), app.PASSWORDS_ARCHIVE_NAME)
    assert app.build_passwords_archive(str(home), _PASS, pw_out) == "ok"
    assert os.path.exists(pw_out)


def test_passwords_archive_holds_the_DECRYPTED_store_and_round_trips(tmp_path):
    """The PROMPT: if the passphrase decrypts the vault, the passwords archive is built
    from the DECRYPTED contents so the user can reach their actual passwords again. Pin
    that the archive carries ``Vault/passwords.txt`` (the plaintext arcname) and that the
    original plaintext round-trips out of it."""
    if not _has_gpg():
        import pytest
        pytest.skip("gpg not installed on the test host")
    secret = "gmail\thunter2\nbank\tswordfish\n"
    home = _make_home(tmp_path)
    _make_vault(home, _PASS, plaintext=secret)
    pw_out = os.path.join(str(home), app.PASSWORDS_ARCHIVE_NAME)
    assert app.build_passwords_archive(str(home), _PASS, pw_out) == "ok"

    # Decrypt the passwords archive and confirm it contains the plaintext store verbatim.
    got = {}

    def _collect(tar, _dest):
        for member in tar:
            if member.isfile():
                got[member.name] = tar.extractfile(member).read().decode("utf-8")

    assert arch.gpg_decrypt_stream(pw_out, _PASS, str(tmp_path), _collect)
    assert "Vault/passwords.txt" in got, "the DECRYPTED store must be the archived member"
    assert got["Vault/passwords.txt"] == secret


def test_backup_skips_passwords_when_passphrase_does_not_match_vault(tmp_path):
    """The PROMPT: a wrong master password must NOT fail the run -- the home archive is
    still made and the passwords store is skipped with a warning. build_passwords_archive
    returns "mismatch" (not a raise, not "ok") and writes no passwords archive."""
    if not _has_gpg():
        import pytest
        pytest.skip("gpg not installed on the test host")
    home = _make_home(tmp_path)
    _make_vault(home, _PASS)
    pw_out = os.path.join(str(home), app.PASSWORDS_ARCHIVE_NAME)
    assert app.build_passwords_archive(str(home), "the WRONG passphrase", pw_out) == "mismatch"
    assert not os.path.exists(pw_out)


def test_backup_skips_passwords_when_vault_is_absent(tmp_path):
    """The PROMPT: if ~/Vault/passwords.txt.gpg does not exist, skip the passwords archive
    gracefully -- never crash. build_passwords_archive returns "missing"."""
    home = _make_home(tmp_path)  # _make_home writes a placeholder store; remove it
    os.remove(os.path.join(str(home), "Vault", "passwords.txt.gpg"))
    pw_out = os.path.join(str(home), app.PASSWORDS_ARCHIVE_NAME)
    assert app.build_passwords_archive(str(home), _PASS, pw_out) == "missing"
    assert not os.path.exists(pw_out)


def test_selection_excludes_our_own_deliverables_so_reruns_dont_self_include(tmp_path):
    """Re-running `backup` must not archive the PREVIOUS run's output: the two deliverables
    (backup.tar.gz.gpg / passwords.tar.gz.gpg) live at the top level of HOME, so they are
    excluded from the selection. Otherwise each run would nest and grow the last run's
    archives."""
    home = _make_home(tmp_path)
    # Simulate a previous run's leftovers sitting in HOME.
    (home / app.HOME_ARCHIVE_NAME).write_bytes(b"OLD-HOME-ARCHIVE")
    (home / app.PASSWORDS_ARCHIVE_NAME).write_bytes(b"OLD-PW-ARCHIVE")
    selected = app.select_entries(str(home))
    assert app.HOME_ARCHIVE_NAME not in selected
    assert app.PASSWORDS_ARCHIVE_NAME not in selected


def _run_backup_main(home, passphrase):
    """Invoke app.main([]) with HOME set and the (confirm) prompt fed `passphrase` twice.
    Patches app.archive.prompt_passphrase -- the exact object the entry calls through (the
    flat app imports its sibling as top-level ``archive``, not packages.backup.archive)."""
    responses = [passphrase, passphrase]

    def fake_prompt(confirm=True):
        return responses.pop(0) if confirm else responses.pop(0)

    old_home = os.environ.get("HOME")
    old_prompt = app.archive.prompt_passphrase
    os.environ["HOME"] = str(home)
    app.archive.prompt_passphrase = fake_prompt
    try:
        return app.main([])
    finally:
        app.archive.prompt_passphrase = old_prompt
        if old_home is not None:
            os.environ["HOME"] = old_home


def test_backup_still_makes_passwords_archive_when_home_has_no_backable_dirs(tmp_path):
    """Regression: a user whose only backable thing is their password store (home has just
    hidden files / Ignore / Vault, no top-level dirs) must STILL get passwords.tar.gz.gpg.
    An earlier empty-selection early-return skipped it. main() must return 0 and produce the
    passwords archive (and no home archive, since there was nothing to put in it)."""
    if not _has_gpg():
        import pytest
        pytest.skip("gpg not installed on the test host")
    home = tmp_path / "sparse"
    home.mkdir()
    (home / ".bashrc").write_text("x")   # hidden -> not backable
    (home / "Ignore").mkdir()            # skipped
    _make_vault(home, _PASS)             # the ONLY thing to back up
    assert app.select_entries(str(home)) == []  # nothing for the home archive
    rc = _run_backup_main(home, _PASS)
    assert rc == 0
    assert os.path.exists(os.path.join(str(home), app.PASSWORDS_ARCHIVE_NAME))
    assert not os.path.exists(os.path.join(str(home), app.HOME_ARCHIVE_NAME))


def test_backup_bails_out_only_when_nothing_at_all_to_do(tmp_path):
    """When there are no backable home dirs AND no password store, main() prints a note and
    returns 0 without producing anything (and without prompting)."""
    home = tmp_path / "empty"
    home.mkdir()
    (home / ".bashrc").write_text("x")
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        assert app.main([]) == 0
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
    assert not os.path.exists(os.path.join(str(home), app.HOME_ARCHIVE_NAME))
    assert not os.path.exists(os.path.join(str(home), app.PASSWORDS_ARCHIVE_NAME))


def test_shred_dir_removes_nested_dirs_and_files(tmp_path):
    """archive.shred_dir must fully clean the scratch dir -- including NESTED dirs like
    ``<tmp>/Vault`` where the decrypted store plaintext lives -- leaving no skeleton behind
    (an earlier version only rmdir'd the top dir, leaking empty ``Vault/`` dirs in /tmp)."""
    scratch = tmp_path / "scratch"
    (scratch / "Vault").mkdir(parents=True)
    (scratch / "Vault" / "passwords.txt").write_text("plaintext secret")
    (scratch / "top.txt").write_text("x")
    arch.shred_dir(str(scratch))
    assert not scratch.exists(), "scratch dir (and its nested Vault/) must be fully removed"


def test_shred_dir_handles_a_symlink_to_a_directory_in_the_scratch(tmp_path):
    """Defence-in-depth: a symlink whose target is a directory sitting in the scratch dir
    (os.walk buckets it under `dirs`) must be unlinked, not rmdir'd, so it does not leave a
    skeleton that blocks removal -- and the link is NEVER followed, so its target outside the
    scratch survives untouched."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    outside = tmp_path / "outside_target"
    outside.mkdir()
    (outside / "keep.txt").write_text("must survive")
    (scratch / "link_to_dir").symlink_to(outside)  # link-to-directory inside the scratch
    (scratch / "plain.txt").write_text("secret")
    arch.shred_dir(str(scratch))
    assert not scratch.exists(), "scratch must be fully removed even with a dir-symlink in it"
    assert (outside / "keep.txt").read_text() == "must survive"  # target not followed/deleted


def test_home_archive_arcnames_are_home_relative(tmp_path):
    """`unpack backup.tar.gz.gpg` restores into ~/ only because the home archive uses
    home-relative arcnames (``Documents/...``, never ``/home/<user>/...``). Build the real
    archive and assert every member path is relative and none is absolute."""
    if not _has_gpg():
        import pytest
        pytest.skip("gpg not installed on the test host")
    home = _make_home(tmp_path)
    entries = app.select_entries(str(home))
    out = os.path.join(str(home), app.HOME_ARCHIVE_NAME)
    assert app.build_home_archive(str(home), entries, out, _PASS)
    names = []

    def _names(tar, _dest):
        names.extend(m.name for m in tar)

    assert arch.gpg_decrypt_stream(out, _PASS, str(tmp_path), _names)
    assert names, "archive is empty"
    assert all(not n.startswith("/") for n in names), names
    assert any(n.startswith("Documents") for n in names), names


# --- bug #1: the launchers must ship EXECUTABLE on the ISO -------------------
def test_backup_and_unpack_launchers_stay_executable_on_iso():
    """Regression guard for last build's bug #1 ("backup: command not found even by full
    path"): archiso's squashfs normalises overlay file modes to 0644 unless the path is
    pinned in profile.FILE_PERMISSIONS. emit_plan() marks both launchers 0o755, but that is
    lost in the squashfs without these entries -- so a 0644 launcher cannot be exec'd and the
    command is dead on the ISO and the installed system. Pin both /usr/local/bin/backup and
    /usr/local/bin/unpack to 0:0:755 (mirrors the passwords launcher fix)."""
    for launcher in (bk.LAUNCHER_SYSTEM_PATH, bk.UNPACK_LAUNCHER_SYSTEM_PATH):
        assert profile.FILE_PERMISSIONS.get(launcher) == "0:0:755", launcher
        assert f'["{launcher}"]="0:0:755"' in profile.profiledef_sh(), launcher


# --- bug #2: reclaim the `backup` name from GNU tar -------------------------
def test_tar_backup_and_restore_are_suppressed_by_overrides():
    """Regression guard for last build's bug #2 (typing `backup` ran GNU tar's
    /usr/bin/backup instead of ours). We KEEP the name and REMOVE tar's copies: both
    usr/bin/backup and usr/bin/restore must be suppress-only ISO_APP_OVERRIDES (basename
    None, remove True) so pacstrap NoExtracts them and the post-pacstrap hook rm -f's them.
    We do NOT reorder PATH."""
    overrides = {target: (basename, remove)
                 for basename, target, remove in pacman.ISO_APP_OVERRIDES}
    for target in ("/usr/bin/backup", "/usr/bin/restore"):
        assert target in overrides, target
        basename, remove = overrides[target]
        assert basename is None and remove is True, target
    # NoExtract must cover both (so pacstrap never lays tar's scripts down)...
    for conf in (pacman.build_profile_conf(), pacman.installer_pacstrap_conf()):
        noextract = next(l for l in conf.splitlines() if l.startswith("NoExtract   ="))
        assert "usr/bin/backup" in noextract
        assert "usr/bin/restore" in noextract
    # ...and the post-pacstrap hook must rm -f both (belt-and-braces), on live + /mnt.
    live = pacman.app_override_cp_sh()
    assert "rm -f /usr/bin/backup" in live
    assert "rm -f /usr/bin/restore" in live
    assert "rm -f /mnt/usr/bin/restore" in pacman.app_override_cp_sh("/mnt")
