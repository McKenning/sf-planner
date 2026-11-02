"""Generate v2/core/gamedata.json from the game's Docs file (en-US.json, UTF-16).

Usage: python tools/build_gamedata.py [path/to/en-US.json]
Never hand-edit the output; re-run this and review the diff.
"""
import json
import re
import sys
from pathlib import Path

DEFAULT_SRC = Path.home() / "sf-inputs/docs/en-US.json"
OUT = Path(__file__).resolve().parent.parent / "core" / "gamedata.json"
BUILD = "25782416"
GAME_VERSION = "1.1"

ITEM_RE = re.compile(r"ItemClass=\"[^\"]*?\.(\w+)'?\"\s*,\s*Amount=(\d+)")
CLASS_RE = re.compile(r"\.(\w+_C)\b")
FLUID = {"RF_LIQUID", "RF_GAS"}


def f(c, k, default=0.0):
    try:
        return float(c.get(k, default))
    except (TypeError, ValueError):
        return default


def sloop_slots(c):
    """Somersloop slots. The Docs' mProductionShardSlotSize is unreliable (Smelter reports 0 but has
    1 slot in game), so derive: round(1 / boost-per-slot) if production boost is allowed, else 0."""
    mult = f(c, "mProductionShardBoostMultiplier")
    if c.get("mCanChangeProductionBoost") != "True" or mult <= 0:
        return 0
    return round(1 / mult)


def load(src):
    raw = json.load(open(src, encoding="utf-16"))
    return {e["NativeClass"].split(".")[-1].rstrip("'"): e["Classes"] for e in raw}


def parse_stacks(s, fluid_items):
    out = []
    for cls, amt in ITEM_RE.findall(s or ""):
        amt = int(amt)
        if cls in fluid_items:
            amt = amt / 1000  # Docs store fluids in mL; we use m3
        out.append({"item": cls, "amount": amt})
    return out


def build(src):
    by = load(src)

    # ---- items ----
    items = {}
    raw_resources = {c["ClassName"] for c in by["FGResourceDescriptor"]}
    for n, classes in by.items():
        for c in classes:
            if not c["ClassName"].startswith(("Desc_", "BP_ItemDescriptor", "BP_EquipmentDescriptor")) \
                    or "mDisplayName" not in c:
                continue
            if c["ClassName"] in items:
                continue
            items[c["ClassName"]] = {
                "class": c["ClassName"],
                "name": c["mDisplayName"],
                "form": c.get("mForm", "RF_SOLID"),
                "sink_points": int(f(c, "mResourceSinkPoints")),
                "energy_mj": f(c, "mEnergyValue"),
                "raw": c["ClassName"] in raw_resources,
            }
    fluid_items = {k for k, v in items.items() if v["form"] in FLUID}

    # ---- buildings (production machines) ----
    buildings = {}
    for n in ("FGBuildableManufacturer", "FGBuildableManufacturerVariablePower"):
        for c in by[n]:
            variable = n.endswith("VariablePower")
            if variable:
                pmin = f(c, "mEstimatedMininumPowerConsumption")
                pmax = f(c, "mEstimatedMaximumPowerConsumption")
                power = (pmin + pmax) / 2
            else:
                pmin = pmax = power = f(c, "mPowerConsumption")
            buildings[c["ClassName"]] = {
                "class": c["ClassName"],
                "name": c["mDisplayName"],
                "power_mw": power,
                "variable_power": variable,
                "power_min_mw": pmin,
                "power_max_mw": pmax,
                "clock_exponent": f(c, "mPowerConsumptionExponent"),
                "sloop_power_exponent": f(c, "mProductionBoostPowerConsumptionExponent"),
                "sloop_slots": sloop_slots(c),
                "sloop_boost_per_slot": f(c, "mProductionShardBoostMultiplier"),
                "min_clock": f(c, "mMinPotential"),
                "max_clock": f(c, "mMaxPotential"),
            }

    # ---- extractors ----
    extractors = {}
    for n in ("FGBuildableResourceExtractor", "FGBuildableWaterPump", "FGBuildableFrackingExtractor"):
        for c in by[n]:
            allowed = CLASS_RE.findall(c.get("mAllowedResources", ""))
            amount = f(c, "mItemsPerCycle")
            extractors[c["ClassName"]] = {
                "class": c["ClassName"],
                "name": c["mDisplayName"],
                "power_mw": f(c, "mPowerConsumption"),
                "cycle_time_s": f(c, "mExtractCycleTime", 1.0),
                "items_per_cycle": amount,
                "forms": re.findall(r"RF_\w+", c.get("mAllowedResourceForms", "")),
                "allowed_resources": allowed,
                "clock_exponent": f(c, "mPowerConsumptionExponent", 1.321929),
            }

    # ---- generators ----
    generators = {}
    for n in ("FGBuildableGeneratorFuel", "FGBuildableGeneratorNuclear"):
        for c in by[n]:
            fuels = []
            for fu in c["mFuel"]:
                if not fu["mFuelClass"]:
                    continue
                fuels.append({
                    "fuel": fu["mFuelClass"],
                    "supplemental": fu["mSupplementalResourceClass"] or None,
                    "byproduct": fu["mByproduct"] or None,
                    "byproduct_amount": float(fu["mByproductAmount"] or 0),
                })
            generators[c["ClassName"]] = {
                "class": c["ClassName"],
                "name": c["mDisplayName"],
                "power_mw": f(c, "mPowerProduction"),
                "supplemental_load": f(c, "mSupplementalLoadAmount"),
                "supplemental_to_power_ratio": f(c, "mSupplementalToPowerRatio"),
                "fuels": fuels,
            }

    # ---- recipes ----
    recipes = {}
    for c in by["FGRecipe"]:
        produced_in = CLASS_RE.findall(c.get("mProducedIn", ""))
        machines = [m for m in produced_in if m in buildings]
        if not machines:
            continue
        ins = parse_stacks(c["mIngredients"], fluid_items)
        outs = parse_stacks(c["mProduct"], fluid_items)
        if not outs:
            continue
        recipes[c["ClassName"]] = {
            "class": c["ClassName"],
            "name": c["mDisplayName"],
            "alternate": c["ClassName"].startswith("Recipe_Alternate_"),
            "machine": machines[0],
            "duration_s": f(c, "mManufactoringDuration"),
            "inputs": ins,
            "outputs": outs,
        }

    # sanity: every referenced item exists
    for r in recipes.values():
        for s in r["inputs"] + r["outputs"]:
            if s["item"] not in items:
                raise SystemExit(f"{r['class']} references unknown item {s['item']}")

    # keep only items that matter (used by a recipe, resource, or fuel)
    used = {s["item"] for r in recipes.values() for s in r["inputs"] + r["outputs"]}
    used |= raw_resources
    for g in generators.values():
        for fu in g["fuels"]:
            used |= {x for x in (fu["fuel"], fu["supplemental"], fu["byproduct"]) if x}
    items = {k: v for k, v in sorted(items.items()) if k in used}

    return {
        "game_version": GAME_VERSION,
        "build": BUILD,
        "items": items,
        "recipes": dict(sorted(recipes.items())),
        "buildings": dict(sorted(buildings.items())),
        "extractors": dict(sorted(extractors.items())),
        "generators": dict(sorted(generators.items())),
    }


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    data = build(src)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(data['items'])} items, {len(data['recipes'])} recipes, "
          f"{len(data['buildings'])} buildings, {len(data['extractors'])} extractors, "
          f"{len(data['generators'])} generators")


if __name__ == "__main__":
    main()
