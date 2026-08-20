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

import compiler
import paths
from packages.backup import packaging as bk
from packages.backup import backup as app


# --- emit_plan() contract ---------------------------------------------------
EXPECTED_KEY_PLAN = {
    "/usr/local/lib/azarch-backup/backup.py": 0o644,
    "/usr/local/bin/backup": 0o755,
}


def test_emit_plan_dest_mode_table():
    """The declarative (dest -> mode) entries compiler.py iterates. The launcher MUST be
    executable (0o755) so typing `backup` runs it; every module is plain data (0o644, run
    through the launcher's python). Pin the key entries + the two structural rules: every
    non-launcher entry is a 0o644 .py under LIB_DIR, and the build wiring never ships."""
    got = {e["dest"]: e["mode"] for e in bk.emit_plan()}
    for dest, mode in EXPECTED_KEY_PLAN.items():
        assert got.get(dest) == mode, dest
    for dest, mode in got.items():
        if dest == bk.LAUNCHER_SYSTEM_PATH:
            assert mode == 0o755
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
    """The launcher cd's into the install dir (so the entry's sibling imports resolve) and
    execs the system python on backup.py, forwarding arguments so `backup --help` reaches
    the script. `exec` so the python process replaces the shell."""
    sh = bk.launcher_sh()
    assert sh.startswith("#!/bin/sh")
    assert f"cd '{bk.LIB_DIR}'" in sh
    assert 'exec python -u backup.py "$@"' in sh


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
    """Build a fake HOME with dirs, dot files, an Ignore dir, and a symlink; return it."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "Documents").mkdir()
    (home / "Documents" / "note.txt").write_text("hi")
    (home / "Pictures").mkdir()
    (home / "Ignore").mkdir()
    (home / "Ignore" / "junk.bin").write_text("junk")
    (home / ".config").mkdir()          # hidden dir -> skipped
    (home / ".bashrc").write_text("x")  # hidden file -> skipped
    (home / "Link").symlink_to(home / "Documents")  # symlink -> kept as a link
    return home


def test_select_entries_skips_ignore_and_dot_files_keeps_the_rest(tmp_path):
    """The PROMPT: back up all top-level home entries EXCEPT the ``Ignore`` directory and
    EXCEPT hidden dot files/dirs. Symlinks ARE included in the selection."""
    home = _make_home(tmp_path)
    selected = app.select_entries(str(home))
    assert "Documents" in selected
    assert "Pictures" in selected
    assert "Link" in selected           # the symlink is selected...
    assert "Ignore" not in selected     # ...but the Ignore dir is not,
    assert ".config" not in selected    # ...and dot files/dirs are not.
    assert ".bashrc" not in selected


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


# --- the deliverable: an encrypted archive named/located per the PROMPT ------
def test_output_archive_is_gpg_encrypted_tar_in_home():
    """The PROMPT: the backup is saved to ``~`` and is encrypted. Pin the output shape in the
    entry source: a GPG (AES256) archive named backup_<date>.tar.gz.gpg, written into HOME."""
    src = (paths.BACKUP_DIR / "backup.py").read_text(encoding="utf-8")
    assert "--symmetric" in src and "AES256" in src   # GPG symmetric AES256
    assert "backup_" in src and ".tar.gz.gpg" in src  # the archive name
    # The output path is joined onto the resolved HOME (os.path.join(home, ...)).
    assert "os.path.join(home, f\"backup_" in src


def test_passphrase_is_never_passed_on_the_command_line():
    """Defense-in-depth: the passphrase must reach gpg over a private fd, never as an argv
    token (which would leak it into the process list). Assert the fd path is used and the
    plaintext-argv forms (`--passphrase <value>` / `--passphrase=<value>`) never appear in
    the gpg command that build_archive constructs. We parse the source and inspect the actual
    gpg_cmd list literal rather than substring-scanning prose, so a mention of the flag in a
    comment can't trip (or hide) this."""
    src = (paths.BACKUP_DIR / "backup.py").read_text(encoding="utf-8")
    assert "--passphrase-fd" in src
    tree = ast.parse(src)
    # Collect every string constant that is an ELEMENT of a list literal (the argv lists).
    argv_strings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    argv_strings.add(elt.value)
    # The safe fd form is allowed; the plaintext argv forms must be entirely absent.
    assert "--passphrase-fd" in argv_strings
    assert "--passphrase" not in argv_strings          # bare flag + separate value arg
    assert not any(s.startswith("--passphrase=") for s in argv_strings)  # =value form
