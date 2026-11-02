"""QA: imported built factories vs the save read independently (save_oracle.mjs) and the Docs-file oracle.
python tests/qa/check_import_vs_save.py <dev planner2.db> <save_oracle.json> <import_run_id>"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.qa import oracle as o  # noqa: E402

db, js, run = sys.argv[1], json.load(open(sys.argv[2])), int(sys.argv[3])
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
D = o.data()
bad = 0
rows = c.execute("SELECT * FROM imported_building WHERE import_run_id=? AND class LIKE 'Build_%'", (run,)).fetchall()
mach = [r for r in rows if r["instance_name"] in js]
print(len(rows), "imported rows;", len(mach), "machines matched to the save;", len(js), "machines in save")
missing = [k for k in js if k not in {r["instance_name"] for r in rows}]
print("save machines not stored by import:", len(missing))
for r in mach:
    s = js[r["instance_name"]]
    clk = s["potential"] if s["potential"] is not None else (s["pending"] if s["pending"] is not None else 1.0)
    if s["recipe"] != r["recipe"] or abs((r["clock"] or 1.0) - clk) > 1e-6 or r["class"] != s["cls"]:
        bad += 1
        if bad < 10:
            print("MISMATCH", r["instance_name"], dict(r), s)
    boost = s["boost"] if s["boost"] is not None else (s["pendingBoost"] if s["pendingBoost"] is not None else 1.0)
    m = D["machines"].get(r["class"])
    exp_s = round((boost - 1) * m["slots"]) if m and m["slots"] and boost > 1 else 0
    if (r["sloops"] or 0) != exp_s:
        bad += 1
        print("SLOOP MISMATCH", r["instance_name"], r["sloops"], exp_s, boost)
# per-factory: lines + outputs vs oracle from raw save values
fac = defaultdict(list)
for r in mach:
    if r["factory_id"]:
        fac[r["factory_id"]].append(r)
for fid, ms in sorted(fac.items(), key=lambda kv: -len(kv[1]))[:6]:
    f = c.execute("SELECT name FROM factory WHERE id=?", (fid,)).fetchone()
    prod, cons = Counter(), Counter()
    cnt = Counter()
    for r in ms:
        s = js[r["instance_name"]]
        R = D["recipes"].get(s["recipe"])
        if not R:
            continue
        clk = s["potential"] if s["potential"] is not None else (s["pending"] if s["pending"] is not None else 1.0)
        boost = s["boost"] if s["boost"] is not None else 1.0
        cpm = 60 / R["dur"] * clk
        cnt[R["name"]] += 1
        for i, a in R["in"]:
            cons[i] += a * cpm / o.unit(i)
        for i, a in R["out"]:
            prod[i] += a * boost * cpm / o.unit(i)
    exp = {D["items"][i]["name"]: prod[i] - cons[i] for i in prod if prod[i] - cons[i] > 1e-6}
    got = {}
    for oo in c.execute("SELECT item, rate_per_min FROM factory_output WHERE factory_id=?", (fid,)):
        got[D["items"][oo["item"]]["name"]] = oo["rate_per_min"]
    lines = Counter()
    for l in c.execute("SELECT recipe, SUM(count) n FROM production_line WHERE factory_id=? GROUP BY recipe", (fid,)):
        lines[D["recipes"][l["recipe"]]["name"]] = l["n"]
    ok_cnt = lines == cnt
    ok_out = set(exp) == set(got) and all(abs(exp[k] - got[k]) < 0.011 for k in exp)
    print(f"{f['name'][:40]:40} machines {sum(cnt.values()):4} counts {'OK' if ok_cnt else 'DIFF'}  outputs {'OK' if ok_out else 'DIFF'}")
    if not ok_out:
        bad += 1
        print("   expected", {k: round(v, 2) for k, v in exp.items()}, "\n   got     ", {k: round(v, 2) for k, v in got.items()})
    if not ok_cnt:
        bad += 1
        print("   expected", dict(cnt), "\n   got", dict(lines))
print("RESULT", "OK" if not bad else f"{bad} problems")
