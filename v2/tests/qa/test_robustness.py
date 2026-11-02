"""QA robustness: bad input must give 4xx (never 5xx) and must not poison stored data (QA.md R-*)."""
import json

import pytest

BADNUM = ["nan", "inf", "-inf", "1e400", "1e308", "0", "-5", "1e-9", "abc", ""]


@pytest.fixture(scope="module")
def fid(server):
    return server.new_factory("robust")


@pytest.mark.parametrize("v", BADNUM)
def test_output_rate_rejected(server, fid, v):
    st, _, _ = server.post(f"/factory/{fid}/output", {"item": "Iron Plate", "rate": v})
    assert st in (400, 422), (v, st)
    assert server.get(f"/factory/{fid}")[0] == 200


@pytest.mark.parametrize("v", ["nan", "inf", "1e400", "1e308", "0", "-1"])
def test_goal_rate_rejected_and_goals_page_survives(server, v):
    assert server.post("/goals/add", {"item": "Iron Plate", "rate": v})[0] in (400, 422)
    assert server.post("/goals/power", {"mw": v})[0] in (400, 422)
    assert server.get("/goals")[0] == 200 and server.get("/")[0] == 200


def test_goal_assign_bad_input(server):
    assert server.post("/goals/add", {"item": "Iron Plate", "rate": "60"})[0] == 303
    assert server.post("/goals/assign", {"item": "Desc_IronPlate_C", "factory_id": "abc"})[0] == 400
    assert server.post("/goals/assign", {"item": "Desc_IronPlate_C", "factory_id": "99999"})[0] == 400
    assert server.post("/goals/assign", {"item": "Desc_IronPlate_C", "new_name": ""})[0] == 400
    assert server.post("/goals/assign", {"item": "nonexistent", "new_name": "x"})[0] == 400


def test_flows_validation(server):
    a, b = server.new_factory("fa"), server.new_factory("fb")
    base = {"item": "Iron Plate", "from_factory": str(a), "to_factory": str(b)}
    for v in ("nan", "inf", "1e308", "0"):
        assert server.post("/flows/add", dict(base, rate=v))[0] == 400, v
    assert server.post("/flows/add", dict(base, rate="5", from_factory="99998", to_factory="99999"))[0] == 400
    assert server.post("/flows/add", dict(base, rate="5"))[0] == 303
    assert server.get("/flows")[0] == 200 and server.get("/")[0] == 200


def test_resources_and_power_bounds(server):
    big = "99999999999999999999"
    assert server.post("/resources/update", {"resource": "Desc_OreIron_C", "pure": big})[0] == 400
    assert server.post("/resources/update", {"resource": "nonexistent", "pure": "5"})[0] == 404
    gen = {"generator": "Build_GeneratorCoal_C", "fuel": "Desc_Coal_C"}
    assert server.post("/power/add", dict(gen, count=big))[0] == 400
    assert server.post("/power/add", dict(gen, count="0"))[0] == 400
    assert server.post("/power/add", dict(gen, count="1", clock_pct="nan"))[0] == 400
    assert server.post("/power/update", {"plant_id": "99999", "count": "1", "clock_pct": "100"})[0] == 404
    assert server.get("/power")[0] == 200


@pytest.mark.parametrize("path", ["/factory/99999", "/factory/-1", "/item/zzz", "/recipe/zzz",
                                  "/api/factory/99999/export.xlsx", "/api/factory/99999/export.json",
                                  "/api/factory/99999/solve"])
def test_bad_ids_are_404(server, path):
    assert server.get(path)[0] == 404


def test_import_api_bad_payloads(server):
    ok = {"format": 1, "buildings": [], "links": []}
    bad = [([], None), ({"payload": "x"}, None), ({"payload": dict(ok, buildings="x")}, None),
           ({"payload": dict(ok, buildings=[{"id": 1}])}, None),
           ({"payload": dict(ok, links=[[0, 1, 5]])}, None),
           ({"payload": ok, "threshold": "nan"}, None), ({"payload": ok, "threshold": -5}, None)]
    for body, _ in bad:
        assert server.req("POST", "/api/import/group", body=body)[0] == 400, body
    for body in ({"payload": ok, "groups": [{"ids": []}]}, {"payload": ok, "groups": [{"ids": ["a"]}]},
                 {"payload": ok, "groups": "x"}, {"payload": ok}):
        assert server.req("POST", "/api/import/save", body=body)[0] == 400, body
    assert server.req("POST", "/api/import/group", body=None, form={"x": "1"})[0] in (400, 415, 422)
