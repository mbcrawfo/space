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
