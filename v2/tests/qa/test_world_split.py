"""Top-down: goal -> split into factories -> automatic flows, numbers vs oracle (QA brief tests 1-2)."""
import html
import re

from . import oracle as o


def text(page):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page)))


def flow_rows(server):
    page = server.get("/flows")[1]
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", page, re.S):
        c = [text(x).strip() for x in re.findall(r"<td.*?>(.*?)</td>", tr, re.S)]
        if len(c) >= 5 and "→" in c[1]:
            out.append((c[0], c[1], float(c[2].split("/")[0]), c[4]))
    return out


def test_goal_split_creates_flows_with_oracle_rates(fresh_server):
    s = fresh_server
    assert s.post("/goals/add", {"item": "Reinforced Iron Plate", "rate": "5"})[0] == 303
    page = text(s.get("/goals")[1])
    exp = o.plan({"Reinforced Iron Plate": 5})
    assert f"Iron Ore {exp['raws']['Iron Ore']:.0f}" in page.replace("/", "").replace("  ", " ") or str(round(exp["raws"]["Iron Ore"])) in page
    for item, name in (("Desc_IronPlateReinforced_C", "Plates"), ("Desc_IronPlate_C", "Plate maker"), ("Desc_IronScrew_C", "Screw maker")):
        st, _, h = s.post("/goals/assign", {"item": item, "new_name": name})   # subtree box unchecked: direct ingredients become inputs
        assert st == 303, (item, st)
    rows = flow_rows(s)
    got = {(r[0], r[1]): r[2] for r in rows}
    # Reinforced Iron Plate recipe: 6 plates + 12 screws per plate every 12 s -> 5/min needs 30 plates, 60 screws
    assert got[("Iron Plate", "Plate maker → Plates")] == 30.0
    assert got[("Screws", "Screw maker → Plates")] == 60.0
    assert all(r[3] == "auto" for r in rows)
    home = text(s.get("/")[1])
    # plates and screws are fully supplied; only the (unassigned) ingots and rods are honestly reported as deficits
    assert "Deficit: Iron Plate" not in home and "Deficit: Screws" not in home
    assert "Deficit: Iron Ingot short by 45.00/min" in home and "Deficit: Iron Rod short by 15.00/min" in home




def test_link_a_deficit_creates_manual_flow(fresh_server):
    s = fresh_server
    assert s.post("/goals/add", {"item": "Iron Plate", "rate": "60"})[0] == 303
    assert s.post("/goals/assign", {"item": "Desc_IronPlate_C", "new_name": "Plates"})[0] == 303
    home = text(s.get("/")[1])
    assert "Deficit: Iron Ingot short by 90.00/min" in home           # 60 plates need 90 ingots; nobody makes them
    a = s.new_factory("Smelters")
    assert s.post(f"/factory/{a}/output", {"item": "Iron Ingot", "rate": "100"})[0] == 303
    assert s.post("/ledger/link", {"item": "Desc_IronIngot_C", "from_factory": str(a)})[0] == 303
    rows = flow_rows(s)
    assert [(r[0], r[1], r[2], r[3]) for r in rows] == [("Iron Ingot", "Smelters → Plates", 90.0, "manual")]
    assert "Deficit" not in text(s.get("/")[1])
    # nothing left to link: a second click must explain, not duplicate
    assert s.post("/ledger/link", {"item": "Desc_IronIngot_C", "from_factory": str(a)})[0] == 400
    assert len(flow_rows(s)) == 1
