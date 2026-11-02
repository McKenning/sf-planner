"""Save import page + API. Parsing happens in the browser; only the compact building list arrives here."""
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app import db
from app import factory_service as fs
from app import import_service as svc
from app import world_service as ws
from core import gamedata as gd
from core import importer as im

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
from app import fmt  # noqa: E402
fmt.install(templates)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _valid(payload):
    if not isinstance(payload, dict) or payload.get("format") != 1 or "buildings" not in payload \
            or "links" not in payload:
        raise HTTPException(400, "Not a SF Planner building list (format 1)")
    B, L = payload["buildings"], payload["links"]
    if not isinstance(B, list) or not isinstance(L, list):
        raise HTTPException(400, "buildings and links must be lists")
    for b in B:
        if not (isinstance(b, dict) and isinstance(b.get("id"), str) and isinstance(b.get("cls"), str)
                and isinstance(b.get("kind"), str) and all(_num(b.get(c)) for c in ("x", "y", "z"))):
            raise HTTPException(400, "Each building needs id, cls, kind (text) and x, y, z (numbers)")
    n = len(B)
    for l in L:
        if not (isinstance(l, (list, tuple)) and len(l) == 3 and all(isinstance(i, int) and 0 <= i < n for i in l[:2])
                and _num(l[2])):
            raise HTTPException(400, "Each link must be [building index, building index, length]")


def _view(g: dict) -> dict:
    return {
        "id": g["id"], "name": g["name"], "label": g["label"], "members": g["members"],
        "size": g["summary"]["size"], "x": round(g["summary"]["x"], 1), "y": round(g["summary"]["y"], 1),
        "machines": sum(l["count"] for l in g["lines"]), "extractors": g["summary"]["kinds"].get("extractor", 0),
        "generators": g["summary"]["kinds"].get("generator", 0), "stations": g["summary"]["stations"],
        "power_mw": round(g["power_mw"], 1),
        "outputs": [{"item": fs.name(k), "rate": round(v, 2)} for k, v in sorted(g["outputs"].items(), key=lambda kv: -kv[1])],
        "needs": [{"item": fs.name(k), "rate": round(v, 2)} for k, v in sorted(g["needs"].items(), key=lambda kv: -kv[1])],
        "recipes": [{"recipe": l["recipe_name"], "machine": l["machine_name"], "count": l["count"],
                     "clock": l["clock_pct"], "sloops": l["sloops"]} for l in g["lines"]],
        "notes": g["notes"],
    }


@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request):
    conn = db.connect()
    try:
        wid = ws.world_id(conn)
        runs = [dict(r) for r in conn.execute(
            "SELECT id, file_name, imported_at, summary FROM import_run WHERE world_id=? ORDER BY id DESC LIMIT 10", (wid,))]
        factories = [dict(r) for r in conn.execute(
            "SELECT id, name FROM factory WHERE world_id=? AND status IN ('planned','built','draft') ORDER BY name", (wid,))]
    finally:
        conn.close()
    return templates.TemplateResponse(request, "import.html", {"nav": "import", "runs": runs, "factories": factories})


async def _body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Body must be JSON")
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    return body


@router.post("/api/import/group")
async def group(request: Request):
    body = await _body(request)
    payload = body.get("payload")
    _valid(payload)
    method = body.get("method", "connection")
    if method not in ("connection", "distance"):
        raise HTTPException(400, "method must be connection or distance")
    try:
        threshold = float(body.get("threshold", 60))
        long_link = float(body.get("long_link", 300))
    except (TypeError, ValueError):
        raise HTTPException(400, "threshold/long_link must be numbers")
    if not (math.isfinite(threshold) and threshold > 0 and math.isfinite(long_link) and long_link > 0):
        raise HTTPException(400, "threshold and long_link must be positive numbers")
    try:
        res = im.build_groups(payload, method, threshold, long_link)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as e:
        raise HTTPException(400, f"Could not group this building list: {type(e).__name__}")
    flows = im.transport_flows(res)
    names = {g["id"]: g["name"] for g in res["groups"]}
    return JSONResponse({
        "method": method, "params": res["params"],
        "groups": [_view(g) for g in res["groups"]],
        "cut_links": res["cut_links"],
        "flows": [{"from": names[f["from"]], "to": names[f["to"]], "item": fs.name(f["item"]),
                   "rate": round(f["rate"], 2), "transport": f["transport"]} for f in flows],
        "plants": sum(sum(p["count"] for p in g["plants"]) for g in res["groups"]),
    })


@router.post("/api/import/save")
async def save(request: Request):
    body = await _body(request)
    payload = body.get("payload")
    _valid(payload)
    groups = body.get("groups")
    if not isinstance(groups, list) or not groups or not all(
            isinstance(g, dict) and isinstance(g.get("ids"), list) and g["ids"]
            and all(isinstance(i, str) for i in g["ids"]) for g in groups):
        raise HTTPException(400, "No groups to save (each group needs a list of building ids)")
    params = body.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(400, "params must be an object")
    try:
        params["long_link"] = float(params.get("long_link", 300))
    except (TypeError, ValueError):
        raise HTTPException(400, "long_link must be a number")
    conn = db.connect()
    try:
        with conn:
            result = svc.save(conn, payload, groups, str(body.get("file_name") or "save.sav")[:200], dict(params))
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as e:
        raise HTTPException(400, f"Could not save this import: {type(e).__name__}")
    finally:
        conn.close()
    return JSONResponse(result)
