import math

import numpy as np
import pytest

from lightspeed import catalog, simulation


def star(name, x, y=0.0, z=0.0):
    """A star at Cartesian (x, y, z) light-years, built by way of RA/Dec so the catalog math is exercised."""
    distance = math.hypot(x, y, z)
    if distance == 0.0:
        return catalog.SOL
    dec = math.degrees(math.asin(z / distance))
    ra = math.degrees(math.atan2(y, x)) % 360.0
    return catalog.Star(name=name, ra_deg=ra, dec_deg=dec, distance_ly=distance, source="test")


def line_of_three():
    return [catalog.SOL, star("A", 3.0), star("B", 7.0)]


def test_positions_are_an_n_by_three_array_in_star_order():
    sim = simulation.Simulation(line_of_three())
    assert sim.positions.shape == (3, 3)
    assert sim.positions[1] == pytest.approx([3.0, 0.0, 0.0])
    assert sim.positions[2] == pytest.approx([7.0, 0.0, 0.0])


def test_arrivals_are_every_ordered_pair_sorted_by_distance():
    sim = simulation.Simulation(line_of_three())
    schedule = [(round(a.time_yr, 9), a.source, a.target) for a in sim.arrivals]
    assert schedule == [(3.0, 0, 1), (3.0, 1, 0), (4.0, 1, 2), (4.0, 2, 1), (7.0, 0, 2), (7.0, 2, 0)]


def test_it_starts_paused_at_time_zero():
    sim = simulation.Simulation(line_of_three())
    assert sim.time_yr == 0.0
    assert sim.running is False
    assert sim.radius() == 0.0


def test_advancing_while_paused_changes_nothing():
    sim = simulation.Simulation(line_of_three())
    assert sim.advance(10.0) == []
    assert sim.time_yr == 0.0


def test_advancing_while_running_moves_the_clock_at_the_chosen_speed():
    sim = simulation.Simulation(line_of_three(), years_per_second=2.0)
    sim.start()
    sim.advance(0.5)
    assert sim.time_yr == pytest.approx(1.0)
    assert sim.radius() == pytest.approx(1.0)


def test_advance_returns_exactly_the_arrivals_in_the_step():
    sim = simulation.Simulation(line_of_three())
    sim.start()
    assert sim.advance(2.9) == []
    first = sim.advance(0.2)  # now 3.1: the two 3.0 ly arrivals
    assert [(a.source, a.target) for a in first] == [(0, 1), (1, 0)]
    second = sim.advance(4.0)  # now 7.1: the 4.0 and 7.0 arrivals
    assert [(a.source, a.target) for a in second] == [(1, 2), (2, 1), (0, 2), (2, 0)]
    assert sim.advance(100.0) == []


def test_an_arrival_exactly_at_the_new_time_counts():
    sim = simulation.Simulation(line_of_three())
    sim.start()
    assert [(a.source, a.target) for a in sim.advance(3.0)] == [(0, 1), (1, 0)]


def test_reset_rewinds_the_clock_and_the_schedule_and_pauses():
    sim = simulation.Simulation(line_of_three())
    sim.start()
    sim.advance(5.0)
    sim.reset()
    assert sim.time_yr == 0.0
    assert sim.running is False
    sim.start()
    assert [(a.source, a.target) for a in sim.advance(3.5)] == [(0, 1), (1, 0)]


def test_toggle_flips_running():
    sim = simulation.Simulation(line_of_three())
    sim.toggle()
    assert sim.running is True
    sim.toggle()
    assert sim.running is False


def test_faster_and_slower_double_and_halve_within_the_clamps():
    sim = simulation.Simulation(line_of_three(), years_per_second=1.0)
    sim.faster()
    assert sim.years_per_second == 2.0
    sim.slower()
    sim.slower()
    assert sim.years_per_second == 0.5
    for _ in range(20):
        sim.faster()
    assert sim.years_per_second == simulation.MAX_SPEED
    for _ in range(40):
        sim.slower()
    assert sim.years_per_second == simulation.MIN_SPEED


@pytest.mark.parametrize("speed", [0.0, -1.0, float("nan"), float("inf")])
def test_a_bad_initial_speed_is_rejected(speed):
    with pytest.raises(ValueError, match="positive, finite"):
        simulation.Simulation(line_of_three(), years_per_second=speed)


@pytest.mark.parametrize("dt", [-0.1, float("nan"), float("inf")])
def test_a_bad_wall_step_is_rejected(dt):
    sim = simulation.Simulation(line_of_three())
    sim.start()
    with pytest.raises(ValueError, match="wall-clock"):
        sim.advance(dt)


def test_a_single_star_has_no_arrivals():
    sim = simulation.Simulation([catalog.SOL])
    sim.start()
    assert sim.arrivals == []
    assert sim.advance(50.0) == []


def test_arrival_times_match_the_real_catalogue_pairwise_distances():
    stars = catalog.load()[:10]
    sim = simulation.Simulation(stars)
    for arrival in sim.arrivals:
        expected = np.linalg.norm(sim.positions[arrival.source] - sim.positions[arrival.target])
        assert arrival.time_yr == pytest.approx(expected)


def test_equal_arrival_times_across_distinct_pairs_sort_by_source_then_target():
    # Sol at the origin, A at (3, 0, 0), B at (0, 3, 0): Sol-A and Sol-B are both exactly
    # 3 ly, so the four arrivals they produce tie on time_yr and must break the tie by
    # (source, target) rather than by whichever pair happened to be computed first.
    sim = simulation.Simulation([catalog.SOL, star("A", 3.0, 0.0, 0.0), star("B", 0.0, 3.0, 0.0)])
    schedule = [(round(a.time_yr, 9), a.source, a.target) for a in sim.arrivals]
    assert schedule[:4] == [(3.0, 0, 1), (3.0, 0, 2), (3.0, 1, 0), (3.0, 2, 0)]
    a_to_b = math.hypot(3.0, 3.0)
    assert schedule[4:] == [(round(a_to_b, 9), 1, 2), (round(a_to_b, 9), 2, 1)]


def test_advance_zero_while_running_returns_nothing_and_does_not_move_the_clock():
    sim = simulation.Simulation(line_of_three())
    sim.start()
    assert sim.advance(0.0) == []
    assert sim.time_yr == 0.0


def test_a_bad_wall_step_is_rejected_even_while_paused():
    sim = simulation.Simulation(line_of_three())
    assert sim.running is False
    with pytest.raises(ValueError, match="wall-clock"):
        sim.advance(-0.1)
