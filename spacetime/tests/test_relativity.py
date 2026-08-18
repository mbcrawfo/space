import math
from dataclasses import FrozenInstanceError

import pytest

from spacetime import relativity
from spacetime.relativity import TripError, solve

# Light-year distances for three bundled stars, rounded from their catalogued
# parsecs. The expected values below were derived from the closed-form
# relativistic-rocket equations at exactly these distances.
PROXIMA_LY = 4.2433
SIRIUS_LY = 8.6007
BETELGEUSE_LY = 548.269

DISTANCES = [0.1, 1.0, PROXIMA_LY, 100.0, 1000.0]
ACCELERATIONS = [0.1, 0.5, 1.0, 3.0, 10.0]


def test_proxima_flip_and_burn_at_one_g():
    trip = solve(PROXIMA_LY, 1.0)
    assert trip.peak_velocity_c == pytest.approx(0.9496004179, rel=1e-8)
    assert trip.peak_lorentz == pytest.approx(3.1901692714, rel=1e-8)
    assert trip.crew_years == pytest.approx(3.5410380333, rel=1e-8)
    assert trip.earth_years == pytest.approx(5.8692239418, rel=1e-8)


def test_proxima_flyby_at_one_g():
    trip = solve(PROXIMA_LY, 1.0, flyby=True)
    assert trip.peak_velocity_c == pytest.approx(0.9825758751, rel=1e-8)
    assert trip.peak_lorentz == pytest.approx(5.3803385428, rel=1e-8)
    assert trip.crew_years == pytest.approx(2.2930922001, rel=1e-8)
    assert trip.earth_years == pytest.approx(5.1212002777, rel=1e-8)


def test_sirius_flip_and_burn_at_one_g():
    trip = solve(SIRIUS_LY, 1.0)
    assert trip.peak_velocity_c == pytest.approx(0.9829544010, rel=1e-8)
    assert trip.peak_lorentz == pytest.approx(5.4392309882, rel=1e-8)
    assert trip.crew_years == pytest.approx(4.6076458917, rel=1e-8)
    assert trip.earth_years == pytest.approx(10.3585014181, rel=1e-8)


def test_sirius_flyby_at_one_g():
    trip = solve(SIRIUS_LY, 1.0, flyby=True)
    assert trip.peak_velocity_c == pytest.approx(0.9948630155, rel=1e-8)
    assert trip.crew_years == pytest.approx(2.8876739862, rel=1e-8)
    assert trip.earth_years == pytest.approx(9.5202571425, rel=1e-8)


def test_sirius_at_three_g():
    trip = solve(SIRIUS_LY, 3.0)
    assert trip.peak_velocity_c == pytest.approx(0.9975579502, rel=1e-8)
    assert trip.crew_years == pytest.approx(2.1656732860, rel=1e-8)
    assert trip.earth_years == pytest.approx(9.2239296147, rel=1e-8)


def test_a_distant_star_costs_the_crew_far_less_than_earth():
    """The whole point of the tool: 12 years on deck, five centuries at home."""
    trip = solve(BETELGEUSE_LY, 1.0)
    assert trip.crew_years == pytest.approx(12.2873277279, rel=1e-8)
    assert trip.earth_years == pytest.approx(550.2030190328, rel=1e-8)
    assert trip.earth_years / trip.crew_years > 40.0


def test_the_trip_records_what_it_was_asked_for():
    trip = solve(PROXIMA_LY, 2.5, flyby=True)
    assert trip.distance_ly == PROXIMA_LY
    assert trip.accel_g == 2.5
    assert trip.flyby is True


def test_low_speed_limit_matches_newtonian_physics():
    """At a whisper of acceleration over a whisper of distance, the relativistic
    answer must collapse onto the Newtonian one: a flip-and-burn peaks at
    sqrt(a*D) and the two clocks agree."""
    distance_ly, accel_g = 1e-9, 1e-9
    trip = solve(distance_ly, accel_g)
    newtonian_ms = math.sqrt(accel_g * relativity.G0 * distance_ly * relativity.METERS_PER_LIGHT_YEAR)
    assert trip.peak_velocity_c * relativity.C == pytest.approx(newtonian_ms, rel=1e-9)
    assert trip.crew_years == pytest.approx(trip.earth_years, rel=1e-12)


@pytest.mark.parametrize("accel_g", ACCELERATIONS)
@pytest.mark.parametrize("distance_ly", DISTANCES)
def test_invariants_hold_across_the_realistic_range(distance_ly, accel_g):
    flip = solve(distance_ly, accel_g)
    fly = solve(distance_ly, accel_g, flyby=True)

    for trip in (flip, fly):
        assert 0.0 < trip.peak_velocity_c < 1.0
        assert trip.peak_lorentz > 1.0
        assert 0.0 < trip.crew_years <= trip.earth_years
        # No profile beats light over the same distance.
        assert trip.earth_years > distance_ly

    # Never stopping is always quicker, and always ends up faster.
    assert fly.earth_years < flip.earth_years
    assert fly.crew_years < flip.crew_years
    assert fly.peak_velocity_c > flip.peak_velocity_c


def test_more_acceleration_is_always_quicker():
    slower = solve(SIRIUS_LY, 1.0)
    faster = solve(SIRIUS_LY, 3.0)
    assert faster.crew_years < slower.crew_years
    assert faster.earth_years < slower.earth_years
    assert faster.peak_velocity_c > slower.peak_velocity_c


def test_further_is_always_slower():
    near = solve(PROXIMA_LY, 1.0)
    far = solve(SIRIUS_LY, 1.0)
    assert far.crew_years > near.crew_years
    assert far.earth_years > near.earth_years


@pytest.mark.parametrize("accel_g", [0.0, -1.0, float("nan"), float("inf")])
def test_unusable_acceleration_is_rejected(accel_g):
    with pytest.raises(TripError):
        solve(PROXIMA_LY, accel_g)


@pytest.mark.parametrize("distance_ly", [0.0, -1.0, float("nan"), float("inf")])
def test_unusable_distance_is_rejected(distance_ly):
    with pytest.raises(TripError):
        solve(distance_ly, 1.0)


def test_validate_acceleration_rejects_what_solve_rejects():
    """The CLI checks the acceleration before it reaches for the network, so
    the check has to be reachable on its own."""
    assert relativity.validate_acceleration(1.0) is None
    with pytest.raises(TripError):
        relativity.validate_acceleration(0.0)


def test_trip_error_is_a_value_error():
    assert issubclass(TripError, ValueError)


def test_a_trip_cannot_be_edited_after_the_fact():
    trip = solve(PROXIMA_LY, 1.0)
    with pytest.raises(FrozenInstanceError):
        trip.crew_years = 0.0
