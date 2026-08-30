"""Tests for libraries/variants.py -- the ISO matrix model.

The contract these lock down: the eight cells of the {headed,headless} x
{plain,instant} x {plain,ssh} cube map onto EXACTLY the eight artifact filenames
the prompt requires, selection is the Cartesian product of the enabled axes in a
stable order that always includes the base point, and the legacy base/sshd keys
still resolve to the headed-plain cells.
"""

from __future__ import annotations

import variants
from variants import Variant, selected_variants


# The eight required ISO stems, from data/PROMPT.md (minus the -<ver>-x86_64.iso
# tail mkarchiso appends). Keyed by (line, instant, ssh) so the mapping is exact.
EXPECTED_ISO_NAMES = {
    ("headed", False, False): "azarch-headed",
    ("headless", False, False): "azarch-headless",
    ("headed", False, True): "azarch-headed-ssh",
    ("headless", False, True): "azarch-headless-ssh",
    ("headed", True, False): "azarch-headed-instant",
    ("headless", True, False): "azarch-headless-instant",
    ("headed", True, True): "azarch-headed-instant-ssh",
    ("headless", True, True): "azarch-headless-instant-ssh",
}


def test_all_eight_cells_produce_the_required_filenames():
    for (line, instant, ssh), name in EXPECTED_ISO_NAMES.items():
        v = Variant(line=line, instant=instant, ssh=ssh)
        assert v.iso_name == name, (line, instant, ssh)


def test_iso_name_orders_instant_before_ssh():
    # The prompt lists ...-instant-ssh, not ...-ssh-instant. Segment order matters.
    v = Variant(line="headless", instant=True, ssh=True)
    assert v.iso_name == "azarch-headless-instant-ssh"
    assert v.key == "headless-instant-ssh"


def test_is_gui_maps_to_line():
    assert Variant(line="headed").is_gui is True
    assert Variant(line="headless").is_gui is False


def test_invalid_line_rejected():
    import pytest

    with pytest.raises(ValueError):
        Variant(line="workstation")
    # The pre-rename line tokens are no longer valid line values.
    with pytest.raises(ValueError):
        Variant(line="desktop")
    with pytest.raises(ValueError):
        Variant(line="server")


def test_variant_is_frozen_and_hashable():
    v = Variant(line="headed", ssh=True)
    # hashable -> usable in sets/dict keys
    assert v in {v}
    # frozen -> immutable
    import dataclasses
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        v.ssh = False  # type: ignore[misc]


# --- selection --------------------------------------------------------------


def test_bare_selection_is_headed_base_point_only():
    assert selected_variants() == (Variant(line="headed", instant=False, ssh=False),)


def test_ssh_only_adds_the_ssh_cell():
    got = selected_variants(ssh=True)
    assert got == (
        Variant(line="headed", ssh=False),
        Variant(line="headed", ssh=True),
    )


def test_headless_only_adds_the_headless_line():
    got = selected_variants(headless=True)
    assert got == (
        Variant(line="headed"),
        Variant(line="headless"),
    )


def test_full_matrix_is_all_eight_unique_cells():
    got = selected_variants(headless=True, instant=True, ssh=True)
    assert len(got) == 8
    assert len(set(got)) == 8
    # every required filename appears exactly once
    names = sorted(v.iso_name for v in got)
    assert names == sorted(EXPECTED_ISO_NAMES.values())


def test_selection_order_is_stable_and_deterministic():
    # headed before headless; within a line plain before instant; within that
    # no-ssh before ssh. Assert the exact sequence so build order is reproducible.
    got = selected_variants(headless=True, instant=True, ssh=True)
    assert [v.key for v in got] == [
        "headed",
        "headed-ssh",
        "headed-instant",
        "headed-instant-ssh",
        "headless",
        "headless-ssh",
        "headless-instant",
        "headless-instant-ssh",
    ]


def test_selection_always_contains_base_point():
    # No matter which axes are enabled, the always-built headed/plain/no-ssh ISO
    # is present (a bare compile.sh must still yield azarch-headed).
    base = Variant(line="headed", instant=False, ssh=False)
    for headless in (False, True):
        for instant in (False, True):
            for ssh in (False, True):
                got = selected_variants(headless=headless, instant=instant, ssh=ssh)
                assert base in got


# --- legacy back-compat -----------------------------------------------------


def test_legacy_base_and_sshd_map_to_headed_cells():
    assert variants.from_legacy_key("base").iso_name == "azarch-headed"
    assert variants.from_legacy_key("sshd").iso_name == "azarch-headed-ssh"


def test_legacy_unknown_key_falls_back_to_base():
    assert variants.from_legacy_key("bogus").iso_name == "azarch-headed"


def test_coerce_accepts_variant_or_string():
    v = Variant(line="headless", ssh=True)
    assert variants.coerce(v) is v
    assert variants.coerce("sshd") == Variant(line="headed", ssh=True)


def test_coerce_bare_line_name_maps_to_that_line():
    # A bare LINE name coerces to that line's plain base point (not a headed fallback),
    # so permissions_for("headless") really keys off the headless line.
    assert variants.coerce("headless") == Variant(line="headless")
    assert variants.coerce("headed") == Variant(line="headed")
    assert variants.coerce("headless").is_gui is False
