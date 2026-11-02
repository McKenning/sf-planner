"""Recipe indexing, planner filtering and default-recipe choice. Pure; works on gamedata dicts."""
from collections import defaultdict
from functools import lru_cache

from core import gamedata as gd


def is_planner_recipe(r: dict) -> bool:
    """Drop recipes that are noise for production planning (same rules as 1.x, applied to Docs data)."""
    name = r["name"]
    if name.startswith(("Unpackage", "Packaged ", "Residual ")):
        return False
    # resource-to-resource Converter recipes e.g. "Coal (Iron)": noise unless the output is a real product
    if "(" in name and ")" in name and "Biomass" not in name:
        prim = gd.items().get(r["outputs"][0]["item"], {})
        return not prim.get("raw", False)
    return True


@lru_cache(maxsize=1)
def producers() -> dict[str, list[str]]:
    """item class -> planner recipe classes producing it (sorted by name for determinism)."""
    out = defaultdict(list)
    for cls, r in sorted(gd.recipes().items(), key=lambda kv: kv[1]["name"]):
        if not is_planner_recipe(r):
            continue
        for o in r["outputs"]:
            if cls not in out[o["item"]]:
                out[o["item"]].append(cls)
    return dict(out)


def is_raw(item: str) -> bool:
    """Terminal inputs: raw resources and anything no planner recipe makes (leaves, slugs, ...)."""
    it = gd.items().get(item, {})
    return bool(it.get("raw")) or item not in producers()


def _qty(r: dict, item: str) -> float:
    return sum(o["amount"] for o in r["outputs"] if o["item"] == item)


def _classify(item: str, rcls: str):
    r = gd.recipes()[rcls]
    qty = _qty(r, item)
    others = [o["amount"] for o in r["outputs"] if o["item"] != item]
    sole = not others
    byproduct = (not sole) and max(others) > qty
    primary = r["outputs"][0]["item"] == item and not byproduct
    return sole, primary, byproduct, qty, (max(others) if others else 0)


def default_recipe(item: str) -> str | None:
    """Same priority as 1.x: standard sole > standard primary > standard other (unless all are
    byproducts and a dedicated alternate exists) > alternates."""
    recs = producers().get(item, [])
    if not recs:
        return None
    std = {"sole": [], "primary": [], "other": []}
    alt = {"sole": [], "primary": [], "other": []}
    for rc in recs:
        sole, primary, _bp, _q, _m = _classify(item, rc)
        bucket = alt if gd.recipes()[rc]["alternate"] else std
        bucket["sole" if sole else "primary" if primary else "other"].append(rc)
    if std["sole"]:
        return std["sole"][0]
    if std["primary"]:
        return std["primary"][0]
    if std["other"]:
        all_bp = all(_classify(item, rc)[3] < _classify(item, rc)[4] for rc in std["other"])
        if all_bp and alt["sole"]:
            return alt["sole"][0]
        return std["other"][0]
    for k in ("sole", "primary", "other"):
        if alt[k]:
            return alt[k][0]
    return recs[0]


def choices_for(item: str) -> list[str]:
    """All recipe options, primary-output standard first."""
    recs = producers().get(item, [])
    buckets = ([], [], [], [])
    for rc in recs:
        r = gd.recipes()[rc]
        primary = r["outputs"][0]["item"] == item
        buckets[(2 if r["alternate"] else 0) + (0 if primary else 1)].append(rc)
    return [x for b in buckets for x in b]
