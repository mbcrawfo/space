"""Travel times under constant proper acceleration.

Acceleration here is *proper* acceleration — what a scale on deck reads —
held constant for the whole burn. A ship at a constant 1 G does not approach
c in a year: its coordinate acceleration falls away as it speeds up. Constant
proper acceleration is also the only reading under which "1 G" means what a
reader expects, namely Earth-normal gravity on deck for the whole trip.

Earth and the destination are treated as mutually at rest, and the distance
is the destination's present catalogued distance in Earth's frame. For a ship
starting at rest and accelerating through a distance d at proper acceleration
a, the standard relativistic-rocket results are:

    gamma = 1 + a*d/c**2             the Lorentz factor reached
    v/c   = sqrt(1 - 1/gamma**2)     the speed reached
    t     = sqrt((d/c)**2 + 2*d/a)   elapsed coordinate time, on Earth
    tau   = (c/a) * arccosh(gamma)   elapsed proper time, on deck
"""

import math
from dataclasses import dataclass

G0 = 9.80665  # m/s^2, standard gravity
C = 299792458.0  # m/s, exact by definition
LY_PER_PC = 3.26156378
SECONDS_PER_JULIAN_YEAR = 365.25 * 86400.0
METERS_PER_LIGHT_YEAR = C * SECONDS_PER_JULIAN_YEAR


class TripError(ValueError):
    """Raised for an acceleration or a distance the model cannot use."""


@dataclass(frozen=True)
class Trip:
    """A trip flown to completion. Both times are in Julian years."""

    distance_ly: float
    accel_g: float
    flyby: bool
    peak_velocity_c: float  # a fraction of c, not a percentage
    peak_lorentz: float
    crew_years: float
    earth_years: float


def validate_acceleration(accel_g: float) -> None:
    """Reject an acceleration the model cannot use.

    Zero acceleration is a trip that never ends and a negative one is not a
    direction, so both are refused here rather than allowed to surface as an
    infinity or a NaN further in. Exposed separately so the CLI can reject bad
    input before it reaches for the network.
    """
    if not math.isfinite(accel_g) or accel_g <= 0.0:
        raise TripError(f"Acceleration must be a positive, finite number of G, not {accel_g!r}.")


def _validate_distance(distance_ly: float) -> None:
    if not math.isfinite(distance_ly) or distance_ly <= 0.0:
        raise TripError(f"Distance must be a positive, finite number of light-years, not {distance_ly!r}.")


def _leg(distance_ly: float, accel_g: float) -> tuple[float, float, float]:
    """One burn from rest through `distance_ly` at `accel_g`.

    Returns `gamma - 1` and the coordinate and proper times in Julian years.
    The Lorentz factor comes back as its excess over 1 because every caller
    wants it that way: forming `gamma` first and subtracting later would throw
    away exactly the precision the small-excess cases depend on.
    """
    distance_m = distance_ly * METERS_PER_LIGHT_YEAR
    accel = accel_g * G0

    excess = accel * distance_m / C**2

    earth_seconds = math.sqrt((distance_m / C) ** 2 + 2.0 * distance_m / accel)
    # arccosh(1 + x) == log1p(x + sqrt(x * (x + 2))), which keeps its precision
    # for small x where math.acosh(1 + x) has already lost it.
    crew_seconds = (C / accel) * math.log1p(excess + math.sqrt(excess * (excess + 2.0)))

    return excess, earth_seconds / SECONDS_PER_JULIAN_YEAR, crew_seconds / SECONDS_PER_JULIAN_YEAR


def solve(distance_ly: float, accel_g: float, *, flyby: bool = False) -> Trip:
    """Work out a trip at constant proper acceleration.

    By default the ship burns for the first half of the distance, flips,
    decelerates for the second half, and arrives at rest — so it is fastest at
    the midpoint. With `flyby` it burns the whole way and passes the
    destination without stopping, fastest at arrival.
    """
    _validate_distance(distance_ly)
    validate_acceleration(accel_g)

    burn_ly = distance_ly if flyby else distance_ly / 2.0
    excess, earth_years, crew_years = _leg(burn_ly, accel_g)
    if not flyby:
        earth_years *= 2.0
        crew_years *= 2.0

    return Trip(
        distance_ly=distance_ly,
        accel_g=accel_g,
        flyby=flyby,
        # sqrt(gamma**2 - 1)/gamma, written in terms of the excess so it never
        # has to evaluate sqrt(1 - tiny) and round its way up to exactly c.
        peak_velocity_c=math.sqrt(excess * (excess + 2.0)) / (1.0 + excess),
        peak_lorentz=1.0 + excess,
        crew_years=crew_years,
        earth_years=earth_years,
    )
