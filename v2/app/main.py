"""SF Planner 2.0 — FastAPI app (Phase 1: foundation + read-only lists)."""
import os
import shutil
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import db
from core import gamedata as gd
from core.power import machine_power_mw  # noqa: F401  (used from Phase 2)

ROOT = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def seed_from_1x() -> None:
    """First start only: import 1.x data from a read-only copy of its DB (never writes to it)."""
    src = os.environ.get("SFP_1X_DB")
    if not src or not Path(src).exists():
        return
    conn = db.connect()
    try:
        if conn.execute("SELECT 1 FROM world LIMIT 1").fetchone():
            return
    finally:
        conn.close()
    from tools import import_1x
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "planner-1x.db"
        s = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        d = sqlite3.connect(str(copy))
        with d:
            s.backup(d)
        s.close()
        d.close()
        print("1.x import:", import_1x.run(copy))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.migrate()
    seed_from_1x()
    yield


app = FastAPI(title="SF Planner 2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def _name(item_class: str) -> str:
    it = gd.items().get(item_class)
    return it["name"] if it else item_class


def _recipe_name(cls: str | None) -> str | None:
    r = gd.recipes().get(cls) if cls else None
    return r["name"] if r else cls


@app.get("/health")
def health():
    conn = db.connect()
    try:
        conn.execute("SELECT 1").fetchone()
    finally:
        conn.close()
    return {"status": "ok", "version": "2.0-p1", "game_build": gd.load()["build"]}


def _render(request, name, **ctx):
    return templates.TemplateResponse(request, name, ctx)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = db.connect()
    try:
        worlds = conn.execute("SELECT * FROM world ORDER BY id").fetchall()
        counts = {
            "factories": conn.execute("SELECT COUNT(*) FROM factory WHERE status != 'archived'").fetchone()[0],
            "archived": conn.execute("SELECT COUNT(*) FROM factory WHERE status = 'archived'").fetchone()[0],
            "power_plants": conn.execute("SELECT COUNT(*) FROM power_plant").fetchone()[0],
        }
    finally:
        conn.close()
    return _render(request, "home.html", nav="world", worlds=worlds, counts=counts, build=gd.load())


@app.get("/factories", response_class=HTMLResponse)
def factories(request: Request):
    conn = db.connect()
    try:
        rows = []
        for f in conn.execute("SELECT f.*, w.name AS world FROM factory f JOIN world w ON w.id=f.world_id "
                              "ORDER BY f.status = 'archived', f.name"):
            outs = [{"item": _name(o["item"]), "rate": o["rate_per_min"]} for o in conn.execute(
                "SELECT item, rate_per_min FROM factory_output WHERE factory_id=?", (f["id"],))]
            ovr = [{"item": _name(o["item"]), "recipe": _recipe_name(o["recipe"]),
                    "clock": o["clock_pct"], "sloops": o["sloops"]} for o in conn.execute(
                "SELECT * FROM factory_recipe WHERE factory_id=? ORDER BY item", (f["id"],))]
            rows.append({"f": f, "outputs": outs, "overrides": ovr})
    finally:
        conn.close()
    return _render(request, "factories.html", nav="factories", rows=rows)


@app.get("/power", response_class=HTMLResponse)
def power(request: Request):
    conn = db.connect()
    try:
        plants = [{"p": p, "generator": gd.load()["generators"][p["generator"]]["name"],
                   "fuel": _name(p["fuel"])} for p in conn.execute("SELECT * FROM power_plant ORDER BY id")]
    finally:
        conn.close()
    return _render(request, "power.html", nav="power", plants=plants)
