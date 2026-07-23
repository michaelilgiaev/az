"""azarch.packages -- the offline package cache builder.

The subprocess-heavy parts (pacman -Sw, repo-add, chown) are not unit-tested.
Two things ARE pure and high-value:

  _split_pkg      parses name-ver-rel out of a .pkg.tar.zst basename. This keys
                  the whole incremental index reconcile; a mis-parse silently
                  desyncs the DB from the files on disk (pacstrap then rejects a
                  "corrupted" package). Hyphenated names and epoch versions are
                  the traps.

  the manifest tokenizer (in _sync_and_download) strips `#` comments the SAME
                  way mkarchiso does. It is inlined, so we re-derive it here and
                  pin the contract against a representative packages.x86_64 body.
"""

from __future__ import annotations

from azarch import packages


# --- _split_pkg: (db_key, name, verrel) ------------------------------------

def test_split_pkg_simple():
    assert packages._split_pkg("librewolf-1.0-1-x86_64.pkg.tar.zst") == (
        "librewolf-1.0-1", "librewolf", "1.0-1",
    )


def test_split_pkg_hyphenated_name():
    # gcc-libs: the hyphen in the NAME must survive; only the arch tail is stripped.
    assert packages._split_pkg("gcc-libs-13.2.1-3-x86_64.pkg.tar.zst") == (
        "gcc-libs-13.2.1-3", "gcc-libs", "13.2.1-3",
    )


def test_split_pkg_dotted_version():
    assert packages._split_pkg("linux-6.9.1.arch1-1-x86_64.pkg.tar.zst") == (
        "linux-6.9.1.arch1-1", "linux", "6.9.1.arch1-1",
    )


def test_split_pkg_epoch_version():
    # Epoch (2:) stays inside verrel.
    key, name, verrel = packages._split_pkg("python-2:3.11.5-1-any.pkg.tar.zst")
    assert name == "python"
    assert verrel == "2:3.11.5-1"


# --- the manifest tokenizer (comment/blank stripping) -----------------------

def _tokenize(text: str):
    # Re-derivation of the inlined parse in packages._sync_and_download so the
    # contract is testable without invoking pacman.
    return [tok for line in text.splitlines()
            if (tok := line.split("#", 1)[0].strip())]


def test_manifest_tokenizer_drops_comments_and_blanks():
    body = (
        "# Az'arch package manifest\n"
        "\n"
        "base\n"
        "linux    # the kernel\n"
        "  \n"
        "# ---- Stock / Az'arch delimiter ----\n"
        "firefox\n"
    )
    assert _tokenize(body) == ["base", "linux", "firefox"]


def test_manifest_tokenizer_matches_real_packages_file():
    # The real manifest must tokenize to a clean, comment-free, non-empty list --
    # every token is a plausible package name (no '#', no whitespace, non-empty).
    text = packages.paths.PACKAGES_FILE.read_text()
    toks = _tokenize(text)
    assert toks, "packages.x86_64 tokenized to nothing"
    for t in toks:
        assert "#" not in t
        assert t == t.strip()
        assert " " not in t


def test_no_duplicates_within_azarch_additions_block():
    # packages.x86_64 has two blocks: STOCK ARCH (the upstream releng baseline) and
    # AZ'ARCH ADDITIONS (the block the maintainer actually edits). A package listed
    # in BOTH blocks is intentional and benign -- releng ships e.g. grub/lvm2 and the
    # installer re-declares them; pacman/mkarchiso dedup the manifest. The real
    # editing hazard is a package listed twice WITHIN the additions block, so that
    # is what we guard.
    lines = packages.paths.PACKAGES_FILE.read_text().splitlines()
    banner = max(i for i, l in enumerate(lines) if "AZ'ARCH ADDITIONS" in l)
    # additions content starts after the closing ===== banner line following the text.
    close = next(i for i in range(banner + 1, len(lines))
                 if set(lines[i].strip()) <= set("#= "))
    additions = _tokenize("\n".join(lines[close + 1:]))
    dupes = {t for t in additions if additions.count(t) > 1}
    assert not dupes, f"duplicate packages within the Az'arch-additions block: {sorted(dupes)}"
