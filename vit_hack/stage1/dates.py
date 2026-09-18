"""Robust date parser and date utility functions for Study Sentinel."""

from __future__ import annotations

import datetime
from typing import Any, Optional, Union

DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%Y%m%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def parse_date(val: Any) -> Optional[datetime.date]:
    """Parses a date string safely into a datetime.date object.
    
    Supports ISO formats, CDISC DD-MON-YYYY strings, slashed formats, etc.
    Returns None if missing, blank, or malformed without crashing.
    """
    if val is None:
        return None
    if isinstance(val, datetime.date):
        return val
    if isinstance(val, datetime.datetime):
        return val.date()

    val_str = str(val).strip()
    if not val_str:
        return None

    val_upper = val_str.upper()
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(val_upper, fmt).date()
        except ValueError:
            continue

    return None


def days_between(d1: Any, d2: Any) -> Optional[int]:
    """Returns absolute number of calendar days between two dates, or None if invalid."""
    date1 = parse_date(d1)
    date2 = parse_date(d2)
    if date1 is None or date2 is None:
        return None
    return abs((date1 - date2).days)


def within_window(target: Any, reference: Any, max_days: int) -> bool:
    """Checks whether target date is within max_days of reference date."""
    diff = days_between(target, reference)
    if diff is None:
        return False
    return diff <= max_days
