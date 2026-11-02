"""Plan vs. the independent oracle (QA brief test 1). Every number the page/exports show must match to 0.01."""
import pytest

from . import oracle as o

ABS = 0.011


def set_goal(c, fid, targets, choices=None, overrides=None):
    for name, rate in targets.items():
        st, _, _ = c.post(f"/factory/{fid}/output", {"item": name, "rate": str(rate)})
        assert st == 303
    for item, rec in (choices or {}).items():
        ov = (overrides or {}).get(item, (None, None))
        st, _, _ = c.post(f"/factory/{fid}/override", {"item": o.item(item), "recipe": o.recipe(rec),
                                                       "clock_pct": "" if ov[0] is None else str(ov[0]),
                                                       "sloops": "" if not ov[1] else str(ov[1])})
        assert st == 303
    for item, ov in (overrides or {}).items():
        if item in (choices or {}):
            continue
        st, _, _ = c.post(f"/factory/{fid}/override", {"item": o.item(item), "recipe": "",
                                                       "clock_pct": "" if ov[0] is None else str(ov[0]),
                                                       "sloops": "" if not ov[1] else str(ov[1])})
        assert st == 303


def compare(app, exp):
    assert app["power_mw"] == pytest.approx(exp["power_mw"], abs=ABS), "total power"
    assert app["somersloops"] == exp["sloops"]
    assert {k: round(v, 2) for k, v in app["raw_inputs_per_min"].items()} == pytest.approx(
        {k: round(v, 2) for k, v in exp["raws"].items()}, abs=ABS)
    assert set(app["byproduct_surplus_per_min"]) == set(exp["surplus"]), (app["byproduct_surplus_per_min"], exp["surplus"])
    for k, v in exp["surplus"].items():
        assert app["byproduct_surplus_per_min"][k] == pytest.approx(v, abs=ABS), k
    got = {l["recipe"]: l for l in app["lines"]}
    assert set(got) == {l["recipe"] for l in exp["lines"]}, (sorted(got), [l["recipe"] for l in exp["lines"]])
    for l in exp["lines"]:
        a = got[l["recipe"]]
        assert a["count"] == l["count"], l["recipe"]
        assert a["clock_pct"] == pytest.approx(l["clock"], abs=ABS), l["recipe"]
        assert a["somersloops_each"] == l["sloops"], l["recipe"]
        assert a["power_mw"] == pytest.approx(l["power"], abs=ABS), l["recipe"]
        for k, v in l["in"].items():
            assert a["inputs_per_min"][k] == pytest.approx(v, abs=ABS), (l["recipe"], k)
        for k, v in l["out"].items():
            assert a["outputs_per_min"][k] == pytest.approx(v, abs=ABS), (l["recipe"], k)


CASES = {
    "iron_plate_60": dict(targets={"Iron Plate": 60}),
    "rip_bolted": dict(targets={"Reinforced Iron Plate": 5}, choices={"Reinforced Iron Plate": "Alternate: Bolted Iron Plate"}),
    "hmf_10": dict(targets={"Heavy Modular Frame": 10}),
    # HOR byproduct of Plastic partly covers the Diluted Fuel's Heavy Oil Residue
    "plastic_hor_reuse": dict(targets={"Plastic": 30, "Fuel": 60}, choices={"Fuel": "Alternate: Diluted Fuel", "Heavy Oil Residue": "Alternate: Heavy Oil Residue"}),
    # loop: Recycled Rubber <-> Recycled Plastic (each consumes the other)
    "recycled_loop": dict(targets={"Plastic": 60, "Rubber": 60},
                          choices={"Plastic": "Alternate: Recycled Plastic", "Rubber": "Alternate: Recycled Rubber"}),
    "distilled_silica": dict(targets={"Silica": 54}, choices={"Silica": "Alternate: Distilled Silica", "Dissolved Silica": "Alternate: Quartz Purification"}),
    # one Manufacturer (Computer 2.5/min at 100%) at 250 % + 2 sloops => 2.5*2.5*1.5 = 9.375/min, 1 machine
    "mfr_250_2": dict(targets={"Computer": 9.375}, overrides={"Computer": (250, 2)}),
    "mfr_250_4": dict(targets={"Computer": 12.5}, overrides={"Computer": (250, 4)}),
    "constructor_250": dict(targets={"Iron Plate": 20 * 2.5}, overrides={"Iron Plate": (250, None)}),
    "fluid_sulfuric": dict(targets={"Sulfuric Acid": 100}),
    "nitric_acid": dict(targets={"Nitric Acid": 30}),
    "uranium_fuel_rod": dict(targets={"Uranium Fuel Rod": 2}),
    "converter_slooped": dict(targets={"Dark Matter Residue": 100}, overrides={"Dark Matter Residue": (None, 2)}),
    "converter_clocked_sloop": dict(targets={"Dark Matter Residue": 250}, overrides={"Dark Matter Residue": (200, 1)}),
    "particle_accel_slooped": dict(targets={"Plutonium Pellet": 10}, overrides={"Plutonium Pellet": (150, 3)}),
}


@pytest.mark.parametrize("case", list(CASES))
def test_case(server, case):
    spec = CASES[case]
    fid = server.new_factory(case)
    set_goal(server, fid, spec["targets"], spec.get("choices"), spec.get("overrides"))
    exp = o.plan(spec["targets"], spec.get("choices"), spec.get("overrides"))
    compare(server.export(fid), exp)


@pytest.mark.parametrize("case", ["hmf_10", "mfr_250_2", "plastic_hor_reuse", "fluid_sulfuric"])
def test_excel_export_matches_oracle(server, case):
    import io
    import openpyxl
    spec = CASES[case]
    fid = server.new_factory("x-" + case)
    set_goal(server, fid, spec["targets"], spec.get("choices"), spec.get("overrides"))
    exp = o.plan(spec["targets"], spec.get("choices"), spec.get("overrides"))
    st, body, hdr = server.get(f"/api/factory/{fid}/export.xlsx", raw=True)
    assert st == 200 and "spreadsheetml" in hdr["Content-Type"]
    wb = openpyxl.load_workbook(io.BytesIO(body))
    s = {r[0]: r[1] for r in wb["Summary"].iter_rows(min_row=2, values_only=True) if r[0]}
    assert s["Total power (MW)"] == pytest.approx(exp["power_mw"], abs=0.011)
    assert s["Somersloops used"] == exp["sloops"]
    lines = list(wb["Lines"].iter_rows(min_row=2, values_only=True))
    got = {l[2]: l for l in lines}
    assert set(got) == {l["recipe"] for l in exp["lines"]}
    for l in exp["lines"]:
        g = got[l["recipe"]]
        assert g[4] == l["count"] and g[5] == pytest.approx(l["clock"], abs=0.0011) and g[6] == l["sloops"]
        assert g[7] == pytest.approx(l["power"], abs=0.0011)
    for k, v in exp["raws"].items():
        raw = {r[0]: r[1] for r in wb["Summary"].iter_rows(values_only=True) if r[0]}
        assert raw[k] == pytest.approx(v, abs=0.0011), k
