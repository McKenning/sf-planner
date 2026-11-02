import pytest

from core import gamedata as gd
from core.power import machine_output_multiplier, machine_power_mw


def b(name):
    return gd.building_by_name(name)


def test_golden_constructor_250():
    assert machine_power_mw(b("Constructor"), 250) == pytest.approx(13.43, abs=0.005)


def test_base_power():
    assert machine_power_mw(b("Constructor"), 100) == pytest.approx(4.0)
    assert machine_power_mw(b("Manufacturer"), 100) == pytest.approx(55.0)


def test_full_sloops_quadruple_power_double_output():
    c = b("Constructor")
    assert machine_power_mw(c, 100, 1) == pytest.approx(16.0)
    assert machine_output_multiplier(c, 100, 1) == pytest.approx(2.0)


def test_partial_sloops():
    m = b("Manufacturer")  # 4 slots
    assert machine_power_mw(m, 100, 2) == pytest.approx(55 * 1.5 ** 2)
    assert machine_output_multiplier(m, 100, 2) == pytest.approx(1.5)


def test_constants_from_docs():
    for bld in gd.buildings().values():
        assert bld["clock_exponent"] == pytest.approx(1.321929)
        assert bld["sloop_power_exponent"] == pytest.approx(2.0)


def test_slots():
    assert b("Constructor")["sloop_slots"] == 1
    assert b("Converter")["sloop_slots"] == 2
    assert b("Particle Accelerator")["sloop_slots"] == 4


def test_variable_power_is_mean():
    pa = b("Particle Accelerator")
    assert pa["power_mw"] == pytest.approx((pa["power_min_mw"] + pa["power_max_mw"]) / 2)
    assert pa["power_mw"] == pytest.approx(875.0)


def test_too_many_sloops():
    with pytest.raises(ValueError):
        machine_power_mw(b("Constructor"), 100, 2)
