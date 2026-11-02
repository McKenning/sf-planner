"""Loader for the generated game data (core/gamedata.json). Pure; no DB or web code."""
import json
from functools import lru_cache
from pathlib import Path

_PATH = Path(__file__).with_name("gamedata.json")


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict:
    return json.loads(Path(path or _PATH).read_text(encoding="utf-8"))


def items() -> dict:
    return load()["items"]


def recipes() -> dict:
    return load()["recipes"]


def buildings() -> dict:
    return load()["buildings"]


def item_by_name(name: str) -> dict | None:
    for it in items().values():
        if it["name"] == name:
            return it
    return None


def recipe_by_name(name: str) -> dict | None:
    for r in recipes().values():
        if r["name"] == name:
            return r
    return None


def building_by_name(name: str) -> dict | None:
    for b in buildings().values():
        if b["name"] == name:
            return b
    return None
