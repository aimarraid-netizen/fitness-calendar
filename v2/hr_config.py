"""Trenn 2.0 — jagatud pulsikonfig + Karvoneni tsoonid.

RESTING_HR ja MAX_HR loetakse .env failist (vaikimisi 62/179).
Kasutavad parse_fit.py ja parse_gpx.py — üks tõeallikas tsooniloogikale.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

RESTING_HR = int(os.getenv("RESTING_HR", 62))
MAX_HR = int(os.getenv("MAX_HR", 179))

ZONE_NAMES = ("z1", "z2", "z3", "z4", "z5")


def hr_zones(resting: int | None = None, max_hr: int | None = None) -> dict[str, tuple[int, int]]:
    """Karvoneni valemiga tsoonipiirid: {z1: (lo, hi), ...}."""
    r = RESTING_HR if resting is None else resting
    m = MAX_HR if max_hr is None else max_hr
    hrr = m - r
    return {
        "z1": (r + int(hrr * 0.50), r + int(hrr * 0.60)),
        "z2": (r + int(hrr * 0.60), r + int(hrr * 0.70)),
        "z3": (r + int(hrr * 0.70), r + int(hrr * 0.80)),
        "z4": (r + int(hrr * 0.80), r + int(hrr * 0.90)),
        "z5": (r + int(hrr * 0.90), m),
    }


def zone_for(hr: int, zones: dict[str, tuple[int, int]] | None = None) -> str:
    """Mis tsooni pulss kuulub. Alla z1 -> z1, üle z5 -> z5."""
    if zones is None:
        zones = hr_zones()
    for name, (lo, hi) in zones.items():
        if lo <= hr <= hi:
            return name
    return "z1" if hr < zones["z1"][0] else "z5"


def zone_minutes(hr_samples: list[int], duration_sec: float | None) -> dict[str, float]:
    """Jaota treeningu kestus tsoonidesse HR-sämplite proportsioonis (minutites)."""
    zone_min = {z: 0.0 for z in ZONE_NAMES}
    if not hr_samples or not duration_sec:
        return zone_min
    zones = hr_zones()
    counts = {z: 0 for z in ZONE_NAMES}
    for hr in hr_samples:
        counts[zone_for(hr, zones)] += 1
    total = len(hr_samples)
    for z in counts:
        zone_min[z] = round((counts[z] / total) * (duration_sec / 60), 1)
    return zone_min
