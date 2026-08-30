"""Tests for network_profile: static IPv4 NetworkManager keyfile builder."""

from __future__ import annotations

import network_profile as np


def test_valid_cidr():
    assert np.is_valid_cidr("192.168.1.50/24")
    assert np.is_valid_cidr("10.0.0.1/8")
    assert np.is_valid_cidr("0.0.0.0/0")


def test_invalid_cidr():
    for bad in ("192.168.1.50", "192.168.1.50/33", "256.1.1.1/24",
                "192.168.1/24", "abc/24", "192.168.1.50/-1", ""):
        assert not np.is_valid_cidr(bad), bad


def test_nmconnection_minimal_has_static_address():
    text = np.nmconnection_text("192.168.1.50/24")
    assert "method=manual" in text
    assert "address1=192.168.1.50/24" in text
    assert "[connection]" in text and "[ipv4]" in text


def test_nmconnection_includes_gateway_and_dns():
    text = np.nmconnection_text("192.168.1.50/24", gateway="192.168.1.1",
                                dns="1.1.1.1,9.9.9.9")
    assert "address1=192.168.1.50/24;192.168.1.1" in text
    assert "dns=1.1.1.1;9.9.9.9;" in text


def test_nmconnection_omits_absent_optionals():
    text = np.nmconnection_text("192.168.1.50/24")
    assert "dns=" not in text
