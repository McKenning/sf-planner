"""
Production chain solver.

Given:
  - A list of top-level targets: [(product, rate_per_min), ...]
  - A recipe choice map: {product: recipe_name} (which recipe to use for each)

Compute:
  - Per-product totals: {product: rate_per_min_needed}
  - Per-product machine count, building, power, clock %
  - Raw resource totals
  - Total power
"""
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# Treat as terminal (don't expand)
TREAT_AS_RAW = {
    "Iron Ore", "Copper Ore", "Limestone", "Coal", "Caterium Ore", "Raw Quartz",
    "Sulfur", "Bauxite", "Uranium", "SAM", "Crude Oil", "Water", "Nitrogen Gas",
    "Leaves", "Wood", "Mycelia", "Alien Protein",
    "Blue Power Slug", "Yellow Power Slug", "Purple Power Slug", "Power Shard",
    "Hatcher Remains", "Hog Remains", "Spitter Remains", "Stinger Remains",
    "Bacon Agaric", "Beryl Nut", "Paleberry",
    "Excited Photonic Matter",
    "Reanimated SAM",
    "Plutonium Waste", "Uranium Waste",
    "Dissolved Silica",
}

# These raws are what the user budgets in their Resources table
BUDGET_RAWS = ["Iron Ore", "Copper Ore", "Limestone", "Coal", "Caterium Ore",
               "Raw Quartz", "Sulfur", "Bauxite", "Uranium", "SAM",
               "Crude Oil", "Water", "Nitrogen Gas"]


def is_planner_recipe(name: str) -> bool:
    """Filter out recipes that are noise for production planning."""
    if name.startswith("Unpackage"):
        return False
    if name.startswith("Packaged "):
        return False
    if name.startswith("Residual "):
        return False
    # Resource conversion recipes have parens, skip unless biomass
    if "(" in name and ")" in name and "Biomass" not in name:
        return False
    return True


class RecipeDB:
    """Indexed view of recipes for fast solving."""

    def __init__(self, raw_recipes: List[Tuple]):
        # raw_recipes: list of (name, inputs, outputs, machines, duration)
        self.recipes_by_name: Dict[str, dict] = {}
        # producers[product] -> list of recipe names that output it
        self.producers: Dict[str, List[str]] = defaultdict(list)
        # For convenience: per-product output qty for each recipe
        self.out_qty_for: Dict[Tuple[str, str], float] = {}

        for name, inputs, outputs, machines, duration in raw_recipes:
            if not is_planner_recipe(name):
                continue
            primary = next((m for m in machines
                            if m not in ("Crafting Bench", "Equipment Workshop")),
                           machines[0])
            self.recipes_by_name[name] = {
                "name": name,
                "inputs": list(inputs),
                "outputs": list(outputs),
                "machine": primary,
                "duration": duration,
            }
            for out_item, out_qty in outputs:
                if name not in self.producers[out_item]:
                    self.producers[out_item].append(name)
                self.out_qty_for[(out_item, name)] = out_qty

    def default_recipe(self, product: str) -> Optional[str]:
        """Pick a sensible default recipe for a product."""
        recs = self.producers.get(product, [])
        if not recs:
            return None
        # Prefer non-Alternate where this product is the FIRST output (primary)
        for rec_name in recs:
            rec = self.recipes_by_name[rec_name]
            if not rec_name.startswith("Alternate:") and rec["outputs"][0][0] == product:
                return rec_name
        # Fall back: any non-Alternate
        for rec_name in recs:
            if not rec_name.startswith("Alternate:"):
                return rec_name
        return recs[0]

    def all_choices_for(self, product: str) -> List[str]:
        """All recipe options for a product, ordered with primary-output non-alt first."""
        recs = self.producers.get(product, [])
        if not recs:
            return []
        std_primary, std_other, alt_primary, alt_other = [], [], [], []
        for rn in recs:
            r = self.recipes_by_name[rn]
            is_alt = rn.startswith("Alternate:")
            is_primary = r["outputs"][0][0] == product
            if not is_alt and is_primary:
                std_primary.append(rn)
            elif not is_alt:
                std_other.append(rn)
            elif is_alt and is_primary:
                alt_primary.append(rn)
            else:
                alt_other.append(rn)
        return std_primary + std_other + alt_primary + alt_other


def solve(targets: Dict[str, float],
          choices: Dict[str, str],
          db: RecipeDB,
          machine_power: Dict[str, float]) -> dict:
    """
    Walk the production graph. Returns:
      {
        "products": [{name, total_per_min, recipe, machine, out_per_min_at_100,
                      machines_ceil, clock_pct, power_total, ingredients: [...], is_raw}],
        "raws": {raw_name: total_per_min},
        "total_power": float,
        "warnings": [str, ...],
      }
    """
    needed = defaultdict(float)
    for prod, rate in targets.items():
        if rate and prod:
            needed[prod] += rate

    # BFS/iterative expansion. Process in waves: keep a worklist of (product, rate)
    # to "subtract" — since each product's required rate increases as more consumers
    # are found, we accumulate first, then resolve in topological order.
    # 
    # Simpler approach: iterate until stable. For each iteration, for each non-raw
    # product with a recipe, compute its ingredient demands and add to other products.
    # We handle ordering by computing in a topo-sorted sequence.

    # Step 1: build a topo order rooted at the targets
    # discovered = set of all products that appear in the chain
    discovered = set(needed.keys())
    queue = list(needed.keys())
    while queue:
        p = queue.pop()
        if p in TREAT_AS_RAW:
            continue
        rec_name = choices.get(p) or db.default_recipe(p)
        if not rec_name or rec_name not in db.recipes_by_name:
            continue
        rec = db.recipes_by_name[rec_name]
        for ing, _ in rec["inputs"]:
            if ing not in discovered:
                discovered.add(ing)
                queue.append(ing)

    # Topological sort: consumer before producer (final products first)
    # We do Kahn's: in_degree counts how many consumers reference this product.
    consumers_of = defaultdict(set)
    for p in discovered:
        if p in TREAT_AS_RAW:
            continue
        rec_name = choices.get(p) or db.default_recipe(p)
        if not rec_name or rec_name not in db.recipes_by_name:
            continue
        rec = db.recipes_by_name[rec_name]
        for ing, _ in rec["inputs"]:
            consumers_of[ing].add(p)

    in_deg = {p: len(consumers_of[p]) for p in discovered}
    from collections import deque
    order = []
    dq = deque([p for p in discovered if in_deg[p] == 0])
    seen = set()
    while dq:
        p = dq.popleft()
        if p in seen:
            continue
        seen.add(p)
        order.append(p)
        if p in TREAT_AS_RAW:
            continue
        rec_name = choices.get(p) or db.default_recipe(p)
        if not rec_name or rec_name not in db.recipes_by_name:
            continue
        rec = db.recipes_by_name[rec_name]
        for ing, _ in rec["inputs"]:
            in_deg[ing] -= 1
            if in_deg[ing] == 0:
                dq.append(ing)

    # If any didn't get visited (cycle - rare), append them
    for p in discovered:
        if p not in seen:
            order.append(p)

    # Step 2: in topo order, propagate demand
    for p in order:
        if p in TREAT_AS_RAW:
            continue
        rec_name = choices.get(p) or db.default_recipe(p)
        if not rec_name or rec_name not in db.recipes_by_name:
            continue
        rec = db.recipes_by_name[rec_name]
        out_qty = next((q for o, q in rec["outputs"] if o == p), rec["outputs"][0][1])
        cycles_per_min = 60.0 / rec["duration"]
        out_per_min_100 = out_qty * cycles_per_min
        # How many machines (fractional) needed
        if out_per_min_100 <= 0:
            continue
        scale = needed[p] / out_per_min_100  # = "machines at 100%" needed (fractional)
        for ing, ing_qty in rec["inputs"]:
            ing_per_min = ing_qty * cycles_per_min * scale
            needed[ing] += ing_per_min

    # Step 3: build output structures
    # Two-pass: first intermediates (in topo order), then raws (in topo order).
    # This keeps the raw resources visually grouped at the bottom.
    products_out_intermediates = []
    products_out_raws = []
    raws_out = {}
    total_power = 0.0
    warnings = []

    for p in order:
        rate = needed[p]
        if rate <= 1e-9 and p not in targets:
            continue
        if p in TREAT_AS_RAW:
            raws_out[p] = rate
            products_out_raws.append({
                "name": p, "total_per_min": rate, "recipe": None, "machine": None,
                "out_per_min_at_100": None, "machines_ceil": None,
                "clock_pct": None, "power_total": 0, "ingredients": [],
                "is_raw": True, "is_target": p in targets,
            })
            continue
        rec_name = choices.get(p) or db.default_recipe(p)
        if not rec_name or rec_name not in db.recipes_by_name:
            warnings.append(f"No recipe found for {p}")
            products_out_intermediates.append({
                "name": p, "total_per_min": rate, "recipe": None, "machine": None,
                "out_per_min_at_100": None, "machines_ceil": None,
                "clock_pct": None, "power_total": 0, "ingredients": [],
                "is_raw": False, "is_target": p in targets, "warning": True,
            })
            continue
        rec = db.recipes_by_name[rec_name]
        out_qty = next((q for o, q in rec["outputs"] if o == p), rec["outputs"][0][1])
        cycles_per_min = 60.0 / rec["duration"]
        out_per_min_100 = out_qty * cycles_per_min
        scale = rate / out_per_min_100
        machines_ceil = -(-rate // out_per_min_100) if out_per_min_100 > 0 else 0  # ceil
        machines_ceil = int(machines_ceil)
        per_machine_clock = (scale / machines_ceil * 100) if machines_ceil > 0 else 0
        power = machine_power.get(rec["machine"], 0) * scale
        total_power += power
        ingredients = []
        for ing, ing_qty in rec["inputs"]:
            ingredients.append({
                "name": ing, "per_min": ing_qty * cycles_per_min * scale
            })
        products_out_intermediates.append({
            "name": p,
            "total_per_min": rate,
            "recipe": rec_name,
            "machine": rec["machine"],
            "out_per_min_at_100": out_per_min_100,
            "machines_ceil": machines_ceil,
            "clock_pct": per_machine_clock,
            "power_total": power,
            "ingredients": ingredients,
            "is_raw": False,
            "is_target": p in targets,
        })

    # Concatenate: intermediates first, then raws
    products_out = products_out_intermediates + products_out_raws

    return {
        "products": products_out,
        "raws": raws_out,
        "total_power": total_power,
        "warnings": warnings,
    }
