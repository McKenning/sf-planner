import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app import db, import_service as svc
from core import gamedata as gd
from core import importer as im

SAVE = Path.home() / "sf-inputs/saves/MK1-2i.sav"
NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parent.parent
HAVE_NODE_PARSER = (ROOT / "tools/vendor/node_modules/@etothepii/satisfactory-file-parser").exists()


def c(n):
    return gd.item_by_name(n)["class"]


def rcp(n):
    return gd.recipe_by_name(n)["class"]


# ---------- synthetic payload (always runs) ----------

def machine(i, x, y, recipe="Recipe_IronPlate_C", cls="Build_ConstructorMk1_C", clock=1.0, boost=1.0, z=0):
    return {"id": f"m{i}", "cls": cls, "kind": "machine", "x": x, "y": y, "z": z, "recipe": recipe,
            "clock": clock, "boost": boost}


def synthetic():
    B = [machine(0, 0, 0), machine(1, 10, 0), machine(2, 20, 0),                       # chain A: 3 plates
         machine(3, 1000, 0, "Recipe_IngotIron_C", "Build_SmelterMk1_C"),               # far away: ingots
         machine(4, 1010, 0, "Recipe_IngotIron_C", "Build_SmelterMk1_C"),
         {"id": "j0", "cls": "Build_ConveyorAttachmentSplitter_C", "kind": "junction", "x": 5, "y": 0, "z": 0},
         {"id": "st", "cls": "Build_TrainStation_C", "kind": "station", "mode": "train", "x": 12, "y": 5, "z": 0},
         {"id": "ex", "cls": "Build_MinerMk2_C", "kind": "extractor", "x": 1005, "y": 5, "z": 0, "clock": 1.0,
          "boost": 1.0, "resource": "Desc_OreIron_C"}]
    L = [[0, 5, 8], [5, 1, 8], [1, 2, 8], [3, 4, 5], [7, 3, 4], [2, 6, 3], [1, 3, 990]]  # last = long belt
    return {"format": 1, "game": {"saveName": "syn"}, "buildings": B, "links": L}


def test_connection_vs_distance_and_long_belt():
    p = synthetic()
    conn_ = im.build_groups(p, "connection", long_link=300)
    sizes = sorted(g["summary"]["size"] for g in conn_["groups"])
    assert len(conn_["groups"]) == 2 and sizes == [3, 5]
    a = next(g for g in conn_["groups"] if sum(l["count"] for l in g["lines"] if l["recipe"] == "Recipe_IronPlate_C"))
    assert a["summary"]["stations"] == {"train": 1}           # station attached, did not join anything
    assert len(conn_["cut_links"]) == 1                        # the 990 m belt
    far = im.build_groups(p, "distance", threshold=60)
    assert len(far["groups"]) == 2


def test_labels_and_rates():
    g = im.build_groups(synthetic(), "connection")["groups"]
    ingots = next(x for x in g if x["lines"][0]["recipe"] == "Recipe_IngotIron_C")
    assert ingots["label"] == "outpost"                       # extractor + smelters (raw inputs only)
    plates = next(x for x in g if x["lines"][0]["recipe"] == "Recipe_IronPlate_C")
    assert plates["label"] == "factory"
    assert plates["outputs"][c("Iron Plate")] == pytest.approx(3 * 20)
    assert plates["needs"][c("Iron Ingot")] == pytest.approx(3 * 30)
    fl = im.transport_flows(im.build_groups(synthetic(), "connection"))
    ing = [f for f in fl if f["item"] == c("Iron Ingot")]
    assert len(ing) == 1 and ing[0]["rate"] == pytest.approx(60) and ing[0]["transport"] == "belt"  # 2 smelters x 30


def test_sloops_from_boost():
    p = synthetic()
    p["buildings"][0].update(boost=2.0, clock=2.5)
    lines, _ = im.machine_lines(p["buildings"], [0])
    assert lines[0]["sloops"] == 1 and lines[0]["clock_pct"] == 250
    assert lines[0]["outputs"][c("Iron Plate")] == pytest.approx(20 * 2.5 * 2)  # clock x sloop


@pytest.fixture
def conn(tmp_path):
    p = tmp_path / "i.db"
    db.migrate(p)
    cn = db.connect(p)
    with cn:
        cn.execute("INSERT INTO world(name) VALUES ('Main')")
    return cn


def specs(payload, method="connection"):
    res = im.build_groups(payload, method)
    return [{"ids": [payload["buildings"][i]["id"] for i in g["members"]], "name": g["name"], "label": g["label"]}
            for g in res["groups"]], res


def test_save_reimport_idempotent_and_matching(conn):
    p = synthetic()
    gs, res = specs(p)
    with conn:
        r1 = svc.save(conn, p, gs, "a.sav", {})
    assert r1["created"] == 2 and not r1["unchanged"]
    n_f = conn.execute("select count(*) from factory").fetchone()[0]
    lines = conn.execute("select count(*) from production_line").fetchone()[0]
    with conn:
        r2 = svc.save(conn, p, gs, "a.sav", {})
    assert r2["unchanged"]
    assert conn.execute("select count(*) from factory").fetchone()[0] == n_f
    # modified save: clocks changed + one new machine -> same factories updated, none created
    p2 = copy.deepcopy(p)
    p2["buildings"][0]["clock"] = 2.0
    p2["buildings"].append(machine(9, 30, 0))
    p2["links"].append([2, len(p2["buildings"]) - 1, 8])
    gs2, res2 = specs(p2)
    with conn:
        r3 = svc.save(conn, p2, gs2, "b.sav", {})
    assert r3["created"] == 0 and r3["updated"] == 2, r3
    assert conn.execute("select count(*) from factory").fetchone()[0] == n_f
    row = conn.execute("select count, clock_pct from production_line pl join factory f on f.id=pl.factory_id "
                       "where pl.recipe='Recipe_IronPlate_C' and pl.clock_pct=200").fetchone()
    assert row and row["count"] == 1
    # a group that disappears is flagged, never deleted
    gs3 = gs2[:1]
    p3 = copy.deepcopy(p2)
    p3["buildings"][3]["clock"] = 0.5
    with conn:
        r4 = svc.save(conn, p3, gs3, "c.sav", {})
    assert conn.execute("select count(*) from factory").fetchone()[0] == n_f
    assert r4["unmatched"]


def test_attach_to_planned_factory(conn):
    with conn:
        conn.execute("INSERT INTO factory(world_id,name,status) VALUES (1,'Plates','planned')")
    p = synthetic()
    gs, res = specs(p)
    plates = next(g for g in gs if "Iron Plate" in g["name"] or "Plate" in g["name"])
    plates["attach_factory_id"] = 1
    with conn:
        r = svc.save(conn, p, gs, "a.sav", {})
    assert r["attached"] == 1
    assert conn.execute("select count(*) from production_line where factory_id=1").fetchone()[0] >= 1
    assert conn.execute("select status from factory where id=1").fetchone()[0] == "planned"


# ---------- the real saves ----------

@pytest.fixture(scope="session")
def mk1(tmp_path_factory):
    if not (SAVE.exists() and NODE and HAVE_NODE_PARSER):
        pytest.skip("MK1-2i.sav or node parser not available")
    out = tmp_path_factory.mktemp("sv") / "mk1.json"
    subprocess.run([NODE, str(ROOT / "tools/extract_save.mjs"), str(SAVE), str(out)], check=True,
                   capture_output=True, timeout=120)
    return json.loads(out.read_text())


def test_mk1_acceptance_hmf_factory(mk1):
    """Connection grouping gives the Rocky Desert HMF factory as one factory (standalone, train station,
    multiple floors, receives materials) with its feeder areas separate, linked by flows."""
    res = im.build_groups(mk1, "connection")
    B = mk1["buildings"]
    hmf_idx = [i for i, b in enumerate(B) if b.get("recipe") == "Recipe_Alternate_ModularFrameHeavy_C"]
    assert len(hmf_idx) == 10
    holder = {i: g for g in res["groups"] for i in g["members"]}
    groups = {holder[i]["id"] for i in hmf_idx}
    assert len(groups) == 1, "all HMF machines must be in one group"
    g = next(x for x in res["groups"] if x["id"] in groups)
    assert g["label"] == "factory" and g["name"].startswith("Heavy Modular Frame")
    assert g["summary"]["stations"].get("train", 0) >= 1                      # has its train station
    zs = {round(B[i]["z"] / 8) for i in g["members"] if B[i]["kind"] == "machine"}
    assert len(zs) >= 3                                                       # multiple floors
    assert g["needs"]                                                         # receives materials
    flows = [f for f in im.transport_flows(res) if f["to"] == g["id"]]
    assert len({f["from"] for f in flows}) >= 3                               # fed by separate groups
    feeders = [x for x in res["groups"] if x["id"] in {f["from"] for f in flows}]
    assert sum(1 for x in feeders if x["label"] == "outpost") >= 2            # incl. adjacent outposts
    d = im.build_groups(mk1, "distance")
    assert len({ {i: gg["id"] for gg in d["groups"] for i in gg["members"]}[i] for i in hmf_idx}) == 1


def test_mk1_save_and_reimport_changes_nothing(mk1, conn):
    gs, res = specs(mk1)
    with conn:
        r1 = svc.save(conn, mk1, gs, "MK1-2i.sav", {})
    assert r1["created"] >= 8 and r1["plants"] >= 1
    snap = [conn.execute(f"select count(*) from {t}").fetchone()[0]
            for t in ("factory", "production_line", "flow", "power_plant", "factory_output")]
    with conn:
        r2 = svc.save(conn, mk1, gs, "MK1-2i.sav", {})
    assert r2["unchanged"]
    assert snap == [conn.execute(f"select count(*) from {t}").fetchone()[0]
                    for t in ("factory", "production_line", "flow", "power_plant", "factory_output")]


def test_m1_stress_parses_fast():
    """The 34 MB save parses in well under 30 s (node, same bundle and patches as the browser worker)."""
    big = Path.home() / "sf-inputs/saves/M1-8m.sav"
    if not (big.exists() and NODE and HAVE_NODE_PARSER):
        pytest.skip("M1-8m.sav or node parser not available")
    import time
    t = time.time()
    r = subprocess.run([NODE, str(ROOT / "tools/extract_save.mjs"), str(big)], capture_output=True, timeout=120)
    assert r.returncode == 0, r.stderr[-500:]
    assert time.time() - t < 30
    assert b"27264 buildings" in r.stderr or b"buildings" in r.stderr


def test_built_vs_planned(conn):
    from app import factory_service as fs
    p = synthetic()
    gs, res = specs(p)
    with conn:
        svc.save(conn, p, gs, "a.sav", {})
    fid = conn.execute("select factory_id from production_line where recipe='Recipe_IronPlate_C'").fetchone()[0]
    _o, _c, _ov, sol = fs.solve_factory(conn, fid)
    rows = fs.built_vs_planned(conn, fid, sol)
    plates = next(r for r in rows if r["recipe"] == "Iron Plate")
    assert plates["built"] == 3 and plates["planned"] == 3 and plates["gap"] == 0
