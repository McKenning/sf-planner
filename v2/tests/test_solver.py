import pytest

from core import gamedata as gd
from core import recipes as rc
from core import solver


def cls(name):
    return gd.item_by_name(name)["class"]


def rcls(name):
    return gd.recipe_by_name(name)["class"]


def line(res, recipe_name):
    return next(l for l in res["lines"] if l["recipe_name"] == recipe_name)


def test_iron_plate_chain():
    res = solver.solve({cls("Iron Plate"): 60})
    assert line(res, "Iron Plate")["machines_exact"] == pytest.approx(60 / 20)  # 20/min per constructor
    assert res["raws"][cls("Iron Ore")] == pytest.approx(90)
    assert line(res, "Iron Plate")["count"] == 3
    assert res["power_mw"] == pytest.approx(3 * 4 + 3 * 4)  # 3 constructors + 3 smelters


def test_sloop_halves_machines_quadruples_power():
    base = solver.solve({cls("Iron Plate"): 40})
    slo = solver.solve({cls("Iron Plate"): 40}, overrides={cls("Iron Plate"): {"sloops": 1}})
    assert line(base, "Iron Plate")["count"] == 2
    assert line(slo, "Iron Plate")["count"] == 1
    assert line(slo, "Iron Plate")["power_mw"] == pytest.approx(16.0)
    # a slooped line turns the same output into half the cycles, so half the inputs
    assert slo["raws"][cls("Iron Ore")] == pytest.approx(base["raws"][cls("Iron Ore")] / 2)


def test_byproduct_credit_reduces_demand():
    # Plastic (Recycled? no: default) makes Heavy Oil Residue; asking for both must not double count
    res = solver.solve({cls("Plastic"): 100, cls("Heavy Oil Residue"): 10})
    assert not res["warnings"]
    assert res["surplus"] is not None


def test_loop_converges_and_balances():
    ch = {cls("Plastic"): rcls("Alternate: Recycled Plastic"), cls("Rubber"): rcls("Alternate: Recycled Rubber")}
    res = solver.solve({cls("Plastic"): 100}, ch)
    assert not res["warnings"]
    # balance: Rubber made == Rubber consumed
    made = sum(l["outputs"].get(cls("Rubber"), 0) for l in res["lines"])
    used = sum(l["inputs"].get(cls("Rubber"), 0) for l in res["lines"])
    assert made == pytest.approx(used, rel=1e-6)


def test_shared_recipe_not_double_counted():
    r = rcls("Alternate: Heavy Oil Residue")  # makes Heavy Oil Residue + Polymer Resin
    ch = {cls("Heavy Oil Residue"): r, cls("Polymer Resin"): r}
    res = solver.solve({cls("Heavy Oil Residue"): 30, cls("Polymer Resin"): 20}, ch)
    lines = [l for l in res["lines"] if l["recipe"] == r]
    assert len(lines) == 1


def test_default_recipe_prefers_standard():
    assert rc.default_recipe(cls("Iron Plate")) == rcls("Iron Plate")
    assert rc.default_recipe(cls("Iron Ingot")) == rcls("Iron Ingot")


def test_raw_items_terminal():
    assert rc.is_raw(cls("Iron Ore")) and rc.is_raw(cls("Water"))
    assert not rc.is_raw(cls("Iron Ingot"))
