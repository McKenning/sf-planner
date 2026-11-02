"""Shared form-input validation. Every rejection is a 400 with a readable message, never a 500."""
import math

from fastapi import HTTPException

MAX_RATE = 1_000_000.0   # items (or m3) per minute; far beyond any real factory
MIN_RATE = 0.0001        # matches the HTML min on rate inputs
MAX_MW = 10_000_000.0
MAX_COUNT = 100_000      # machines / generators / nodes of one kind


def rate(v: float, label: str = "Rate") -> float:
    if not math.isfinite(v) or v < MIN_RATE or v > MAX_RATE:
        raise HTTPException(400, f"{label} must be a number between {MIN_RATE:g} and {MAX_RATE:,.0f} per minute")
    return v


def megawatts(v: float) -> float:
    if not math.isfinite(v) or v <= 0 or v > MAX_MW:
        raise HTTPException(400, f"MW must be a number between 0 and {MAX_MW:,.0f}")
    return v


def clock(v: float) -> float:
    if not math.isfinite(v) or not (1 <= v <= 250):
        raise HTTPException(400, "Clock must be between 1 and 250 %")
    return v


def count(v: int, label: str = "Count", minimum: int = 0) -> int:
    if not (minimum <= v <= MAX_COUNT):
        raise HTTPException(400, f"{label} must be a whole number between {minimum} and {MAX_COUNT:,}")
    return v
