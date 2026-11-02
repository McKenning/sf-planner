import pytest

from app import db, world_service as ws
from app import factory_service as fs
from core import budget, ledger
from core import gamedata as gd


def c(n):
    return gd.item_by_name(n)["class"]


@pytest.fixture
def conn(tmp_path):
    p = tmp_path / "w.db"
    db.migrate(p)
    cn = db.connect(p)
    with cn:
        cn.execute("INSERT INTO world(name) VALUES ('Main')")
        for res, (pu, no, im) in {"Iron Ore": (46, 42, 39), "Copper Ore": (13, 29, 13), "Limestone": (30, 49, 15),
                                   "Coal": (16, 31, 15), "Crude Oil": (12, 18, 18), "Water": (0, 0, 0),
                                   "Raw Quartz": (7, 7, 3), "Caterium Ore": (8, 9, 0), "Sulfur": (5, 5, 6)}.items():
            cn.execute("INSERT INTO world_resource(world_id,resource,pure,normal,impure,miner,clock_pct) "
                       "VALUES (1,?,?,?,?,?,250)", (c(res), pu, no, im, budget.default_extractor(c(res))))
    return cn


def test_budget_matches_1x_for_solids():
    assert budget.available_per_min(c("Iron Ore"), 46, 42, 39) == 92100
    assert budget.available_per_min(c("Water"), 0, 0, 0) == float("inf")


def test_generator_stats_match_game():
    s = ledger.generator_stats({"generator": "Build_GeneratorNuclear_C", "fuel": c("Uranium Fuel Rod"),
                                "count": 100, "clock_pct": 250})
    assert s["mw"] == pytest.approx(625000)
    assert s["fuel_per_min"] == pytest.approx(50)
    assert s["waste_per_min"] == pytest.approx(2500)


def test_allocate_flows():
    fl = ledger.allocate_flows([{"factory": 2, "item": "x", "rate": 30}, {"factory": 3, "item": "x", "rate": 50}],
                               [{"factory": 1, "item": "x", "rate": 60}])
    assert [(f["to"], round(f["rate"], 6)) for f in fl] == [(2, 30), (3, 30)]  # 20 short for factory 3


def test_project_assembly_top_down_split(conn):
    """Done-when: a Project Assembly goal planned top-down shows raw totals vs budget and splits
    into >= 2 factories with auto-created flows."""
    with conn:
        for part, rate in (("Smart Plating", 5), ("Versatile Framework", 5), ("Automated Wiring", 2.5),
                           ("Modular Engine", 2.5), ("Adaptive Control Unit", 1)):
            conn.execute("INSERT INTO world_goal(world_id,item,rate_per_min) VALUES (1,?,?)", (c(part), rate))
    goals, choices, res, assigned = ws.goal_tree(conn, 1)
    assert not res["warnings"] and res["raws"]
    raw_demand = {k: v for k, v in res["raws"].items()}
    assert c("Iron Ore") in raw_demand
    av = ws.available(conn, 1)
    rows = ledger.raw_budget(raw_demand, av)
    assert all(r["available"] is not None for r in rows if r["item"] in av)

    with conn:
        plating = ws.assign(conn, 1, c("Smart Plating"), None, "Plating", True)
        engines = ws.assign(conn, 1, c("Modular Engine"), None, "Engines", True)   # Smart Plating -> external
        control = ws.assign(conn, 1, c("Adaptive Control Unit"), None, "Control", False)
    assert len({plating, engines, control}) == 3
    flows = conn.execute("SELECT * FROM flow WHERE auto=1").fetchall()
    assert flows, "auto flows must be created at the cut points"
    plating_flow = [f for f in flows if f["item"] == c("Smart Plating") and f["to_factory"] == engines]
    assert plating_flow and plating_flow[0]["from_factory"] == plating
    # Control builds only the ACU: its direct ingredients are external
    ext = {r[0] for r in conn.execute("select item from factory_input where factory_id=?", (control,))}
    assert c("Computer") in ext and c("Circuit Board") in ext
    ov = ws.overview(conn, 1)
    assert ov["factories"] and ov["budget"]
    # Control's inputs have no producer yet -> deficits are reported, deficits sort first
    assert ov["ledger"][0]["net"] < 0
    assert any(w.startswith("Deficit:") for w in ov["warnings"])
    # re-running the split is idempotent for flows
    n = conn.execute("select count(*) from flow").fetchone()[0]
    with conn:
        ws.rebuild_auto_flows(conn, 1)
    assert conn.execute("select count(*) from flow").fetchone()[0] == n


def test_overview_power(conn):
    with conn:
        conn.execute("INSERT INTO power_plant(world_id,name,generator,fuel,count,clock_pct) VALUES (1,'c','Build_GeneratorCoal_C',?,10,100)",
                     (c("Coal"),))
        conn.execute("INSERT INTO factory(world_id,name) VALUES (1,'f')")
        conn.execute("INSERT INTO factory_output(factory_id,item,rate_per_min) VALUES (1,?,60)", (c("Iron Plate"),))
    ov = ws.overview(conn, 1)
    assert ov["gen_mw"] == 750 and ov["used_mw"] == pytest.approx(24)
    coal = next(b for b in ov["budget"] if b["item"] == c("Coal"))
    assert coal["demand"] == pytest.approx(150)


def test_route_validation(conn, monkeypatch):
    from fastapi import HTTPException
    from app import world_routes as wr
    monkeypatch.setattr(db, "DB_PATH", conn.execute("pragma database_list").fetchone()[2])
    with pytest.raises(HTTPException):
        wr.goal_add("Iron Plate", -3)
    wr.goal_add("Iron Plate", 30)
    wr.goal_add("Iron Plate", 40)  # updates, not duplicates
    assert conn.execute("select count(*), max(rate_per_min) from world_goal").fetchone()[:] == (1, 40)
    with pytest.raises(HTTPException):
        wr.power_add("", "Build_GeneratorCoal_C", c("Uranium Fuel Rod"), 1, 100)   # wrong fuel for generator
    wr.power_add("x", "Build_GeneratorCoal_C", c("Coal"), 2, 100)
    with pytest.raises(HTTPException):
        wr.resources_update(c("Iron Ore"), 1, 1, 1, "", 900)
    with pytest.raises(HTTPException):
        wr.flow_add("Iron Plate", 1, 1, 5, "")   # same factory both ends
