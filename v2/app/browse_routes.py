"""Search (Ctrl+K) and read-only item/recipe pages."""
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import db
from app import factory_service as fs
from core import gamedata as gd
from core import recipes as rc
from core.power import machine_power_mw

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _score(q: str, name: str):
    n, q = name.lower(), q.lower()
    if n == q:
        return 0
    if n.startswith(q):
        return 1
    if any(w.startswith(q) for w in n.replace("-", " ").split()):
        return 2
    return 3 if q in n else None


@router.get("/api/search")
def search(q: str = ""):
    q = q.strip()
    out = []
    conn = db.connect()
    try:
        facs = [(f["name"], f"/factory/{f['id']}", f["status"]) for f in conn.execute("SELECT id, name, status FROM factory")]
    finally:
        conn.close()
    cands = [(n, u, "factory", st) for n, u, st in facs]
    cands += [(v["name"], f"/item/{k}", "item", "") for k, v in gd.items().items()]
    cands += [(v["name"], f"/recipe/{k}", "recipe", gd.buildings()[v["machine"]]["name"]) for k, v in gd.recipes().items()]
    if not q:
        out = [{"name": n, "url": u, "kind": k, "detail": d} for n, u, k, d in cands if k == "factory"][:8]
        return JSONResponse({"results": out})
    scored = []
    for n, u, k, d in cands:
        s = _score(q, n)
        if s is not None:
            scored.append((s, {"factory": 0, "item": 1, "recipe": 2}[k], n, {"name": n, "url": u, "kind": k, "detail": d}))
    scored.sort(key=lambda t: t[:3])
    return JSONResponse({"results": [t[3] for t in scored[:12]]})


@router.get("/item/{item}", response_class=HTMLResponse)
def item_page(request: Request, item: str):
    it = gd.items().get(item)
    if not it:
        raise HTTPException(404, "Unknown item")
    makers = [r for r in rc.producers().get(item, [])]
    users = [k for k, r in gd.recipes().items() if any(s["item"] == item for s in r["inputs"]) and rc.is_planner_recipe(r)]
    fmt = lambda k: {"cls": k, "name": gd.recipes()[k]["name"], "machine": gd.buildings()[gd.recipes()[k]["machine"]]["name"],
                     "alt": gd.recipes()[k]["alternate"]}
    return templates.TemplateResponse(request, "item.html", {
        "nav": "", "it": it, "makers": [fmt(k) for k in makers],
        "users": sorted((fmt(k) for k in users), key=lambda x: x["name"]),
        "default": rc.default_recipe(item), "raw": rc.is_raw(item), "unit": "m³" if it["form"] != "RF_SOLID" else "items"})


@router.get("/recipe/{rcls}", response_class=HTMLResponse)
def recipe_page(request: Request, rcls: str):
    r = gd.recipes().get(rcls)
    if not r:
        raise HTTPException(404, "Unknown recipe")
    b = gd.buildings()[r["machine"]]
    cpm = 60.0 / r["duration_s"]
    return templates.TemplateResponse(request, "recipe.html", {
        "nav": "", "r": r, "b": b, "cpm": cpm,
        "inputs": [(s["item"], fs.name(s["item"]), s["amount"], s["amount"] * cpm) for s in r["inputs"]],
        "outputs": [(s["item"], fs.name(s["item"]), s["amount"], s["amount"] * cpm) for s in r["outputs"]],
        "power": machine_power_mw(b, 100, 0), "power250": machine_power_mw(b, 250, 0),
        "power_full": machine_power_mw(b, 100, b["sloop_slots"]) if b["sloop_slots"] else None})
