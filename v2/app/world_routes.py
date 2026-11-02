"""World pages: home (budget/power/ledger), goals + split, flows, resources, power plants."""
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import db
from app import validate as vd
from app import factory_service as fs
from app import world_service as ws
from app.factory_routes import _item_by_name
from core import gamedata as gd
from core import ledger
from core import recipes as rc

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
from app import fmt  # noqa: E402
fmt.install(templates)
TRANSPORTS = ("belt", "train", "drone", "truck")


def _go(path):
    return RedirectResponse(path, status_code=303)


def _page(request, tpl, **ctx):
    return templates.TemplateResponse(request, tpl, ctx)


def _open():
    conn = db.connect()
    return conn, ws.world_id(conn)


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn, wid = _open()
    try:
        ov = ws.overview(conn, wid)
        w = conn.execute("SELECT * FROM world WHERE id=?", (wid,)).fetchone()
        flows = [dict(f) for f in conn.execute("SELECT * FROM flow WHERE world_id=?", (wid,))]
        names = {f["id"]: f["name"] for f in ov["factories"]}
        for f in flows:
            f["from_name"], f["to_name"] = names.get(f["from_factory"]), names.get(f["to_factory"])
        surplus_factories = [{"id": f["id"], "name": f["name"]} for f in ov["factories"]
                             if f["status"] in ws.COUNTED]
    finally:
        conn.close()
    return _page(request, "home.html", nav="world", w=w, ov=ov, flows=flows, name=fs.name,
                 build=gd.load(), factories=surplus_factories, inf=float("inf"))


# ---------- goals + split ----------

@router.get("/goals", response_class=HTMLResponse)
def goals(request: Request):
    conn, wid = _open()
    try:
        goals_, choices, res, assigned = ws.goal_tree(conn, wid)
        p = fs.present(res)
        av = ws.available(conn, wid)
        raw_rows = ledger.raw_budget({k: v for k, v in res["raws"].items()}, av)
        goal_rows = [dict(g) for g in conn.execute("SELECT * FROM world_goal WHERE world_id=? ORDER BY id", (wid,))]
        facs = [dict(f) for f in conn.execute(
            "SELECT id, name FROM factory WHERE world_id=? AND status IN ('planned','built','draft') ORDER BY name", (wid,))]
        lines = []
        for l in p["lines"]:
            it = l["items"][0]
            lines.append({**l, "item": it, "rate": res["item_rates"].get(it, 0.0),
                          "assigned": assigned.get(it, []),
                          "options": fs.recipe_options(it, res["item_rates"].get(it) or 1.0, choices.get(it))})
        lines.sort(key=lambda l: (-l["stage"], l["item_names"][0]))
        item_names = sorted(gd.items()[i]["name"] for i in rc.producers() if i in gd.items())
    finally:
        conn.close()
    return _page(request, "goals.html", nav="goals", goals=goal_rows, lines=lines, raws=raw_rows,
                 res=p, facs=facs, item_names=item_names, name=fs.name, inf=float("inf"))


@router.post("/goals/add")
def goal_add(item: str = Form(...), rate: float = Form(...)):
    vd.rate(rate)
    cls = _item_by_name(item)
    conn, wid = _open()
    try:
        with conn:
            cur = conn.execute("UPDATE world_goal SET rate_per_min=? WHERE world_id=? AND item=?", (rate, wid, cls)).rowcount
            if not cur:
                conn.execute("INSERT INTO world_goal(world_id,item,rate_per_min) VALUES (?,?,?)", (wid, cls, rate))
    finally:
        conn.close()
    return _go("/goals")


@router.post("/goals/power")
def goal_power(mw: float = Form(...)):
    vd.megawatts(mw)
    conn, wid = _open()
    try:
        with conn:
            conn.execute("DELETE FROM world_goal WHERE world_id=? AND power_mw IS NOT NULL", (wid,))
            conn.execute("INSERT INTO world_goal(world_id,power_mw) VALUES (?,?)", (wid, mw))
    finally:
        conn.close()
    return _go("/goals")


@router.post("/goals/delete")
def goal_delete(goal_id: int = Form(...)):
    conn, wid = _open()
    try:
        with conn:
            conn.execute("DELETE FROM world_goal WHERE id=? AND world_id=?", (goal_id, wid))
    finally:
        conn.close()
    return _go("/goals")


@router.post("/goals/recipe")
def world_recipe(item: str = Form(...), recipe: str = Form("")):
    if item not in gd.items():
        raise HTTPException(400, "Unknown item")
    if recipe:
        r = gd.recipes().get(recipe)
        if not r or not any(o["item"] == item for o in r["outputs"]):
            raise HTTPException(400, "Recipe does not make that item")
    conn, wid = _open()
    try:
        with conn:
            if recipe:
                conn.execute("INSERT INTO world_recipe(world_id,item,recipe) VALUES (?,?,?) "
                             "ON CONFLICT(world_id,item) DO UPDATE SET recipe=excluded.recipe", (wid, item, recipe))
            else:
                conn.execute("DELETE FROM world_recipe WHERE world_id=? AND item=?", (wid, item))
    finally:
        conn.close()
    return _go("/goals")


@router.post("/goals/assign")
def goal_assign(item: str = Form(...), factory_id: str = Form(""), new_name: str = Form(""),
                subtree: str = Form("")):
    conn, wid = _open()
    try:
        with conn:
            try:
                fid = int(factory_id) if factory_id.strip() else None
            except ValueError:
                raise HTTPException(400, "Pick a factory from the list")
            if fid is not None:
                f = conn.execute("SELECT status FROM factory WHERE id=? AND world_id=?", (fid, wid)).fetchone()
                if not f or f["status"] == "archived":
                    raise HTTPException(400, "Pick an editable factory")
            try:
                fid = ws.assign(conn, wid, item, fid, new_name, bool(subtree))
            except ValueError as e:
                raise HTTPException(400, str(e))
    finally:
        conn.close()
    return _go(f"/factory/{fid}")


# ---------- flows ----------

@router.get("/flows", response_class=HTMLResponse)
def flows_page(request: Request):
    conn, wid = _open()
    try:
        names = {f["id"]: f["name"] for f in conn.execute("SELECT id, name FROM factory WHERE world_id=?", (wid,))}
        flows = [dict(f, from_name=names.get(f["from_factory"], "—"), to_name=names.get(f["to_factory"], "—"),
                      item_name=fs.name(f["item"])) for f in conn.execute(
            "SELECT * FROM flow WHERE world_id=? ORDER BY item, id", (wid,))]
        item_names = sorted(gd.items()[i]["name"] for i in gd.items())
    finally:
        conn.close()
    return _page(request, "flows.html", nav="flows", flows=flows, factories=names, transports=TRANSPORTS,
                 item_names=item_names)


@router.post("/flows/transport")
def flow_transport(flow_id: int = Form(...), transport: str = Form("")):
    if transport and transport not in TRANSPORTS:
        raise HTTPException(400, "Unknown transport")
    conn, wid = _open()
    try:
        with conn:
            conn.execute("UPDATE flow SET transport=? WHERE id=? AND world_id=?", (transport or None, flow_id, wid))
    finally:
        conn.close()
    return _go("/flows")


@router.post("/flows/add")
def flow_add(item: str = Form(...), from_factory: int = Form(...), to_factory: int = Form(...),
             rate: float = Form(...), transport: str = Form("")):
    it = gd.item_by_name(item.strip())
    if not it or from_factory == to_factory or (transport and transport not in TRANSPORTS):
        raise HTTPException(400, "Check item, factories and transport")
    vd.rate(rate)
    conn, wid = _open()
    try:
        with conn:
            ids = {r["id"] for r in conn.execute("SELECT id FROM factory WHERE world_id=? AND status != 'archived'", (wid,))}
            if from_factory not in ids or to_factory not in ids:
                raise HTTPException(400, "Both factories must exist and not be archived")
            conn.execute("INSERT INTO flow(world_id,from_factory,to_factory,item,rate_per_min,transport,auto) "
                         "VALUES (?,?,?,?,?,?,0)", (wid, from_factory, to_factory, it["class"], rate, transport or None))
    finally:
        conn.close()
    return _go("/flows")


@router.post("/flows/delete")
def flow_delete(flow_id: int = Form(...)):
    conn, wid = _open()
    try:
        with conn:
            conn.execute("DELETE FROM flow WHERE id=? AND world_id=? AND auto=0", (flow_id, wid))
    finally:
        conn.close()
    return _go("/flows")


@router.post("/ledger/link")
def ledger_link(item: str = Form(...), from_factory: int = Form(...)):
    """Link a deficit to a factory that has the item: manual flows to every consumer still short."""
    conn, wid = _open()
    try:
        with conn:
            facs = [f for f in ws.factory_summaries(conn, wid) if f["status"] in ws.COUNTED]
            src = next((f for f in facs if f["id"] == from_factory), None)
            if not src:
                raise HTTPException(400, "Unknown factory")
            cap = src["outputs"].get(item, 0.0) + src["surplus"].get(item, 0.0)
            cap -= sum(r["rate_per_min"] for r in conn.execute(
                "SELECT rate_per_min FROM flow WHERE from_factory=? AND item=?", (from_factory, item)))
            made = 0
            for f in facs:
                if f["id"] == from_factory or cap <= ledger.EPS:
                    continue
                need = f["raws"].get(item, 0.0)
                got = sum(r["rate_per_min"] for r in conn.execute(
                    "SELECT rate_per_min FROM flow WHERE to_factory=? AND item=?", (f["id"], item)))
                short = need - got
                if short > ledger.EPS:
                    take = min(short, cap)
                    cap -= take
                    conn.execute("INSERT INTO flow(world_id,from_factory,to_factory,item,rate_per_min,auto) "
                                 "VALUES (?,?,?,?,?,0)", (wid, from_factory, f["id"], item, take))
                    conn.execute("INSERT OR IGNORE INTO factory_input(factory_id,item) VALUES (?,?)", (f["id"], item))
                    made += 1
            if not made:
                raise HTTPException(400, "No factory needs that item, or the source has nothing to spare")
    finally:
        conn.close()
    return _go("/flows")


# ---------- resources ----------

@router.get("/resources", response_class=HTMLResponse)
def resources_page(request: Request):
    conn, wid = _open()
    try:
        av = ws.available(conn, wid)
        ov = ws.overview(conn, wid)
        demand = {b["item"]: b["demand"] for b in ov["budget"]}
        rows = []
        for r in conn.execute("SELECT * FROM world_resource WHERE world_id=?", (wid,)):
            rows.append({**dict(r), "name": fs.name(r["resource"]), "available": av.get(r["resource"]),
                         "demand": demand.get(r["resource"], 0.0)})
        rows.sort(key=lambda r: r["name"])
        extractors = {k: v["name"] for k, v in gd.load()["extractors"].items()}
    finally:
        conn.close()
    return _page(request, "resources.html", nav="resources", rows=rows, extractors=extractors, inf=float("inf"))


@router.post("/resources/update")
def resources_update(resource: str = Form(...), pure: int = Form(0), normal: int = Form(0), impure: int = Form(0),
                     miner: str = Form(""), clock_pct: float = Form(250)):
    for v in (pure, normal, impure):
        vd.count(v, "Node count")
    vd.clock(clock_pct)
    if miner and miner not in gd.load()["extractors"]:
        raise HTTPException(400, "Unknown extractor")
    conn, wid = _open()
    try:
        with conn:
            n = conn.execute("UPDATE world_resource SET pure=?, normal=?, impure=?, miner=?, clock_pct=? "
                             "WHERE world_id=? AND resource=?", (pure, normal, impure, miner or None, clock_pct, wid, resource)).rowcount
            if not n:
                raise HTTPException(404, "Unknown resource")
    finally:
        conn.close()
    return _go("/resources")


# ---------- power plants ----------

@router.get("/power", response_class=HTMLResponse)
def power_page(request: Request):
    conn, wid = _open()
    try:
        ov = ws.overview(conn, wid)
        gens = gd.load()["generators"]
        rows = []
        for p in ov["plants"]:
            st = ledger.generator_stats(p)
            rows.append({"p": p, "generator": gens[p["generator"]]["name"], "fuel": fs.name(p["fuel"]), "st": st,
                         "unit": "items" if gd.items()[p["fuel"]]["form"] == "RF_SOLID" else "m³",
                         "water": fs.name(st["supplemental"]) if st["supplemental"] else None,
                         "waste": fs.name(st["waste"]) if st["waste"] else None})
        options = [{"generator": k, "name": g["name"], "fuels": [{"item": f["fuel"], "name": fs.name(f["fuel"])}
                                                                  for f in g["fuels"]]}
                   for k, g in gens.items() if g["fuels"]]
    finally:
        conn.close()
    return _page(request, "power.html", nav="power", rows=rows, ov=ov, options=options)


@router.post("/power/add")
def power_add(name: str = Form(""), generator: str = Form(...), fuel: str = Form(...), count: int = Form(1),
              clock_pct: float = Form(100)):
    g = gd.load()["generators"].get(generator)
    if not g or not any(f["fuel"] == fuel for f in g["fuels"]):
        raise HTTPException(400, "Check generator and fuel")
    vd.count(count, "Count", 1)
    vd.clock(clock_pct)
    conn, wid = _open()
    try:
        with conn:
            conn.execute("INSERT INTO power_plant(world_id,name,generator,fuel,count,clock_pct) VALUES (?,?,?,?,?,?)",
                         (wid, name.strip(), generator, fuel, count, clock_pct))
    finally:
        conn.close()
    return _go("/power")


@router.post("/power/update")
def power_update(plant_id: int = Form(...), count: int = Form(...), clock_pct: float = Form(...)):
    vd.count(count, "Count", 1)
    vd.clock(clock_pct)
    conn, wid = _open()
    try:
        with conn:
            n = conn.execute("UPDATE power_plant SET count=?, clock_pct=? WHERE id=? AND world_id=?",
                             (count, clock_pct, plant_id, wid)).rowcount
            if not n:
                raise HTTPException(404, "Power plant not found")
    finally:
        conn.close()
    return _go("/power")


@router.post("/power/delete")
def power_delete(plant_id: int = Form(...)):
    conn, wid = _open()
    try:
        with conn:
            conn.execute("DELETE FROM power_plant WHERE id=? AND world_id=?", (plant_id, wid))
    finally:
        conn.close()
    return _go("/power")
