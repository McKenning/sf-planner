"""Independent QA oracle for SF Planner 2.0.

Reads the game's Docs file (~/sf-inputs/docs/en-US.json, UTF-16) directly and computes expected
rates, machine counts and power from first principles. It deliberately imports NOTHING from v2/core or
v2/app, and does not use v2/core/gamedata.json.

Maths (Satisfactory 1.1; https://satisfactory.wiki.gg/wiki/Clock_speed and /wiki/Somersloop):
    P        = P_base * (clock/100)^mPowerConsumptionExponent * (1 + sloops/slots)^mProductionBoostPowerConsumptionExponent
    output   = rate * (1 + sloops/slots)
    slots    = round(1 / mProductionShardBoostMultiplier) when mCanChangeProductionBoost else 0
    variable-power machines (Converter, Particle Accelerator, Quantum Encoder): P_base = mean(min, max)
               (an estimate of the average draw; the wiki gives the same min/max range)
Fluids: the Docs file stores liquid/gas amounts in litres (30000 = 30 m3); the planner shows m3/min.
Generators: output and fuel use are linear in clock speed (wiki.gg/wiki/Clock_speed).
    fuel/min  = MW / mEnergyValue * 60;  supplemental (water) m3/min = MW * ratio * 60 / 1000
    waste/min = fuel/min * waste items per fuel item (Uranium Fuel Rod -> 50 Uranium Waste, see mWasteAmount)

Conventions that are *planner* choices rather than game facts, mirrored here so numbers are comparable:
    machine count = ceil(cycles / (cycles_per_machine_at_target_clock)); the clock is then spread evenly over
    the machines (clock = cycles/(count*cpm)*100).
"""
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

DOCS = Path(os.environ.get("SFP_DOCS", Path.home() / "sf-inputs/docs/en-US.json"))
CLOCK_EXP = 1.321929


def _cls(s: str) -> str:
    """'/Game/.../Desc_IronPlate.Desc_IronPlate_C' -> 'Desc_IronPlate_C'"""
    return s.rsplit(".", 1)[-1].strip("'\" ")


def _amounts(s: str) -> list[tuple[str, float]]:
    return [(_cls(m.group(1)), float(m.group(2))) for m in
            re.finditer(r'ItemClass="[^"]*?([A-Za-z0-9_./]+)\'?",Amount=(\d+)', s or "")]


@lru_cache(maxsize=1)
def data() -> dict:
    d = json.load(open(DOCS, encoding="utf-16"))
    by = {}
    for e in d:
        by.setdefault(e["NativeClass"].split(".")[-1].rstrip("'"), []).extend(e["Classes"])
    items = {}
    for k, lst in by.items():
        if k.startswith(("FGItemDescriptor", "FGResourceDescriptor", "FGConsumableDescriptor")):
            for c in lst:
                items[c["ClassName"]] = {"name": c["mDisplayName"], "form": c.get("mForm"),
                                         "energy": float(c.get("mEnergyValue") or 0),
                                         "resource": k == "FGResourceDescriptor"}
    machines = {}
    for k, lst in by.items():
        if k.startswith("FGBuildableManufacturer") or k.startswith("FGBuildableGenerator"):
            for c in lst:
                boost = float(c.get("mProductionShardBoostMultiplier") or 0)
                can = str(c.get("mCanChangeProductionBoost")).lower() == "true"
                if "mEstimatedMininumPowerConsumption" in c:
                    base = (float(c["mEstimatedMininumPowerConsumption"]) + float(c["mEstimatedMaximumPowerConsumption"])) / 2
                else:
                    base = float(c.get("mPowerConsumption") or 0)
                machines[c["ClassName"]] = {
                    "name": c.get("mDisplayName"), "base": base,
                    "slots": round(1 / boost) if can and boost > 0 else 0,
                    "gen_mw": float(c.get("mPowerProduction") or 0), "water_ratio": float(c.get("mSupplementalToPowerRatio") or 0),
                    "clock_exp": float(c.get("mPowerConsumptionExponent") or CLOCK_EXP),
                    "sloop_exp": float(c.get("mProductionBoostPowerConsumptionExponent") or 2),
                }
    recipes = {}
    for c in by["FGRecipe"]:
        prod = re.findall(r"Build_[A-Za-z0-9_]+_C", c["mProducedIn"])
        prod = [p for p in prod if p in machines]
        if not prod:
            continue
        recipes[c["ClassName"]] = {
            "name": c["mDisplayName"], "alt": c["mDisplayName"].startswith("Alternate:"), "machine": prod[0],
            "dur": float(c["mManufactoringDuration"]), "in": _amounts(c["mIngredients"]), "out": _amounts(c["mProduct"])}
    return {"items": items, "machines": machines, "recipes": recipes}


def item(name: str) -> str:
    for k, v in data()["items"].items():
        if v["name"] == name:
            return k
    raise KeyError(name)


def recipe(name: str) -> str:
    for k, v in data()["recipes"].items():
        if v["name"] == name:
            return k
    raise KeyError(name)


def unit(item_cls: str) -> float:
    """Docs stores fluids in litres; 1000 per m3."""
    return 1000.0 if data()["items"][item_cls]["form"] in ("RF_LIQUID", "RF_GAS") else 1.0


def is_raw(item_cls: str) -> bool:
    return data()["items"][item_cls]["resource"]


def default_recipe(item_cls: str) -> str | None:
    """The standard recipe is, by the game's naming convention, Recipe_<ItemName>_C (Desc_IronPlate_C ->
    Recipe_IronPlate_C). Fall back to the single non-alternate machine recipe that makes it."""
    rs = data()["recipes"]
    guess = "Recipe_" + item_cls[len("Desc_"):]
    if guess in rs:
        return guess
    std = [k for k, r in rs.items() if not r["alt"] and any(o[0] == item_cls for o in r["out"])]
    return std[0] if len(std) == 1 else None


def slots(machine: str) -> int:
    return data()["machines"][machine]["slots"]


def machine_power(machine: str, clock_pct: float = 100.0, sloops: int = 0) -> float:
    m = data()["machines"][machine]
    return m["base"] * (clock_pct / 100.0) ** m["clock_exp"] * (1 + sloops / m["slots"] if m["slots"] else 1) ** m["sloop_exp"]


def _solve_linear(A, b):
    n = len(b)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            raise ValueError("singular system (recipe loop that never closes?)")
        M[c], M[p] = M[p], M[c]
        for r in range(n):
            if r != c:
                f = M[r][c] / M[c][c]
                for k in range(c, n + 1):
                    M[r][k] -= f * M[c][k]
    return [M[i][n] / M[i][i] for i in range(n)]


def plan(targets: dict, choices: dict | None = None, overrides: dict | None = None, external: set | None = None) -> dict:
    """targets {item display name: per min}; choices {item name: recipe display name};
    overrides {item name: (clock_pct, sloops)}; external {item names} treated like raw inputs.
    Returns lines, raws, surplus (all keyed by display name, per minute, m3 for fluids), power_mw, sloops."""
    D = data()
    choices = {item(k): recipe(v) for k, v in (choices or {}).items()}
    overrides = {item(k): v for k, v in (overrides or {}).items()}
    external = {item(k) for k in (external or set())}
    T = {item(k): v for k, v in targets.items()}
    owner: dict[str, str] = {}
    raws: set[str] = set()
    todo = list(T)
    while todo:
        i = todo.pop()
        if i in owner or i in raws:
            continue
        r = choices.get(i) or default_recipe(i)
        if is_raw(i) or (i in external and i not in T) or r is None:
            raws.add(i)
            continue
        owner[i] = r
        todo += [x for x, _ in D["recipes"][r]["in"]]
    mult = {}
    for i, r in owner.items():
        m = D["recipes"][r]["machine"]
        s = (overrides.get(i) or (None, 0))[1] or 0
        mult[r] = 1 + s / D["machines"][m]["slots"] if s else 1.0
    active = dict(owner)
    while True:  # active-set: an owner recipe with negative cycles is not needed (its item is fully covered by byproducts)
        rs = sorted(set(active.values()))
        if not rs:
            x = {}
            break
        idx = {r: n for n, r in enumerate(rs)}
        A = [[0.0] * len(rs) for _ in rs]
        b = [0.0] * len(rs)
        eq = {}
        for i, r in active.items():
            eq.setdefault(r, i)  # one equation per recipe (first owner item)
        for r, i in eq.items():
            row = idx[r]
            b[row] = T.get(i, 0.0)
            for r2 in rs:
                R = D["recipes"][r2]
                A[row][idx[r2]] += sum(a for it, a in R["out"] if it == i) * mult[r2] / unit(i)
                A[row][idx[r2]] -= sum(a for it, a in R["in"] if it == i) / unit(i)
        x_l = _solve_linear(A, b)
        neg = [r for r, v in zip(rs, x_l) if v < -1e-9]
        if not neg:
            x = {r: max(0.0, v) for r, v in zip(rs, x_l)}
            break
        worst = min(neg, key=lambda r: x_l[idx[r]])
        active = {i: r for i, r in active.items() if r != worst}
        raws |= {i for i, r in owner.items() if r == worst} - {i for i in T}
    lines, power, sl = [], 0.0, 0
    prod, cons = {}, {}
    for r, c in x.items():
        R = D["recipes"][r]
        M = D["machines"][R["machine"]]
        if c < 1e-9:
            continue
        own = [i for i, rr in owner.items() if rr == r]
        clock_t, s = overrides.get(own[0]) or (None, 0)
        clock_t = clock_t or 100.0
        cpm = 60.0 / R["dur"]
        count = max(1, math.ceil(c / (cpm * clock_t / 100) - 1e-9))
        clock = c / (count * cpm) * 100
        p = count * machine_power(R["machine"], clock, s or 0)
        power += p
        sl += (s or 0) * count
        ins = {i: a * c / unit(i) for i, a in R["in"]}
        outs = {i: a * mult[r] * c / unit(i) for i, a in R["out"]}
        for i, v in ins.items():
            cons[i] = cons.get(i, 0) + v
        for i, v in outs.items():
            prod[i] = prod.get(i, 0) + v
        lines.append({"recipe": R["name"], "machine": M["name"], "count": count, "exact": c / cpm, "clock": clock,
                      "sloops": s or 0, "power": p, "in": {D["items"][i]["name"]: v for i, v in ins.items()},
                      "out": {D["items"][i]["name"]: v for i, v in outs.items()}, "items": [D["items"][i]["name"] for i in own]})
    n = lambda i: D["items"][i]["name"]
    raw_need = {n(i): T.get(i, 0) + cons.get(i, 0) - prod.get(i, 0) for i in raws}
    raw_need = {k: v for k, v in raw_need.items() if v > 1e-7}
    surplus = {n(i): prod[i] - cons.get(i, 0) - T.get(i, 0) for i in prod if i not in raws}
    surplus = {k: v for k, v in surplus.items() if v > 1e-7}
    return {"lines": sorted(lines, key=lambda l: l["recipe"]), "raws": raw_need, "surplus": surplus,
            "power_mw": power, "sloops": sl}


def generator(gen_class: str, fuel_name: str, count: int, clock_pct: float, waste_per_fuel: float = 0.0) -> dict:
    D = data()
    g = D["machines"][gen_class]
    fuel = item(fuel_name)
    mw = g["gen_mw"] * count * clock_pct / 100
    fpm = mw / (D["items"][fuel]["energy"] * unit(fuel)) * 60  # Docs: fluid energy is MJ per litre
    return {"mw": mw, "fuel_per_min": fpm, "water_m3_per_min": mw * g["water_ratio"] * 60 / 1000,
            "waste_per_min": fpm * waste_per_fuel}


if __name__ == "__main__":
    # self-check against the wiki golden values
    assert abs(machine_power(recipe_machine := data()["recipes"][recipe("Iron Plate")]["machine"], 250) - 13.4310) < 1e-3, "constructor @250% = 13.43 MW"
    print("oracle ok; Constructor@250% =", round(machine_power(recipe_machine, 250), 4))
