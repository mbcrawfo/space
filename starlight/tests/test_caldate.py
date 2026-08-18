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
        "0000-01-01",
        "2026-0²-16",
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
