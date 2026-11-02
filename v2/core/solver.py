"""Factory solver. Pure functions — no DB or web code.

Given output targets, recipe choices and per-item clock/Somersloop overrides, work out how many
machines of each recipe are needed, the raw inputs, byproduct surplus and power.

Model: one *line* per chosen recipe, run at c cycles/min. A recipe's outputs per cycle are
multiplied by m = 1 + sloops/slots; inputs are not. Every item's balance is
    demand = target + inputs consumed by all lines
    supplied-by-others = byproducts of lines owned by other items
and a recipe owned by item i must run enough to cover max(0, demand - supplied-by-others).
Byproduct credits, shared recipes and loops (e.g. Recycled Rubber <-> Recycled Plastic) make this
a piecewise-linear fixed point, solved by Gauss-Seidel iteration in pure Python.
"""
from collections import defaultdict
from math import ceil

from core import gamedata as gd
from core import recipes as rc
from core.power import machine_power_mw, sloop_multiplier

EPS = 1e-9


def resolve_recipe(item: str, choices: dict, warnings: list) -> str | None:
    """Chosen recipe if valid for the item, else the default."""
    chosen = choices.get(item)
    if chosen:
        r = gd.recipes().get(chosen)
        if r and any(o["item"] == item for o in r["outputs"]):
            return chosen
        warnings.append(f"Recipe {chosen} does not make {gd.items().get(item, {}).get('name', item)}; using default")
    return rc.default_recipe(item)


def solve(outputs: dict, choices: dict | None = None, overrides: dict | None = None,
          max_iter: int = 20000, tol: float = 1e-11) -> dict:
    """outputs: {item_class: rate/min}. choices: {item: recipe_class}.
    overrides: {item: {"clock_pct": float|None, "sloops": int|None}} (applies to the recipe line for item).
    """
    choices = choices or {}
    overrides = overrides or {}
    recipes, buildings = gd.recipes(), gd.buildings()
    warnings: list[str] = []
    targets = {k: v for k, v in outputs.items() if v and v > 0}

    # --- discover the chain: owner item -> recipe class ---
    owner_recipe: dict[str, str] = {}
    raw_items: set[str] = set()
    stack = list(targets)
    seen = set(stack)
    while stack:
        item = stack.pop()
        if rc.is_raw(item):
            raw_items.add(item)
            continue
        r = resolve_recipe(item, choices, warnings)
        if r is None:
            raw_items.add(item)
            warnings.append(f"No recipe found for {gd.items().get(item, {}).get('name', item)}")
            continue
        owner_recipe[item] = r
        for s in recipes[r]["inputs"]:
            if s["item"] not in seen:
                seen.add(s["item"])
                stack.append(s["item"])

    # recipe -> owner items (a recipe may serve several items, e.g. both outputs of one recipe)
    owners: dict[str, list[str]] = defaultdict(list)
    for item, r in owner_recipe.items():
        owners[r].append(item)
    for r in owners:
        owners[r].sort()

    # per-recipe boost m, from the first owner's override
    mult: dict[str, float] = {}
    sloops_of: dict[str, int] = {}
    clock_of: dict[str, float] = {}
    for r, its in owners.items():
        b = buildings[recipes[r]["machine"]]
        ov = overrides.get(its[0], {}) or {}
        for other in its[1:]:
            o2 = overrides.get(other, {}) or {}
            if (o2.get("clock_pct"), o2.get("sloops")) != (ov.get("clock_pct"), ov.get("sloops")) and o2:
                warnings.append(f"{recipes[r]['name']}: overrides differ between its outputs; using the first")
        s = int(ov.get("sloops") or 0)
        if s > b["sloop_slots"]:
            warnings.append(f"{recipes[r]['name']}: {s} Somersloops exceeds {b['sloop_slots']} slots; capped")
            s = b["sloop_slots"]
        sloops_of[r] = s
        mult[r] = sloop_multiplier(s, b["sloop_slots"])
        clock_of[r] = float(ov.get("clock_pct") or 100.0)

    def per_cycle(r, item, side):
        return sum(x["amount"] for x in recipes[r][side] if x["item"] == item)

    # --- fixed-point iteration on cycles/min per recipe ---
    cyc = {r: 0.0 for r in owners}
    order = list(owners)  # stable
    converged = not owners
    for _ in range(max_iter):
        delta = 0.0
        for r in order:
            need = 0.0
            for item in owners[r]:
                demand = targets.get(item, 0.0)
                for r2, c2 in cyc.items():
                    demand += per_cycle(r2, item, "inputs") * c2
                # production of item by recipes other than r (byproducts of other lines)
                other = sum(per_cycle(r2, item, "outputs") * mult[r2] * c2
                            for r2, c2 in cyc.items() if r2 != r)
                q = per_cycle(r, item, "outputs") * mult[r]
                need = max(need, max(0.0, demand - other) / q)
            delta = max(delta, abs(need - cyc[r]) / max(1.0, need))
            cyc[r] = need
        if delta < tol:
            converged = True
            break
    if not converged:
        warnings.append("Solver did not fully converge (check for a recipe loop that consumes more than it makes)")

    # --- build results ---
    produced: dict[str, float] = defaultdict(float)
    consumed: dict[str, float] = defaultdict(float)
    lines = []
    total_power = 0.0
    for r, c in cyc.items():
        if c <= EPS:
            continue
        rec = recipes[r]
        b = buildings[rec["machine"]]
        cpm = 60.0 / rec["duration_s"]            # cycles/min of one machine at 100%
        m = mult[r]
        exact = c / cpm                            # machines at 100% clock (sloops add output, not speed)
        cap = cpm * (clock_of[r] / 100.0)          # cycles/min of one machine at the target clock
        count = max(1, ceil(c / cap - 1e-9))
        clock = c / (count * cpm) * 100.0          # even clock across the machines
        power = count * machine_power_mw(b, clock, sloops_of[r])
        total_power += power
        ins = {s["item"]: s["amount"] * c for s in rec["inputs"]}
        outs = {s["item"]: s["amount"] * m * c for s in rec["outputs"]}
        for k, v in ins.items():
            consumed[k] += v
        for k, v in outs.items():
            produced[k] += v
        lines.append({
            "recipe": r, "recipe_name": rec["name"], "machine": rec["machine"],
            "machine_name": b["name"], "items": owners[r], "cycles_per_min": c,
            "machines_exact": exact, "count": count, "clock_pct": clock,
            "target_clock_pct": clock_of[r], "sloops": sloops_of[r],
            "sloops_total": sloops_of[r] * count, "power_mw": power,
            "inputs": ins, "outputs": outs,
        })

    raws = {}
    for item in raw_items:
        d = targets.get(item, 0.0) + consumed.get(item, 0.0) - produced.get(item, 0.0)
        if d > EPS:
            raws[item] = d
    surplus = {}
    for item, p in produced.items():
        s = p - consumed.get(item, 0.0) - targets.get(item, 0.0)
        if s > 1e-7:
            surplus[item] = s

    # per-item net rate (demand after byproduct credits) — what the line must make for that item
    item_rates = {}
    for item, r in owner_recipe.items():
        item_rates[item] = per_cycle(r, item, "outputs") * mult[r] * cyc[r] if cyc[r] > EPS else 0.0

    return {"lines": lines, "raws": raws, "surplus": surplus, "item_rates": item_rates,
            "power_mw": total_power, "warnings": warnings,
            "sloops_total": sum(l["sloops_total"] for l in lines)}
