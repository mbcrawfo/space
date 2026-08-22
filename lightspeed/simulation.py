"""The simulation: one flash from every star at t = 0, spreading at one light-year a year.

Pure state over numpy, with no knowledge of how it is drawn. The viewer owns a
`Simulation`, feeds it wall-clock seconds, and asks for the shell radius and for the
arrivals that fell inside each step. Because every star emits at the same instant and
light goes one light-year per year, the shell radius is simply the clock, and the
wavefront from star i reaches star j at exactly their separation in light-years — and j's
reaches i at the same instant — so the whole arrival schedule is the sorted list of
pairwise distances, one entry per pair, worked out once.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .catalog import Star

MIN_SPEED = 1.0 / 64.0
MAX_SPEED = 4096.0


@dataclass(frozen=True)
class Arrival:
    """The moment the wavefronts of stars `a` and `b` reach each other's star.

    Both crossings happen at the same instant — the two stars are the same distance apart
    either way — so one arrival stands for the pair. `a < b`, indices into the star list.
    """

    time_yr: float
    a: int
    b: int


def _check_speed(years_per_second: float) -> float:
    if not (math.isfinite(years_per_second) and years_per_second > 0.0):
        raise ValueError(f"Speed must be a positive, finite number of years per second, not {years_per_second}.")
    return float(years_per_second)


class Simulation:
    def __init__(self, stars: Sequence[Star], *, years_per_second: float = 1.0):
        self.stars = list(stars)
        self.positions = np.array([star.position for star in self.stars], dtype=float).reshape(len(self.stars), 3)
        self.years_per_second = _check_speed(years_per_second)
        self.time_yr = 0.0
        self.running = False
        self.arrivals = self._schedule()
        self._next = 0  # index into self.arrivals of the first arrival not yet delivered

    def _schedule(self) -> list[Arrival]:
        n = len(self.stars)
        if n < 2:
            return []
        separations = np.linalg.norm(self.positions[:, None, :] - self.positions[None, :, :], axis=2)
        first, second = np.triu_indices(n, k=1)  # each unordered pair once, lower index first
        times = separations[first, second]
        order = np.lexsort((second, first, times))  # by time, then a, then b
        return [Arrival(float(times[k]), int(first[k]), int(second[k])) for k in order]

    def start(self) -> None:
        self.running = True

    def pause(self) -> None:
        self.running = False

    def toggle(self) -> None:
        self.running = not self.running

    def reset(self) -> None:
        self.running = False
        self.time_yr = 0.0
        self._next = 0

    def faster(self) -> None:
        self.years_per_second = min(self.years_per_second * 2.0, MAX_SPEED)

    def slower(self) -> None:
        self.years_per_second = max(self.years_per_second / 2.0, MIN_SPEED)

    def radius(self) -> float:
        """Every shell's radius in light-years — the clock, since light does one light-year a year."""
        return self.time_yr

    def advance(self, wall_dt_s: float) -> list[Arrival]:
        """Move the clock by `wall_dt_s` real seconds and return the arrivals that fell in the step, in order."""
        if not (math.isfinite(wall_dt_s) and wall_dt_s >= 0.0):
            raise ValueError(f"The wall-clock step must be a non-negative, finite number of seconds, not {wall_dt_s}.")
        if not self.running:
            return []
        self.time_yr += wall_dt_s * self.years_per_second
        start = self._next
        while self._next < len(self.arrivals) and self.arrivals[self._next].time_yr <= self.time_yr:
            self._next += 1
        return self.arrivals[start : self._next]
