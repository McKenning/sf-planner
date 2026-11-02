"""Group imported buildings into candidate factories two ways. Pure functions on the worker's compact JSON.

Buildings: [{id, cls, kind, x, y, z, ...}] (metres). Links: [[a_index, b_index, length_m]].
  distance:   buildings closer than `threshold` m (3-D) share a group.
  connection: buildings joined by belts/pipes/lifts, passing through splitters/mergers/junctions/storage,
              share a group. Stations and Dimensional Depot uploaders hand items to *other* places, so they
              never join two groups; links longer than `long_link` m become flows, not joins.
"""
from collections import defaultdict
from math import floor, hypot, sqrt

PHYSICAL = {"machine", "extractor", "generator", "storage", "station", "junction"}
BREAKS = {"station"}                  # never union through these
BREAK_CLASSES = ("CentralStorage",)   # dimensional depot uploader


def _breaks(b: dict) -> bool:
    return b["kind"] in BREAKS or any(c in b["cls"] for c in BREAK_CLASSES)


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def group_by_distance(buildings: list[dict], threshold: float = 60.0) -> list[list[int]]:
    n = len(buildings)
    d = DSU(n)
    cell = threshold
    grid = defaultdict(list)
    for i, b in enumerate(buildings):
        grid[(floor(b["x"] / cell), floor(b["y"] / cell), floor(b["z"] / cell))].append(i)
    for (cx, cy, cz), members in grid.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    other = grid.get((cx + dx, cy + dy, cz + dz))
                    if not other:
                        continue
                    for i in members:
                        bi = buildings[i]
                        for j in other:
                            if j <= i:
                                continue
                            bj = buildings[j]
                            if sqrt((bi["x"] - bj["x"]) ** 2 + (bi["y"] - bj["y"]) ** 2 + (bi["z"] - bj["z"]) ** 2) <= threshold:
                                d.union(i, j)
    return _collect(d, n)


def group_by_connection(buildings: list[dict], links: list, long_link: float = 300.0):
    """Returns (groups, long_links) — long_links are the cut links, candidates for flows."""
    n = len(buildings)
    d = DSU(n)
    cut = []
    for a, b, length in links:
        if length > long_link:
            cut.append((a, b, length))
            continue
        if _breaks(buildings[a]) or _breaks(buildings[b]):
            continue
        d.union(a, b)
    return _collect(d, n), cut


def _collect(d: DSU, n: int) -> list[list[int]]:
    out = defaultdict(list)
    for i in range(n):
        out[d.find(i)].append(i)
    return list(out.values())


def attach_breakers(buildings, groups, links):
    """Stations / depot uploaders were never unioned: put each in the group of its neighbours
    (most common neighbour group), else the nearest group by centroid."""
    where = {}
    for gi, g in enumerate(groups):
        for i in g:
            where[i] = gi
    nbrs = defaultdict(list)
    for a, b, _l in links:
        nbrs[a].append(b)
        nbrs[b].append(a)
    return where, nbrs


def summarize(buildings: list[dict], members: list[int]) -> dict:
    kinds = defaultdict(int)
    machines = defaultdict(int)
    recipes = defaultdict(int)
    stations = defaultdict(int)
    xs = ys = zs = 0.0
    for i in members:
        b = buildings[i]
        kinds[b["kind"]] += 1
        xs += b["x"]; ys += b["y"]; zs += b["z"]
        if b["kind"] == "machine":
            machines[b["cls"]] += 1
            if b.get("recipe"):
                recipes[b["recipe"]] += 1
        if b["kind"] == "station":
            stations[b.get("mode") or "?"] += 1
    n = len(members)
    return {"size": n, "kinds": dict(kinds), "machines": dict(machines), "recipes": dict(recipes),
            "stations": dict(stations), "x": xs / n, "y": ys / n, "z": zs / n}


def classify(s: dict) -> str:
    """'power' (generators only), 'outpost' (extractors + a few smelters), 'factory', or 'other'."""
    k = s["kinds"]
    m = sum(s["machines"].values())
    if m == 0 and k.get("extractor", 0) == 0 and k.get("generator", 0) > 0:
        return "power"
    if m == 0 and k.get("extractor", 0) > 0:
        return "outpost"
    if k.get("extractor", 0) > 0 and m <= 8 and set(s["machines"]) <= {"Build_SmelterMk1_C"}:
        return "outpost"
    if m == 0:
        return "other"
    return "factory"
