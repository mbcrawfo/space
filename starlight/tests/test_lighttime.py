import pytest

from starlight.lighttime import (
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
