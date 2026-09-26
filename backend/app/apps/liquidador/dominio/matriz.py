"""Dynamic generation of the 12×8 shift hours matrix.

Instead of typing 96 cells by hand, a shift is defined by just:
  - ordinary_hours  (e.g. 8.8)
  - overtime_hours  (e.g. 2.4)
  - start_time      (e.g. 18:00)
  - night_start_hour (e.g. 19 — editable legal parameter)

The worked hours (ordinary first, then overtime) are placed continuously from
the start time (any rest/break falls at the end). Each slice is classified as
day [DAY_START_HOUR, night_start) or night [night_start, DAY_START_HOUR), on the
current or the next calendar day (when the shift crosses midnight). The 8 day
types already encode whether the current/next day is Sunday or a holiday, so
each slice maps to the right concept.

This reproduces the original hand-built D and N matrices cell-for-cell.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.apps.liquidador.dominio.tipos import DayType, empty_matrix

# Night ends at 06:00 → daytime window is [06:00, night_start).
# Derivable from the original D seed (a 06:00 day shift has zero night hours).
DAY_START_HOUR = 6

# Day categories that drive which surcharge concept a slice maps to.
_NORMAL = "normal"
_SUNDAY = "sunday"
_HOLIDAY = "holiday"

# (current_day_category, next_day_category) per DayType. The 8 day types encode
# exactly this: e.g. a Saturday's next day is always Sunday; a HOLIDAY_EVE's
# next day is a holiday; etc.
_CATEGORIES: dict[DayType, tuple[str, str]] = {
    DayType.WEEKDAY: (_NORMAL, _NORMAL),
    DayType.SATURDAY: (_NORMAL, _SUNDAY),
    DayType.SATURDAY_HOLIDAY: (_HOLIDAY, _SUNDAY),
    DayType.SUNDAY: (_SUNDAY, _NORMAL),
    DayType.SUNDAY_HOLIDAY_EVE: (_SUNDAY, _HOLIDAY),
    DayType.HOLIDAY: (_HOLIDAY, _NORMAL),
    DayType.HOLIDAY_EVE: (_NORMAL, _HOLIDAY),
    DayType.HOLIDAY_DOUBLE: (_HOLIDAY, _HOLIDAY),
}

# Surcharge concept for an ORDINARY slice given (category, is_night).
# Normal+day adds no surcharge (it's just the base count).
_ORDINARY_SURCHARGE: dict[tuple[str, bool], str | None] = {
    (_NORMAL, False): None,
    (_NORMAL, True): "ordinary_night",
    (_SUNDAY, False): "sunday_surcharge",
    (_SUNDAY, True): "sunday_night_surcharge",
    (_HOLIDAY, False): "holiday_day_surcharge",
    (_HOLIDAY, True): "holiday_night_surcharge",
}

# Concept for an OVERTIME slice given (category, is_night).
_OVERTIME: dict[tuple[str, bool], str] = {
    (_NORMAL, False): "overtime_day",
    (_NORMAL, True): "overtime_night",
    (_SUNDAY, False): "sunday_overtime_day",
    (_SUNDAY, True): "sunday_overtime_night",
    (_HOLIDAY, False): "holiday_overtime_day",
    (_HOLIDAY, True): "holiday_overtime_night",
}

_EPS = 1e-9


def _is_night(local_hour: float, night_start: int) -> bool:
    return local_hour >= night_start or local_hour < DAY_START_HOUR


def _split_segments(
    start_hour: float, worked: float, night_start: int
) -> list[tuple[float, bool, int]]:
    """Walk `worked` hours from `start_hour`, returning homogeneous slices.

    Each slice: (hours, is_night, day_index) where day_index 0 = current day,
    1 = next day, etc. Breakpoints are DAY_START_HOUR, night_start and midnight.
    """
    segments: list[tuple[float, bool, int]] = []
    t = start_hour
    end = start_hour + worked
    while t < end - _EPS:
        day_index = int(t // 24)
        local = t - day_index * 24
        is_night = _is_night(local, night_start)
        # Nearest boundary strictly after t, across this day and the next.
        candidates: list[float] = []
        for di in (day_index, day_index + 1):
            base = di * 24
            for b in (base + DAY_START_HOUR, base + night_start, base + 24):
                if b > t + _EPS:
                    candidates.append(b)
        seg_end = min(min(candidates), end)
        hours = seg_end - t
        if hours > _EPS:
            segments.append((hours, is_night, day_index))
        t = seg_end
    return segments


def build_shift_matrix(
    ordinary_hours: Decimal | float,
    overtime_hours: Decimal | float,
    start_time: dt.time,
    night_start_hour: int,
) -> dict[str, dict[str, float]]:
    """Build the 12×8 matrix from the shift's hours and start time.

    Shifts with no worked hours (Z paid-rest, L unpaid, AUS absence) return an
    all-zero matrix.
    """
    matrix = empty_matrix()
    ordinary = float(ordinary_hours or 0)
    overtime = float(overtime_hours or 0)
    worked = ordinary + overtime
    if worked <= 0:
        return matrix

    start_hour = start_time.hour + start_time.minute / 60.0
    segments = _split_segments(start_hour, worked, night_start_hour)

    # Allocate ordinary first, then overtime, across slices in order.
    # Same split for every day type — only the concept mapping differs.
    allocations: list[tuple[float, float, bool, int]] = []
    remaining_ord = ordinary
    for hours, is_night, day_index in segments:
        ord_part = min(remaining_ord, hours)
        remaining_ord -= ord_part
        ot_part = hours - ord_part
        allocations.append((ord_part, ot_part, is_night, day_index))

    for day_type in DayType:
        current_cat, next_cat = _CATEGORIES[day_type]
        col = day_type.value
        for ord_part, ot_part, is_night, day_index in allocations:
            cat = current_cat if day_index == 0 else next_cat
            if ord_part > _EPS:
                matrix["ordinary_day"][col] += ord_part
                surcharge = _ORDINARY_SURCHARGE[(cat, is_night)]
                if surcharge is not None:
                    matrix[surcharge][col] += ord_part
            if ot_part > _EPS:
                matrix[_OVERTIME[(cat, is_night)]][col] += ot_part

    # Round away float noise (matrix values are tenths of an hour).
    for row in matrix.values():
        for day in row:
            row[day] = round(row[day], 2)
    return matrix
