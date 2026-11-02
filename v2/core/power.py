"""Satisfactory 1.1 machine power / output maths. Pure functions.

P = P_base * (clock/100)^clock_exponent * (1 + sloops/slots)^sloop_exponent
output multiplier = 1 + sloops/slots
Constants come from the building record (generated from the Docs file).
"""


def sloop_multiplier(sloops: int, slots: int) -> float:
    if sloops <= 0 or slots <= 0:
        return 1.0
    if sloops > slots:
        raise ValueError(f"{sloops} sloops exceeds {slots} slots")
    return 1.0 + sloops / slots


def machine_power_mw(building: dict, clock_pct: float = 100.0, sloops: int = 0) -> float:
    """Power draw of one machine in MW."""
    boost = sloop_multiplier(sloops, building["sloop_slots"])
    return (building["power_mw"]
            * (clock_pct / 100.0) ** building["clock_exponent"]
            * boost ** building["sloop_power_exponent"])


def machine_output_multiplier(building: dict, clock_pct: float = 100.0, sloops: int = 0) -> float:
    """Items-per-minute multiplier vs one machine at 100%, no sloops."""
    return (clock_pct / 100.0) * sloop_multiplier(sloops, building["sloop_slots"])


def machines_power_mw(building: dict, count: float, clock_pct: float = 100.0, sloops: int = 0) -> float:
    return count * machine_power_mw(building, clock_pct, sloops)
