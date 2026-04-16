"""
Satisfactory Master Planner - FastAPI backend
"""
import json
import sqlite3
import os
import socket
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sf_recipes import RECIPES, RAW_RESOURCES
from sf_data import MACHINES, RESOURCES as DEFAULT_RESOURCES, ALT_TIERS, GENERATORS
from solver import RecipeDB, solve, BUDGET_RAWS, TREAT_AS_RAW

# ----- Setup -----
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "planner.db"

app = FastAPI(title="Satisfactory Master Planner")
HOSTNAME = os.environ.get("PLANNER_HOST", socket.gethostname())
templates = Jinja2Templates(directory=str(BASE_DIR.parent / "frontend"))

db = RecipeDB(RECIPES)
MACHINE_POWER = {m: d["power"] for m, d in MACHINES.items()}


# ----- Database -----
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            rate_per_min REAL NOT NULL,
            FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS recipe_choices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            recipe TEXT NOT NULL,
            UNIQUE(plan_id, product),
            FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            resource TEXT NOT NULL,
            pure INTEGER DEFAULT 0,
            normal INTEGER DEFAULT 0,
            impure INTEGER DEFAULT 0,
            miner_tier TEXT DEFAULT 'Mk.2',
            UNIQUE(plan_id, resource),
            FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS factories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS factory_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factory_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            rate_per_min REAL NOT NULL,
            FOREIGN KEY (factory_id) REFERENCES factories(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS power_plants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            generator_type TEXT NOT NULL,
            fuel_type TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 1,
            clock_pct REAL NOT NULL DEFAULT 100,
            FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS clock_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            clock_pct REAL NOT NULL DEFAULT 100,
            UNIQUE(plan_id, product),
            FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS factory_choices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factory_id INTEGER NOT NULL,
            product TEXT NOT NULL,
            recipe TEXT NOT NULL,
            UNIQUE(factory_id, product),
            FOREIGN KEY (factory_id) REFERENCES factories(id) ON DELETE CASCADE
        );
        """)
        # Create a default plan if none exists
        cur = conn.execute("SELECT COUNT(*) c FROM plans")
        if cur.fetchone()["c"] == 0:
            conn.execute("INSERT INTO plans (name) VALUES (?)", ("Default Plan",))
            plan_id = conn.execute("SELECT id FROM plans WHERE name='Default Plan'").fetchone()["id"]
            for res, info in DEFAULT_RESOURCES.items():
                conn.execute(
                    "INSERT INTO resources (plan_id, resource, pure, normal, impure) VALUES (?,?,?,?,?)",
                    (plan_id, res, info["pure"], info["normal"], info["impure"])
                )


init_db()


# ----- Helpers -----
def get_active_plan_id(conn) -> int:
    """For now, always use the first plan. Future: cookie-based selection."""
    row = conn.execute("SELECT id FROM plans ORDER BY id LIMIT 1").fetchone()
    return row["id"] if row else None


# Miner rates at 250% overclock (base * 2.5)
# Mk.1: 60/120/300  Mk.2: 120/240/600  Mk.3: 240/480/1200 (capped at belt speed in-game)
MINER_RATES_PER_PURITY = {
    "Mk.1": {"pure": 300, "normal": 150, "impure": 75},
    "Mk.2": {"pure": 600, "normal": 300, "impure": 150},
    "Mk.3": {"pure": 1200, "normal": 600, "impure": 300},
}
# Oil Extractor / Resource Well at 250% overclock (base 120 * 2.5 = 300 per normal)
EXTRACTOR_RATES = {"pure": 600, "normal": 300, "impure": 150}


def calculate_available(resource: str, pure: int, normal: int, impure: int, tier: str) -> float:
    """Calculate items/min available given node counts and miner tier."""
    if resource == "Water":
        # Water Extractors are effectively unlimited; show a high but finite number
        return 999999
    if resource in ("Crude Oil", "Nitrogen Gas"):
        rates = EXTRACTOR_RATES
    else:
        rates = MINER_RATES_PER_PURITY.get(tier, MINER_RATES_PER_PURITY["Mk.2"])
    return pure * rates["pure"] + normal * rates["normal"] + impure * rates["impure"]


def load_plan_state(plan_id: int) -> dict:
    """Load all of a plan's state from DB."""
    with get_db() as conn:
        plan = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        targets = conn.execute(
            "SELECT id, product, rate_per_min FROM targets WHERE plan_id=? ORDER BY id",
            (plan_id,)
        ).fetchall()
        choices = conn.execute(
            "SELECT product, recipe FROM recipe_choices WHERE plan_id=?",
            (plan_id,)
        ).fetchall()
        resources = conn.execute(
            "SELECT resource, pure, normal, impure, miner_tier FROM resources WHERE plan_id=? ORDER BY id",
            (plan_id,)
        ).fetchall()
        clocks = conn.execute(
            "SELECT product, clock_pct FROM clock_overrides WHERE plan_id=?",
            (plan_id,)
        ).fetchall()
        pplants = conn.execute(
            "SELECT * FROM power_plants WHERE plan_id=? ORDER BY id",
            (plan_id,)
        ).fetchall()
    return {
        "plan": dict(plan) if plan else None,
        "targets": [dict(t) for t in targets],
        "choices": {c["product"]: c["recipe"] for c in choices},
        "clocks": {c["product"]: c["clock_pct"] for c in clocks},
        "resources": [dict(r) for r in resources],
        "power_plants": [dict(pp) for pp in pplants],
    }


def compute_plan(plan_id: int) -> dict:
    state = load_plan_state(plan_id)
    targets = {t["product"]: t["rate_per_min"] for t in state["targets"]}
    result = solve(targets, state["choices"], db, MACHINE_POWER, state.get("clocks", {}))

    # Compute available raw resources
    available = {}
    for r in state["resources"]:
        available[r["resource"]] = calculate_available(
            r["resource"], r["pure"], r["normal"], r["impure"], r["miner_tier"]
        )

    # Build budget table
    budget = []
    for raw in BUDGET_RAWS:
        demand = result["raws"].get(raw, 0)
        avail = available.get(raw, 0)
        surplus = avail - demand
        util = (demand / avail * 100) if avail > 0 else 0
        budget.append({
            "resource": raw,
            "demand": demand,
            "available": avail,
            "surplus": surplus,
            "utilization": util,
            "ok": surplus >= 0,
        })

    # Compute power plant stats
    pp_stats = []
    pp_total_generation = 0
    pp_fuel_demand = {}  # fuel -> total per min needed
    for pp in state.get("power_plants", []):
        gen = GENERATORS.get(pp["generator_type"], {})
        base_mw = gen.get("power_mw", 0)
        fuel_rate = gen.get("fuels", {}).get(pp["fuel_type"], 0)
        water_rate = gen.get("water_per_min", 0)
        clock = pp["clock_pct"] / 100.0
        total_mw = base_mw * pp["count"] * clock
        total_fuel = fuel_rate * pp["count"] * clock
        total_water = water_rate * pp["count"] * clock
        pp_total_generation += total_mw
        pp_fuel_demand[pp["fuel_type"]] = pp_fuel_demand.get(pp["fuel_type"], 0) + total_fuel
        if total_water > 0:
            pp_fuel_demand["Water"] = pp_fuel_demand.get("Water", 0) + total_water
        pp_stats.append({
            **pp,
            "mw_each": base_mw * clock,
            "mw_total": total_mw,
            "fuel_per_min": total_fuel,
            "water_per_min": total_water,
        })

    return {
        "state": state,
        "result": result,
        "budget": budget,
        "available": available,
        "pp_stats": pp_stats,
        "pp_total_generation": pp_total_generation,
        "pp_fuel_demand": pp_fuel_demand,
    }


# ----- Routes -----
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with get_db() as conn:
        plan_id = get_active_plan_id(conn)
    data = compute_plan(plan_id)

    # Build choices_data: only include products with >1 recipe option
    # (single-recipe products are noise — nothing to choose)
    choices_data = {}
    for product in sorted(db.producers.keys()):
        if product in TREAT_AS_RAW:
            continue
        opts = db.all_choices_for(product)
        if len(opts) < 2:
            continue
        default = db.default_recipe(product)
        choices_data[product] = {
            "default": default,
            "options": [
                {
                    "recipe": rn,
                    "tier": ALT_TIERS.get(rn, ""),
                    "is_alternate": rn.startswith("Alternate:"),
                }
                for rn in opts
            ],
        }

    with get_db() as conn:
        factories_list = load_factories_summary(conn)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "plan_id": plan_id,
        "state": data["state"],
        "result": data["result"],
        "budget": data["budget"],
        "all_products": sorted(db.producers.keys()),
        "choices_data": choices_data,
        "machines_info": MACHINES,
        "factories": factories_list,
        "generators": GENERATORS,
        "pp_stats": data["pp_stats"],
        "pp_total_generation": data["pp_total_generation"],
        "pp_fuel_demand": data["pp_fuel_demand"],
        "hostname": HOSTNAME,
    })


@app.post("/api/targets/add")
def add_target(plan_id: int = Form(...), product: str = Form(...), rate: float = Form(...)):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO targets (plan_id, product, rate_per_min) VALUES (?,?,?)",
            (plan_id, product.strip(), rate)
        )
    return RedirectResponse("/", status_code=303)


@app.post("/api/targets/{target_id}/delete")
def delete_target(target_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM targets WHERE id=?", (target_id,))
    return RedirectResponse("/", status_code=303)


@app.post("/api/targets/{target_id}/update")
def update_target(target_id: int, rate: float = Form(...)):
    with get_db() as conn:
        conn.execute("UPDATE targets SET rate_per_min=? WHERE id=?", (rate, target_id))
    return RedirectResponse("/", status_code=303)


@app.post("/api/choices/set")
def set_choice(plan_id: int = Form(...), product: str = Form(...), recipe: str = Form(...)):
    with get_db() as conn:
        # Upsert
        existing = conn.execute(
            "SELECT id FROM recipe_choices WHERE plan_id=? AND product=?",
            (plan_id, product)
        ).fetchone()
        if existing:
            conn.execute("UPDATE recipe_choices SET recipe=? WHERE id=?", (recipe, existing["id"]))
        else:
            conn.execute(
                "INSERT INTO recipe_choices (plan_id, product, recipe) VALUES (?,?,?)",
                (plan_id, product, recipe)
            )
    return RedirectResponse("/#choices", status_code=303)


@app.post("/api/choices/reset")
def reset_choice(plan_id: int = Form(...), product: str = Form(...)):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM recipe_choices WHERE plan_id=? AND product=?",
            (plan_id, product)
        )
    return RedirectResponse("/#choices", status_code=303)


@app.post("/api/resources/update")
def update_resource(resource_id: int = Form(...),
                    pure: int = Form(0),
                    normal: int = Form(0),
                    impure: int = Form(0)):
    with get_db() as conn:
        conn.execute(
            "UPDATE resources SET pure=?, normal=?, impure=? WHERE id=?",
            (pure, normal, impure, resource_id)
        )
    return RedirectResponse("/#resources", status_code=303)


@app.post("/api/resources/tier")
def update_tier(plan_id: int = Form(...), tier: str = Form(...)):
    with get_db() as conn:
        conn.execute("UPDATE resources SET miner_tier=? WHERE plan_id=?", (tier, plan_id))
    return RedirectResponse("/#resources", status_code=303)


@app.post("/api/targets/clear")
def clear_targets(plan_id: int = Form(...)):
    with get_db() as conn:
        conn.execute("DELETE FROM targets WHERE plan_id=?", (plan_id,))
    return RedirectResponse("/", status_code=303)


@app.post("/api/choices/clear")
def clear_choices(plan_id: int = Form(...)):
    with get_db() as conn:
        conn.execute("DELETE FROM recipe_choices WHERE plan_id=?", (plan_id,))
    return RedirectResponse("/#choices", status_code=303)


@app.get("/api/recipe/{product}/options")
def recipe_options(product: str):
    """JSON: list of recipes that produce this product."""
    options = []
    for recipe_name in db.all_choices_for(product):
        rec = db.recipes_by_name[recipe_name]
        out_qty = next((q for o, q in rec["outputs"] if o == product), rec["outputs"][0][1])
        options.append({
            "recipe": recipe_name,
            "machine": rec["machine"],
            "duration": rec["duration"],
            "out_per_min": out_qty * 60 / rec["duration"],
            "tier": ALT_TIERS.get(recipe_name, ""),
            "is_alternate": recipe_name.startswith("Alternate:"),
            "inputs": rec["inputs"],
        })
    return options


@app.get("/api/plan/export")
def export_plan():
    """Export current plan as JSON."""
    with get_db() as conn:
        plan_id = get_active_plan_id(conn)
    state = load_plan_state(plan_id)
    return JSONResponse(state)



@app.post("/api/clock/set")
def set_clock(plan_id: int = Form(...), product: str = Form(...), clock_pct: float = Form(...)):
    """Set target clock speed for a product."""
    clock_pct = max(1, min(250, clock_pct))  # clamp 1-250%
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM clock_overrides WHERE plan_id=? AND product=?",
            (plan_id, product)
        ).fetchone()
        if abs(clock_pct - 100.0) < 0.01:
            # 100% is default, just delete the override
            if existing:
                conn.execute("DELETE FROM clock_overrides WHERE id=?", (existing["id"],))
        elif existing:
            conn.execute("UPDATE clock_overrides SET clock_pct=? WHERE id=?", (clock_pct, existing["id"]))
        else:
            conn.execute(
                "INSERT INTO clock_overrides (plan_id, product, clock_pct) VALUES (?,?,?)",
                (plan_id, product, clock_pct)
            )
    return RedirectResponse("/#chain", status_code=303)



# ----- Power plant routes -----
@app.post("/api/powerplants/add")
def add_power_plant(plan_id: int = Form(...),
                    generator_type: str = Form(...),
                    fuel_type: str = Form(...),
                    count: int = Form(1),
                    clock_pct: float = Form(100),
                    pp_name: str = Form("")):
    gen = GENERATORS.get(generator_type)
    if not gen or fuel_type not in gen["fuels"]:
        return RedirectResponse("/", status_code=303)
    clock_pct = max(1, min(250, clock_pct))
    count = max(1, count)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO power_plants (plan_id, name, generator_type, fuel_type, count, clock_pct) VALUES (?,?,?,?,?,?)",
            (plan_id, pp_name.strip(), generator_type, fuel_type, count, clock_pct)
        )
    return RedirectResponse("/#power", status_code=303)


@app.post("/api/powerplants/{pp_id}/update")
def update_power_plant(pp_id: int,
                       count: int = Form(None),
                       clock_pct: float = Form(None),
                       fuel_type: str = Form(None)):
    with get_db() as conn:
        if count is not None:
            conn.execute("UPDATE power_plants SET count=? WHERE id=?", (max(1, count), pp_id))
        if clock_pct is not None:
            conn.execute("UPDATE power_plants SET clock_pct=? WHERE id=?", (max(1, min(250, clock_pct)), pp_id))
        if fuel_type is not None:
            conn.execute("UPDATE power_plants SET fuel_type=? WHERE id=?", (fuel_type, pp_id))
    return RedirectResponse("/#power", status_code=303)


@app.post("/api/powerplants/{pp_id}/delete")
def delete_power_plant(pp_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM power_plants WHERE id=?", (pp_id,))
    return RedirectResponse("/#power", status_code=303)


# ----- Factory helpers -----
def load_factories_summary(conn) -> list:
    """Load all factories with their target summaries."""
    factories = conn.execute(
        "SELECT * FROM factories ORDER BY created_at DESC"
    ).fetchall()
    result = []
    for f in factories:
        targets = conn.execute(
            "SELECT product, rate_per_min FROM factory_targets WHERE factory_id=? ORDER BY id",
            (f["id"],)
        ).fetchall()
        choices_count = conn.execute(
            "SELECT COUNT(*) c FROM factory_choices WHERE factory_id=?",
            (f["id"],)
        ).fetchone()["c"]
        # Load power plants for this factory's plan (via plan_id reference)
        result.append({
            "id": f["id"],
            "name": f["name"],
            "created_at": f["created_at"],
            "targets": [dict(t) for t in targets],
            "choices_count": choices_count,
        })
    return result


# ----- Factory routes -----
@app.post("/api/factories/save")
def save_factory(plan_id: int = Form(...), factory_name: str = Form(...)):
    """Snapshot the current plan targets + choices into a named factory."""
    if not factory_name.strip():
        return RedirectResponse("/", status_code=303)
    with get_db() as conn:
        conn.execute("INSERT INTO factories (name) VALUES (?)", (factory_name.strip(),))
        fid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        targets = conn.execute(
            "SELECT product, rate_per_min FROM targets WHERE plan_id=?", (plan_id,)
        ).fetchall()
        for t in targets:
            conn.execute(
                "INSERT INTO factory_targets (factory_id, product, rate_per_min) VALUES (?,?,?)",
                (fid, t["product"], t["rate_per_min"])
            )
        choices = conn.execute(
            "SELECT product, recipe FROM recipe_choices WHERE plan_id=?", (plan_id,)
        ).fetchall()
        for c in choices:
            conn.execute(
                "INSERT INTO factory_choices (factory_id, product, recipe) VALUES (?,?,?)",
                (fid, c["product"], c["recipe"])
            )
    return RedirectResponse("/", status_code=303)


@app.post("/api/factories/{factory_id}/delete")
def delete_factory(factory_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM factories WHERE id=?", (factory_id,))
    return RedirectResponse("/", status_code=303)


@app.post("/api/factories/{factory_id}/load")
def load_factory(factory_id: int):
    """Load a factory back into the active plan for editing."""
    with get_db() as conn:
        plan_id = get_active_plan_id(conn)
        factory = conn.execute("SELECT * FROM factories WHERE id=?", (factory_id,)).fetchone()
        if not factory:
            return RedirectResponse("/", status_code=303)
        conn.execute("DELETE FROM targets WHERE plan_id=?", (plan_id,))
        conn.execute("DELETE FROM recipe_choices WHERE plan_id=?", (plan_id,))
        ftargets = conn.execute(
            "SELECT product, rate_per_min FROM factory_targets WHERE factory_id=?",
            (factory_id,)
        ).fetchall()
        for t in ftargets:
            conn.execute(
                "INSERT INTO targets (plan_id, product, rate_per_min) VALUES (?,?,?)",
                (plan_id, t["product"], t["rate_per_min"])
            )
        fchoices = conn.execute(
            "SELECT product, recipe FROM factory_choices WHERE factory_id=?",
            (factory_id,)
        ).fetchall()
        for c in fchoices:
            conn.execute(
                "INSERT INTO recipe_choices (plan_id, product, recipe) VALUES (?,?,?)",
                (plan_id, c["product"], c["recipe"])
            )
    return RedirectResponse("/", status_code=303)


@app.get("/world", response_class=HTMLResponse)
def world_view(request: Request):
    """Aggregate all factories into one combined world view."""
    with get_db() as conn:
        plan_id = get_active_plan_id(conn)
        factories_list = load_factories_summary(conn)

        merged_targets = {}
        merged_choices = {}
        merged_clocks = {}
        for f in factories_list:
            ftargets = conn.execute(
                "SELECT product, rate_per_min FROM factory_targets WHERE factory_id=?",
                (f["id"],)
            ).fetchall()
            for t in ftargets:
                merged_targets[t["product"]] = merged_targets.get(t["product"], 0) + t["rate_per_min"]
            fchoices = conn.execute(
                "SELECT product, recipe FROM factory_choices WHERE factory_id=?",
                (f["id"],)
            ).fetchall()
            for c in fchoices:
                merged_choices[c["product"]] = c["recipe"]


        result = solve(merged_targets, merged_choices, db, MACHINE_POWER, merged_clocks)

        resources = conn.execute(
            "SELECT resource, pure, normal, impure, miner_tier FROM resources WHERE plan_id=? ORDER BY id",
            (plan_id,)
        ).fetchall()

    available = {}
    for r in resources:
        available[r["resource"]] = calculate_available(
            r["resource"], r["pure"], r["normal"], r["impure"], r["miner_tier"]
        )

    budget = []
    for raw in BUDGET_RAWS:
        demand = result["raws"].get(raw, 0)
        avail = available.get(raw, 0)
        surplus = avail - demand
        util = (demand / avail * 100) if avail > 0 else 0
        budget.append({
            "resource": raw, "demand": demand, "available": avail,
            "surplus": surplus, "utilization": util, "ok": surplus >= 0,
        })

    return templates.TemplateResponse("world.html", {
        "request": request,
        "factories": factories_list,
        "result": result,
        "budget": budget,
        "merged_targets": merged_targets,
        "total_power": result["total_power"],
        "machines_info": MACHINES,
        "hostname": HOSTNAME,
    })



@app.get("/power", response_class=HTMLResponse)
def power_budget(request: Request):
    """Power budget: all factories consumption vs all power plants generation."""
    with get_db() as conn:
        plan_id = get_active_plan_id(conn)
        factories_list = load_factories_summary(conn)

        # Get power plants from active plan
        pplants = conn.execute(
            "SELECT * FROM power_plants WHERE plan_id=? ORDER BY id", (plan_id,)
        ).fetchall()

    # Compute factory power consumption per factory
    factory_power = []
    total_consumption = 0
    for f in factories_list:
        # Solve each factory individually to get its power consumption
        ftargets = {t["product"]: t["rate_per_min"] for t in f["targets"]}
        # Load factory choices
        with get_db() as conn:
            fchoices_rows = conn.execute(
                "SELECT product, recipe FROM factory_choices WHERE factory_id=?",
                (f["id"],)
            ).fetchall()
        fchoices = {c["product"]: c["recipe"] for c in fchoices_rows}
        fresult = solve(ftargets, fchoices, db, MACHINE_POWER)
        factory_power.append({
            "name": f["name"],
            "power_mw": fresult["total_power"],
            "targets": f["targets"],
        })
        total_consumption += fresult["total_power"]

    # Compute power plant generation
    pp_stats = []
    total_generation = 0
    pp_fuel_demand = {}
    for pp in pplants:
        pp = dict(pp)
        gen = GENERATORS.get(pp["generator_type"], {})
        base_mw = gen.get("power_mw", 0)
        fuel_rate = gen.get("fuels", {}).get(pp["fuel_type"], 0)
        water_rate = gen.get("water_per_min", 0)
        clock = pp["clock_pct"] / 100.0
        total_mw = base_mw * pp["count"] * clock
        total_fuel = fuel_rate * pp["count"] * clock
        total_water = water_rate * pp["count"] * clock
        total_generation += total_mw
        pp_fuel_demand[pp["fuel_type"]] = pp_fuel_demand.get(pp["fuel_type"], 0) + total_fuel
        if total_water > 0:
            pp_fuel_demand["Water"] = pp_fuel_demand.get("Water", 0) + total_water
        pp_stats.append({
            **pp,
            "mw_each": base_mw * clock,
            "mw_total": total_mw,
            "fuel_per_min": total_fuel,
        })

    return templates.TemplateResponse("power.html", {
        "request": request,
        "factory_power": factory_power,
        "total_consumption": total_consumption,
        "pp_stats": pp_stats,
        "total_generation": total_generation,
        "net_power": total_generation - total_consumption,
        "pp_fuel_demand": pp_fuel_demand,
        "generators": GENERATORS,
        "hostname": HOSTNAME,
    })


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ----- Catch-all: redirect stray GETs on POST-only API routes back home -----
@app.get("/api/{path:path}")
def api_catch_all(path: str):
    return RedirectResponse("/", status_code=303)
