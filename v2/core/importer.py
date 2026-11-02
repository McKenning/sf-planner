"""Turn grouped save buildings into factory data (lines, rates, labels, flows, matching). Pure."""
from collections import Counter, defaultdict

from core import gamedata as gd
from core import grouping as gp
from core import recipes as rc
from core.power import machine_output_multiplier, machine_power_mw

OUTPOST_MAX_MACHINES = 60


def sloops_of(building: dict, boost: float) -> int:
    per = building.get("sloop_boost_per_slot") or 0
    if building["sloop_slots"] <= 0 or per <= 0 or boost <= 1.0 + 1e-9:
        return 0
    return min(building["sloop_slots"], round((boost - 1.0) / per))


def machine_lines(buildings: list[dict], members: list[int]) -> tuple[list[dict], list[str]]:
    """Aggregate a group's machines into production lines by (recipe, machine, clock, sloops)."""
    recipes, blds = gd.recipes(), gd.buildings()
    agg = defaultdict(int)
    notes = []
    for i in members:
        b = buildings[i]
        if b["kind"] != "machine":
            continue
        if not b.get("recipe") or b["recipe"] not in recipes:
            notes.append(f"{b['cls']} without a known recipe ({b.get('recipe')})")
            continue
        r = recipes[b["recipe"]]
        bld = blds.get(b["cls"])
        if not bld or bld["class"] != r["machine"]:
            if not bld:
                notes.append(f"unknown machine {b['cls']}")
                continue
        clock = round(b.get("clock", 1.0) * 100, 3)
        agg[(b["recipe"], b["cls"], clock, sloops_of(bld, b.get("boost", 1.0)))] += 1
    lines = []
    for (rcp, cls, clock, sl), count in sorted(agg.items()):
        r, bld = recipes[rcp], blds[cls]
        cpm = 60.0 / r["duration_s"] * (clock / 100.0) * count
        m = machine_output_multiplier(bld, 100.0, sl) / 1.0  # sloop part only (clock applied via cpm)
        mult = 1.0 + (sl / bld["sloop_slots"] if bld["sloop_slots"] else 0)
        lines.append({
            "recipe": rcp, "recipe_name": r["name"], "machine": cls, "machine_name": bld["name"],
            "item": r["outputs"][0]["item"], "count": count, "clock_pct": clock, "sloops": sl,
            "power_mw": count * machine_power_mw(bld, clock, sl),
            "inputs": {s["item"]: s["amount"] * cpm for s in r["inputs"]},
            "outputs": {s["item"]: s["amount"] * mult * cpm for s in r["outputs"]},
        })
    return lines, notes


def net_rates(lines: list[dict]) -> tuple[dict, dict]:
    """(outputs, needs): items/min the group makes beyond its own use, and items it must receive."""
    prod, cons = Counter(), Counter()
    for l in lines:
        for k, v in l["outputs"].items():
            prod[k] += v
        for k, v in l["inputs"].items():
            cons[k] += v
    # An intermediate that the group makes AND uses is "balanced" when the difference is rounding noise
    # (clocks are stored to 3 decimals): ignore it below 0.1 % of what flows through, so it does not show up
    # as a phantom 0.00/min output (and a phantom planned line). Final products (never consumed) always count.
    tol = lambda k: 1e-6 + 0.001 * max(prod[k], cons[k]) if (prod[k] > 0 and cons[k] > 0) else 1e-6
    outs = {k: prod[k] - cons[k] for k in prod if prod[k] - cons[k] > tol(k)}
    needs = {k: cons[k] - prod[k] for k in cons if cons[k] - prod[k] > tol(k) and not rc.is_raw(k)}
    return outs, needs


def classify(summary: dict, lines: list[dict]) -> str:
    k = summary["kinds"]
    m = sum(l["count"] for l in lines)
    ext, gen = k.get("extractor", 0), k.get("generator", 0)
    if m == 0 and ext == 0 and gen > 0:
        return "power"
    if m == 0 and ext > 0:
        return "outpost"
    if ext > 0 and m <= OUTPOST_MAX_MACHINES and all(
            rc.is_raw(i) for l in lines for i in l["inputs"]):
        return "outpost"          # extractors + first-step processing only (ore -> ingot, wet concrete ...)
    if m == 0:
        return "other"
    return "factory"


def _nearest(groups_xy, b, max_dist):
    best, bd = None, max_dist
    for gi, (x, y, z) in enumerate(groups_xy):
        d = ((b["x"] - x) ** 2 + (b["y"] - y) ** 2 + (b["z"] - z) ** 2) ** 0.5
        if d < bd:
            best, bd = gi, d
    return best


def build_groups(payload: dict, method: str = "connection", threshold: float = 60.0,
                 long_link: float = 300.0) -> dict:
    """Group the payload and describe every group. Returns {groups, flows, method, params}."""
    B, L = payload["buildings"], payload["links"]
    cut = []
    if method == "distance":
        raw = gp.group_by_distance(B, threshold)
    else:
        raw, cut = gp.group_by_connection(B, L, long_link)
    # stations / depot uploaders: attach to neighbours' group, else nearest group
    where = {i: gi for gi, g in enumerate(raw) for i in g}
    useful = [gi for gi, g in enumerate(raw) if any(B[i]["kind"] in ("machine", "extractor", "generator") for i in g)]
    useful_set = set(useful)
    nbrs = defaultdict(list)
    for a, b, _l in L:
        nbrs[a].append(b)
        nbrs[b].append(a)
    xy = {gi: tuple(sum(B[i][c] for i in raw[gi]) / len(raw[gi]) for c in ("x", "y", "z")) for gi in useful}
    members = {gi: list(raw[gi]) for gi in useful}
    for i, b in enumerate(B):
        if where[i] in useful_set:
            continue
        cand = Counter(where[n] for n in nbrs[i] if where[n] in useful_set)
        target = cand.most_common(1)[0][0] if cand else None
        if target is None and b["kind"] in ("station", "storage"):
            near = _nearest([xy[g] for g in useful], b, 250.0)
            target = useful[near] if near is not None else None
        if target is not None and (b["kind"] in ("station", "junction", "storage")):
            members[target].append(i)
    out = []
    for gi in useful:
        mem = sorted(members[gi])
        s = gp.summarize(B, mem)
        lines, notes = machine_lines(B, mem)
        outs, needs = net_rates(lines)
        label = classify(s, lines)
        # name by the most advanced product it ships (deepest recipe chain), ties by rate
        top = max(outs.items(), key=lambda kv: (item_depth(kv[0]), kv[1]))[0] if outs else None
        name = None
        if top:
            name = gd.items()[top]["name"]
        out.append({
            "members": mem, "label": label, "summary": s, "lines": lines, "notes": notes,
            "outputs": outs, "needs": needs, "suggested_name": name,
            "power_mw": sum(l["power_mw"] for l in lines),
            "plants": plants_of(B, mem) if label == "power" or s["kinds"].get("generator") else [],
        })
    out.sort(key=lambda g: (-g["summary"]["size"]))
    for n, g in enumerate(out):
        g["id"] = n
        g["name"] = unique_name(g, n, out)
    cut_pairs = []
    gid = {i: g["id"] for g in out for i in g["members"]}
    for a, b, length in cut:
        if a in gid and b in gid and gid[a] != gid[b]:
            cut_pairs.append((gid[a], gid[b], length))
    return {"method": method, "params": {"threshold": threshold, "long_link": long_link},
            "groups": out, "cut_links": cut_pairs}


_DEPTH = {}


def item_depth(item: str, _stack=()) -> int:
    """How many production steps from raw resources (default recipes; loops cut)."""
    if item in _DEPTH:
        return _DEPTH[item]
    if rc.is_raw(item) or item in _stack:
        return 0
    r = rc.default_recipe(item)
    if not r:
        return 0
    d = 1 + max((item_depth(s["item"], _stack + (item,)) for s in gd.recipes()[r]["inputs"]), default=0)
    if not _stack:
        _DEPTH[item] = d
    return d


def unique_name(g, n, groups):
    base = g["suggested_name"] or "Area"
    suffix = {"outpost": "outpost", "power": "power plant", "factory": "factory", "other": "area"}[g["label"]]
    if g["label"] == "power":
        base = "Generator"
    same = [x for x in groups[:n] if x["suggested_name"] == g["suggested_name"] and x["label"] == g["label"]]
    s = g["summary"]
    where = f"({s['x']:.0f}, {s['y']:.0f})"
    return f"{base} {suffix} {where}" if same else f"{base} {suffix}"


def plants_of(buildings, members):
    """Generators in a group -> [{generator, fuel, count, clock_pct}] (unknown fuel -> first fuel in the Docs)."""
    gens = gd.load()["generators"]
    agg = Counter()
    for i in members:
        b = buildings[i]
        if b["kind"] != "generator" or b["cls"] not in gens:
            continue
        fuel = b.get("fuel")
        if fuel not in gd.items():
            fuel = gens[b["cls"]]["fuels"][0]["fuel"] if gens[b["cls"]]["fuels"] else None
        if fuel:
            agg[(b["cls"], fuel, round(b.get("clock", 1.0) * 100, 3))] += 1
    return [{"generator": g, "fuel": f, "clock_pct": c, "count": n} for (g, f, c), n in sorted(agg.items())]


def transport_flows(result: dict) -> list[dict]:
    """Flows between groups: group A has a surplus of an item that group B needs.
    transport: belt if a long link joins them, else train/drone/truck if both have such a station."""
    groups = {g["id"]: g for g in result["groups"] if g["label"] in ("factory", "outpost")}
    linked = {(min(a, b), max(a, b)) for a, b, _l in result["cut_links"]}
    spare = {gid: dict(g["outputs"]) for gid, g in groups.items()}
    flows = []
    for bid, b in sorted(groups.items()):
        for item, need in sorted(b["needs"].items()):
            for aid, a in sorted(groups.items()):
                if aid == bid or need <= 1e-6:
                    continue
                have = spare[aid].get(item, 0.0)
                if have <= 1e-6:
                    continue
                take = min(have, need)
                transport = None
                if (min(aid, bid), max(aid, bid)) in linked:
                    transport = "belt"
                else:
                    for mode in ("train", "drone", "truck"):
                        if a["summary"]["stations"].get(mode) and b["summary"]["stations"].get(mode):
                            transport = mode
                            break
                spare[aid][item] -= take
                need -= take
                flows.append({"from": aid, "to": bid, "item": item, "rate": take, "transport": transport})
    return flows


def overlap(a_ids: set, b_ids: set) -> float:
    """Share of the smaller set found in the other (for re-import matching, >= 0.5 = same factory)."""
    if not a_ids or not b_ids:
        return 0.0
    return len(a_ids & b_ids) / min(len(a_ids), len(b_ids))
