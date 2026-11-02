"""Template helpers shared by every router's Jinja environment."""


def thousands(v, digits: int = 0) -> str:
    """12345.6 -> '12,346' (readable big power figures)."""
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return str(v)


def install(templates):
    templates.env.filters["n0"] = thousands
    templates.env.filters["n1"] = lambda v: thousands(v, 1)
    templates.env.filters["n2"] = lambda v: thousands(v, 2)
    return templates
