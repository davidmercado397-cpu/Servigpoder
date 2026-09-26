"""Prueba copiada de la app original del liquidador (sin cambios de lógica)."""
"""The dynamic matrix builder must reproduce the original hand-built D and N
seed matrices (migration 0002) cell-for-cell — that's the correctness anchor.
"""
import datetime as dt

import pytest

from app.apps.liquidador.dominio.matriz import build_shift_matrix
from app.apps.liquidador.dominio.tipos import DayType, HourConcept


# ── Expected seed matrices (verbatim from alembic 0002) ──────────────────

def _empty() -> dict[str, dict[str, float]]:
    return {c.value: {d.value: 0.0 for d in DayType} for c in HourConcept}


def _seed_d() -> dict[str, dict[str, float]]:
    m = _empty()
    for day in ("weekday", "saturday", "saturday_holiday",
                "sunday", "sunday_holiday_eve", "holiday", "holiday_eve"):
        m["ordinary_day"][day] = 8.8
    for day in ("saturday_holiday", "holiday", "holiday_double"):
        m["holiday_day_surcharge"][day] = 8.8
    for day in ("sunday", "sunday_holiday_eve"):
        m["sunday_surcharge"][day] = 8.8
    for day in ("weekday", "saturday", "holiday_eve"):
        m["overtime_day"][day] = 2.4
    for day in ("saturday_holiday", "holiday", "holiday_double"):
        m["holiday_overtime_day"][day] = 2.4
    for day in ("sunday", "sunday_holiday_eve"):
        m["sunday_overtime_day"][day] = 2.4
    return m


def _seed_n() -> dict[str, dict[str, float]]:
    m = _empty()
    for day in [d.value for d in DayType]:
        m["ordinary_day"][day] = 8.8
    m["ordinary_night"]["weekday"] = 7.8
    m["ordinary_night"]["saturday"] = 5.0
    m["ordinary_night"]["sunday"] = 2.8
    m["ordinary_night"]["holiday"] = 2.8
    m["ordinary_night"]["holiday_eve"] = 5.0
    for day in ("saturday_holiday", "holiday", "holiday_double"):
        m["holiday_day_surcharge"][day] = 1.0
    m["holiday_night_surcharge"]["saturday_holiday"] = 5.0
    m["holiday_night_surcharge"]["sunday_holiday_eve"] = 2.8
    m["holiday_night_surcharge"]["holiday"] = 5.0
    m["holiday_night_surcharge"]["holiday_eve"] = 2.8
    m["holiday_night_surcharge"]["holiday_double"] = 7.8
    m["sunday_surcharge"]["sunday"] = 1.0
    m["sunday_surcharge"]["sunday_holiday_eve"] = 1.0
    m["sunday_night_surcharge"]["saturday"] = 2.8
    m["sunday_night_surcharge"]["saturday_holiday"] = 2.8
    m["sunday_night_surcharge"]["sunday"] = 5.0
    m["sunday_night_surcharge"]["sunday_holiday_eve"] = 5.0
    m["overtime_night"]["weekday"] = 2.4
    m["overtime_night"]["sunday"] = 2.4
    m["overtime_night"]["holiday"] = 2.4
    m["holiday_overtime_night"]["sunday_holiday_eve"] = 2.4
    m["holiday_overtime_night"]["holiday_eve"] = 2.4
    m["holiday_overtime_night"]["holiday_double"] = 2.4
    m["sunday_overtime_night"]["saturday"] = 2.4
    m["sunday_overtime_night"]["saturday_holiday"] = 2.4
    return m


# Cells where the generator intentionally differs from the seed (harmless: the
# seed omitted the base count here; ORDINARY_DAY is not paid separately).
_D_KNOWN_DIFF = {("ordinary_day", "holiday_double")}


def _assert_matrix_equal(got, expected, *, ignore=frozenset()):
    for concept in [c.value for c in HourConcept]:
        for day in [d.value for d in DayType]:
            if (concept, day) in ignore:
                continue
            assert got[concept][day] == pytest.approx(expected[concept][day], abs=1e-6), (
                f"cell ({concept}, {day}): got {got[concept][day]}, "
                f"expected {expected[concept][day]}"
            )


def test_day_shift_reproduces_seed():
    got = build_shift_matrix(8.8, 2.4, dt.time(6, 0), night_start_hour=19)
    _assert_matrix_equal(got, _seed_d(), ignore=_D_KNOWN_DIFF)
    # The one documented difference: generator fills the base count consistently.
    assert got["ordinary_day"]["holiday_double"] == pytest.approx(8.8)


def test_night_shift_reproduces_seed_exactly():
    got = build_shift_matrix(8.8, 2.4, dt.time(18, 0), night_start_hour=19)
    _assert_matrix_equal(got, _seed_n())


def test_zero_hours_returns_empty_matrix():
    got = build_shift_matrix(0, 0, dt.time(0, 0), night_start_hour=19)
    for concept in [c.value for c in HourConcept]:
        for day in [d.value for d in DayType]:
            assert got[concept][day] == 0.0


def test_night_threshold_changes_split():
    """Moving night start later (19 → 21) shifts hours out of the night bucket."""
    at19 = build_shift_matrix(8.8, 2.4, dt.time(18, 0), night_start_hour=19)
    at21 = build_shift_matrix(8.8, 2.4, dt.time(18, 0), night_start_hour=21)
    # Weekday ordinary_night: with night@19 the 18:00 shift has 7.8 night hours;
    # with night@21 the 19:00-21:00 portion becomes daytime, so night drops.
    assert at21["ordinary_night"]["weekday"] < at19["ordinary_night"]["weekday"]


def test_pure_day_shift_has_no_night_hours():
    """A 06:00 day shift working 11.2h ends at 17:12 — entirely daytime."""
    got = build_shift_matrix(8.8, 2.4, dt.time(6, 0), night_start_hour=19)
    for day in [d.value for d in DayType]:
        assert got["ordinary_night"][day] == 0.0
        assert got["overtime_night"][day] == 0.0
        assert got["holiday_night_surcharge"][day] == 0.0
        assert got["sunday_night_surcharge"][day] == 0.0
