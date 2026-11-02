"""Resource budget: how much of a raw resource the world's nodes can supply per minute. Pure."""
from core import gamedata as gd

PURITY = {"impure": 0.5, "normal": 1.0, "pure": 2.0}
UNLIMITED = float("inf")


def default_extractor(resource_item: str) -> str | None:
    """Extractor class used to budget a resource (Docs data decides what each can mine)."""
    it = gd.items().get(resource_item)
    if not it:
        return None
    ex = gd.load()["extractors"]
    if it["name"] == "Water":
        return "Build_WaterPump_C"
    if it["name"] == "Crude Oil":
        return "Build_OilPump_C"
    if it["form"] in ("RF_GAS", "RF_LIQUID"):
        return "Build_FrackingExtractor_C"
    return "Build_MinerMk3_C" if "Build_MinerMk3_C" in ex else None


def rate_per_node(extractor: str, purity: str, clock_pct: float) -> float:
    """Items (or m3) per minute from one node at the given purity and clock."""
    e = gd.load()["extractors"][extractor]
    amount = e["items_per_cycle"]
    if "RF_LIQUID" in e["forms"] or "RF_GAS" in e["forms"]:
        amount /= 1000.0  # Docs store fluids in mL
    base = amount * 60.0 / e["cycle_time_s"]
    return base * PURITY[purity] * clock_pct / 100.0


def available_per_min(resource_item: str, pure: int, normal: int, impure: int,
                      extractor: str | None = None, clock_pct: float = 250.0) -> float:
    """Total per-minute supply of a resource across all its nodes. Water is unlimited."""
    name = gd.items().get(resource_item, {}).get("name")
    if name == "Water":
        return UNLIMITED
    ex = extractor or default_extractor(resource_item)
    if not ex:
        return 0.0
    return (pure * rate_per_node(ex, "pure", clock_pct) + normal * rate_per_node(ex, "normal", clock_pct)
            + impure * rate_per_node(ex, "impure", clock_pct))
