import io
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from app import db
from app import factory_routes as fr
from app import factory_service as fs
from core import gamedata as gd
from tools import import_1x

SRC = Path.home() / "sf-inputs/planner-1x.db"


@pytest.fixture
def conn(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setattr(db, "DB_PATH", p)
    db.migrate(p)
    c = db.connect(p)
    with c:
        c.execute("INSERT INTO world(name) VALUES ('Main')")
        c.execute("INSERT INTO factory(world_id,name) VALUES (1,'t')")
    return c


def test_output_and_override_validation(conn):
    plate = gd.item_by_name("Iron Plate")["class"]
    fr.set_output(1, "Iron Plate", 60)
    assert conn.execute("select rate_per_min from factory_output").fetchone()[0] == 60
    with pytest.raises(HTTPException):
        fr.set_output(1, "Not An Item", 5)
    with pytest.raises(HTTPException):
        fr.set_output(1, "Iron Plate", -1)
    fr.set_override(1, plate, "", "200", "")
    assert conn.execute("select clock_pct from factory_recipe").fetchone()[0] == 200
    with pytest.raises(HTTPException):
        fr.set_override(1, plate, "", "900", "")       # clock out of range
    with pytest.raises(HTTPException):
        fr.set_override(1, plate, "", "", "2")         # Constructor has 1 slot
    fr.set_override(1, plate, "", "", "1")             # full sloop ok
    fr.set_override(1, plate, "", "", "")              # clears row entirely
    assert conn.execute("select count(*) from factory_recipe").fetchone()[0] == 0
    with pytest.raises(HTTPException):
        fr.set_override(1, plate, "Recipe_IronIngot_C", "", "")  # recipe doesn't make plate


def test_archived_is_read_only(conn):
    with conn:
        conn.execute("UPDATE factory SET status='archived'")
    with pytest.raises(HTTPException):
        fr.set_output(1, "Iron Plate", 5)


def test_exports(conn):
    fr.set_output(1, "Iron Plate", 60)
    outputs, _c, _o, res = fs.solve_factory(conn, 1)
    j = json.loads(fs.export_json("t", outputs, res))
    assert j["raw_inputs_per_min"]["Iron Ore"] == pytest.approx(90)
    wb = load_workbook(io.BytesIO(fs.export_xlsx("t", outputs, res)))
    assert wb.sheetnames == ["Summary", "Lines"]
    assert wb["Lines"].max_row == 3


def test_recipe_options_compare(conn):
    opts = fs.recipe_options(gd.item_by_name("Iron Ingot")["class"], 60, None)
    names = {o["name"] for o in opts}
    assert "Iron Ingot" in names and "Alternate: Pure Iron Ingot" in names
    assert sum(o["current"] for o in opts) == 1


@pytest.mark.skipif(not SRC.exists(), reason="1.x snapshot not present")
def test_every_imported_factory_solves(tmp_path, monkeypatch):
    p = tmp_path / "i.db"
    monkeypatch.setattr(db, "DB_PATH", p)
    import_1x.run(SRC, p)
    c = db.connect(p)
    for f in c.execute("select id, name from factory where status != 'archived'").fetchall():
        outputs, _c, _o, res = fs.solve_factory(c, f["id"])
        assert outputs and res["lines"] and not res["warnings"], f["name"]
        assert res["power_mw"] > 0
