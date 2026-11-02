"""Import a copy of 1.x's planner.db into 2.0 (world "Main"). Read-only on the source.

Usage: python -m tools.import_1x [path/to/planner-1x.db]
Idempotent: factories/power plants carry a source_ref ('1x:factory:<id>') and are skipped if present.
"""
import sqlite3
import sys
from pathlib import Path

from app import db
from core import gamedata as gd

WORLD = "Main"
GENERATOR_BY_NAME = {
    "Coal Generator": "Build_GeneratorCoal_C",
    "Fuel Generator": "Build_GeneratorFuel_C",
    "Nuclear Power Plant": "Build_GeneratorNuclear_C",
}


class Unmapped(Exception):
    pass


def _item(name: str) -> str:
    it = gd.item_by_name(name)
    if not it:
        raise Unmapped(f"unknown item '{name}'")
    return it["class"]


def _recipe(name: str) -> str:
    r = gd.recipe_by_name(name)
    if not r:
        raise Unmapped(f"unknown recipe '{name}'")
    return r["class"]


def _full_slots(item: str, recipe_cls: str | None) -> int:
    """Slots of the machine that makes `item` (override recipe, else the default non-alternate one)."""
    if recipe_cls:
        r = gd.recipes()[recipe_cls]
    else:
        cands = [r for r in gd.recipes().values()
                 if r["outputs"][0]["item"] == item and not r["alternate"]]
        if not cands:
            raise Unmapped(f"no default recipe for {item}")
        r = cands[0]
    return gd.buildings()[r["machine"]]["sloop_slots"]


def _world(conn) -> int:
    row = conn.execute("SELECT id FROM world WHERE name = ?", (WORLD,)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO world(name, game_build) VALUES (?, ?)",
                        (WORLD, gd.load()["build"])).lastrowid


def _plan_clocks(src) -> list:
    """1.x merges the active (first) plan's clock overrides under every factory's own."""
    row = src.execute("SELECT id FROM plans ORDER BY id LIMIT 1").fetchone()
    return list(src.execute("SELECT product, clock_pct FROM clock_overrides WHERE plan_id=?",
                            (row["id"],))) if row else []


def _backfill_plan_clocks(conn, src, fid):
    """Fill-only: plan-level clock for items the factory has no clock for (never overwrites)."""
    n = 0
    for r in _plan_clocks(src):
        item = _item(r["product"])
        cur = conn.execute("UPDATE factory_recipe SET clock_pct=? WHERE factory_id=? AND item=? "
                           "AND clock_pct IS NULL", (r["clock_pct"], fid, item)).rowcount
        if not cur:
            cur = conn.execute("INSERT OR IGNORE INTO factory_recipe(factory_id, item, clock_pct) "
                               "VALUES (?,?,?)", (fid, item, r["clock_pct"])).rowcount
        n += cur
    return n


def _import_container(conn, src, world_id, *, ref, name, status, outputs_sql, choices_sql,
                      clock_sql, sloop_sql, key, stats, merge_plan_clocks=False):
    existing = conn.execute("SELECT id FROM factory WHERE source_ref = ?", (ref,)).fetchone()
    if existing:
        stats["skipped"] += 1
        if merge_plan_clocks:
            stats["backfilled"] = stats.get("backfilled", 0) + _backfill_plan_clocks(conn, src, existing["id"])
        return
    fid = conn.execute(
        "INSERT INTO factory(world_id, name, status, origin, source_ref) VALUES (?,?,?, 'import', ?)",
        (world_id, name, status, ref)).lastrowid
    for r in src.execute(outputs_sql, (key,)):
        conn.execute("INSERT INTO factory_output(factory_id, item, rate_per_min) VALUES (?,?,?)",
                     (fid, _item(r["product"]), r["rate_per_min"]))
    over = {}
    for r in src.execute(choices_sql, (key,)):
        over.setdefault(_item(r["product"]), {})["recipe"] = _recipe(r["recipe"])
    for r in src.execute(clock_sql, (key,)):
        over.setdefault(_item(r["product"]), {})["clock_pct"] = r["clock_pct"]
    if merge_plan_clocks:
        for r in _plan_clocks(src):
            over.setdefault(_item(r["product"]), {}).setdefault("clock_pct", r["clock_pct"])
    for r in src.execute(sloop_sql, (key,)):
        item = _item(r["product"])
        over.setdefault(item, {})["sloops"] = _full_slots(item, over.setdefault(item, {}).get("recipe")) if r["slooped"] else 0
    for item, o in over.items():
        conn.execute("INSERT INTO factory_recipe(factory_id, item, recipe, clock_pct, sloops) "
                     "VALUES (?,?,?,?,?)",
                     (fid, item, o.get("recipe"), o.get("clock_pct"), o.get("sloops")))
    stats["factories"] += 1


def _import_resources(conn, src, wid, stats):
    """1.x's per-plan resource node counts -> world_resource (first plan = the active one). Insert-only."""
    from core import budget
    row = src.execute("SELECT id FROM plans ORDER BY id LIMIT 1").fetchone()
    if not row:
        return
    for r in src.execute("SELECT * FROM resources WHERE plan_id=? ORDER BY id", (row["id"],)):
        item = _item(r["resource"])
        ex = budget.default_extractor(item)
        tier = r["miner_tier"] or ""
        if ex and ex.startswith("Build_MinerMk") and tier.startswith("Mk."):
            ex = f"Build_MinerMk{tier[3:]}_C"
        n = conn.execute(
            "INSERT OR IGNORE INTO world_resource(world_id,resource,pure,normal,impure,miner,clock_pct) "
            "VALUES (?,?,?,?,?,?,250)", (wid, item, r["pure"], r["normal"], r["impure"], ex)).rowcount
        stats["resources"] = stats.get("resources", 0) + n


def run(src_path: Path | str, dest_path: Path | str | None = None) -> dict:
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    db.migrate(dest_path)
    conn = db.connect(dest_path)
    stats = {"factories": 0, "power_plants": 0, "skipped": 0, "archived_plans": 0}
    try:
        with conn:
            wid = _world(conn)
            for f in src.execute("SELECT id, name FROM factories ORDER BY id"):
                _import_container(
                    conn, src, wid, ref=f"1x:factory:{f['id']}", name=f["name"], status="planned",
                    outputs_sql="SELECT product, rate_per_min FROM factory_targets WHERE factory_id=?",
                    choices_sql="SELECT product, recipe FROM factory_choices WHERE factory_id=?",
                    clock_sql="SELECT product, clock_pct FROM factory_clock_overrides WHERE factory_id=?",
                    sloop_sql="SELECT product, slooped FROM factory_sloop_overrides WHERE factory_id=?",
                    key=f["id"], stats=stats, merge_plan_clocks=True)
            # the 1.x scratchpad(s) -> archived draft factory
            for p in src.execute("SELECT id FROM plans ORDER BY id"):
                before = stats["factories"]
                _import_container(
                    conn, src, wid, ref=f"1x:plan:{p['id']}", name="1.x plan (archived)",
                    status="archived",
                    outputs_sql="SELECT product, rate_per_min FROM targets WHERE plan_id=?",
                    choices_sql="SELECT product, recipe FROM recipe_choices WHERE plan_id=?",
                    clock_sql="SELECT product, clock_pct FROM clock_overrides WHERE plan_id=?",
                    sloop_sql="SELECT product, slooped FROM sloop_overrides WHERE plan_id=?",
                    key=p["id"], stats=stats)
                stats["archived_plans"] += stats["factories"] - before
            _import_resources(conn, src, wid, stats)
            for pp in src.execute("SELECT * FROM power_plants ORDER BY id"):
                ref = f"1x:power_plant:{pp['id']}"
                if conn.execute("SELECT 1 FROM power_plant WHERE source_ref=?", (ref,)).fetchone():
                    stats["skipped"] += 1
                    continue
                gen = GENERATOR_BY_NAME.get(pp["generator_type"])
                if not gen:
                    raise Unmapped(f"unknown generator '{pp['generator_type']}'")
                conn.execute(
                    "INSERT INTO power_plant(world_id,name,generator,fuel,count,clock_pct,source_ref) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (wid, pp["name"], gen, _item(pp["fuel_type"]), pp["count"], pp["clock_pct"], ref))
                stats["power_plants"] += 1
    finally:
        conn.close()
        src.close()
    return stats


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else Path.home() / "sf-inputs/planner-1x.db"
    print(run(path))
