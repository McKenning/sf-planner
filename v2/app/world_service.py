"""World-level services: overview/ledger, top-down goals, split into factories, auto flows."""
from app import factory_service as fs
from core import budget, ledger, solver
from core import gamedata as gd
from core import recipes as rc

COUNTED = ("planned", "built")  # statuses that count towards the ledger and power


def world_id(conn) -> int:
    w = conn.execute("SELECT id FROM world ORDER BY id LIMIT 1").fetchone()
    if w:
        return w["id"]
    return conn.execute("INSERT INTO world(name, game_build) VALUES ('Main', ?)", (gd.load()["build"],)).lastrowid


def factory_summaries(conn, wid: int) -> list[dict]:
    out = []
    for f in conn.execute("SELECT * FROM factory WHERE world_id=? ORDER BY id", (wid,)):
        outputs, _c, _o, res = fs.solve_factory(conn, f["id"])
        out.append({"f": f, "id": f["id"], "name": f["name"], "status": f["status"], "outputs": outputs,
                    "raws": res["raws"], "surplus": res["surplus"], "power_mw": res["power_mw"],
                    "sloops": res["sloops_total"], "machines": sum(l["count"] for l in res["lines"]),
                    "warnings": res["warnings"], "externals": fs.external_inputs(conn, f["id"])})
    return out


def available(conn, wid: int) -> dict:
    av = {}
    for r in conn.execute("SELECT * FROM world_resource WHERE world_id=?", (wid,)):
        av[r["resource"]] = budget.available_per_min(r["resource"], r["pure"], r["normal"], r["impure"],
                                                     r["miner"], r["clock_pct"])
    return av


def plants(conn, wid: int) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM power_plant WHERE world_id=? ORDER BY id", (wid,))]


def overview(conn, wid: int) -> dict:
    facs = [f for f in factory_summaries(conn, wid)]
    live = [f for f in facs if f["status"] in COUNTED]
    pl = plants(conn, wid)
    goals = [dict(g) for g in conn.execute("SELECT * FROM world_goal WHERE world_id=?", (wid,))]
    item_goals = [g for g in goals if g["item"]]
    av = available(conn, wid)
    raw_res = {i for i, v in gd.items().items() if v["raw"]}
    led = ledger.build_ledger(live, item_goals, pl, raw_res)
    raw_demand = {}
    for f in live:
        for item, r in f["raws"].items():
            if item in raw_res:
                raw_demand[item] = raw_demand.get(item, 0.0) + r
    for p in pl:  # generator fuel/water that are raw resources (coal, water, ...)
        st = ledger.generator_stats(p)
        if p["fuel"] in raw_res:
            raw_demand[p["fuel"]] = raw_demand.get(p["fuel"], 0.0) + st["fuel_per_min"]
        if st["supplemental"] in raw_res:
            raw_demand[st["supplemental"]] = raw_demand.get(st["supplemental"], 0.0) + st["supplemental_per_min"]
    gen_mw = sum(ledger.generator_stats(p)["mw"] for p in pl)
    used_mw = sum(f["power_mw"] for f in live)
    power_goal = sum(g["power_mw"] or 0 for g in goals if g["power_mw"])
    warnings = []
    for f in facs:
        for w in f["warnings"]:
            warnings.append(f"{f['name']}: {w}")
    for b in ledger.raw_budget(raw_demand, av):
        if b["over"]:
            warnings.append(f"Over budget: {fs.name(b['item'])} needs {b['demand']:.0f}/min, nodes give {b['available']:.0f}/min")
    if used_mw > gen_mw:
        warnings.append(f"Power: factories use {used_mw:.0f} MW but plants generate {gen_mw:.0f} MW")
    for l in led:
        if l["net"] < -ledger.EPS:
            warnings.append(f"Deficit: {fs.name(l['item'])} short by {-l['net']:.2f}/min")
    unflowed = [f for f in facs if f["status"] in COUNTED and f["externals"]]
    flows = list(conn.execute("SELECT * FROM flow WHERE world_id=?", (wid,)))
    for f in unflowed:
        for item in f["externals"]:
            got = sum(x["rate_per_min"] for x in flows if x["to_factory"] == f["id"] and x["item"] == item)
            need = f["raws"].get(item, 0.0)
            if need - got > ledger.EPS:
                warnings.append(f"Unbalanced flow: {f['name']} needs {fs.name(item)} {need:.2f}/min, "
                                f"only {got:.2f}/min arrives")
    return {"factories": facs, "ledger": led, "budget": ledger.raw_budget(raw_demand, av),
            "gen_mw": gen_mw, "used_mw": used_mw, "power_goal": power_goal, "goals": goals,
            "warnings": warnings, "plants": pl}


# ---------- top-down ----------

def goal_tree(conn, wid: int):
    """Solve the world's item goals with the world's default recipes."""
    goals = {}
    for g in conn.execute("SELECT item, rate_per_min FROM world_goal WHERE world_id=? AND item IS NOT NULL", (wid,)):
        goals[g["item"]] = goals.get(g["item"], 0.0) + g["rate_per_min"]
    choices = {r["item"]: r["recipe"] for r in conn.execute(
        "SELECT item, recipe FROM world_recipe WHERE world_id=?", (wid,))}
    res = solver.solve(goals, choices)
    assigned = {}
    for r in conn.execute("SELECT fo.item, f.id, f.name FROM factory_output fo JOIN factory f ON f.id=fo.factory_id "
                          "WHERE f.world_id=? AND f.status != 'archived'", (wid,)):
        assigned.setdefault(r["item"], []).append((r["id"], r["name"]))
    return goals, choices, res, assigned


def descendants(res: dict, item: str) -> set:
    """Items made (by lines in the world solve) below `item`, excluding raw resources."""
    maker = {i: l for l in res["lines"] for i in l["items"]}
    seen, stack = set(), [item]
    while stack:
        i = stack.pop()
        l = maker.get(i)
        if not l:
            continue
        for inp in l["inputs"]:
            if inp in maker and inp not in seen and inp != item:
                seen.add(inp)
                stack.append(inp)
    return seen


def assign(conn, wid: int, item: str, factory_id: int | None, new_name: str | None, subtree: bool) -> int:
    """Split step: make `factory` responsible for `item` at the world's required rate.
    subtree=False: the factory builds only this item; its direct ingredients become external inputs.
    subtree=True: it also builds everything below, except items other factories already make."""
    goals, choices, res, assigned = goal_tree(conn, wid)
    rate = res["item_rates"].get(item, 0.0)
    if rate <= ledger.EPS:
        raise ValueError("The world goals do not need that item")
    maker = {i: l for l in res["lines"] for i in l["items"]}
    if factory_id is None:
        if not (new_name or "").strip():
            raise ValueError("Pick a factory or give a new factory name")
        factory_id = conn.execute("INSERT INTO factory(world_id,name,status,origin) VALUES (?,?, 'planned','manual')",
                                  (wid, new_name.strip())).lastrowid
    cur = conn.execute("UPDATE factory_output SET rate_per_min=? WHERE factory_id=? AND item=?",
                       (rate, factory_id, item)).rowcount
    if not cur:
        conn.execute("INSERT INTO factory_output(factory_id,item,rate_per_min) VALUES (?,?,?)", (factory_id, item, rate))
    # keep the world's recipe choice for the chain visible to the factory (via world_recipe fallback)
    l = maker.get(item)
    below = descendants(res, item) if subtree else {i for i in (l["inputs"] if l else {}) if i in maker}
    others = {r["item"] for r in conn.execute(
        "SELECT fo.item FROM factory_output fo JOIN factory f ON f.id=fo.factory_id "
        "WHERE f.world_id=? AND f.id != ? AND f.status != 'archived'", (wid, factory_id))}
    for d in below:
        if (not subtree) or d in others:
            conn.execute("INSERT OR IGNORE INTO factory_input(factory_id,item) VALUES (?,?)", (factory_id, d))
    # the item now has a dedicated maker: every other factory that builds it internally takes it instead
    for r in conn.execute("SELECT id FROM factory WHERE world_id=? AND id != ? AND status IN ('planned','built')",
                          (wid, factory_id)).fetchall():
        outs, _c, _o, sol = fs.solve_factory(conn, r["id"])
        if item not in outs and any(item in ln["items"] for ln in sol["lines"]):
            conn.execute("INSERT OR IGNORE INTO factory_input(factory_id,item) VALUES (?,?)", (r["id"], item))
    rebuild_auto_flows(conn, wid)
    return factory_id


def rebuild_auto_flows(conn, wid: int) -> int:
    """Recreate auto flows from factory_input demand and factory output/surplus supply."""
    conn.execute("DELETE FROM flow WHERE world_id=? AND auto=1", (wid,))
    facs = [f for f in factory_summaries(conn, wid) if f["status"] in COUNTED]
    consumers, producers = [], []
    for f in facs:
        for item in f["externals"]:
            r = f["raws"].get(item, 0.0)
            if r > ledger.EPS:
                consumers.append({"factory": f["id"], "item": item, "rate": r})
        for item, r in f["outputs"].items():
            producers.append({"factory": f["id"], "item": item, "rate": r})
        for item, r in f["surplus"].items():
            producers.append({"factory": f["id"], "item": item, "rate": r})
    flows = ledger.allocate_flows(consumers, producers)
    for fl in flows:
        conn.execute("INSERT INTO flow(world_id,from_factory,to_factory,item,rate_per_min,auto) VALUES (?,?,?,?,?,1)",
                     (wid, fl["from"], fl["to"], fl["item"], fl["rate"]))
    return len(flows)
