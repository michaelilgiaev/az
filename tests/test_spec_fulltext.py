"""spec_fulltext -- the exhaustive plain-text component listing
(documentation/SPECIFICATIONS_COMPONENTS_FULL.txt).

Why these tests matter: this file is meant to be BOTH pleasant to read AND
trivially machine-parseable -- every block is a `### name` header plus stable
`key: value` lines. Two things silently break that contract, and neither raises
an exception at generation time, so only a value assertion catches them:

  1. `_fmt_size` -- the human byte formatter. It picks one of four branches by
     magnitude and each branch has a DIFFERENT precision (GiB 2 decimals, MiB/KiB
     1 decimal, bytes 0). An off-by-one on a `1024**n` threshold, or the wrong
     precision, changes the size string every reader and every downstream parser
     sees. The branch boundaries (`>=`, not `>`) and the per-branch `.2f`/`.1f`
     format are pinned here with an exhaustive boundary table.

  2. `LAYER_ROLE` -- the per-layer role strings. They are DERIVED from
     spec_svg.LAYER_DEFS (`f"{title} -- {subtitle}"`) precisely so the SVG and
     this text file can never disagree about what "layer N" means. If someone
     hard-codes them here instead, the two artifacts drift. We pin that
     `LAYER_ROLE == [f"{t} -- {s}" for t, s in spec_svg.LAYER_DEFS]`, that it has
     the same length as LAYER_DEFS, and that `len(LAYER_ROLE) - 1` (the top layer
     index printed in every entry's `layer:` line) stays 6.

`_layer_of` is a thin re-export of spec_svg.layer_of, kept so the two modules
share ONE layer-assignment function; we assert it delegates identically across
the whole height range rather than re-implementing the thresholds. The list
helpers (`_name_list`, `_wrap_field`) and the pluralised `(none)` / `component(s)`
labels are the other places a formatting change would silently corrupt a record,
so a small render smoke test locks the whole assembled block shape.
"""

from __future__ import annotations

import spec_fulltext as F
import spec_svg


# --- _fmt_size: per-branch precision + threshold boundaries ----------------

def test_fmt_size_bytes_branch_no_decimals():
    # Under 1 KiB: raw integer count + " B", no scaling, no decimals.
    assert F._fmt_size(0) == "0 B"
    assert F._fmt_size(1) == "1 B"
    assert F._fmt_size(512) == "512 B"


def test_fmt_size_bytes_upper_boundary():
    # 1023 is the last value that must stay in the byte branch (< 1024).
    assert F._fmt_size(1023) == "1023 B"


def test_fmt_size_kib_lower_boundary_is_inclusive():
    # Exactly 1024 crosses into KiB (branch is `>= 1024`, not `> 1024`).
    assert F._fmt_size(1024) == "1.0 KiB"


def test_fmt_size_kib_one_decimal():
    assert F._fmt_size(1536) == "1.5 KiB"


def test_fmt_size_kib_upper_boundary():
    # Just below 1 MiB still formats as KiB, and shows 4-digit "1024.0".
    assert F._fmt_size(1024 ** 2 - 1) == "1024.0 KiB"


def test_fmt_size_mib_lower_boundary_is_inclusive():
    assert F._fmt_size(1024 ** 2) == "1.0 MiB"


def test_fmt_size_mib_one_decimal():
    assert F._fmt_size(int(1.5 * 1024 ** 2)) == "1.5 MiB"


def test_fmt_size_mib_upper_boundary():
    assert F._fmt_size(1024 ** 3 - 1) == "1024.0 MiB"


def test_fmt_size_gib_lower_boundary_is_inclusive_two_decimals():
    # GiB is the only branch with TWO decimals; 1 GiB exactly must land here.
    assert F._fmt_size(1024 ** 3) == "1.00 GiB"


def test_fmt_size_gib_two_decimals():
    assert F._fmt_size(int(2.75 * 1024 ** 3)) == "2.75 GiB"
    assert F._fmt_size(5 * 1024 ** 3) == "5.00 GiB"


def test_fmt_size_branch_precision_differs():
    # The whole point of the four branches: same-ish magnitude, different decimal
    # count. 1.5 in each unit shows the branch's own precision.
    assert F._fmt_size(int(1.5 * 1024)).endswith(".5 KiB")
    assert F._fmt_size(int(1.5 * 1024 ** 2)).endswith(".5 MiB")
    assert F._fmt_size(int(1.5 * 1024 ** 3)).endswith(".50 GiB")


# --- LAYER_ROLE: derived from spec_svg.LAYER_DEFS, never hand-copied --------

def test_layer_role_is_derived_from_layer_defs():
    # The anti-drift contract: exact "title -- subtitle" join of every LAYER_DEFS.
    expected = [f"{t} -- {s}" for t, s in spec_svg.LAYER_DEFS]
    assert F.LAYER_ROLE == expected


def test_layer_role_length_matches_layer_defs():
    assert len(F.LAYER_ROLE) == len(spec_svg.LAYER_DEFS)


def test_layer_role_has_seven_entries():
    # Seven depth bands; the top-layer index printed in every entry is len-1 == 6.
    assert len(F.LAYER_ROLE) == 7
    assert len(F.LAYER_ROLE) - 1 == 6


def test_layer_role_first_and_last():
    assert F.LAYER_ROLE[0] == (
        "Foundation -- depth 0 -- nothing below them; true sinks of the graph"
    )
    assert F.LAYER_ROLE[6] == (
        "Leaves (34+) -- top; the deepest chains -- nothing depends on these"
    )


def test_layer_role_all_contain_separator():
    # Every entry is a "title -- subtitle" join, so the separator must appear.
    for role in F.LAYER_ROLE:
        assert " -- " in role


# --- _layer_of: thin re-export of spec_svg.layer_of ------------------------

def test_layer_of_delegates_across_full_height_range():
    # _layer_of must return exactly what spec_svg.layer_of returns for every
    # height, so the SVG and the text file assign the same band.
    for h in range(0, 60):
        assert F._layer_of("pkg", "AnyCategory", h) == spec_svg.layer_of(
            "pkg", "AnyCategory", h
        )


def test_layer_of_height_zero_is_foundation():
    assert F._layer_of("p", "c", 0) == 0


def test_layer_of_top_band_index():
    # Deep chains land in the last band, whose index is len(LAYER_ROLE) - 1.
    assert F._layer_of("p", "c", 44) == len(F.LAYER_ROLE) - 1


# --- rule/separator constants ----------------------------------------------

def test_rule_and_thin_widths():
    # Both separators span the 78-column layout; RULE is '=', THIN is '-'.
    assert F.RULE == "=" * 78
    assert F.THIN == "-" * 78
    assert len(F.RULE) == 78 and len(F.THIN) == 78


# --- EDITION_SHORT / EDITION_LABEL keys ------------------------------------

def test_edition_maps_share_the_same_two_keys():
    assert set(F.EDITION_SHORT) == set(F.EDITION_LABEL) == {"az'arch", "stock"}


def test_edition_short_is_identity_labelled():
    assert F.EDITION_SHORT["az'arch"] == "az'arch"
    assert F.EDITION_SHORT["stock"] == "stock"


def test_edition_label_apostrophe_form():
    # The literal apostrophe form "az'arch" (not "azarch") is the brand spelling
    # printed in the legend and in every entry's edition line.
    assert F.EDITION_LABEL["az'arch"].startswith("az'arch")
    assert "Az'arch Component" in F.EDITION_LABEL["az'arch"]
    assert F.EDITION_LABEL["stock"].startswith("stock")


# --- _name_list: pluralised (none) vs a real wrapped list ------------------

def test_name_list_empty_shows_none_placeholder():
    # Empty -> a single '(none)' line so the field is always present, never
    # silently omitted (the parser expects the key).
    assert F._name_list([], "requires") == ["requires: (none)"]


def test_name_list_single_name_on_one_line():
    assert F._name_list(["foo"], "requires") == ["requires: foo"]


def test_name_list_keeps_hyphenated_token_whole():
    # break_on_hyphens=False: a hyphenated package name must stay one whitespace-
    # free token even when the line is long, so the file stays parseable.
    names = ["xdg-user-dirs"] * 8
    lines = F._name_list(names, "requires", width=40)
    joined = "\n".join(lines)
    # The token is never split across a newline.
    assert "xdg-user-dirs" in joined
    for ln in lines:
        assert "user-\ndirs" not in ln  # sanity: not physically broken
    # Reassembling the tokens must recover every original name intact.
    flat = joined.replace("requires:", "").replace("\n", " ")
    assert flat.count("xdg-user-dirs") == 8


def test_wrap_field_short_text_single_line():
    assert F._wrap_field("purpose", "short desc") == ["purpose: short desc"]


def test_wrap_field_hangs_continuation_under_value():
    # Long text wraps; continuation lines are indented under the value column
    # (len(label) + 2 spaces), keeping the block readable.
    lines = F._wrap_field("purpose", "word " * 40, width=40)
    assert len(lines) > 1
    assert lines[0].startswith("purpose: ")
    for cont in lines[1:]:
        assert cont.startswith(" " * (len("purpose") + 2))


# --- _component_block: assembled record shape ------------------------------

def _fixture():
    packages = {
        "foo": {
            "desc": "A foo tool", "url": "http://foo", "version": "1.0",
            "repo": "core", "isize": 2048, "license": "GPL",
            "optdepends": ["bar: does stuff"],
        },
        "bar": {
            "desc": "A bar lib", "version": "2.0", "repo": "extra",
            "isize": 1024 ** 3, "license": None,
        },
    }
    resolved = {"closure": ["foo", "bar"], "edges": {"foo": ["bar"], "bar": []}}
    tiers = {
        "heights": {"foo": 5, "bar": 0},
        "rev": {"bar": ["foo"], "foo": []},
        "trans_deps": {"foo": 1, "bar": 0},
        "trans_dependents": {"foo": 0, "bar": 1},
    }
    tags = {
        "foo": {"edition": "az'arch", "category": "Application",
                "azarch_note": "added by azarch", "removed": False},
        "bar": {"edition": "stock", "category": "Shared library"},
    }
    return packages, resolved, tiers, tags


def test_component_block_header_and_size_use_fmt_size():
    packages, resolved, tiers, tags = _fixture()
    block = F._component_block("foo", packages, resolved, tiers, tags)
    text = "\n".join(block)
    assert block[0] == "### foo  (1.0)"
    # 2048 bytes routes through _fmt_size -> "2.0 KiB".
    assert "installed size: 2.0 KiB" in text
    assert "license: GPL" in text


def test_component_block_layer_line_uses_layer_role_top_index():
    packages, resolved, tiers, tags = _fixture()
    block = F._component_block("foo", packages, resolved, tiers, tags)
    text = "\n".join(block)
    # height 5 -> layer 2; "of 6" is len(LAYER_ROLE)-1; role text is LAYER_ROLE[2].
    assert f"layer:    2 of {len(F.LAYER_ROLE) - 1}  ({F.LAYER_ROLE[2]})" in text


def test_component_block_shipped_note_branch():
    packages, resolved, tiers, tags = _fixture()
    block = F._component_block("foo", packages, resolved, tiers, tags)
    text = "\n".join(block)
    # removed=False -> "shipped, with Az'arch changes".
    assert "[shipped, with Az'arch changes]" in text
    assert "REMOVED" not in text


def test_component_block_removed_note_branch():
    packages, resolved, tiers, tags = _fixture()
    tags["foo"]["removed"] = True
    block = F._component_block("foo", packages, resolved, tiers, tags)
    text = "\n".join(block)
    assert "[REMOVED (not shipped on the ISO)]" in text


def test_component_block_optional_deps_one_per_line_unwrapped():
    packages, resolved, tiers, tags = _fixture()
    block = F._component_block("foo", packages, resolved, tiers, tags)
    assert "optional:" in block
    # Each optdep is its own line, indented 4 spaces, carrying its ': reason'.
    assert "    bar: does stuff" in block


def test_component_block_missing_record_uses_defaults():
    # rec = {} -> version '?', repo '?', size '0 B', placeholder desc, no upstream.
    tags = {"ghost": {"edition": "az'arch", "category": "X",
                      "azarch_note": "was here", "removed": True}}
    resolved = {"closure": ["ghost"], "edges": {}}
    tiers = {"heights": {}, "rev": {},
             "trans_deps": {"ghost": 0}, "trans_dependents": {"ghost": 0}}
    block = F._component_block("ghost", {}, resolved, tiers, tags)
    text = "\n".join(block)
    assert block[0] == "### ghost  (?)"
    assert "purpose: (no description in the Arch package database)" in text
    assert "repo:     ?    installed size: 0 B    license: (unknown)" in text
    assert "upstream:" not in text  # empty url -> line omitted


def test_component_block_none_placeholders_for_empty_edges():
    packages, resolved, tiers, tags = _fixture()
    # bar has no deps and one dependent; foo has one dep and no dependents.
    bar = "\n".join(F._component_block("bar", packages, resolved, tiers, tags))
    assert "requires: (none)" in bar
    assert "required-by: foo" in bar
    foo = "\n".join(F._component_block("foo", packages, resolved, tiers, tags))
    assert "requires: bar" in foo
    assert "required-by: (none)" in foo


# --- render_fulltext: full document assembly smoke test --------------------

def _glance():
    return {
        "base": "archiso", "desktop": "openbox", "kernel": "6.9", "init": "256",
        "ram": "50%", "closure": 2, "by_repo": {"core": 1, "extra": 1, "multilib": 0},
        "azarch": 1, "stock": 1, "max_height": 5, "size": "1.0 GiB",
    }


def test_render_fulltext_returns_newline_terminated_string():
    # Source assembles `"\n".join(lines) + "\n"`. The last band's final component
    # is followed by a THIN separator and a blank line, so the document ends with
    # a trailing blank line then the joiner newline -> the tail is "...----\n\n".
    packages, resolved, tiers, tags = _fixture()
    out = F.render_fulltext(packages, resolved, tiers, tags, _glance(),
                            "a.svg", "b.md")
    assert isinstance(out, str)
    assert out.endswith("\n")
    # It is exactly one blank line at the very end (the join newline after the
    # last already-empty body line), not more.
    assert out.endswith(F.THIN + "\n\n")
    assert not out.endswith("\n\n\n")


def test_render_fulltext_emits_a_band_per_layer_role():
    packages, resolved, tiers, tags = _fixture()
    out = F.render_fulltext(packages, resolved, tiers, tags, _glance(),
                            "a.svg", "b.md")
    # One "LAYER N --" header per layer role (top-down), so exactly 7 of them.
    assert out.count("\nLAYER ") == len(F.LAYER_ROLE)
    for idx in range(len(F.LAYER_ROLE)):
        assert f"LAYER {idx} -- {F.LAYER_ROLE[idx]}" in out


def test_render_fulltext_layer_counts_are_pluralised_component_s():
    packages, resolved, tiers, tags = _fixture()
    out = F.render_fulltext(packages, resolved, tiers, tags, _glance(),
                            "a.svg", "b.md")
    # foo (height 5) -> layer 2; bar (height 0) -> layer 0. Both non-empty bands
    # print "1 component(s)"; every other band prints "0 component(s)".
    assert out.count(" component(s)") == len(F.LAYER_ROLE)
    assert "1 component(s)" in out
    assert "0 component(s)" in out


def test_render_fulltext_index_lists_every_component():
    packages, resolved, tiers, tags = _fixture()
    out = F.render_fulltext(packages, resolved, tiers, tags, _glance(),
                            "a.svg", "b.md")
    assert "COMPONENT INDEX" in out
    # Index rows use the short edition tag and the version.
    assert "foo" in out and "bar" in out
    assert "az'arch" in out and "stock" in out


def test_render_fulltext_at_a_glance_uses_glance_values():
    packages, resolved, tiers, tags = _fixture()
    out = F.render_fulltext(packages, resolved, tiers, tags, _glance(),
                            "a.svg", "b.md")
    assert "linux 6.9" in out          # kernel prefixed with 'linux '
    assert "systemd 256" in out        # init prefixed with 'systemd '
    assert "5 hops (leaf -> base)" in out
    assert "1 / 1 / 0" in out          # core / extra / multilib


def test_render_fulltext_header_references_both_companion_paths():
    packages, resolved, tiers, tags = _fixture()
    out = F.render_fulltext(packages, resolved, tiers, tags, _glance(),
                            "the.svg", "the.md")
    assert "- the.svg" in out
    assert "- the.md" in out
