# Starlight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A stdlib-only Python CLI that takes a star name and an observation date and reports the date, in Earth's frame of reference, when the observed light left the star.

**Architecture:** Four small modules with one responsibility each. `caldate.py` does proleptic Gregorian ↔ Julian Day Number arithmetic so dates can run past `datetime`'s 1 CE floor. `lighttime.py` holds the physical model. `catalog.py` resolves names against a bundled JSON catalog with a SIMBAD network fallback. `starlight.py` is the CLI that wires them together and formats output.

**Tech Stack:** Python 3.10+, standard library only at runtime. pytest for tests.

**Spec:** `docs/superpowers/specs/2026-08-16-starlight-design.md`

## Global Constraints

- **Python 3.10 or newer.** `X | None` union syntax is used throughout.
- **No third-party runtime dependencies.** Standard library only. pytest is a development dependency.
- **Tests never touch the network.** The SIMBAD HTTP call is stubbed in every test.
- **All arithmetic on dates goes through Julian Day Numbers.** `datetime` is used only for "what is today", never for date arithmetic.
- **Astronomical year numbering internally** (year 0 exists and is 1 BCE); **historical numbering at the I/O boundary** (no year 0 is ever parsed or printed).
- **Distances are stored in parsecs.** Light-years are derived for display only.
- Errors go to stderr as plain sentences, never as tracebacks. Exit codes: 0 success, 1 unknown star, 2 malformed date, 3 network failure.

## Deviations from the spec

Two refinements, both deliberate:

1. The spec lists three modules but also says `starlight.py` "owns no astronomy". Those conflict, since the light-travel calculation has to live somewhere. This plan adds a fourth module, `lighttime.py`, holding the constants and the physical model. `starlight.py` stays free of astronomy as the spec intends.
2. The spec says "roughly 100 entries". This plan ships a concrete catalog of 50 entries, listed in full in Task 3. Fifty covers every naked-eye-famous star, the stellar neighbourhood, and enough distant objects to exercise BCE output. Entries are trivial to add later.

---

### Task 1: Calendar arithmetic (`caldate.py`)

The foundation. Everything else depends on these conversions being exactly right, so this task is heavy on known-value anchors.

**Files:**
- Create: `caldate.py`
- Test: `test_caldate.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `gregorian_to_jdn(year: int, month: int, day: int) -> int` — astronomical year numbering
  - `jdn_to_gregorian(jdn: int) -> tuple[int, int, int]` — returns `(year, month, day)`, astronomical year numbering
  - `parse_date(text: str) -> int` — returns a JDN; raises `DateError`
  - `format_date(jdn: int) -> str` — e.g. `"6 April 1478 CE"`
  - `format_year(jdn: int) -> str` — e.g. `"1478 CE"`
  - `today_jdn() -> int`
  - `class DateError(ValueError)`

- [ ] **Step 1: Write the failing test for JDN conversion anchors**

Create `test_caldate.py`:

```python
import pytest

from caldate import (
    DateError,
    format_date,
    format_year,
    gregorian_to_jdn,
    jdn_to_gregorian,
    parse_date,
    today_jdn,
)


# Anchors are proleptic Gregorian, astronomical year numbering (year 0 = 1 BCE).
@pytest.mark.parametrize(
    "year,month,day,jdn",
    [
        (2000, 1, 1, 2451545),  # J2000.0 epoch date
        (1, 1, 1, 1721426),  # first day of 1 CE
        (0, 12, 31, 1721425),  # last day of 1 BCE, the day before it
        (1970, 1, 1, 2440588),  # Unix epoch
        (2026, 8, 16, 2461269),
    ],
)
def test_gregorian_to_jdn_matches_known_anchors(year, month, day, jdn):
    assert gregorian_to_jdn(year, month, day) == jdn


@pytest.mark.parametrize(
    "year,month,day,jdn",
    [
        (2000, 1, 1, 2451545),
        (1, 1, 1, 1721426),
        (0, 12, 31, 1721425),
        (1970, 1, 1, 2440588),
        (2026, 8, 16, 2461269),
    ],
)
def test_jdn_to_gregorian_matches_known_anchors(year, month, day, jdn):
    assert jdn_to_gregorian(jdn) == (year, month, day)


def test_conversion_round_trips_across_the_era_boundary():
    # 400 years spanning 200 BCE through 200 CE, day by day.
    start = gregorian_to_jdn(-200, 1, 1)
    end = gregorian_to_jdn(200, 1, 1)
    for jdn in range(start, end):
        year, month, day = jdn_to_gregorian(jdn)
        assert gregorian_to_jdn(year, month, day) == jdn


def test_conversion_round_trips_at_negative_jdns():
    # Light from the most distant catalogued stars left them before JDN 0,
    # which the conversions must survive. Eta Carinae lands near here.
    start = gregorian_to_jdn(-5500, 1, 1)
    end = gregorian_to_jdn(-5450, 1, 1)
    assert start < 0
    for jdn in range(start, end):
        year, month, day = jdn_to_gregorian(jdn)
        assert gregorian_to_jdn(year, month, day) == jdn


def test_a_known_deep_past_date_converts_both_ways():
    assert gregorian_to_jdn(-5476, 11, 15) == -278689
    assert jdn_to_gregorian(-278689) == (-5476, 11, 15)


def test_leap_year_rules_hold_in_the_proleptic_past():
    # 2000 is a leap year, 1900 is not, and the same rules run backwards.
    assert gregorian_to_jdn(2000, 3, 1) - gregorian_to_jdn(2000, 2, 1) == 29
    assert gregorian_to_jdn(1900, 3, 1) - gregorian_to_jdn(1900, 2, 1) == 28
    assert gregorian_to_jdn(-400, 3, 1) - gregorian_to_jdn(-400, 2, 1) == 29
    assert gregorian_to_jdn(-300, 3, 1) - gregorian_to_jdn(-300, 2, 1) == 28
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest test_caldate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'caldate'`

- [ ] **Step 3: Implement the conversions**

Create `caldate.py`:

```python
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
```

Python's `//` floors toward negative infinity, which is exactly what these
algorithms need for negative years. Do not substitute truncating division.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest test_caldate.py -v`
Expected: PASS, all tests written so far

- [ ] **Step 5: Write the failing tests for parsing and formatting**

Append to `test_caldate.py`:

```python
def test_parse_reads_iso_dates():
    assert parse_date("2000-01-01") == 2451545
    assert parse_date("2026-08-16") == 2461269


def test_parse_reads_bce_dates_in_historical_numbering():
    # A leading minus means the BCE year as humans count it: -0044 is 44 BCE,
    # which is astronomical year -43.
    assert parse_date("-0044-03-15") == gregorian_to_jdn(-43, 3, 15)
    assert parse_date("-0001-01-01") == gregorian_to_jdn(0, 1, 1)


def test_parse_rejects_bad_input():
    for bad in [
        "",
        "not a date",
        "2026",
        "2026-13-01",
        "2026-02-30",
        "2026-00-10",
        "2026-01-00",
        "-0000-01-01",
        "2026/08/16",
    ]:
        with pytest.raises(DateError):
            parse_date(bad)


def test_format_date_uses_historical_era_labels():
    assert format_date(gregorian_to_jdn(1478, 4, 6)) == "6 April 1478 CE"
    assert format_date(gregorian_to_jdn(0, 3, 12)) == "12 March 1 BCE"
    assert format_date(gregorian_to_jdn(-5483, 3, 12)) == "12 March 5484 BCE"


def test_format_year_drops_the_day():
    assert format_year(gregorian_to_jdn(1478, 4, 6)) == "1478 CE"
    assert format_year(gregorian_to_jdn(-5483, 4, 6)) == "5484 BCE"


def test_parse_and_format_round_trip():
    for text in ["2026-08-16", "0001-01-01", "-0044-03-15", "-5484-03-12"]:
        assert format_date(parse_date(text)).endswith("BCE" if text.startswith("-") else "CE")


def test_today_is_a_plausible_jdn():
    # Sometime after 2020 and before 2200 — a sanity check, not an oracle.
    assert gregorian_to_jdn(2020, 1, 1) < today_jdn() < gregorian_to_jdn(2200, 1, 1)
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `pytest test_caldate.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_date'`

- [ ] **Step 7: Implement parsing and formatting**

Append to `caldate.py`:

```python
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
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise DateError(
            f"Could not read {text!r} as a date. Expected YYYY-MM-DD, "
            "with a leading minus for BCE years (for example -0044-03-15)."
        )

    year, month, day = (int(p) for p in parts)

    if bce:
        if year == 0:
            raise DateError("There is no year 0. The year before 1 CE is 1 BCE, written -0001.")
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
```

- [ ] **Step 8: Run the full test file**

Run: `pytest test_caldate.py -v`
Expected: PASS, all tests

- [ ] **Step 9: Commit**

```bash
git add caldate.py test_caldate.py
git commit -m "feat: add proleptic Gregorian date arithmetic via Julian Day Numbers"
```

---

### Task 2: The physical model (`lighttime.py`)

**Files:**
- Create: `lighttime.py`
- Test: `test_lighttime.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `LY_PER_PC: float` = 3.26156378
  - `DAYS_PER_JULIAN_YEAR: float` = 365.25
  - `to_light_years(distance_pc: float) -> float`
  - `travel_days(distance_pc: float) -> float`
  - `travel_years(distance_pc: float) -> float`
  - `emission_jdn(observation_jdn: int, distance_pc: float) -> int`

- [ ] **Step 1: Write the failing test**

Create `test_lighttime.py`:

```python
import pytest

from lighttime import (
    DAYS_PER_JULIAN_YEAR,
    LY_PER_PC,
    emission_jdn,
    to_light_years,
    travel_days,
    travel_years,
)


def test_parsec_converts_to_light_years():
    assert to_light_years(1.0) == pytest.approx(3.26156378)
    # Proxima Centauri, 1.301 pc, is famously about 4.24 light-years away.
    assert to_light_years(1.301) == pytest.approx(4.243, abs=0.001)


def test_travel_time_for_a_nearby_star():
    # 4.2433 ly x 365.25 days
    assert travel_days(1.301) == pytest.approx(1549.86, abs=0.05)
    assert travel_years(1.301) == pytest.approx(4.243, abs=0.001)


def test_travel_time_for_a_distant_star():
    # Eta Carinae, about 2300 pc.
    assert travel_days(2300.0) == pytest.approx(2739958, abs=2)
    assert travel_years(2300.0) == pytest.approx(7501.6, abs=0.1)


def test_emission_precedes_observation_by_the_travel_time():
    observation = 2461269  # 2026-08-16
    assert emission_jdn(observation, 1.301) == observation - 1550
    assert emission_jdn(observation, 0.0) == observation


def test_emission_of_a_distant_star_lands_before_the_common_era():
    observation = 2461269  # 2026-08-16
    # 1 CE begins at JDN 1721426; Eta Carinae's light left well before that.
    assert emission_jdn(observation, 2300.0) < 1721426


def test_constants_are_the_documented_ones():
    assert LY_PER_PC == 3.26156378
    assert DAYS_PER_JULIAN_YEAR == 365.25
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest test_lighttime.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lighttime'`

- [ ] **Step 3: Implement the model**

Create `lighttime.py`:

```python
"""Light travel time, in Earth's frame of reference.

The model is deliberately the naive one: the light we see today left the star
a distance/c ago, using the star's present catalogued distance. It ignores the
star's radial motion (which made its distance slightly different at emission),
its proper motion, and gravitational and cosmological effects. For every star
within our galaxy those corrections are far smaller than the uncertainty on
the published distance itself.
"""

LY_PER_PC = 3.26156378
DAYS_PER_JULIAN_YEAR = 365.25


def to_light_years(distance_pc: float) -> float:
    """Convert parsecs to light-years."""
    return distance_pc * LY_PER_PC


def travel_years(distance_pc: float) -> float:
    """Light travel time in Julian years — numerically the distance in ly."""
    return to_light_years(distance_pc)


def travel_days(distance_pc: float) -> float:
    """Light travel time in days."""
    return travel_years(distance_pc) * DAYS_PER_JULIAN_YEAR


def emission_jdn(observation_jdn: int, distance_pc: float) -> int:
    """The JDN on which light observed at `observation_jdn` left the star."""
    return observation_jdn - round(travel_days(distance_pc))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest test_lighttime.py -v`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add lighttime.py test_lighttime.py
git commit -m "feat: add light travel time model"
```

---

### Task 3: Bundled catalog and local name resolution (`stars.json`, `catalog.py`)

**Files:**
- Create: `stars.json`
- Create: `catalog.py`
- Test: `test_catalog.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class Star` — frozen dataclass with fields `name: str`, `designation: str | None`, `distance_pc: float`, `distance_pc_err: float | None`, `source: str`
  - `class StarNotFound(Exception)` — attributes `name: str`, `suggestions: list[str]`
  - `normalize(name: str) -> str`
  - `load_catalog(path: str | None = None) -> list[Star]`
  - `resolve(name: str, *, offline: bool = False) -> Star` — in this task the `offline` flag is accepted and the catalog is searched; Task 4 fills in the network branch.

- [ ] **Step 1: Write the catalog data file**

Create `stars.json`. These are the shipped entries — 50 stars and systems,
each with the survey its distance came from. Bright stars saturate Gaia's
detectors, so their distances come from the revised Hipparcos reduction;
Eta Carinae's comes from its expanding nebula. Values are the published
figures rounded to the precision shown.

```json
[
  {"name": "Proxima Centauri", "designation": "Alpha Centauri C", "aliases": ["proxima", "alpha cen c", "gj 551", "hip 70890"], "distance_pc": 1.301, "distance_pc_err": 0.0002, "source": "Gaia DR3"},
  {"name": "Alpha Centauri", "designation": "Rigil Kentaurus", "aliases": ["alpha cen", "rigil kent", "toliman", "hip 71683"], "distance_pc": 1.339, "distance_pc_err": 0.005, "source": "Hipparcos"},
  {"name": "Barnard's Star", "designation": "Gliese 699", "aliases": ["barnard", "gj 699", "hip 87937"], "distance_pc": 1.828, "distance_pc_err": 0.001, "source": "Gaia DR3"},
  {"name": "Wolf 359", "designation": "CN Leonis", "aliases": ["gj 406", "cn leo"], "distance_pc": 2.409, "distance_pc_err": 0.001, "source": "Gaia DR3"},
  {"name": "Lalande 21185", "designation": "Gliese 411", "aliases": ["gj 411", "hip 54035"], "distance_pc": 2.546, "distance_pc_err": 0.001, "source": "Gaia DR3"},
  {"name": "Sirius", "designation": "Alpha Canis Majoris", "aliases": ["alpha cma", "alpha canis majoris", "dog star", "hd 48915", "hip 32349"], "distance_pc": 2.637, "distance_pc_err": 0.011, "source": "Hipparcos"},
  {"name": "Luyten 726-8", "designation": "UV Ceti", "aliases": ["uv cet", "gj 65"], "distance_pc": 2.676, "distance_pc_err": 0.002, "source": "Gaia DR3"},
  {"name": "Ross 154", "designation": "V1216 Sagittarii", "aliases": ["gj 729", "v1216 sgr"], "distance_pc": 2.976, "distance_pc_err": 0.001, "source": "Gaia DR3"},
  {"name": "Epsilon Eridani", "designation": "Ran", "aliases": ["eps eri", "ran", "hd 22049", "hip 16537"], "distance_pc": 3.212, "distance_pc_err": 0.002, "source": "Gaia DR3"},
  {"name": "61 Cygni", "designation": "Bessel's Star", "aliases": ["61 cyg", "bessel star", "hip 104214"], "distance_pc": 3.497, "distance_pc_err": 0.003, "source": "Gaia DR3"},
  {"name": "Procyon", "designation": "Alpha Canis Minoris", "aliases": ["alpha cmi", "alpha canis minoris", "hd 61421", "hip 37279"], "distance_pc": 3.514, "distance_pc_err": 0.015, "source": "Hipparcos"},
  {"name": "Epsilon Indi", "designation": "Epsilon Indi A", "aliases": ["eps ind", "hd 209100", "hip 108870"], "distance_pc": 3.639, "distance_pc_err": 0.002, "source": "Gaia DR3"},
  {"name": "Tau Ceti", "designation": "Tau Ceti", "aliases": ["tau cet", "hd 10700", "hip 8102"], "distance_pc": 3.652, "distance_pc_err": 0.002, "source": "Gaia DR3"},
  {"name": "Van Maanen's Star", "designation": "Wolf 28", "aliases": ["van maanen", "wolf 28", "gj 35"], "distance_pc": 4.311, "distance_pc_err": 0.005, "source": "Gaia DR3"},
  {"name": "Altair", "designation": "Alpha Aquilae", "aliases": ["alpha aql", "alpha aquilae", "hd 187642", "hip 97649"], "distance_pc": 5.130, "distance_pc_err": 0.015, "source": "Hipparcos"},
  {"name": "Gliese 581", "designation": "Wolf 562", "aliases": ["gj 581", "hip 74995"], "distance_pc": 6.299, "distance_pc_err": 0.003, "source": "Gaia DR3"},
  {"name": "Vega", "designation": "Alpha Lyrae", "aliases": ["alpha lyr", "alpha lyrae", "hd 172167", "hip 91262"], "distance_pc": 7.680, "distance_pc_err": 0.031, "source": "Hipparcos"},
  {"name": "Fomalhaut", "designation": "Alpha Piscis Austrini", "aliases": ["alpha psa", "alpha piscis austrini", "hd 216956", "hip 113368"], "distance_pc": 7.704, "distance_pc_err": 0.028, "source": "Hipparcos"},
  {"name": "Pollux", "designation": "Beta Geminorum", "aliases": ["beta gem", "beta geminorum", "hd 62509", "hip 37826"], "distance_pc": 10.34, "distance_pc_err": 0.05, "source": "Hipparcos"},
  {"name": "Denebola", "designation": "Beta Leonis", "aliases": ["beta leo", "beta leonis", "hd 102647", "hip 57632"], "distance_pc": 11.00, "distance_pc_err": 0.06, "source": "Hipparcos"},
  {"name": "Arcturus", "designation": "Alpha Bootis", "aliases": ["alpha boo", "alpha bootis", "hd 124897", "hip 69673"], "distance_pc": 11.26, "distance_pc_err": 0.09, "source": "Hipparcos"},
  {"name": "TRAPPIST-1", "designation": "2MASS J23062928-0502285", "aliases": ["trappist 1", "trappist1"], "distance_pc": 12.47, "distance_pc_err": 0.01, "source": "Gaia DR3"},
  {"name": "Capella", "designation": "Alpha Aurigae", "aliases": ["alpha aur", "alpha aurigae", "hd 34029", "hip 24608"], "distance_pc": 13.12, "distance_pc_err": 0.10, "source": "Hipparcos"},
  {"name": "Rasalhague", "designation": "Alpha Ophiuchi", "aliases": ["alpha oph", "alpha ophiuchi", "hd 159561", "hip 86032"], "distance_pc": 14.9, "distance_pc_err": 0.1, "source": "Hipparcos"},
  {"name": "51 Pegasi", "designation": "Helvetios", "aliases": ["51 peg", "helvetios", "hd 217014", "hip 113357"], "distance_pc": 15.61, "distance_pc_err": 0.01, "source": "Gaia DR3"},
  {"name": "Castor", "designation": "Alpha Geminorum", "aliases": ["alpha gem", "alpha geminorum", "hd 60179", "hip 36850"], "distance_pc": 15.6, "distance_pc_err": 1.1, "source": "Hipparcos"},
  {"name": "Beta Pictoris", "designation": "Beta Pictoris", "aliases": ["beta pic", "hd 39060", "hip 27321"], "distance_pc": 19.44, "distance_pc_err": 0.05, "source": "Gaia DR3"},
  {"name": "Aldebaran", "designation": "Alpha Tauri", "aliases": ["alpha tau", "alpha tauri", "hd 29139", "hip 21421"], "distance_pc": 20.0, "distance_pc_err": 0.4, "source": "Hipparcos"},
  {"name": "Regulus", "designation": "Alpha Leonis", "aliases": ["alpha leo", "alpha leonis", "hd 87901", "hip 49669"], "distance_pc": 24.3, "distance_pc_err": 0.2, "source": "Hipparcos"},
  {"name": "Alcor", "designation": "80 Ursae Majoris", "aliases": ["80 uma", "hd 116842", "hip 65477"], "distance_pc": 25.1, "distance_pc_err": 0.4, "source": "Hipparcos"},
  {"name": "Mizar", "designation": "Zeta Ursae Majoris", "aliases": ["zeta uma", "zeta ursae majoris", "hd 116656", "hip 65378"], "distance_pc": 25.6, "distance_pc_err": 0.5, "source": "Hipparcos"},
  {"name": "Algol", "designation": "Beta Persei", "aliases": ["beta per", "beta persei", "demon star", "hd 19356", "hip 14576"], "distance_pc": 28.5, "distance_pc_err": 0.9, "source": "Hipparcos"},
  {"name": "Alkaid", "designation": "Eta Ursae Majoris", "aliases": ["eta uma", "eta ursae majoris", "benetnash", "hd 120315", "hip 67301"], "distance_pc": 31.9, "distance_pc_err": 0.5, "source": "Hipparcos"},
  {"name": "Dubhe", "designation": "Alpha Ursae Majoris", "aliases": ["alpha uma", "alpha ursae majoris", "hd 95689", "hip 54061"], "distance_pc": 37.7, "distance_pc_err": 1.0, "source": "Hipparcos"},
  {"name": "Achernar", "designation": "Alpha Eridani", "aliases": ["alpha eri", "alpha eridani", "hd 10144", "hip 7588"], "distance_pc": 42.8, "distance_pc_err": 1.0, "source": "Hipparcos"},
  {"name": "Bellatrix", "designation": "Gamma Orionis", "aliases": ["gamma ori", "gamma orionis", "hd 35468", "hip 25336"], "distance_pc": 76.7, "distance_pc_err": 3.0, "source": "Hipparcos"},
  {"name": "Spica", "designation": "Alpha Virginis", "aliases": ["alpha vir", "alpha virginis", "hd 116658", "hip 65474"], "distance_pc": 76.3, "distance_pc_err": 6.0, "source": "Hipparcos"},
  {"name": "Mira", "designation": "Omicron Ceti", "aliases": ["omicron cet", "omicron ceti", "hd 14386", "hip 10826"], "distance_pc": 92.0, "distance_pc_err": 10.0, "source": "Hipparcos"},
  {"name": "Canopus", "designation": "Alpha Carinae", "aliases": ["alpha car", "alpha carinae", "hd 45348", "hip 30438"], "distance_pc": 95.0, "distance_pc_err": 3.0, "source": "Hipparcos"},
  {"name": "Acrux", "designation": "Alpha Crucis", "aliases": ["alpha cru", "alpha crucis", "hd 108248", "hip 60718"], "distance_pc": 98.9, "distance_pc_err": 9.0, "source": "Hipparcos"},
  {"name": "Polaris", "designation": "Alpha Ursae Minoris", "aliases": ["alpha umi", "alpha ursae minoris", "north star", "pole star", "hd 8890", "hip 11767"], "distance_pc": 132.6, "distance_pc_err": 3.0, "source": "Hipparcos"},
  {"name": "Albireo", "designation": "Beta Cygni", "aliases": ["beta cyg", "beta cygni", "hd 183912", "hip 95947"], "distance_pc": 133.0, "distance_pc_err": 20.0, "source": "Hipparcos"},
  {"name": "Antares", "designation": "Alpha Scorpii", "aliases": ["alpha sco", "alpha scorpii", "hd 148478", "hip 80763"], "distance_pc": 168.0, "distance_pc_err": 27.0, "source": "Hipparcos"},
  {"name": "Betelgeuse", "designation": "Alpha Orionis", "aliases": ["alpha ori", "alpha orionis", "hd 39801", "hip 27989"], "distance_pc": 168.1, "distance_pc_err": 27.5, "source": "Hipparcos (revised)"},
  {"name": "Rigel", "designation": "Beta Orionis", "aliases": ["beta ori", "beta orionis", "hd 34085", "hip 24436"], "distance_pc": 264.6, "distance_pc_err": 24.0, "source": "Hipparcos"},
  {"name": "Mintaka", "designation": "Delta Orionis", "aliases": ["delta ori", "delta orionis", "hd 36486", "hip 25930"], "distance_pc": 380.0, "distance_pc_err": 40.0, "source": "Hipparcos"},
  {"name": "Alnitak", "designation": "Zeta Orionis", "aliases": ["zeta ori", "zeta orionis", "hd 37742", "hip 26727"], "distance_pc": 387.0, "distance_pc_err": 54.0, "source": "Hipparcos"},
  {"name": "Alnilam", "designation": "Epsilon Orionis", "aliases": ["eps ori", "epsilon orionis", "hd 37128", "hip 26311"], "distance_pc": 606.0, "distance_pc_err": 130.0, "source": "Hipparcos"},
  {"name": "Deneb", "designation": "Alpha Cygni", "aliases": ["alpha cyg", "alpha cygni", "hd 197345", "hip 102098"], "distance_pc": 802.0, "distance_pc_err": 130.0, "source": "Hipparcos"},
  {"name": "Eta Carinae", "designation": "Eta Carinae", "aliases": ["eta car", "hd 93308"], "distance_pc": 2300.0, "distance_pc_err": 100.0, "source": "Homunculus nebula expansion"}
]
```

- [ ] **Step 2: Write the failing test for normalization and lookup**

Create `test_catalog.py`:

```python
import pytest

from catalog import Star, StarNotFound, load_catalog, normalize, resolve


def test_normalize_collapses_case_spacing_and_punctuation():
    assert normalize("Barnard's Star") == "barnardsstar"
    assert normalize("  SIRIUS  ") == "sirius"
    assert normalize("61 Cygni") == "61cygni"
    assert normalize("HD 48915") == "hd48915"


def test_normalize_expands_greek_letters():
    assert normalize("α Orionis") == normalize("Alpha Orionis")
    assert normalize("β Cyg") == "betacyg"
    assert normalize("η Carinae") == "etacarinae"


def test_catalog_loads_and_every_entry_is_well_formed():
    stars = load_catalog()
    assert len(stars) >= 50
    for star in stars:
        assert star.name
        assert star.distance_pc > 0
        assert star.source
        if star.distance_pc_err is not None:
            assert star.distance_pc_err >= 0


def test_resolve_finds_a_star_by_its_common_name():
    star = resolve("Betelgeuse", offline=True)
    assert star.name == "Betelgeuse"
    assert star.distance_pc == pytest.approx(168.1)
    assert star.source == "Hipparcos (revised)"


def test_resolve_ignores_case_spacing_and_punctuation():
    for query in ["betelgeuse", "BETELGEUSE", "  Betelgeuse  "]:
        assert resolve(query, offline=True).name == "Betelgeuse"


def test_resolve_finds_a_star_by_designation_alias_or_catalogue_number():
    assert resolve("Alpha Orionis", offline=True).name == "Betelgeuse"
    assert resolve("α Ori", offline=True).name == "Betelgeuse"
    assert resolve("HD 39801", offline=True).name == "Betelgeuse"
    assert resolve("north star", offline=True).name == "Polaris"


def test_resolve_raises_with_suggestions_for_a_near_miss():
    with pytest.raises(StarNotFound) as excinfo:
        resolve("Betelgeus", offline=True)
    assert "Betelgeuse" in excinfo.value.suggestions


def test_resolve_raises_without_suggestions_for_nonsense():
    with pytest.raises(StarNotFound) as excinfo:
        resolve("zzzzzzzz", offline=True)
    assert excinfo.value.suggestions == []
    assert excinfo.value.name == "zzzzzzzz"
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pytest test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'catalog'`

- [ ] **Step 4: Implement the catalog module**

Create `catalog.py`:

```python
"""Star name resolution against the bundled catalog.

Names arrive from humans in every possible spelling: `Betelgeuse`, `alpha ori`,
`α Orionis`, `HD 39801`. Everything is compared in a normalized form —
casefolded, Greek letters spelled out, punctuation and spacing dropped.
"""

import difflib
import json
import os
from dataclasses import dataclass

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stars.json")

GREEK_LETTERS = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "ο": "omicron",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "ς": "sigma",
    "τ": "tau",
    "υ": "upsilon",
    "φ": "phi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
}


@dataclass(frozen=True)
class Star:
    name: str
    designation: str | None
    distance_pc: float
    distance_pc_err: float | None
    source: str


class StarNotFound(Exception):
    """Raised when a name matches nothing, with near misses if there are any."""

    def __init__(self, name: str, suggestions: list[str]):
        self.name = name
        self.suggestions = suggestions
        super().__init__(f"No star named {name!r} was found.")


def normalize(name: str) -> str:
    """Reduce a name to its comparison form."""
    expanded = "".join(GREEK_LETTERS.get(ch, ch) for ch in name.strip())
    return "".join(ch for ch in expanded.casefold() if ch.isalnum())


_catalog_cache: list[Star] | None = None


def load_catalog(path: str | None = None) -> list[Star]:
    """Load the bundled catalog. Cached, since it never changes at runtime."""
    global _catalog_cache
    if path is None and _catalog_cache is not None:
        return _catalog_cache

    with open(path or CATALOG_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)

    stars = [
        Star(
            name=entry["name"],
            designation=entry.get("designation"),
            distance_pc=float(entry["distance_pc"]),
            distance_pc_err=(float(entry["distance_pc_err"]) if entry.get("distance_pc_err") is not None else None),
            source=entry["source"],
        )
        for entry in raw
    ]
    if path is None:
        _catalog_cache = stars
    return stars


def _index(stars: list[Star], raw_entries: list[dict]) -> dict[str, Star]:
    index: dict[str, Star] = {}
    for star, entry in zip(stars, raw_entries):
        keys = [star.name, star.designation or "", *entry.get("aliases", [])]
        for key in keys:
            if key:
                index.setdefault(normalize(key), star)
    return index


def _load_index() -> dict[str, Star]:
    with open(CATALOG_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)
    return _index(load_catalog(), raw)


def _suggestions(name: str, stars: list[Star]) -> list[str]:
    names = [star.name for star in stars]
    by_normalized = {normalize(n): n for n in names}
    close = difflib.get_close_matches(normalize(name), list(by_normalized), n=3, cutoff=0.75)
    return [by_normalized[key] for key in close]


def resolve(name: str, *, offline: bool = False) -> Star:
    """Resolve a star name to a `Star`, consulting SIMBAD if the catalog misses."""
    index = _load_index()
    star = index.get(normalize(name))
    if star is not None:
        return star

    raise StarNotFound(name, _suggestions(name, load_catalog()))
```

Note the `resolve` docstring already mentions SIMBAD; the network branch
arrives in Task 4 and slots in immediately before the `raise`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest test_catalog.py -v`
Expected: PASS, 8 tests

- [ ] **Step 6: Commit**

```bash
git add stars.json catalog.py test_catalog.py
git commit -m "feat: add bundled star catalog and name resolution"
```

---

### Task 4: SIMBAD fallback (`catalog.py`)

**Files:**
- Modify: `catalog.py`
- Test: `test_simbad.py`

**Interfaces:**
- Consumes: `Star`, `StarNotFound`, `resolve` from Task 3.
- Produces:
  - `class SimbadError(Exception)`
  - `simbad_lookup(name: str, *, timeout: float = 10.0) -> Star` — raises `SimbadError` on network trouble, `StarNotFound` when SIMBAD has no such object or no usable parallax
  - `resolve(name, *, offline=False)` now calls `simbad_lookup` when the catalog misses and `offline` is false

- [ ] **Step 1: Write the failing test**

Create `test_simbad.py`. Every test stubs the HTTP layer — nothing here
touches the network.

```python
import json
import urllib.error

import pytest

import catalog
from catalog import SimbadError, StarNotFound, simbad_lookup


# A real SIMBAD TAP response, trimmed to the columns we ask for.
BETELGEUSE_RESPONSE = json.dumps(
    {
        "metadata": [
            {"name": "main_id"},
            {"name": "plx_value"},
            {"name": "plx_err"},
        ],
        "data": [["* alf Ori", 5.95, 0.58]],
    }
)

EMPTY_RESPONSE = json.dumps({"metadata": [], "data": []})

NULL_PARALLAX_RESPONSE = json.dumps(
    {
        "metadata": [
            {"name": "main_id"},
            {"name": "plx_value"},
            {"name": "plx_err"},
        ],
        "data": [["* alf Ori", None, None]],
    }
)


def stub_fetch(monkeypatch, response=None, error=None):
    def fake(url, data, timeout):
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(catalog, "_http_post", fake)


def test_lookup_converts_parallax_to_distance(monkeypatch):
    stub_fetch(monkeypatch, response=BETELGEUSE_RESPONSE)
    star = simbad_lookup("Betelgeuse")
    assert star.name == "* alf Ori"
    assert star.distance_pc == pytest.approx(1000 / 5.95)  # 168.07 pc
    assert star.distance_pc_err == pytest.approx(1000 * 0.58 / 5.95**2, rel=1e-6)
    assert star.source == "SIMBAD"


def test_lookup_of_an_unknown_object_is_a_miss(monkeypatch):
    stub_fetch(monkeypatch, response=EMPTY_RESPONSE)
    with pytest.raises(StarNotFound):
        simbad_lookup("zzzzzzzz")


def test_lookup_without_a_usable_parallax_is_a_miss(monkeypatch):
    stub_fetch(monkeypatch, response=NULL_PARALLAX_RESPONSE)
    with pytest.raises(StarNotFound):
        simbad_lookup("Betelgeuse")


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("no route to host"),
        urllib.error.HTTPError("url", 500, "Server Error", {}, None),
        TimeoutError("timed out"),
    ],
)
def test_network_trouble_becomes_a_simbad_error(monkeypatch, error):
    stub_fetch(monkeypatch, error=error)
    with pytest.raises(SimbadError):
        simbad_lookup("Betelgeuse")


def test_malformed_response_becomes_a_simbad_error(monkeypatch):
    stub_fetch(monkeypatch, response="<html>not json</html>")
    with pytest.raises(SimbadError):
        simbad_lookup("Betelgeuse")


def test_resolve_falls_back_to_simbad_when_the_catalog_misses(monkeypatch):
    stub_fetch(monkeypatch, response=BETELGEUSE_RESPONSE)
    star = catalog.resolve("some obscure star")
    assert star.source == "SIMBAD"


def test_offline_never_calls_the_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("the network must not be touched in offline mode")

    monkeypatch.setattr(catalog, "_http_post", explode)
    with pytest.raises(StarNotFound):
        catalog.resolve("some obscure star", offline=True)


def test_catalog_hits_never_call_the_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("a catalog hit must not touch the network")

    monkeypatch.setattr(catalog, "_http_post", explode)
    assert catalog.resolve("Betelgeuse").name == "Betelgeuse"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest test_simbad.py -v`
Expected: FAIL — `ImportError: cannot import name 'SimbadError' from 'catalog'`

- [ ] **Step 3: Implement the SIMBAD lookup**

Move the three `urllib` imports up into the import block at the top of
`catalog.py` alongside `difflib`, `json`, and `os`, then append the rest:

```python
import urllib.error
import urllib.parse
import urllib.request

SIMBAD_TAP_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
SIMBAD_TIMEOUT = 10.0


class SimbadError(Exception):
    """Raised when SIMBAD cannot be reached or answers with nonsense."""


def _http_post(url: str, data: bytes, timeout: float) -> str:
    """POST and return the body as text. Seam for tests to stub."""
    request = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def simbad_lookup(name: str, *, timeout: float = SIMBAD_TIMEOUT) -> Star:
    """Look a name up in SIMBAD and derive its distance from parallax.

    Sends only the name the user typed. Results are used for this run alone —
    nothing is cached and `stars.json` is never written to.
    """
    escaped = name.replace("'", "''")
    query = (
        "SELECT b.main_id, b.plx_value, b.plx_err "
        "FROM basic AS b JOIN ident AS i ON b.oid = i.oidref "
        f"WHERE LOWER(i.id) = LOWER('{escaped}')"
    )
    payload = urllib.parse.urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "json",
            "QUERY": query,
        }
    ).encode("utf-8")

    try:
        body = _http_post(SIMBAD_TAP_URL, payload, timeout)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SimbadError(f"Could not reach SIMBAD: {exc}") from exc

    try:
        rows = json.loads(body)["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SimbadError("SIMBAD returned a response that could not be read.") from exc

    if not rows:
        raise StarNotFound(name, [])

    main_id, plx_value, plx_err = rows[0][0], rows[0][1], rows[0][2]
    if not plx_value or plx_value <= 0:
        raise StarNotFound(name, [])

    distance_pc = 1000.0 / plx_value
    distance_err = (1000.0 * plx_err / plx_value**2) if plx_err else None

    return Star(
        name=main_id,
        designation=None,
        distance_pc=distance_pc,
        distance_pc_err=distance_err,
        source="SIMBAD",
    )
```

`urllib.error.HTTPError` is a subclass of `URLError`, so it is already caught.

- [ ] **Step 4: Wire the fallback into `resolve`**

In `catalog.py`, replace the body of `resolve` after the catalog hit with:

```python
def resolve(name: str, *, offline: bool = False) -> Star:
    """Resolve a star name to a `Star`, consulting SIMBAD if the catalog misses."""
    index = _load_index()
    star = index.get(normalize(name))
    if star is not None:
        return star

    if not offline:
        return simbad_lookup(name)

    raise StarNotFound(name, _suggestions(name, load_catalog()))
```

`simbad_lookup` raises `StarNotFound` itself on a miss, but with no
suggestions — so offline misses get the near-match hints and online misses
report the authoritative answer. Fill in suggestions on the online miss too:

```python
    if not offline:
        try:
            return simbad_lookup(name)
        except StarNotFound:
            raise StarNotFound(name, _suggestions(name, load_catalog())) from None

    raise StarNotFound(name, _suggestions(name, load_catalog()))
```

Use this second version.

- [ ] **Step 5: Run all tests**

Run: `pytest -v`
Expected: PASS, all tests across all four files

- [ ] **Step 6: Commit**

```bash
git add catalog.py test_simbad.py
git commit -m "feat: fall back to SIMBAD when the bundled catalog misses"
```

---

### Task 5: The CLI (`starlight.py`)

**Files:**
- Create: `starlight.py`
- Test: `test_starlight.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `main(argv: list[str] | None = None) -> int` — returns the exit code
  - `build_result(star, observation_jdn) -> dict` — the data behind both output formats

- [ ] **Step 1: Write the failing test**

Create `test_starlight.py`:

```python
import json

import pytest

import catalog
import starlight


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("CLI tests must not touch the network")

    monkeypatch.setattr(catalog, "_http_post", explode)


def run(capsys, *args):
    code = starlight.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_reports_the_emission_date_for_a_known_star(capsys):
    code, out, err = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline")
    assert code == 0
    assert "Betelgeuse" in out
    assert "Alpha Orionis" in out
    assert "16 August 2026 CE" in out
    assert "548.3 ly" in out
    # 168.1 pc -> 548.268871418 ly -> 200255 days before JDN 2461269
    assert "6 May 1478 CE" in out
    assert err == ""


def test_distant_stars_report_a_bce_emission_date(capsys):
    code, out, _ = run(capsys, "Eta Carinae", "--on", "2026-08-16", "--offline")
    assert code == 0
    assert "15 November 5477 BCE" in out  # 2026 minus about 7502 years


def test_nearby_star_light_left_within_living_memory(capsys):
    code, out, _ = run(capsys, "Proxima Centauri", "--on", "2026-08-16", "--offline")
    assert code == 0
    assert "2022 CE" in out  # 4.24 years earlier


def test_uncertainty_flag_adds_a_range(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--uncertainty")
    assert code == 0
    assert "between" in out
    assert "1388 CE" in out and "1568 CE" in out  # +/- 27.5 pc is about 90 years


def test_verbose_flag_shows_source_and_caveat(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--verbose")
    assert code == 0
    assert "Hipparcos (revised)" in out
    assert "radial" in out.lower()


def test_json_flag_emits_machine_readable_output(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--json")
    assert code == 0
    result = json.loads(out)
    assert result["name"] == "Betelgeuse"
    assert result["distance_pc"] == pytest.approx(168.1)
    assert result["distance_ly"] == pytest.approx(548.2, abs=0.5)
    assert result["observation_date"] == "16 August 2026 CE"
    assert result["observation_jdn"] == 2461269
    assert result["emission_date"].endswith("1478 CE")
    assert result["travel_years"] == pytest.approx(548.2, abs=0.5)
    assert result["source"] == "Hipparcos (revised)"
    assert "uncertainty" not in result


def test_json_with_uncertainty_includes_the_range(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--uncertainty", "--json")
    assert code == 0
    result = json.loads(out)
    assert result["uncertainty"]["earliest_year"].endswith("BCE") is False
    assert "1388 CE" in result["uncertainty"]["earliest_year"]
    assert "1568 CE" in result["uncertainty"]["latest_year"]


def test_observation_date_defaults_to_today(capsys):
    code, out, _ = run(capsys, "Sirius", "--offline")
    assert code == 0
    assert "Sirius" in out


def test_unknown_star_exits_1_with_suggestions(capsys):
    code, out, err = run(capsys, "Betelgeus", "--offline")
    assert code == 1
    assert out == ""
    assert "Betelgeuse" in err


def test_malformed_date_exits_2(capsys):
    code, out, err = run(capsys, "Sirius", "--on", "not-a-date", "--offline")
    assert code == 2
    assert out == ""
    assert "YYYY-MM-DD" in err


def test_network_failure_exits_3(capsys, monkeypatch):
    def fail(*args, **kwargs):
        raise catalog.SimbadError("Could not reach SIMBAD: no route to host")

    monkeypatch.setattr(catalog, "simbad_lookup", fail)
    code, out, err = run(capsys, "some obscure star")
    assert code == 3
    assert "--offline" in err


def test_bce_observation_dates_are_accepted(capsys):
    code, out, _ = run(capsys, "Sirius", "--on", "-0044-03-15", "--offline")
    assert code == 0
    assert "15 March 44 BCE" in out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest test_starlight.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'starlight'`

- [ ] **Step 3: Implement the CLI**

Create `starlight.py`:

```python
#!/usr/bin/env python3
"""When we look at a star, we see light that left it years ago.

Given a star and a date of observation, report the date — in Earth's frame of
reference — when that light began its journey.
"""

import argparse
import json
import sys

import caldate
import catalog
import lighttime

CAVEAT = (
    "Light travel time uses the star's present catalogued distance. It ignores "
    "the star's radial motion, which made that distance slightly different when "
    "the light left — an effect far smaller than the distance uncertainty itself."
)


def build_result(star: catalog.Star, observation_jdn: int) -> dict:
    """Everything both output formats are built from."""
    emission = lighttime.emission_jdn(observation_jdn, star.distance_pc)
    result = {
        "name": star.name,
        "designation": star.designation,
        "distance_pc": star.distance_pc,
        "distance_ly": lighttime.to_light_years(star.distance_pc),
        "source": star.source,
        "observation_jdn": observation_jdn,
        "observation_date": caldate.format_date(observation_jdn),
        "emission_jdn": emission,
        "emission_date": caldate.format_date(emission),
        "travel_days": lighttime.travel_days(star.distance_pc),
        "travel_years": lighttime.travel_years(star.distance_pc),
    }

    if star.distance_pc_err:
        nearest = max(star.distance_pc - star.distance_pc_err, 0.0)
        farthest = star.distance_pc + star.distance_pc_err
        result["uncertainty"] = {
            "distance_pc_err": star.distance_pc_err,
            # A nearer star means the light left more recently.
            "latest_year": caldate.format_year(lighttime.emission_jdn(observation_jdn, nearest)),
            "earliest_year": caldate.format_year(lighttime.emission_jdn(observation_jdn, farthest)),
        }

    return result


def render(result: dict, *, uncertainty: bool, verbose: bool) -> str:
    heading = result["name"]
    if result["designation"] and result["designation"] != result["name"]:
        heading += f" ({result['designation']})"

    distance = f"{result['distance_ly']:,.1f} ly  ({result['distance_pc']:,.4g} pc, {result['source']})"

    left = result["emission_date"]
    if uncertainty and "uncertainty" in result:
        span = result["uncertainty"]
        left += f"  (between {span['earliest_year']} and {span['latest_year']})"

    lines = [
        heading,
        f"  Distance     {distance}",
        f"  Observed     {result['observation_date']}",
        f"  Light left   {left}",
    ]

    if verbose:
        lines.append(f"  Travel time  {result['travel_years']:,.1f} years ({result['travel_days']:,.0f} days)")
        lines.append("")
        lines.append(f"  {CAVEAT}")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="starlight.py",
        description="Find out when the light you see tonight left its star.",
    )
    parser.add_argument("name", help="star or system name, designation, or catalogue number")
    parser.add_argument(
        "--on",
        dest="date",
        metavar="DATE",
        help="date of observation, YYYY-MM-DD (leading minus for BCE). Defaults to today.",
    )
    parser.add_argument(
        "--uncertainty",
        action="store_true",
        help="show the range implied by the distance error bars",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit machine-readable JSON")
    parser.add_argument("--verbose", action="store_true", help="show travel time, source, and modelling caveats")
    parser.add_argument("--offline", action="store_true", help="never query SIMBAD; use the bundled catalog only")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        observation_jdn = caldate.parse_date(args.date) if args.date else caldate.today_jdn()
    except caldate.DateError as exc:
        print(exc, file=sys.stderr)
        return 2

    try:
        star = catalog.resolve(args.name, offline=args.offline)
    except catalog.StarNotFound as exc:
        print(f"No star named {exc.name!r} was found.", file=sys.stderr)
        if exc.suggestions:
            print(f"Did you mean: {', '.join(exc.suggestions)}?", file=sys.stderr)
        return 1
    except catalog.SimbadError as exc:
        print(exc, file=sys.stderr)
        print("Use --offline to search only the bundled catalog.", file=sys.stderr)
        return 3

    result = build_result(star, observation_jdn)

    if args.as_json:
        if not args.uncertainty:
            result.pop("uncertainty", None)
        print(json.dumps(result, indent=2))
    else:
        print(render(result, uncertainty=args.uncertainty, verbose=args.verbose))

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest test_starlight.py -v`
Expected: PASS, 12 tests

The expected dates in these tests were computed from the catalog distances and
verified against the JDN algorithm at full decimal precision: Betelgeuse at
168.1 pc is 548.268871418 ly, so 200,255 days before JDN 2461269 is JDN
2261014, which is 6 May 1478 CE. Eta Carinae at 2300 pc is 2,739,958 days,
landing on JDN -278689, which is 15 November 5477 BCE.

**Do not round the light-year figure before multiplying by 365.25.** Rounding
548.268871418 to 548.27 first yields 200,256 days and shifts the answer a full
day, to 5 May. An earlier draft of this plan made exactly that mistake. If a
test disagrees, the model or the conversion is wrong — do not adjust the
assertion to match the output without redoing that arithmetic first, at full
precision.

- [ ] **Step 5: Make the script executable and check it by hand**

```bash
chmod +x starlight.py
./starlight.py Betelgeuse --on 2026-08-16 --offline
./starlight.py "Eta Carinae" --offline --uncertainty --verbose
./starlight.py Betelgeus --offline
```

Expected: the first two print results; the third exits 1 and suggests
`Betelgeuse`.

- [ ] **Step 6: Run the whole suite**

Run: `pytest -v`
Expected: PASS, all tests

- [ ] **Step 7: Commit**

```bash
git add starlight.py test_starlight.py
git commit -m "feat: add starlight CLI"
```

---

### Task 6: Documentation and project files

**Files:**
- Create: `README.md`
- Create: `.gitignore`
- Create: `pyproject.toml`

- [ ] **Step 1: Write the README**

Create `README.md`:

````markdown
# starlight

When you look at a star, you are looking into the past. `starlight.py` tells you
how far into the past: give it a star and a date, and it reports when the light
you saw began its journey.

```
$ ./starlight.py Betelgeuse --on 2026-08-16
Betelgeuse (Alpha Orionis)
  Distance     548.3 ly  (168.1 pc, Hipparcos (revised))
  Observed     16 August 2026 CE
  Light left   6 May 1478 CE
```

## Usage

```
starlight.py NAME [--on DATE] [--uncertainty] [--json] [--verbose] [--offline]
```

- `NAME` — a common name, Bayer designation, or catalogue number. Spelling is
  forgiving: `Betelgeuse`, `alpha ori`, `α Orionis`, and `HD 39801` all work.
- `--on DATE` — observation date as `YYYY-MM-DD`, with a leading minus for BCE
  years (`-0044-03-15` is the Ides of March). Defaults to today.
- `--uncertainty` — show the range implied by the distance error bars.
- `--json` — machine-readable output.
- `--verbose` — travel time, distance provenance, and modelling caveats.
- `--offline` — never query SIMBAD.

## How it works

The emission date is the observation date minus the light travel time,
`distance / c`, using the star's present catalogued distance.

Two things make that harder than it sounds. First, `datetime` cannot represent
years before 1 CE, and light from Eta Carinae left it in 5477 BCE — so all
date arithmetic runs on Julian Day Numbers over the proleptic Gregorian
calendar, which extends backwards without limit. Second, star names have no
canonical spelling, so names are matched in a normalized form with Greek
letters spelled out.

Fifty stars ship in `stars.json`. Anything else is looked up in SIMBAD, with
distance derived from parallax; `--offline` disables that.

## What the model ignores

The answer is the naive Earth-frame one. It ignores the star's radial motion,
which means its distance at emission differed slightly from its distance today;
it ignores proper motion; and it ignores gravitational and cosmological
effects. For every star here, those corrections are far smaller than the
uncertainty on the published distance — which `--uncertainty` will show you.

## Requirements

Python 3.10 or newer. No third-party runtime dependencies.

## Tests

```
pip install pytest
pytest
```

Tests never touch the network — the SIMBAD call is stubbed throughout.
````

- [ ] **Step 2: Write the project files**

Create `.gitignore`:

```
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
venv/
```

Create `pyproject.toml`:

```toml
[project]
name = "starlight"
version = "1.0.0"
description = "Calculate when the light you see from a star left it"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["."]
python_files = ["test_*.py"]
```

- [ ] **Step 3: Verify the whole thing from a clean state**

```bash
pytest -v
./starlight.py Sirius --offline --verbose
./starlight.py Deneb --on 2026-08-16 --offline --uncertainty
```

Expected: all tests pass; both commands print sensible results, with Deneb's
light having left on **18 October 591 BCE** (802 pc is 2,615.77 ly, or
955,411.5 days, which rounds to 955,412). Do not round the light-year figure
before multiplying by 365.25 — doing so shifts the answer by days.

- [ ] **Step 4: Commit**

```bash
git add README.md .gitignore pyproject.toml
git commit -m "docs: add README and project configuration"
```

---

## Self-Review Notes

**Spec coverage:** Physical model → Task 2. Calendar/JDN and BCE handling →
Task 1. Catalog schema and resolution → Task 3. SIMBAD fallback with all five
failure modes → Task 4. CLI flags, output formats, and all four exit codes →
Task 5. README caveats → Task 6. Every test group named in the spec appears in
a task.

**Deviations:** `lighttime.py` added as a fourth module; catalog fixed at 50
concrete entries. Both are recorded at the top of this plan.

**Type consistency:** `Star` fields are identical across Tasks 3, 4, and 5.
`StarNotFound` carries `name` and `suggestions` everywhere it is raised or
caught. `emission_jdn(observation_jdn, distance_pc)` keeps the same signature
in Tasks 2 and 5.
