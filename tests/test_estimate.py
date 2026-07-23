"""azarch.estimate -- the --estimate-full-compile heuristic.

_fmt_hours is pure math and the part most likely to drift (min vs hours, the
zero-minutes case). estimate() reads /proc for the real machine, so we assert its
structural invariants (a valid range, all keys present) rather than exact numbers.
"""

from __future__ import annotations

import pytest

from azarch import estimate


@pytest.mark.parametrize("hours,expected", [
    (0.25, "15 min"),
    (0.5, "30 min"),
    (0.99, "59 min"),
    (1.0, "1h"),
    (2.0, "2h"),
    (2.5, "2h 30m"),
    (1.75, "1h 45m"),
])
def test_fmt_hours(hours, expected):
    assert estimate._fmt_hours(hours) == expected


def test_fmt_hours_sub_hour_uses_minutes():
    assert estimate._fmt_hours(0.1).endswith("min")


def test_fmt_hours_whole_hour_has_no_minutes():
    assert estimate._fmt_hours(3.0) == "3h"


def test_estimate_returns_a_valid_range():
    e = estimate.estimate()
    assert e["low_hours"] < e["high_hours"]
    assert e["low_hours"] > 0


def test_estimate_has_all_keys():
    e = estimate.estimate()
    for k in ("cores", "model", "mhz", "ram_gb", "low_hours", "high_hours", "ram_warning"):
        assert k in e


def test_estimate_cores_is_positive():
    assert estimate.estimate()["cores"] >= 1


def test_run_returns_zero(capsys):
    # run() only prints and returns 0 -- no build, no network, no sudo.
    rc = estimate.run()
    assert rc == 0
    out = capsys.readouterr().out
    assert "estimate-full-compile" in out
