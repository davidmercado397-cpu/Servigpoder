"""Prueba copiada de la app original del liquidador (sin cambios de lógica)."""
"""Tests for the matrix expansion + aggregation pipeline.

Uses the seed values of the Night (N) shift to verify that a Saturday work-day
splits correctly into ordinary night surcharge + Sunday night surcharge.
"""
from decimal import Decimal

from app.apps.liquidador.dominio.expansor import expand_workday_to_concepts
from app.apps.liquidador.dominio.tipos import DayType, HourConcept


# Minimal Night-shift matrix containing only the cells we care about for these tests.
NIGHT_MATRIX = {
    HourConcept.ORDINARY_DAY.value: {DayType.SATURDAY.value: 8.8},
    HourConcept.ORDINARY_NIGHT.value: {DayType.SATURDAY.value: 5.0},
    HourConcept.SUNDAY_NIGHT_SURCHARGE.value: {DayType.SATURDAY.value: 2.8},
}


def test_saturday_night_shift_splits_concepts():
    concepts = expand_workday_to_concepts(NIGHT_MATRIX, DayType.SATURDAY)
    # Only the three populated rows show up
    assert set(concepts.keys()) == {
        HourConcept.ORDINARY_DAY,
        HourConcept.ORDINARY_NIGHT,
        HourConcept.SUNDAY_NIGHT_SURCHARGE,
    }
    assert concepts[HourConcept.ORDINARY_NIGHT] == Decimal("5.0")
    assert concepts[HourConcept.SUNDAY_NIGHT_SURCHARGE] == Decimal("2.8")


def test_empty_column_returns_no_concepts():
    empty = {c.value: {d.value: 0 for d in DayType} for c in HourConcept}
    assert expand_workday_to_concepts(empty, DayType.WEEKDAY) == {}
