"""Generators vs the oracle (QA brief test 1: nuclear MW, waste/min, fluids in m3/min)."""
import html
import re

import pytest

from . import oracle as o

CASES = [  # (generator class, fuel, count, clock, waste items per fuel item)
    ("Build_GeneratorNuclear_C", "Uranium Fuel Rod", 3, 150, 50),   # Docs: Uranium Fuel Rod -> 50 Uranium Waste (mWasteAmount? see oracle note)
    ("Build_GeneratorNuclear_C", "Plutonium Fuel Rod", 2, 100, 10),
    ("Build_GeneratorCoal_C", "Coal", 5, 100, 0),
    ("Build_GeneratorFuel_C", "Fuel", 4, 250, 0),
]


def rows(page):
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", page, flags=re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<td.*?>(.*?)</td>", tr, flags=re.S)]
        vals = re.findall(r'value="([^"]*)"', tr)
        if len(cells) >= 9:
            out.append((cells, vals))
    return out


@pytest.mark.parametrize("gen,fuel,count,clock,waste", CASES)
def test_generator_row(server, gen, fuel, count, clock, waste):
    name = f"qa-{gen}-{fuel}"
    st, _, _ = server.post("/power/add", {"name": name, "generator": gen, "fuel": o.item(fuel), "count": str(count),
                                           "clock_pct": str(clock)})
    assert st == 303
    page = server.get("/power")[1]
    row = [c for c, v in rows(page) if c[0] == name][0]
    exp = o.generator(gen, fuel, count, clock, waste)
    mw, fuel_pm = float(row[5].replace(",", "")), float(row[6].replace(",", ""))
    assert mw == pytest.approx(exp["mw"], abs=0.5)           # page shows whole MW
    assert fuel_pm == pytest.approx(exp["fuel_per_min"], abs=0.011)
    if exp["water_m3_per_min"]:
        assert float(row[7]) == pytest.approx(exp["water_m3_per_min"], abs=0.06)
    if waste:
        assert float(row[8].split()[0]) == pytest.approx(exp["waste_per_min"], abs=0.06)
