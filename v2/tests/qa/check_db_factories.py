"""QA: every non-import factory in a DB solves to the oracle's numbers (choices/overrides read from the DB tables).
python tests/qa/check_db_factories.py <planner2.db> <base url serving that DB>"""
import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.qa import oracle as o  # noqa: E402
from tests.qa.test_oracle_numbers import compare  # noqa: E402

c = sqlite3.connect(sys.argv[1]); c.row_factory = sqlite3.Row
D = o.data()
nm = lambda i: D["items"][i]["name"]
bad = 0
for f in c.execute("SELECT * FROM factory WHERE id <= 5 ORDER BY id"):
    outs = {nm(r["item"]): r["rate_per_min"] for r in c.execute("SELECT * FROM factory_output WHERE factory_id=? AND rate_per_min BETWEEN 0.0001 AND 1000000", (f["id"],))}
    choices = {nm(r["item"]): D["recipes"][r["recipe"]]["name"] for r in c.execute("SELECT * FROM world_recipe WHERE world_id=?", (f["world_id"],)) if r["recipe"] in D["recipes"]}
    ov = {}
    for r in c.execute("SELECT * FROM factory_recipe WHERE factory_id=?", (f["id"],)):
        if r["recipe"] in D["recipes"]:
            choices[nm(r["item"])] = D["recipes"][r["recipe"]]["name"]
        if r["clock_pct"] is not None or r["sloops"]:
            ov[nm(r["item"])] = (r["clock_pct"], r["sloops"])
    ext = {nm(r["item"]) for r in c.execute("SELECT item FROM factory_input WHERE factory_id=?", (f["id"],))}
    if not outs:
        print(f["id"], f["name"], "(no outputs)"); continue
    try:
        exp = o.plan(outs, choices, ov, ext)
    except Exception as e:
        print(f["id"], f["name"], "ORACLE ERROR", e); continue
    app = json.load(urllib.request.urlopen(f"{sys.argv[2]}/api/factory/{f['id']}/export.json"))
    try:
        compare(app, exp); print("OK  ", f["id"], f["name"], f"{exp['power_mw']:.2f} MW", len(exp["lines"]), "lines")
    except AssertionError as e:
        bad += 1; print("DIFF", f["id"], f["name"], str(e)[:300].replace("\n", " "))
print("RESULT", "OK" if not bad else f"{bad} differ")
