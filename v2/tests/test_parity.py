from pathlib import Path

import pytest

from tools import parity_1x

SRC = Path.home() / "sf-inputs/planner-1x.db"
pytestmark = pytest.mark.skipif(not SRC.exists(), reason="1.x snapshot not present")


def test_parity_with_1x_solver_at_tight_tolerance():
    """Every 1.x factory: same rates, machine counts, clocks and raws as 1.x's solver.
    (Stock 1.x stops its loop iteration at 0.01%, so the comparison uses 1.x with a tight tolerance.)"""
    rep = parity_1x.run(SRC, tight=True)
    assert len(rep) >= 4
    for r in rep:
        assert r["diffs"] == [], (r["factory"], r["diffs"][:5])
