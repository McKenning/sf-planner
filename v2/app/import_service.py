"""Save import: describe groups, save them as built factories, match on re-import."""
import hashlib
import json

from app import world_service as ws
from core import gamedata as gd
from core import importer as im

TEXT_LABELS = ("factory", "outpost", "power", "other")


def digest(payload: dict) -> str:
    """Stable fingerprint of what the save contains that matters for planning."""
    rows = sorted((b["id"], b["cls"], b.get("recipe"), round(b.get("clock", 1.0), 4), round(b.get("boost", 1.0), 4))
                  for b in payload["buildings"] if b["kind"] in ("machine", "generator", "extractor"))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def describe(payload: dict, members: list[int], label: str | None = None) -> dict:
    B = payload["buildings"]
    s = im.gp.summarize(B, members)
    lines, notes = im.machine_lines(B, members)
    outs, needs = im.net_rates(lines)
    return {"members": members, "summary": s, "lines": lines, "notes": notes, "outputs": outs, "needs": needs,
            "label": label or im.classify(s, lines), "plants": im.plants_of(B, members)}


def latest_run_buildings(conn, world_id: int):
    """{factory_id: set(instance names)} from each factory's most recent import_run."""
    out = {}
    for r in conn.execute(
            "SELECT ib.factory_id, ib.instance_name FROM imported_building ib "
            "JOIN import_run ir ON ir.id = ib.import_run_id WHERE ir.world_id=? AND ib.factory_id IS NOT NULL "
            "AND ib.import_run_id = (SELECT MAX(ib2.import_run_id) FROM imported_building ib2 "
            "WHERE ib2.factory_id = ib.factory_id)", (world_id,)):
        out.setdefault(r["factory_id"], set()).add(r["instance_name"])
    return out


def save(conn, payload: dict, groups: list[dict], file_name: str, params: dict) -> dict:
    """groups: [{ids:[building ids], name, label, attach_factory_id|None}]. One transaction by caller."""
    wid = ws.world_id(conn)
    dg = digest(payload)
    # what the reviewer chose: which buildings go to which group, with what type and attach target.
    # (names are cosmetic and do not count). Same save + same choices = nothing to do.
    spec = sorted((sorted(g["ids"]), g.get("label") or "", g.get("attach_factory_id") or 0) for g in groups)
    gdg = hashlib.sha256(json.dumps(spec).encode()).hexdigest()
    last = conn.execute("SELECT summary FROM import_run WHERE world_id=? ORDER BY id DESC LIMIT 1", (wid,)).fetchone()
    if last and last["summary"]:
        try:
            ls = json.loads(last["summary"])
            if ls.get("digest") == dg and ls.get("groups_digest") in (None, gdg):
                return {"unchanged": True, "message": "This save is identical to the last import — nothing changed."}
        except ValueError:
            pass
    B = payload["buildings"]
    by_id = {b["id"]: i for i, b in enumerate(B)}
    prev = latest_run_buildings(conn, wid)
    run = conn.execute("INSERT INTO import_run(world_id, file_name, summary) VALUES (?,?,?)",
                       (wid, file_name, None)).lastrowid
    stats = {"created": 0, "updated": 0, "attached": 0, "plants": 0, "flows": 0, "skipped": 0, "unmatched": []}
    used_factories, gid_to_factory, described = set(), {}, []
    for n, g in enumerate(groups):
        idx = sorted(by_id[i] for i in g["ids"] if i in by_id)
        label = g.get("label")
        if label is not None and label not in TEXT_LABELS:
            raise ValueError(f"unknown label {label!r}")
        d = describe(payload, idx, label)
        d["name"], d["spec"] = " ".join(str(g.get("name") or f"Area {n + 1}").split())[:120] or f"Area {n + 1}", g
        described.append(d)
    for n, d in enumerate(described):
        label, spec = d["label"], d["spec"]
        if label in ("other",) or (label == "power" and not d["lines"]):
            fid = None
        else:
            fid = None
            if label != "power":
                names = {B[i]["id"] for i in d["members"]}
                attach = spec.get("attach_factory_id")
                if attach:
                    row = conn.execute("SELECT id, status FROM factory WHERE id=? AND world_id=?", (attach, wid)).fetchone()
                    if row and row["status"] != "archived" and row["id"] not in used_factories:
                        fid = row["id"]
                        stats["attached"] += 1
                if fid is None:
                    best = max(((im.overlap(names, ids), f) for f, ids in prev.items() if f not in used_factories),
                               default=(0, None))
                    if best[0] >= 0.5:
                        fid = best[1]
                        stats["updated"] += 1
                if fid is None:
                    s = d["summary"]
                    note = f"Imported from {file_name} ({label})."
                    fid = conn.execute(
                        "INSERT INTO factory(world_id,name,status,x,y,z,notes,origin) VALUES (?,?, 'built',?,?,?,?, 'import')",
                        (wid, d["name"], s["x"], s["y"], s["z"], note)).lastrowid
                    for item, rate in d["outputs"].items():
                        conn.execute("INSERT INTO factory_output(factory_id,item,rate_per_min) VALUES (?,?,?)",
                                     (fid, item, round(rate, 4)))
                    stats["created"] += 1
                used_factories.add(fid)
                gid_to_factory[n] = fid
                conn.execute("DELETE FROM production_line WHERE factory_id=?", (fid,))
                for l in d["lines"]:
                    conn.execute("INSERT INTO production_line(factory_id,item,recipe,machine,count,clock_pct,sloops) "
                                 "VALUES (?,?,?,?,?,?,?)", (fid, l["item"], l["recipe"], l["machine"], l["count"],
                                                            l["clock_pct"], l["sloops"]))
        for i in d["members"]:
            b = B[i]
            if b["kind"] in ("machine", "extractor", "generator", "station"):
                conn.execute("INSERT INTO imported_building(import_run_id,instance_name,class,recipe,clock,sloops,x,y,z,"
                             "factory_id,grp) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                             (run, b["id"], b["cls"], b.get("recipe"), b.get("clock"),
                              im.sloops_of(gd.buildings()[b["cls"]], b.get("boost", 1.0)) if b["cls"] in gd.buildings() else 0,
                              b["x"], b["y"], b["z"], fid, d["name"]))
        # generators -> power plants (upsert by a key stable across saves)
        key = min(B[i]["id"] for i in d["members"]) if d["members"] else str(n)
        for p in d["plants"]:
            ref = f"save:{key}:{p['generator']}:{p['fuel']}:{p['clock_pct']}"
            cur = conn.execute("UPDATE power_plant SET count=? WHERE source_ref=?", (p["count"], ref)).rowcount
            if not cur:
                conn.execute("INSERT INTO power_plant(world_id,name,generator,fuel,count,clock_pct,source_ref) "
                             "VALUES (?,?,?,?,?,?,?)", (wid, f"{d['name']} (import)", p["generator"], p["fuel"],
                                                        p["count"], p["clock_pct"], ref))
                stats["plants"] += 1
    # flows between imported groups
    where = {i: n for n, d in enumerate(described) for i in d["members"]}
    long_link = float(params.get("long_link", 300))
    cut = {(min(where[a], where[b]), max(where[a], where[b]), l) for a, b, l in payload["links"]
           if l > long_link and a in where and b in where and where[a] != where[b]}
    rr = {"groups": [{"id": n, "label": d["label"], "outputs": d["outputs"], "needs": d["needs"],
                      "summary": d["summary"]} for n, d in enumerate(described)],
          "cut_links": sorted(cut)}
    for fl in im.transport_flows(rr):
        a, b = gid_to_factory.get(fl["from"]), gid_to_factory.get(fl["to"])
        if not a or not b or a == b:
            continue
        cur = conn.execute("UPDATE flow SET rate_per_min=?, transport=COALESCE(?, transport) WHERE world_id=? "
                           "AND from_factory=? AND to_factory=? AND item=? AND auto=0",
                           (round(fl["rate"], 4), fl["transport"], wid, a, b, fl["item"])).rowcount
        if not cur:
            conn.execute("INSERT INTO flow(world_id,from_factory,to_factory,item,rate_per_min,transport,auto) "
                         "VALUES (?,?,?,?,?,?,0)", (wid, a, b, fl["item"], round(fl["rate"], 4), fl["transport"]))
            stats["flows"] += 1
    # flag imported factories that vanished from this save (never deleted)
    seen_now = set(used_factories)
    for f in prev:
        if f not in seen_now:
            row = conn.execute("SELECT name, notes FROM factory WHERE id=?", (f,)).fetchone()
            if row and "not found in import" not in (row["notes"] or ""):
                conn.execute("UPDATE factory SET notes=? WHERE id=?",
                             ((row["notes"] or "") + f" [not found in import of {file_name}]", f))
            stats["unmatched"].append(row["name"] if row else f)
    summary = {"digest": dg, "groups_digest": gdg, **{k: v for k, v in stats.items()}, "groups": len(described),
               "game": payload.get("game"), "params": {k: v for k, v in params.items() if k != "cut_links"}}
    conn.execute("UPDATE import_run SET summary=? WHERE id=?", (json.dumps(summary), run))
    conn.execute("UPDATE world SET save_name=?, game_build=COALESCE(game_build, ?) WHERE id=?",
                 ((payload.get("game") or {}).get("saveName") or file_name, gd.load()["build"], wid))
    return {"unchanged": False, "run_id": run, **stats}
