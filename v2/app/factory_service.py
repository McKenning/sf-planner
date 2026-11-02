"""Load a factory from the DB, solve it, and present it (names, units). No web code."""
import io
import json

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from core import gamedata as gd
from core import recipes as rc
from core import solver
from core.power import machine_power_mw


def name(item_class: str) -> str:
    it = gd.items().get(item_class)
    return it["name"] if it else item_class


def load_inputs(conn, factory_id: int):
    outputs = {r["item"]: r["rate_per_min"] for r in conn.execute(
        "SELECT item, rate_per_min FROM factory_output WHERE factory_id=? ORDER BY id", (factory_id,))}
    choices, overrides = {}, {}
    for r in conn.execute("SELECT * FROM factory_recipe WHERE factory_id=?", (factory_id,)):
        if r["recipe"]:
            choices[r["item"]] = r["recipe"]
        if r["clock_pct"] is not None or r["sloops"]:
            overrides[r["item"]] = {"clock_pct": r["clock_pct"], "sloops": r["sloops"]}
    return outputs, choices, overrides


def solve_factory(conn, factory_id: int):
    outputs, choices, overrides = load_inputs(conn, factory_id)
    return outputs, choices, overrides, solver.solve(outputs, choices, overrides)


def present(res: dict) -> dict:
    """Decorate a solve result with display names."""
    lines = []
    for l in res["lines"]:
        d = dict(l)
        d["item_names"] = [name(i) for i in l["items"]]
        d["inputs_named"] = [(name(k), v) for k, v in sorted(l["inputs"].items())]
        d["outputs_named"] = [(name(k), v) for k, v in sorted(l["outputs"].items())]
        lines.append(d)
    return {
        "lines": lines,
        "raws": sorted(((name(k), v) for k, v in res["raws"].items()), key=lambda x: -x[1]),
        "surplus": sorted(((name(k), v) for k, v in res["surplus"].items()), key=lambda x: -x[1]),
        "power_mw": res["power_mw"], "sloops_total": res["sloops_total"],
        "warnings": res["warnings"],
    }


def recipe_options(item: str, rate: float, current: str | None) -> list[dict]:
    """Side-by-side comparison of every recipe that makes `item`, at `rate`/min (one step, 100% clock)."""
    out = []
    for rcls in rc.choices_for(item):
        r = gd.recipes()[rcls]
        b = gd.buildings()[r["machine"]]
        cpm = 60.0 / r["duration_s"]
        q = sum(o["amount"] for o in r["outputs"] if o["item"] == item)
        cycles = rate / q if q else 0
        machines = cycles / cpm
        out.append({
            "recipe": rcls, "name": r["name"], "alternate": r["alternate"], "machine": b["name"],
            "per_machine": q * cpm,
            "machines": machines,
            "power_mw": machines * machine_power_mw(b, 100.0, 0),
            "inputs": [(name(s["item"]), s["amount"] * cycles) for s in r["inputs"]],
            "byproducts": [(name(o["item"]), o["amount"] * cycles) for o in r["outputs"] if o["item"] != item],
            "current": rcls == (current or rc.default_recipe(item)),
        })
    return out


def export_json(fname: str, outputs, res) -> str:
    p = present(res)
    return json.dumps({
        "factory": fname, "game_build": gd.load()["build"],
        "outputs": [{"item": name(k), "per_min": v} for k, v in outputs.items()],
        "power_mw": p["power_mw"], "somersloops": p["sloops_total"],
        "raw_inputs_per_min": {k: v for k, v in p["raws"]},
        "byproduct_surplus_per_min": {k: v for k, v in p["surplus"]},
        "lines": [{"items": l["item_names"], "recipe": l["recipe_name"], "machine": l["machine_name"],
                   "count": l["count"], "clock_pct": round(l["clock_pct"], 4), "somersloops_each": l["sloops"],
                   "power_mw": round(l["power_mw"], 4),
                   "inputs_per_min": dict(l["inputs_named"]), "outputs_per_min": dict(l["outputs_named"])}
                  for l in p["lines"]],
        "warnings": p["warnings"],
    }, indent=2)


def export_xlsx(fname: str, outputs, res) -> bytes:
    p = present(res)
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([f"{fname} — SF Planner 2.0 (Satisfactory {gd.load()['game_version']}, build {gd.load()['build']})"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])
    ws.append(["Total power (MW)", round(p["power_mw"], 2)])
    ws.append(["Somersloops used", p["sloops_total"]])
    ws.append([])
    ws.append(["Output", "Rate / min"])
    for k, v in outputs.items():
        ws.append([name(k), v])
    ws.append([])
    ws.append(["Raw input", "Rate / min"])
    for k, v in p["raws"]:
        ws.append([k, round(v, 4)])
    if p["surplus"]:
        ws.append([])
        ws.append(["Byproduct surplus", "Rate / min"])
        for k, v in p["surplus"]:
            ws.append([k, round(v, 4)])
    ln = wb.create_sheet("Lines")
    ln.append(["Stage", "Item(s)", "Recipe", "Machine", "Machines", "Clock %", "Somersloops each",
               "Power (MW)", "Inputs / min", "Outputs / min"])
    for l in p["lines"]:
        ln.append([l["stage"], ", ".join(l["item_names"]), l["recipe_name"], l["machine_name"], l["count"],
                   round(l["clock_pct"], 3), l["sloops"], round(l["power_mw"], 3),
                   "; ".join(f"{k} {v:.2f}" for k, v in l["inputs_named"]),
                   "; ".join(f"{k} {v:.2f}" for k, v in l["outputs_named"])])
    for sheet in (ws, ln):
        for c in sheet[1 if sheet is ln else 6]:
            c.font = Font(bold=True)
        for i in range(1, sheet.max_column + 1):
            sheet.column_dimensions[get_column_letter(i)].width = 28
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
