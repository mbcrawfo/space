"""Proleptic Gregorian calendar arithmetic via Julian Day Numbers.

`datetime` cannot represent years before 1 CE, and light from distant stars
left them long before that. Julian Day Numbers are plain integers counting
days, so they extend indefinitely in both directions.

Years are in astronomical numbering internally: year 0 exists and is 1 BCE,
year -1 is 2 BCE. Conversion to the historical numbering used by humans
happens only in `parse_date` and the formatting functions.
"""

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class DateError(ValueError):
    """Raised when a date cannot be parsed or does not exist."""


def gregorian_to_jdn(year: int, month: int, day: int) -> int:
    """Convert a proleptic Gregorian date to a Julian Day Number."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def jdn_to_gregorian(jdn: int) -> tuple[int, int, int]:
    """Convert a Julian Day Number to a proleptic Gregorian date."""
    a = jdn + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    day = e - (153 * m + 2) // 5 + 1
    month = m + 3 - 12 * (m // 10)
    year = 100 * b + d - 4800 + m // 10
    return year, month, day


def is_leap_year(year: int) -> bool:
    """Gregorian leap rule, in astronomical year numbering."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if is_leap_year(year) else 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def parse_date(text: str) -> int:
    """Parse `YYYY-MM-DD`, or `-YYYY-MM-DD` for a BCE year, into a JDN.

    The leading minus carries the BCE year as it is normally written, so
    `-0044-03-15` is the Ides of March, 44 BCE. There is no year zero, which
    mirrors how dates are printed back out.
    """
    text = text.strip()
    bce = text.startswith("-")
    body = text[1:] if bce else text

    parts = body.split("-")
    if len(parts) != 3 or not all(p.isdecimal() for p in parts):
        raise DateError(
            f"Could not read {text!r} as a date. Expected YYYY-MM-DD, "
            "with a leading minus for BCE years (for example -0044-03-15)."
        )

    year, month, day = (int(p) for p in parts)

    if year == 0:
        raise DateError("There is no year 0. The year before 1 CE is 1 BCE, written -0001.")

    if bce:
        year = 1 - year  # 44 BCE -> astronomical -43

    if not 1 <= month <= 12:
        raise DateError(f"{month} is not a month. Months run from 1 to 12.")
    if not 1 <= day <= days_in_month(year, month):
        raise DateError(f"{text} is not a real date — that month has no such day.")

    return gregorian_to_jdn(year, month, day)


def _era(year: int) -> tuple[int, str]:
    """Astronomical year -> (historical year number, era label)."""
    return (year, "CE") if year > 0 else (1 - year, "BCE")


def format_date(jdn: int) -> str:
    """Render a JDN as, for example, `6 April 1478 CE`."""
    year, month, day = jdn_to_gregorian(jdn)
    shown_year, era = _era(year)
    return f"{day} {MONTH_NAMES[month - 1]} {shown_year} {era}"


def format_year(jdn: int) -> str:
    """Render just the year of a JDN, for example `1478 CE`."""
    year, _, _ = jdn_to_gregorian(jdn)
    shown_year, era = _era(year)
    return f"{shown_year} {era}"


def today_jdn() -> int:
    """Today's date, in the local timezone, as a JDN."""
    from datetime import date

    now = date.today()
    return gregorian_to_jdn(now.year, now.month, now.day)
