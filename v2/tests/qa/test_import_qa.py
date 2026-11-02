"""Import regressions found by QA (QA-08, QA-09)."""
import pytest

from app import db, import_service as svc
from core import importer as im
from tests.test_import import machine, synthetic, specs


@pytest.fixture
def conn(tmp_path):
    p = tmp_path / "i.db"
    db.migrate(p)
    cn = db.connect(p)
    with cn:
        cn.execute("INSERT INTO world(name) VALUES ('Main')")
    return cn


def test_same_save_different_grouping_is_not_dropped(conn):
    """Re-saving an unchanged save with a different grouping used to answer 'identical, nothing changed'."""
    p = synthetic()
    by_conn, _ = specs(p, "connection")
    by_dist, _ = specs(p, "distance")
    # make the two groupings actually differ: split one connection group in two
    first = by_conn[0]
    by_split = [dict(first, ids=first["ids"][:1]), dict(first, ids=first["ids"][1:], name="second half")] + by_conn[1:]
    with conn:
        assert not svc.save(conn, p, by_conn, "a.sav", {})["unchanged"]
    with conn:
        assert svc.save(conn, p, by_conn, "a.sav", {})["unchanged"]              # same save, same choices
    with conn:
        assert svc.save(conn, p, [dict(g, name="renamed only") for g in by_conn], "a.sav", {})["unchanged"]  # names are cosmetic
    with conn:
        assert not svc.save(conn, p, by_split, "a.sav", {})["unchanged"]         # different grouping is processed


def test_balanced_intermediates_do_not_become_phantom_outputs():
    """A line chain whose intermediate is balanced to within clock rounding must not export 0.00/min outputs."""
    p = synthetic()
    # ingots 30/min per smelter; plates need 30 ingots/min each: make smelters 99.99 % so ingots are short by 0.003/min
    B = [machine(0, 0, 0, "Recipe_IngotIron_C", "Build_SmelterMk1_C"), machine(1, 5, 0)]
    lines, _ = im.machine_lines(B, [0, 1])
    outs, needs = im.net_rates(lines)
    assert "Desc_IronIngot_C" not in outs and "Desc_IronIngot_C" not in needs      # 30 made, 30 used
    B[0]["clock"] = 1.00004                                                         # 30.0012 made / 30 used
    lines, _ = im.machine_lines(B, [0, 1])
    outs, needs = im.net_rates(lines)
    assert "Desc_IronIngot_C" not in outs
    assert outs.get("Desc_IronPlate_C") == pytest.approx(20)                        # the real product stays
    B[0]["clock"] = 2.0                                                             # real surplus (30 ingots/min) stays
    outs, _ = im.net_rates(im.machine_lines(B, [0, 1])[0])
    assert outs["Desc_IronIngot_C"] == pytest.approx(30)


def test_inline_clock_form_does_not_revert_recipe_from_other_tab(server):
    fid = server.new_factory("two tabs")
    assert server.post(f"/factory/{fid}/output", {"item": "Reinforced Iron Plate", "rate": "5"})[0] == 303
    # tab A changes the recipe
    assert server.post(f"/factory/{fid}/override", {"item": "Desc_IronPlateReinforced_C",
                                                    "recipe": "Recipe_Alternate_ReinforcedIronPlate_1_C"})[0] == 303
    # tab B (opened earlier) applies a clock through the inline form, which no longer carries the recipe
    assert server.post(f"/factory/{fid}/override", {"item": "Desc_IronPlateReinforced_C", "keep_recipe": "1",
                                                    "clock_pct": "150", "sloops": ""})[0] == 303
    page = server.get(f"/factory/{fid}")[1]
    assert "Alternate: Bolted Iron Plate" in page


def test_built_vs_planned_is_clock_and_recipe_aware(conn):
    """QA-10: 2 constructors at 250 % making plates from an alternate ingot recipe in a foundry used to read
    'SHORT' (planner used default recipes and ignored clocks). The created factory now plans what was built."""
    from app import factory_service as fs
    from core import gamedata as gd
    alt = gd.recipe_by_name("Alternate: Iron Alloy Ingot")
    assert alt and alt["machine"] == "Build_FoundryMk1_C"
    alt_cls = next(k for k, v in gd.recipes().items() if v is alt)
    B = [machine(0, 0, 0, clock=2.5), machine(1, 10, 0, clock=2.5),
         machine(2, 20, 0, alt_cls, "Build_FoundryMk1_C", clock=1.0),
         machine(3, 30, 0, alt_cls, "Build_FoundryMk1_C", clock=1.0)]
    p = {"format": 1, "game": {"saveName": "q"}, "buildings": B, "links": [[0, 1, 5], [1, 2, 5], [2, 3, 5]]}
    gs, _ = specs(p)
    with conn:
        assert svc.save(conn, p, gs, "q.sav", {})["created"] == 1
    fid = conn.execute("select id from factory where origin='import'").fetchone()[0]
    _o, _c, _ov, sol = fs.solve_factory(conn, fid)
    rows = {r["recipe"]: r for r in fs.built_vs_planned(conn, fid, sol)}
    plates = rows["Iron Plate"]
    assert plates["built"] == 2 and plates["planned"] == 2 and plates["gap"] == 0
    assert plates["have"] == pytest.approx(5.0) and plates["need"] == pytest.approx(5.0)
    assert all(r["gap"] == 0 for r in rows.values()), rows
    # integer machine counts, not 2.0
    assert isinstance(plates["built"], int)


def test_built_vs_planned_reports_a_real_shortfall(conn):
    from app import factory_service as fs
    p = synthetic()
    gs, _ = specs(p)
    with conn:
        svc.save(conn, p, gs, "a.sav", {})
    fid = conn.execute("select factory_id from production_line where recipe='Recipe_IronPlate_C'").fetchone()[0]
    with conn:   # the user now wants 100 plates/min instead of the 60 that were built
        conn.execute("UPDATE factory_output SET rate_per_min=100 WHERE factory_id=? AND item='Desc_IronPlate_C'", (fid,))
    _o, _c, _ov, sol = fs.solve_factory(conn, fid)
    rows = {r["recipe"]: r for r in fs.built_vs_planned(conn, fid, sol)}
    assert rows["Iron Plate"]["gap"] == pytest.approx(-2.0)      # 3 built, 5 needed
