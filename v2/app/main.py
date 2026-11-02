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
        has_world = conn.execute("SELECT 1 FROM world LIMIT 1").fetchone()
        done = conn.execute("PRAGMA user_version").fetchone()[0] >= 2
    finally:
        conn.close()
    if has_world and done:
        return  # imported already; run() would be a no-op and must not resurrect deleted factories
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
    conn = db.connect()
    try:
        conn.execute("PRAGMA user_version = 2")  # one-shot marker (2 = 1.x import incl. plan clocks + resources)
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.migrate()
    seed_from_1x()
    yield


app = FastAPI(title="SF Planner 2.0", lifespan=lifespan)
from app.factory_routes import router as factory_router  # noqa: E402
app.include_router(factory_router)
from app.world_routes import router as world_router  # noqa: E402
app.include_router(world_router)
from app.import_routes import router as import_router  # noqa: E402
app.include_router(import_router)
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


@app.get("/factories", response_class=HTMLResponse)
def factories(request: Request):
    from app import factory_service as fs
    conn = db.connect()
    try:
        rows = []
        for f in conn.execute("SELECT f.*, w.name AS world FROM factory f JOIN world w ON w.id=f.world_id "
                              "ORDER BY f.status = 'archived', f.name"):
            outputs, _c, _o, res = fs.solve_factory(conn, f["id"])
            rows.append({"f": f, "outputs": [{"item": _name(k), "rate": v} for k, v in outputs.items()],
                         "power": res["power_mw"], "sloops": res["sloops_total"],
                         "machines": sum(l["count"] for l in res["lines"]), "warnings": res["warnings"]})
    finally:
        conn.close()
    return _render(request, "factories.html", nav="factories", rows=rows)
