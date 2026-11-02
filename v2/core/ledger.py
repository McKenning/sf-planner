"""World item ledger, power and generator maths, flow allocation. Pure functions on plain dicts.

Ledger per item: supply (factory outputs + byproduct surplus + generator waste) against demand
(factory raw/external inputs + generator fuel and water + world goals). Deficits sort first.
"""
from core import gamedata as gd

EPS = 1e-7


def generator_stats(plant: dict) -> dict:
    """plant: {generator, fuel, count, clock_pct}. Generators scale linearly with clock."""
    g = gd.load()["generators"][plant["generator"]]
    clock = plant["clock_pct"] / 100.0
    mw = g["power_mw"] * plant["count"] * clock
    fuel_item = gd.items()[plant["fuel"]]
    fuel_per_min = (mw / fuel_item["energy_mj"] * 60.0) if fuel_item["energy_mj"] > 0 else 0.0
    fuel = next((f for f in g["fuels"] if f["fuel"] == plant["fuel"]), None)
    water = waste_item = None
    water_per_min = waste_per_min = 0.0
    if fuel and fuel["supplemental"]:
        # supplemental (water) m3/min = MW * ratio * 60 / 1000
        water = fuel["supplemental"]
        water_per_min = mw * g["supplemental_to_power_ratio"] * 60.0 / 1000.0
    if fuel and fuel["byproduct"]:
        waste_item = fuel["byproduct"]
        waste_per_min = fuel_per_min * fuel["byproduct_amount"]
    return {"mw": mw, "fuel_per_min": fuel_per_min, "supplemental": water, "supplemental_per_min": water_per_min,
            "waste": waste_item, "waste_per_min": waste_per_min}


def build_ledger(factories: list[dict], goals: list[dict], plants: list[dict], raw_resources: set) -> list[dict]:
    """factories: [{id, name, outputs{item:rate}, raws{item:rate}, surplus{item:rate}}]
    goals: [{item, rate_per_min}] (item goals only). plants: [{generator, fuel, count, clock_pct}].
    Returns rows sorted deficits first: {item, supply, demand, net, parts}. Raw resources are excluded
    (they are budgeted against nodes, not supplied by factories)."""
    rows: dict[str, dict] = {}

    def row(item):
        return rows.setdefault(item, {"item": item, "supply": 0.0, "demand": 0.0,
                                      "sources": [], "sinks": []})

    for f in factories:
        for item, r in f["outputs"].items():
            x = row(item)
            x["supply"] += r
            x["sources"].append((f["name"], r))
        for item, r in f["surplus"].items():
            x = row(item)
            x["supply"] += r
            x["sources"].append((f["name"] + " (byproduct)", r))
        for item, r in f["raws"].items():
            if item in raw_resources:
                continue
            x = row(item)
            x["demand"] += r
            x["sinks"].append((f["name"], r))
    for g in goals:
        x = row(g["item"])
        x["demand"] += g["rate_per_min"]
        x["sinks"].append(("World goal", g["rate_per_min"]))
    for p in plants:
        st = generator_stats(p)
        label = f"{gd.load()['generators'][p['generator']]['name']} ×{p['count']}"
        if st["fuel_per_min"] > EPS:
            x = row(p["fuel"])
            x["demand"] += st["fuel_per_min"]
            x["sinks"].append((label, st["fuel_per_min"]))
        if st["supplemental"] and st["supplemental_per_min"] > EPS and st["supplemental"] not in raw_resources:
            x = row(st["supplemental"])
            x["demand"] += st["supplemental_per_min"]
            x["sinks"].append((label, st["supplemental_per_min"]))
        if st["waste"] and st["waste_per_min"] > EPS:
            x = row(st["waste"])
            x["supply"] += st["waste_per_min"]
            x["sources"].append((label + " (waste)", st["waste_per_min"]))
    out = []
    for item, x in rows.items():
        x["net"] = x["supply"] - x["demand"]
        out.append(x)
    out.sort(key=lambda x: (x["net"] >= -EPS, x["net"], x["item"]))
    return out


def raw_budget(raw_demand: dict, available: dict) -> list[dict]:
    """raw_demand: {item: per_min}, available: {item: per_min or inf}. Over-budget first."""
    out = []
    for item in sorted(set(raw_demand) | set(available)):
        d = raw_demand.get(item, 0.0)
        a = available.get(item)
        out.append({"item": item, "demand": d, "available": a,
                    "unbudgeted": a is None,
                    "over": a is not None and d > a + EPS,
                    "pct": (d / a * 100.0) if a not in (None, 0) and a != float("inf") else 0.0})
    out.sort(key=lambda x: (not x["over"], -x["pct"], x["item"]))
    return out


def allocate_flows(consumers: list[dict], producers: list[dict]) -> list[dict]:
    """Match external-input demand to producing factories.
    consumers: [{factory, item, rate}]; producers: [{factory, item, rate}] (capacity per item).
    Returns [{from, to, item, rate}] filling producers in id order; shortfalls get no flow."""
    cap = {}
    for p in producers:
        cap.setdefault(p["item"], []).append([p["factory"], p["rate"]])
    flows = []
    for c in sorted(consumers, key=lambda c: (c["item"], c["factory"])):
        need = c["rate"]
        for slot in sorted(cap.get(c["item"], []), key=lambda s: s[0]):
            if need <= EPS:
                break
            if slot[0] == c["factory"] or slot[1] <= EPS:
                continue
            take = min(need, slot[1])
            slot[1] -= take
            need -= take
            flows.append({"from": slot[0], "to": c["factory"], "item": c["item"], "rate": take})
    return flows
