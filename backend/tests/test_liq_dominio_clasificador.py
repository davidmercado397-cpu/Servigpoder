"""Prueba copiada de la app original del liquidador (sin cambios de lógica)."""
import datetime as dt

import pytest

from app.apps.liquidador.dominio.clasificador import classify
from app.apps.liquidador.dominio.tipos import DayType


# Reference dates: 2026-05-04 is Monday, 05-09 is Saturday, 05-10 is Sunday.
MON = dt.date(2026, 5, 4)
TUE = dt.date(2026, 5, 5)
SAT = dt.date(2026, 5, 9)
SUN = dt.date(2026, 5, 10)


@pytest.mark.parametrize("date,h_today,h_tomorrow,expected", [
    # Plain weekday
    (MON, False, False, DayType.WEEKDAY),
    # Weekday before a holiday
    (TUE, False, True, DayType.HOLIDAY_EVE),
    # Plain Saturday
    (SAT, False, False, DayType.SATURDAY),
    # Saturday that is itself a holiday → SATURDAY_HOLIDAY
    (SAT, True, False, DayType.SATURDAY_HOLIDAY),
    # Plain Sunday
    (SUN, False, False, DayType.SUNDAY),
    # Sunday before a holiday Monday
    (SUN, False, True, DayType.SUNDAY_HOLIDAY_EVE),
    # Holiday Monday
    (MON, True, False, DayType.HOLIDAY),
    # Holiday Monday followed by a holiday Tuesday → HOLIDAY_DOUBLE
    (MON, True, True, DayType.HOLIDAY_DOUBLE),
])
def test_day_classification(date, h_today, h_tomorrow, expected):
    assert classify(date, holiday_today=h_today, holiday_tomorrow=h_tomorrow) is expected
