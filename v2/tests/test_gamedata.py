import json
from pathlib import Path

import pytest

from core import gamedata as gd

DOCS = Path.home() / "sf-inputs/docs/en-US.json"


def test_build_and_version():
    d = gd.load()
    assert d["build"] == "25782416" and d["game_version"] == "1.1"


def test_recipe_integrity():
    for r in gd.recipes().values():
        assert r["machine"] in gd.buildings()
        assert r["duration_s"] > 0
        for s in r["inputs"] + r["outputs"]:
            assert s["item"] in gd.items()
            assert s["amount"] > 0


def test_known_recipe():
    r = gd.recipe_by_name("Iron Plate")
    assert r["duration_s"] == 6 and r["inputs"] == [{"item": "Desc_IronIngot_C", "amount": 3}]
    assert r["outputs"] == [{"item": "Desc_IronPlate_C", "amount": 2}]


def test_fluid_units_are_m3():
    r = gd.recipes()["Recipe_Alternate_PureIronIngot_C"]
    assert {"item": "Desc_Water_C", "amount": 4.0} in r["inputs"]


@pytest.mark.skipif(not DOCS.exists(), reason="Docs file not present")
def test_recipe_count_matches_docs():
    """Every Docs recipe that is crafted in a production machine is in gamedata."""
    import re
    raw = json.load(open(DOCS, encoding="utf-16"))
    by = {e["NativeClass"].split(".")[-1].rstrip("'"): e["Classes"] for e in raw}
    machines = set(gd.buildings())
    expected = {c["ClassName"] for c in by["FGRecipe"]
                if machines & set(re.findall(r"\.(\w+_C)\b", c["mProducedIn"])) and "mProduct" in c
                and re.search(r"Amount=", c["mProduct"])}
    assert set(gd.recipes()) == expected
    assert len(gd.recipes()) == 291
