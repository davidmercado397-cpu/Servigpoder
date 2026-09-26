from __future__ import annotations

from enum import Enum


class HourConcept(str, Enum):
    """Rows of the shift hours matrix — one per type of hour worked."""

    ORDINARY_DAY = "ordinary_day"
    ORDINARY_NIGHT = "ordinary_night"
    HOLIDAY_DAY_SURCHARGE = "holiday_day_surcharge"
    HOLIDAY_NIGHT_SURCHARGE = "holiday_night_surcharge"
    SUNDAY_SURCHARGE = "sunday_surcharge"
    SUNDAY_NIGHT_SURCHARGE = "sunday_night_surcharge"
    OVERTIME_DAY = "overtime_day"
    OVERTIME_NIGHT = "overtime_night"
    HOLIDAY_OVERTIME_DAY = "holiday_overtime_day"
    HOLIDAY_OVERTIME_NIGHT = "holiday_overtime_night"
    SUNDAY_OVERTIME_DAY = "sunday_overtime_day"
    SUNDAY_OVERTIME_NIGHT = "sunday_overtime_night"


class DayType(str, Enum):
    """Columns of the shift hours matrix — one per type of day worked."""

    WEEKDAY = "weekday"
    SATURDAY = "saturday"
    SATURDAY_HOLIDAY = "saturday_holiday"
    SUNDAY = "sunday"
    SUNDAY_HOLIDAY_EVE = "sunday_holiday_eve"
    HOLIDAY = "holiday"
    HOLIDAY_EVE = "holiday_eve"
    HOLIDAY_DOUBLE = "holiday_double"


# Spanish labels for the UI. Ordered for display.
CONCEPT_LABELS: dict[HourConcept, str] = {
    HourConcept.ORDINARY_DAY: "Diurnas ordinarias",
    HourConcept.ORDINARY_NIGHT: "Nocturnas ordinarias",
    HourConcept.HOLIDAY_DAY_SURCHARGE: "Recargo festivo diurno",
    HourConcept.HOLIDAY_NIGHT_SURCHARGE: "Recargo nocturno festivo",
    HourConcept.SUNDAY_SURCHARGE: "Recargo dominical",
    HourConcept.SUNDAY_NIGHT_SURCHARGE: "Recargo nocturno dominical",
    HourConcept.OVERTIME_DAY: "Extras diurnas",
    HourConcept.OVERTIME_NIGHT: "Extras nocturnas",
    HourConcept.HOLIDAY_OVERTIME_DAY: "Extras diurnas festivas",
    HourConcept.HOLIDAY_OVERTIME_NIGHT: "Extras nocturnas festivas",
    HourConcept.SUNDAY_OVERTIME_DAY: "Extras diurnas dominicales",
    HourConcept.SUNDAY_OVERTIME_NIGHT: "Extras nocturnas dominicales",
}

DAY_LABELS: dict[DayType, str] = {
    DayType.WEEKDAY: "Ordinario",
    DayType.SATURDAY: "Sábado",
    DayType.SATURDAY_HOLIDAY: "Sáb. festivo",
    DayType.SUNDAY: "Domingo",
    DayType.SUNDAY_HOLIDAY_EVE: "Dom. ant. fest.",
    DayType.HOLIDAY: "Festivo",
    DayType.HOLIDAY_EVE: "Ant. festivo",
    DayType.HOLIDAY_DOUBLE: "Fest. ant. fest.",
}

DAY_SHORT_LABELS: dict[DayType, str] = {
    DayType.WEEKDAY: "ORDIN",
    DayType.SATURDAY: "SAB",
    DayType.SATURDAY_HOLIDAY: "SAB FEST",
    DayType.SUNDAY: "DOM",
    DayType.SUNDAY_HOLIDAY_EVE: "DOM ANT FEST",
    DayType.HOLIDAY: "FESTIVO",
    DayType.HOLIDAY_EVE: "ANT FEST",
    DayType.HOLIDAY_DOUBLE: "FEST ANT FEST",
}


def empty_matrix() -> dict[str, dict[str, float]]:
    """Builds a fresh 12x8 matrix initialized to zero."""
    return {
        concept.value: {day.value: 0.0 for day in DayType}
        for concept in HourConcept
    }


def validated_matrix(raw: dict) -> dict[str, dict[str, float]]:
    """Returns a clean matrix accepting only known concept/day slugs.

    Unknown keys are ignored. Missing keys default to 0. Non-numeric values
    are coerced to 0.
    """
    result = empty_matrix()
    if not isinstance(raw, dict):
        return result
    for concept_key, row in raw.items():
        if concept_key not in result or not isinstance(row, dict):
            continue
        for day_key, value in row.items():
            if day_key not in result[concept_key]:
                continue
            try:
                result[concept_key][day_key] = float(value or 0)
            except (TypeError, ValueError):
                result[concept_key][day_key] = 0.0
    return result
