from __future__ import annotations

import datetime as dt

from app.apps.liquidador.dominio.tipos import DayType


def classify(
    date: dt.date,
    *,
    holiday_today: bool,
    holiday_tomorrow: bool,
) -> DayType:
    """Classify a date into one of the 8 DayType columns of the shift matrix.

    Pure function: the caller resolves holiday status (from python-holidays
    plus DB overrides) and hands it in as booleans. Keeps the classification
    logic deterministic and 100% testable.

    Mapping rules:
      - holiday today AND tomorrow → HOLIDAY_DOUBLE
      - holiday today, Saturday    → SATURDAY_HOLIDAY (Sábado festivo)
      - holiday today, otherwise   → HOLIDAY
      - Saturday, not a holiday    → SATURDAY
      - Sunday, holiday tomorrow   → SUNDAY_HOLIDAY_EVE
      - Sunday, otherwise          → SUNDAY
      - weekday, holiday tomorrow  → HOLIDAY_EVE
      - weekday, otherwise         → WEEKDAY
    """
    weekday = date.weekday()  # 0=Mon, 5=Sat, 6=Sun

    if holiday_today and holiday_tomorrow:
        return DayType.HOLIDAY_DOUBLE
    if holiday_today:
        return DayType.SATURDAY_HOLIDAY if weekday == 5 else DayType.HOLIDAY
    if weekday == 5:
        return DayType.SATURDAY
    if weekday == 6:
        return DayType.SUNDAY_HOLIDAY_EVE if holiday_tomorrow else DayType.SUNDAY
    # Monday–Friday
    return DayType.HOLIDAY_EVE if holiday_tomorrow else DayType.WEEKDAY
