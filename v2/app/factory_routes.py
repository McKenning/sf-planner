"""Factory pages and API (Phase 2)."""
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import db
from app import validate as vd
from app import factory_service as fs
from core import gamedata as gd
from core import recipes as rc
from pathlib import Path

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
EDITABLE = ("planned", "built", "draft")


def _factory(conn, fid):
    f = conn.execute("SELECT * FROM factory WHERE id=?", (fid,)).fetchone()
    if not f:
        raise HTTPException(404, "Factory not found")
    return f


def _editable(f):
    if f["status"] == "archived":
        raise HTTPException(409, "Archived factories are read-only")


def _item_by_name(n: str) -> str:
    it = gd.item_by_name(n.strip())
    if not it or it["class"] not in rc.producers():
        raise HTTPException(400, f"Unknown or unproducible item: {n}")
    return it["class"]


def _clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not name:
        raise HTTPException(400, "Name required")
    if len(name) > 120:
        raise HTTPException(400, "Name must be 120 characters or fewer")
    return name


def _back(fid):
    return RedirectResponse(f"/factory/{fid}", status_code=303)


@router.post("/api/factories")
def create_factory(name: str = Form(...)):
    name = _clean_name(name)
    conn = db.connect()
    try:
        with conn:
            w = conn.execute("SELECT id FROM world ORDER BY id LIMIT 1").fetchone()
            wid = w["id"] if w else conn.execute("INSERT INTO world(name, game_build) VALUES ('Main', ?)",
                                                 (gd.load()["build"],)).lastrowid
            fid = conn.execute("INSERT INTO factory(world_id, name, status, origin) VALUES (?,?, 'planned','manual')",
                               (wid, name)).lastrowid
    finally:
        conn.close()
    return _back(fid)


@router.post("/factory/{fid}/rename")
def rename_factory(fid: int, name: str = Form(...)):
    name = _clean_name(name)
    conn = db.connect()
    try:
        with conn:
            _editable(_factory(conn, fid))
            conn.execute("UPDATE factory SET name=? WHERE id=?", (name, fid))
    finally:
        conn.close()
    return _back(fid)


@router.post("/factory/{fid}/archive")
def archive_factory(fid: int):
    """Archiving is reversible: the factory keeps all its data, becomes read-only and leaves the world totals."""
    conn = db.connect()
    try:
        with conn:
            f = _factory(conn, fid)
            if f["status"] != "archived":
                conn.execute("UPDATE factory SET status='archived', notes=COALESCE(notes,'') || ? WHERE id=?",
                             (f" [archived from {f['status']}]", fid))
    finally:
        conn.close()
    return _back(fid)


@router.post("/factory/{fid}/restore")
def restore_factory(fid: int):
    import re
    conn = db.connect()
    try:
        with conn:
            f = _factory(conn, fid)
            if f["status"] == "archived":
                m = re.findall(r"\[archived from (\w+)\]", f["notes"] or "")
                prev = m[-1] if m and m[-1] in EDITABLE else "planned"
                notes = re.sub(r"\s*\[archived from \w+\]", "", f["notes"] or "")
                conn.execute("UPDATE factory SET status=?, notes=? WHERE id=?", (prev, notes, fid))
    finally:
        conn.close()
    return _back(fid)


@router.get("/factory/{fid}", response_class=HTMLResponse)
def factory_page(request: Request, fid: int):
    conn = db.connect()
    try:
        f = _factory(conn, fid)
        outputs, choices, overrides, res = fs.solve_factory(conn, fid)
        p = fs.present(res)
        rate_of = res["item_rates"]
        picker = {}
        for l in p["lines"]:
            it = l["items"][0]
            picker[l["recipe"]] = fs.recipe_options(it, rate_of.get(it) or outputs.get(it, 0) or 1.0,
                                                    choices.get(it))
        built = fs.built_vs_planned(conn, fid, res)
        out_rows = [{"item": k, "name": fs.name(k), "rate": v} for k, v in outputs.items()]
        item_names = sorted(gd.items()[i]["name"] for i in rc.producers() if i in gd.items())
        ctx = dict(nav="factories", f=f, outputs=out_rows, res=p, picker=picker,
                   item_names=item_names, editable=f["status"] != "archived", built=built,
                   by_stage={})
        for l in p["lines"]:
            ctx["by_stage"].setdefault(l["stage"], []).append(l)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "factory.html", ctx)


@router.post("/factory/{fid}/output")
def set_output(fid: int, item: str = Form(...), rate: float = Form(...)):
    vd.rate(rate)
    cls = _item_by_name(item)
    conn = db.connect()
    try:
        with conn:
            _editable(_factory(conn, fid))
            cur = conn.execute("UPDATE factory_output SET rate_per_min=? WHERE factory_id=? AND item=?",
                               (rate, fid, cls)).rowcount
            if not cur:
                conn.execute("INSERT INTO factory_output(factory_id,item,rate_per_min) VALUES (?,?,?)",
                             (fid, cls, rate))
    finally:
        conn.close()
    return _back(fid)


@router.post("/factory/{fid}/output/delete")
def delete_output(fid: int, item: str = Form(...)):
    conn = db.connect()
    try:
        with conn:
            _editable(_factory(conn, fid))
            conn.execute("DELETE FROM factory_output WHERE factory_id=? AND item=?", (fid, item))
    finally:
        conn.close()
    return _back(fid)


@router.post("/factory/{fid}/override")
def set_override(fid: int, item: str = Form(...), recipe: str = Form(""), clock_pct: str = Form(""),
                 sloops: str = Form("")):
    """Set recipe / clock / sloops for an item's line. Blank recipe = default; blank clock = 100%."""
    if item not in gd.items():
        raise HTTPException(400, "Unknown item")
    rec = recipe.strip() or None
    if rec:
        r = gd.recipes().get(rec)
        if not r or not any(o["item"] == item for o in r["outputs"]):
            raise HTTPException(400, "Recipe does not make that item")
    try:
        clk = float(clock_pct) if clock_pct.strip() else None
        slp = int(sloops) if sloops.strip() else None
    except ValueError:
        raise HTTPException(400, "Clock must be a number and Somersloops a whole number")
    if clk is not None:
        vd.clock(clk)
    if slp is not None:
        rcls = rec or rc.default_recipe(item)
        slots = gd.buildings()[gd.recipes()[rcls]["machine"]]["sloop_slots"]
        if not (0 <= slp <= slots):
            raise HTTPException(400, f"Somersloops must be 0..{slots} for this machine")
    conn = db.connect()
    try:
        with conn:
            _editable(_factory(conn, fid))
            if rec is None and clk is None and not slp:
                conn.execute("DELETE FROM factory_recipe WHERE factory_id=? AND item=?", (fid, item))
            else:
                conn.execute(
                    "INSERT INTO factory_recipe(factory_id,item,recipe,clock_pct,sloops) VALUES (?,?,?,?,?) "
                    "ON CONFLICT(factory_id,item) DO UPDATE SET recipe=excluded.recipe, "
                    "clock_pct=excluded.clock_pct, sloops=excluded.sloops",
                    (fid, item, rec, clk, slp))
    finally:
        conn.close()
    return _back(fid)


@router.get("/api/factory/{fid}/solve")
def api_solve(fid: int):
    conn = db.connect()
    try:
        f = _factory(conn, fid)
        outputs, _c, _o, res = fs.solve_factory(conn, fid)
    finally:
        conn.close()
    return JSONResponse(__import__("json").loads(fs.export_json(f["name"], outputs, res)))


@router.get("/api/factory/{fid}/export.json")
def export_json(fid: int):
    conn = db.connect()
    try:
        f = _factory(conn, fid)
        outputs, _c, _o, res = fs.solve_factory(conn, fid)
    finally:
        conn.close()
    return Response(fs.export_json(f["name"], outputs, res), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="factory-{fid}.json"'})


@router.get("/api/factory/{fid}/export.xlsx")
def export_xlsx(fid: int):
    conn = db.connect()
    try:
        f = _factory(conn, fid)
        outputs, _c, _o, res = fs.solve_factory(conn, fid)
    finally:
        conn.close()
    return Response(fs.export_xlsx(f["name"], outputs, res),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="factory-{fid}.xlsx"'})
