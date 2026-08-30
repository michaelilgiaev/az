"""Tests for libraries/variants.py -- the ISO matrix model.

The contract these lock down: the eight cells of the {desktop,server} x
{plain,instant} x {plain,ssh} cube map onto EXACTLY the eight artifact filenames
the prompt requires, selection is the Cartesian product of the enabled axes in a
stable order that always includes the base point, and the legacy base/sshd keys
still resolve to the desktop-plain cells.
"""

from __future__ import annotations

import variants
from variants import Variant, selected_variants


# The eight required ISO stems, from data/PROMPT.md (minus the -<ver>-x86_64.iso
# tail mkarchiso appends). Keyed by (line, instant, ssh) so the mapping is exact.
EXPECTED_ISO_NAMES = {
    ("desktop", False, False): "azarch-desktop",
    ("server", False, False): "azarch-server",
    ("desktop", False, True): "azarch-desktop-ssh",
    ("server", False, True): "azarch-server-ssh",
    ("desktop", True, False): "azarch-desktop-instant",
    ("server", True, False): "azarch-server-instant",
    ("desktop", True, True): "azarch-desktop-instant-ssh",
    ("server", True, True): "azarch-server-instant-ssh",
}


def test_all_eight_cells_produce_the_required_filenames():
    for (line, instant, ssh), name in EXPECTED_ISO_NAMES.items():
        v = Variant(line=line, instant=instant, ssh=ssh)
        assert v.iso_name == name, (line, instant, ssh)


def test_iso_name_orders_instant_before_ssh():
    # The prompt lists ...-instant-ssh, not ...-ssh-instant. Segment order matters.
    v = Variant(line="server", instant=True, ssh=True)
    assert v.iso_name == "azarch-server-instant-ssh"
    assert v.key == "server-instant-ssh"


def test_is_gui_maps_to_line():
    assert Variant(line="desktop").is_gui is True
    assert Variant(line="server").is_gui is False


def test_invalid_line_rejected():
    import pytest

    with pytest.raises(ValueError):
        Variant(line="workstation")


def test_variant_is_frozen_and_hashable():
    v = Variant(line="desktop", ssh=True)
    # hashable -> usable in sets/dict keys
    assert v in {v}
    # frozen -> immutable
    import dataclasses
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        v.ssh = False  # type: ignore[misc]


# --- selection --------------------------------------------------------------


def test_bare_selection_is_desktop_base_point_only():
    assert selected_variants() == (Variant(line="desktop", instant=False, ssh=False),)


def test_ssh_only_adds_the_ssh_cell():
    got = selected_variants(ssh=True)
    assert got == (
        Variant(line="desktop", ssh=False),
        Variant(line="desktop", ssh=True),
    )


def test_server_only_adds_the_server_line():
    got = selected_variants(server=True)
    assert got == (
        Variant(line="desktop"),
        Variant(line="server"),
    )


def test_full_matrix_is_all_eight_unique_cells():
    got = selected_variants(server=True, instant=True, ssh=True)
    assert len(got) == 8
    assert len(set(got)) == 8
    # every required filename appears exactly once
    names = sorted(v.iso_name for v in got)
    assert names == sorted(EXPECTED_ISO_NAMES.values())


def test_selection_order_is_stable_and_deterministic():
    # desktop before server; within a line plain before instant; within that
    # no-ssh before ssh. Assert the exact sequence so build order is reproducible.
    got = selected_variants(server=True, instant=True, ssh=True)
    assert [v.key for v in got] == [
        "desktop",
        "desktop-ssh",
        "desktop-instant",
        "desktop-instant-ssh",
        "server",
        "server-ssh",
        "server-instant",
        "server-instant-ssh",
    ]


def test_selection_always_contains_base_point():
    # No matter which axes are enabled, the always-built desktop/plain/no-ssh ISO
    # is present (a bare compile.sh must still yield azarch-desktop).
    base = Variant(line="desktop", instant=False, ssh=False)
    for server in (False, True):
        for instant in (False, True):
            for ssh in (False, True):
                got = selected_variants(server=server, instant=instant, ssh=ssh)
                assert base in got


# --- legacy back-compat -----------------------------------------------------


def test_legacy_base_and_sshd_map_to_desktop_cells():
    assert variants.from_legacy_key("base").iso_name == "azarch-desktop"
    assert variants.from_legacy_key("sshd").iso_name == "azarch-desktop-ssh"


def test_legacy_unknown_key_falls_back_to_base():
    assert variants.from_legacy_key("bogus").iso_name == "azarch-desktop"


def test_coerce_accepts_variant_or_string():
    v = Variant(line="server", ssh=True)
    assert variants.coerce(v) is v
    assert variants.coerce("sshd") == Variant(line="desktop", ssh=True)
