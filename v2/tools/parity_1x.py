"""Phase 2 parity: compare 2.0's solver with 1.x's backend/solver.py for every 1.x factory.

Read-only: imports 1.x's solver/data modules (not app.py, which touches the DB) and opens the 1.x DB
copy with mode=ro. Usage: python -m tools.parity_1x [1x.db] [--md out.md]
Power is expected to differ (1.x is linear in machine count); rates and machine counts should match.
"""
import importlib
import io
import contextlib
import sqlite3
import sys
from pathlib import Path

from core import gamedata as gd
from core import solver

BACKEND = Path(__file__).resolve().parents[2] / "legacy" / "backend"
REL = 1e-6


def load_1x(tight=False):
    """tight=True: the same 1.x solver source (read, never modified on disk) with its loop
    convergence tolerance tightened, to separate 1.x's early stop from real differences."""
    sys.path.insert(0, str(BACKEND))
    with contextlib.redirect_stdout(io.StringIO()):
        sr = importlib.import_module("sf_recipes")
        sd = importlib.import_module("sf_data")
        sv = importlib.import_module("solver")
    if tight:
        import types
        src = (BACKEND / "solver.py").read_text()
        assert "prev_total * 0.0001" in src and "range(50)" in src
        src = src.replace("prev_total * 0.0001", "prev_total * 1e-14").replace("range(50)", "range(20000)")
        sv = types.ModuleType("solver_tight")
        exec(compile(src, "solver_tight", "exec"), sv.__dict__)
    db = sv.RecipeDB(sr.RECIPES)
    power = {m: d["power"] for m, d in sd.MACHINES.items()}
    slots = {m: d.get("sloop_slots", 0) for m, d in sd.MACHINES.items()}
    return sv, db, power, slots


def close(a, b):
    return abs(a - b) <= REL * max(1.0, abs(a), abs(b))


def run(src_path, tight=False):
    sv, db1, power, slots = load_1x(tight)
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    plan = src.execute("SELECT id FROM plans ORDER BY id LIMIT 1").fetchone()["id"]
    plan_clocks = {r["product"]: r["clock_pct"] for r in src.execute(
        "SELECT product, clock_pct FROM clock_overrides WHERE plan_id=?", (plan,))}
    name2cls = {v["name"]: k for k, v in gd.items().items()}
    rname2cls = {v["name"]: k for k, v in gd.recipes().items()}
    report = []
    for f in src.execute("SELECT id, name FROM factories ORDER BY id"):
        fid = f["id"]
        targets = {r["product"]: r["rate_per_min"] for r in src.execute(
            "SELECT product, rate_per_min FROM factory_targets WHERE factory_id=?", (fid,))}
        choices = {r["product"]: r["recipe"] for r in src.execute(
            "SELECT product, recipe FROM factory_choices WHERE factory_id=?", (fid,))}
        clocks = {**plan_clocks, **{r["product"]: r["clock_pct"] for r in src.execute(
            "SELECT product, clock_pct FROM factory_clock_overrides WHERE factory_id=?", (fid,))}}
        sloops = {r["product"]: bool(r["slooped"]) for r in src.execute(
            "SELECT product, slooped FROM factory_sloop_overrides WHERE factory_id=?", (fid,))}
        r1 = sv.solve(targets, choices, db1, power, clocks, sloops, slots)

        outputs = {name2cls[k]: v for k, v in targets.items()}
        ch2 = {name2cls[k]: rname2cls[v] for k, v in choices.items()}
        ov2 = {}
        for k, v in clocks.items():
            ov2.setdefault(name2cls[k], {})["clock_pct"] = v
        for k, v in sloops.items():
            if v:
                item = name2cls[k]
                rcls = ch2.get(item)
                from core import recipes as rc
                rcls = rcls or rc.default_recipe(item)
                ov2.setdefault(item, {})["sloops"] = gd.buildings()[gd.recipes()[rcls]["machine"]]["sloop_slots"]
        r2 = solver.solve(outputs, ch2, ov2)

        diffs = []
        n1 = {p["name"]: p for p in r1["products"]}
        lines2 = {}
        for l in r2["lines"]:
            for it in l["items"]:
                lines2[gd.items()[it]["name"]] = l
        # recipes
        for name, p in n1.items():
            if p["is_raw"] or p.get("warning"):
                continue
            l = lines2.get(name)
            if l is None:
                diffs.append((name, "line", f"1.x has {p['machines_ceil']}x {p['machine']}", "absent in 2.0",
                              "item not demanded in 2.0 (byproduct credit)"))
                continue
            if l["recipe_name"] != p["recipe"]:
                diffs.append((name, "recipe", p["recipe"], l["recipe_name"], "default-recipe choice differs"))
            if l["machine_name"] != p["machine"]:
                diffs.append((name, "machine", p["machine"], l["machine_name"], "machine mapping differs"))
            rate2 = r2["item_rates"].get(name2cls[name], 0.0)
            if not close(rate2, p["total_per_min"]):
                diffs.append((name, "rate/min", f"{p['total_per_min']:.4f}", f"{rate2:.4f}",
                              "byproduct/loop handling"))
            if l["count"] != p["machines_ceil"]:
                diffs.append((name, "machines", p["machines_ceil"], l["count"], "rate or clock-distribution differs"))
            if not close(l["clock_pct"], p["clock_pct"]):
                diffs.append((name, "clock %", f"{p['clock_pct']:.3f}", f"{l['clock_pct']:.3f}", "see machines"))
        for name in lines2:
            if name not in n1:
                diffs.append((name, "line", "absent in 1.x", f"{lines2[name]['count']}x {lines2[name]['machine_name']}",
                              "2.0 only"))
        # raws
        raws2 = {gd.items()[k]["name"]: v for k, v in r2["raws"].items()}
        for name in sorted(set(r1["raws"]) | set(raws2)):
            a, b = r1["raws"].get(name, 0.0), raws2.get(name, 0.0)
            if not close(a, b):
                diffs.append((name, "raw/min", f"{a:.4f}", f"{b:.4f}", "see line diffs"))
        report.append({"factory": f["name"], "diffs": diffs, "power_1x": r1["total_power"],
                       "power_2": r2["power_mw"], "lines": len(r2["lines"]),
                       "warnings1": r1["warnings"], "warnings2": r2["warnings"],
                       "surplus": {gd.items()[k]["name"]: v for k, v in r2["surplus"].items()}})
    return report


def to_markdown(report):
    out = []
    for r in report:
        out.append(f"### {r['factory']}\n")
        out.append(f"- power: 1.x {r['power_1x']:.1f} MW (linear) vs 2.0 {r['power_2']:.1f} MW (1.1 formula) — expected to differ")
        out.append(f"- 2.0 lines: {r['lines']}; 1.x warnings: {r['warnings1'] or 'none'}; 2.0 warnings: {r['warnings2'] or 'none'}")
        if r["surplus"]:
            out.append("- 2.0 byproduct surplus/min: " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(r["surplus"].items())))
        if not r["diffs"]:
            out.append("- **rates and machine counts identical**")
        else:
            out.append(f"- {len(r['diffs'])} difference(s):\n")
            out.append("| item | what | 1.x | 2.0 | cause |\n| --- | --- | --- | --- | --- |")
            for d in r["diffs"]:
                out.append("| " + " | ".join(str(x) for x in d) + " |")
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = args[0] if args else Path.home() / "sf-inputs/planner-1x.db"
    tight = "--tight" in sys.argv
    print(to_markdown(run(path, tight=tight)))
