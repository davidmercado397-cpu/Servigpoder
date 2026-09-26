from __future__ import annotations

from decimal import Decimal

from app.apps.liquidador.dominio.tipos import DayType, HourConcept


def expand_workday_to_concepts(
    matrix: dict, day_type: DayType
) -> dict[HourConcept, Decimal]:
    """Reads the `day_type` column of the shift matrix and returns
    {concept: hours} for that single day."""
    result: dict[HourConcept, Decimal] = {}
    for concept in HourConcept:
        row = matrix.get(concept.value, {})
        raw = row.get(day_type.value, 0) if isinstance(row, dict) else 0
        try:
            value = Decimal(str(raw))
        except (TypeError, ValueError):
            value = Decimal("0")
        if value > 0:
            result[concept] = value
    return result
