"""Trenn 2.0 — sisendvalideerimine parseritele.

Piirid on hinnangulised mõistlikkuse kontrollid (mitte füüsika seadused) —
muuda konstante julgelt, kui treening neist üle kasvab.
"""
from datetime import datetime, timedelta

REPS_MIN, REPS_MAX = 1, 200
WEIGHT_MAX_KG = 400.0
DURATION_MAX_MIN = 1440
HR_MIN, HR_MAX = 25, 250
KCAL_MAX = 10000
DISTANCE_MAX_M = 500_000.0
DATE_MIN = datetime(2020, 1, 1)


class ValidationError(Exception):
    """Sisend on nii vigane, et tervet faili ei saa importida."""


def valid_reps(reps: int | None) -> bool:
    return reps is None or REPS_MIN <= reps <= REPS_MAX


def valid_weight(weight_kg: float | None) -> bool:
    return weight_kg is None or 0 < weight_kg <= WEIGHT_MAX_KG


def valid_duration_min(duration_min: int | None) -> bool:
    return duration_min is None or 0 < duration_min <= DURATION_MAX_MIN


def valid_hr(hr: int | None) -> bool:
    return hr is None or HR_MIN <= hr <= HR_MAX


def valid_kcal(kcal: int | None) -> bool:
    return kcal is None or 0 <= kcal <= KCAL_MAX


def valid_distance_m(distance_m: float | None) -> bool:
    return distance_m is None or 0 < distance_m <= DISTANCE_MAX_M


def valid_date(dt: datetime | None, now: datetime | None = None) -> bool:
    if dt is None:
        return False
    now = now or datetime.now()
    return DATE_MIN <= dt <= now + timedelta(days=2)
