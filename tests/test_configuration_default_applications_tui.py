"""The azarch TUI's "Default Applications" screen + the `azarch default-applications` CLI, and
the LOCK-STEP that keeps them derived from packages/azarch/default_applications.py (PROMPT: the
TUI must derive its rows/labels from that single source, no second hardcoded copy -- mirror the
wallpaper.py <-> model.c pattern where a test pins the strings).

Three drift traps are guarded here:
  * the bundled CLI's DA_CATEGORIES mirror == default_applications.CATEGORIES / CANDIDATES,
  * the C model.c category screens (labels, keys, set-commands) match that same source,
  * the CLI is wired into the dispatcher + usage.
"""

from __future__ import annotations

import types

from packages.azarch import default_applications as da
from packages.azarch.bundle import bundle_source
import paths


def _bundled():
    mod = types.ModuleType("azarch_cli_da")
    exec(compile(bundle_source(), "azarch_cli_da", "exec"), mod.__dict__)
    return mod


def _model_c() -> str:
    # The screen TREE (ROWS_* + SCREENS[]) lives in model_tree.c since model.c was split for the
    # size budget; read both so a row/screen check finds it wherever it is.
    d = paths.LIBDIR / "packages/azarch"
    return (d / "model.c").read_text(encoding="utf-8") + "\n" + \
        (d / "model_tree.c").read_text(encoding="utf-8")


# --- single source of truth: the CLI mirror matches default_applications.py -----

def test_cli_da_categories_mirror_the_single_source():
    cli = _bundled()
    # keys + labels + groups + mimes + candidates must match default_applications exactly.
    src_rows = da.tui_categories()   # (group, label, key, default_id), in order (Mail included)
    # the CLI table omits Mail? No -- it includes every CATEGORIES row EXCEPT Mail is present in
    # default_applications but the TUI list omits it. The CLI mirrors the FULL set incl. Mail
    # (so `get mail` works), so compare against CATEGORIES directly.
    cli_by_key = {row[0]: row for row in cli.DA_CATEGORIES}
    for group, label, desktop_id, mimes in da.CATEGORIES:
        key = da.CATEGORY_KEYS[label]
        assert key in cli_by_key, f"CLI missing category {key}"
        ck, clabel, cgroup, cmimes, ccands = cli_by_key[key]
        assert clabel == label, key
        assert cgroup == group, key
        assert tuple(cmimes) == tuple(mimes), key
        assert tuple(ccands) == tuple(da.CANDIDATES[label]), key
    # no extra categories in the CLI beyond the source.
    assert set(cli_by_key) == {da.CATEGORY_KEYS[label] for _g, label, _d, _m in da.CATEGORIES}


def test_candidate_first_is_the_shipped_default():
    # The first candidate of each category must be that category's CATEGORIES default handler
    # (so re-picking the top option restores the shipped default). Mail has no default/candidate.
    for _group, label, desktop_id, _mimes in da.CATEGORIES:
        cands = da.CANDIDATES[label]
        if desktop_id:
            assert cands and cands[0] == desktop_id, label
        else:
            assert cands == (), label  # Mail: no handler, no candidates


def test_representative_mime_is_first_mime():
    for _group, label, _desktop_id, mimes in da.CATEGORIES:
        assert da.representative_mime(label) == (mimes[0] if mimes else "")


# --- the CLI is wired + behaves ---------------------------------------------

def test_default_applications_dispatch_wired():
    src = bundle_source()
    assert 'cmd == "default-applications"' in src
    assert "return cmd_default_applications(argv[1:])" in src
    # advertised in usage()
    assert "default-applications" in src


def test_cli_categories_verb_lists_keys():
    cli = _bundled()
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.cmd_default_applications(["categories"])
    assert rc == 0
    keys = buf.getvalue().split()
    assert keys == [da.CATEGORY_KEYS[label] for _g, label, _d, _m in da.CATEGORIES]


def test_cli_set_rejects_non_candidate():
    cli = _bundled()
    rc = cli.cmd_default_applications(["set", "web", "not-a-real-app.desktop"])
    assert rc == 2  # not offered for that category


def test_cli_set_rejects_unknown_category():
    cli = _bundled()
    rc = cli.cmd_default_applications(["set", "bogus", "librewolf.desktop"])
    assert rc == 2


def test_cli_helpers_rc_path_matches_emitter():
    # The CLI writes the exo TerminalEmulator selection to the SAME helpers.rc the emitter ships.
    cli = _bundled()
    assert da.HELPERS_RC_PATH.endswith("/.config/" + cli.DA_HELPERS_RC)


# --- the C model.c derives from the same source (pinning, wallpaper.py pattern) ---

def test_model_c_defaultapps_screen_pinned_to_source():
    model = _model_c()
    # ROWS_MAIN has the entry; the category list screen id + subtitle are present.
    assert '.label="Default Applications", .kind=AZ_ACT_SCREEN, .target="defaultapps"' in model
    assert '.id="defaultapps"' in model
    # every TUI category (Mail excluded) has a row label, a per-category screen id, and its
    # current-handler probe, using the EXACT key from default_applications.CATEGORY_KEYS.
    tui_labels = [label for _g, label, _d, _m in da.CATEGORIES if label != "Mail"]
    for label in tui_labels:
        key = da.CATEGORY_KEYS[label]
        assert f'.target="defaultapps.{key}"' in model, key
        assert f'.id="defaultapps.{key}"' in model, key
        # the category row label appears (as a ROWS_DEFAULTAPPS entry).
        assert f'.label="{label}",' in model, label
    # Mail is NOT surfaced in the C model.
    assert '"defaultapps.mail"' not in model


def test_model_c_set_commands_match_candidates():
    model = _model_c()
    # each candidate handler for each TUI category must appear as a
    # `azarch default-applications set <key> <id>` apply target in model.c.
    for _group, label, desktop_id, _mimes in da.CATEGORIES:
        if label == "Mail":
            continue
        key = da.CATEGORY_KEYS[label]
        for cand in da.CANDIDATES[label]:
            needle = f"azarch default-applications set {key} {cand}"
            assert needle in model, needle
