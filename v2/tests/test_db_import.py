import sqlite3
from pathlib import Path

import pytest

from app import db
from tools import import_1x

SRC = Path.home() / "sf-inputs/planner-1x.db"
pytestmark = pytest.mark.skipif(not SRC.exists(), reason="1.x snapshot not present")


def test_migrate_idempotent(tmp_path):
    p = tmp_path / "t.db"
    assert db.migrate(p) == [1]
    assert db.migrate(p) == []
    c = db.connect(p)
    assert {r[0] for r in c.execute("select version from schema_version")} == {1}


def test_import_1x_all_present_and_idempotent(tmp_path):
    p = tmp_path / "t.db"
    s = import_1x.run(SRC, p)
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    n_fact = src.execute("select count(*) from factories").fetchone()[0]
    n_pp = src.execute("select count(*) from power_plants").fetchone()[0]
    assert s["factories"] == n_fact + 1 and s["power_plants"] == n_pp  # +1 archived scratchpad
    c = db.connect(p)
    names = {r["name"] for r in c.execute("select name from factory")}
    assert {r[0] for r in src.execute("select name from factories")} <= names
    assert "1.x plan (archived)" in names
    assert c.execute("select status from factory where name='1.x plan (archived)'").fetchone()[0] == "archived"
    assert c.execute("select count(*) from power_plant").fetchone()[0] == n_pp
    # overrides preserved
    plan = {r[0] for r in src.execute("select product from clock_overrides")}
    expected = len(plan)  # archived scratchpad keeps the plan-level clocks
    for fid, in src.execute("select id from factories"):
        own = {r[0] for r in src.execute("select product from factory_clock_overrides where factory_id=?", (fid,))}
        expected += len(own | plan)  # 1.x merges plan clocks under each factory's own
    assert c.execute("select count(clock_pct) from factory_recipe").fetchone()[0] == expected
    # factory-level value wins over the plan-level one
    for fid, prod, clk in src.execute("select factory_id, product, clock_pct from factory_clock_overrides"):
        assert c.execute("select clock_pct from factory_recipe fr join factory f on f.id=fr.factory_id "
                         "where f.source_ref=? and fr.item=?",
                         (f"1x:factory:{fid}", import_1x._item(prod))).fetchone()[0] == clk
    again = import_1x.run(SRC, p)
    assert again["factories"] == 0 and again["power_plants"] == 0


def test_sloop_override_maps_to_full_slots(tmp_path):
    p = tmp_path / "t.db"
    import_1x.run(SRC, p)
    c = db.connect(p)
    # 1.x: Ficsite Trigon slooped in factory 3; Docs: its machine's full slot count (>0)
    t = [r for r in c.execute("select item, sloops from factory_recipe where sloops is not null and sloops > 0")]
    assert t and all(isinstance(r["sloops"], int) for r in t)
