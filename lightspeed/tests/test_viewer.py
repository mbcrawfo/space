import math
import warnings

import numpy as np
import pytest
import pyvista

from lightspeed import catalog, simulation, viewer


class FakeActor:
    def __init__(self):
        self.position = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.visibility = True


class FakeRenderWindow:
    """Stands in for vtkRenderWindow: records observers so a test can fire a render."""

    def __init__(self):
        self.observers = []  # (event, callback)

    def AddObserver(self, event, callback):  # noqa: N802 - VTK's spelling
        self.observers.append((event, callback))

    def fire(self, event):
        for name, callback in self.observers:
            if name == event:
                callback(self, event)


class FakePlotter:
    """Records every call the Viewer makes; knows nothing about VTK."""

    def __init__(self):
        self.meshes = []  # (mesh, kwargs)
        self.actors = []
        self.texts = {}  # name -> (text, kwargs)
        self.text_calls = {}  # name -> count of add_text calls for that name
        self.keys = {}  # key -> callback
        self.timers = []  # (max_steps, duration, callback)
        self.labels = None
        self.background = None
        self.depth_peeling = False
        self.renders = 0
        self.camera_position = None
        self.render_window = FakeRenderWindow()  # None once the plotter has been closed, as in pyvista

    def add_mesh(self, mesh, **kwargs):
        actor = FakeActor()
        self.meshes.append((mesh, kwargs))
        self.actors.append(actor)
        return actor

    def add_point_labels(self, points, labels, **kwargs):
        self.labels = (np.asarray(points), list(labels), kwargs)

    def add_text(self, text, **kwargs):
        name = kwargs["name"]
        self.texts[name] = (text, kwargs)
        self.text_calls[name] = self.text_calls.get(name, 0) + 1

    def add_key_event(self, key, callback):
        self.keys[key] = callback

    def add_timer_event(self, max_steps, duration, callback):
        self.timers.append((max_steps, duration, callback))

    def enable_depth_peeling(self, *args, **kwargs):
        self.depth_peeling = True

    def set_background(self, color, **kwargs):
        self.background = color

    def render(self):
        self.renders += 1


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def star(name, x):
    return catalog.Star(name=name, ra_deg=0.0, dec_deg=0.0, distance_ly=x, source="test")


def make_viewer(speed=1.0):
    sim = simulation.Simulation([catalog.SOL, star("A", 3.0), star("B", 7.0)], years_per_second=speed)
    plotter = FakePlotter()
    clock = FakeClock()
    # Tests jump the fake clock by whole seconds; the per-frame cap is tested on its own below.
    view = viewer.Viewer(sim, plotter, clock=clock, max_frame_seconds=math.inf)
    view.build()
    return view, sim, plotter, clock


def shell_meshes(plotter):
    return [(m, kw) for m, kw in plotter.meshes if kw.get("opacity") is not None]


def test_build_adds_one_translucent_unit_shell_per_star_placed_at_the_star():
    view, sim, plotter, _ = make_viewer()
    shells = shell_meshes(plotter)
    assert len(shells) == 3
    assert len(view.shells) == 3
    for (mesh, kwargs), actor, position in zip(shells, view.shells, sim.positions, strict=True):
        assert 0.0 < kwargs["opacity"] < 0.5
        assert np.linalg.norm(mesh.points, axis=1).max() == pytest.approx(1.0, abs=1e-6)
        assert actor.position == pytest.approx(tuple(position))
        assert actor.visibility is False  # nothing has been emitted yet


def test_build_adds_the_star_points_with_sol_in_yellow():
    _, _, plotter, _ = make_viewer()
    points = [(m, kw) for m, kw in plotter.meshes if kw.get("rgb")]
    assert len(points) == 1
    mesh, kwargs = points[0]
    assert kwargs["scalars"] == "rgb"
    assert kwargs["render_points_as_spheres"] is True
    assert mesh.n_points == 3
    assert tuple(mesh["rgb"][0]) == viewer.SOL_COLOR
    assert tuple(mesh["rgb"][1]) == viewer.STAR_COLOR


def test_build_labels_every_star_with_name_and_distance():
    _, _, plotter, _ = make_viewer()
    points, labels, kwargs = plotter.labels
    assert labels == ["Sol (0 ly)", "A (3.0 ly)", "B (7.0 ly)"]
    assert points.shape == (3, 3)
    assert kwargs["always_visible"] is True
    assert kwargs["shape"] is None
    assert kwargs["show_points"] is False
    assert kwargs["text_color"] is not None


def test_build_sets_up_the_scene_the_overlays_the_keys_and_the_timer():
    _, _, plotter, _ = make_viewer()
    assert plotter.background == "black"
    assert plotter.depth_peeling is True
    assert plotter.camera_position is not None
    assert {"clock", "log", "help"} <= set(plotter.texts)
    for _text, kwargs in plotter.texts.values():
        assert kwargs.get("color") is not None  # the default theme draws text black on black
    assert "paused" in plotter.texts["clock"][0]
    assert "space" in plotter.texts["help"][0]
    assert set(plotter.keys) == {"space", "plus", "equal", "minus", "r"}
    assert len(plotter.timers) == 1
    max_steps, duration, callback = plotter.timers[0]
    assert max_steps > 10**6
    assert duration == viewer.FRAME_MS
    assert callable(callback)


def test_ticking_while_paused_keeps_shells_hidden_and_does_not_render():
    view, sim, plotter, clock = make_viewer()
    clock.now += 1.0
    plotter.timers[0][2](1)  # the registered timer callback is view.on_tick
    assert sim.time_yr == 0.0
    assert all(actor.visibility is False for actor in view.shells)
    # pyvista's real Timer.execute renders the window itself right after invoking this
    # callback, so on_tick must not render a second time.
    assert plotter.renders == 0


def test_space_starts_and_ticks_grow_every_shell_to_the_clock():
    view, sim, plotter, clock = make_viewer(speed=2.0)
    plotter.keys["space"]()
    assert sim.running is True
    view.on_tick(1)  # the first tick only primes the frame clock
    clock.now += 0.5  # 0.5 s x 2 yr/s = 1 yr
    view.on_tick(2)
    assert sim.time_yr == pytest.approx(1.0)
    for actor in view.shells:
        assert actor.visibility is True
        assert actor.scale == pytest.approx((1.0, 1.0, 1.0))
    assert "t =" in plotter.texts["clock"][0]
    assert "1.0" in plotter.texts["clock"][0]
    assert "paused" not in plotter.texts["clock"][0]


def test_the_first_tick_after_build_does_not_jump_the_clock():
    """build() happens long before the window appears; the first frame must measure from the first tick, not from build()."""
    view, sim, _, clock = make_viewer()
    view.toggle()
    clock.now += 1000.0
    view.on_tick(1)
    assert sim.time_yr == 0.0
    clock.now += 1.0
    view.on_tick(2)
    assert sim.time_yr == pytest.approx(1.0)


def test_an_arrival_highlights_the_target_and_logs_a_line():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    mesh = next(m for m, kw in plotter.meshes if kw.get("rgb"))
    assert tuple(mesh["rgb"][1]) == viewer.HIGHLIGHT_COLOR  # A was reached by Sol's light
    assert tuple(mesh["rgb"][0]) == viewer.HIGHLIGHT_COLOR  # and Sol by A's
    assert tuple(mesh["rgb"][2]) == viewer.STAR_COLOR
    assert view.log_lines == ["y    3.0  light from Sol reaches A", "y    3.0  light from A reaches Sol"]
    assert plotter.texts["log"][0] == "\n".join(view.log_lines)


def test_a_highlight_fades_back_after_highlight_seconds():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    mesh = next(m for m, kw in plotter.meshes if kw.get("rgb"))
    clock.now += viewer.HIGHLIGHT_SECONDS / 2
    view.on_tick(3)
    assert tuple(mesh["rgb"][1]) == viewer.HIGHLIGHT_COLOR
    clock.now += viewer.HIGHLIGHT_SECONDS
    view.on_tick(4)
    assert tuple(mesh["rgb"][1]) == viewer.STAR_COLOR
    assert tuple(mesh["rgb"][0]) == viewer.SOL_COLOR  # Sol goes back to its own colour, not white


def test_an_arrival_tick_refreshes_the_log_text_exactly_once():
    """A burst of several arrivals in one tick must add_text('log', ...) only once, not once per arrival."""
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)  # primes the frame clock, no arrivals yet
    plotter.text_calls.clear()
    clock.now += 10.0  # far enough for all six arrivals to land in this one tick
    view.on_tick(2)
    assert len(view.log_lines) == 6
    assert plotter.text_calls["log"] == 1


def test_the_log_keeps_only_the_last_lines():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 10.0
    view.on_tick(2)  # all six arrivals
    assert len(view.log_lines) == 6
    view.log_lines.clear()
    for i in range(viewer.LOG_LINES + 3):
        view._log(f"line {i}")  # append-only: does not touch plotter.texts by itself
    assert view.log_lines == [f"line {i}" for i in range(3, viewer.LOG_LINES + 3)]
    view._refresh_log()
    assert plotter.texts["log"][0] == "\n".join(view.log_lines)


def test_plus_equal_and_minus_change_the_speed_and_the_clock_text():
    _, sim, plotter, _ = make_viewer()
    plotter.keys["plus"]()
    assert sim.years_per_second == 2.0
    assert "2 yr/s" in plotter.texts["clock"][0]
    plotter.keys["equal"]()
    assert sim.years_per_second == 4.0
    plotter.keys["minus"]()
    assert sim.years_per_second == 2.0


def test_r_resets_the_clock_hides_the_shells_and_clears_the_log_and_highlights():
    view, sim, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    plotter.keys["r"]()
    mesh = next(m for m, kw in plotter.meshes if kw.get("rgb"))
    assert sim.time_yr == 0.0
    assert sim.running is False
    assert all(actor.visibility is False for actor in view.shells)
    assert view.log_lines == []
    assert plotter.texts["log"][0] == ""
    assert tuple(mesh["rgb"][1]) == viewer.STAR_COLOR
    assert "paused" in plotter.texts["clock"][0]


def test_format_arrival_reads_like_a_log_line():
    sim = simulation.Simulation([catalog.SOL, star("Proxima Centauri", 4.2465)])
    line = viewer.format_arrival(sim, simulation.Arrival(4.2465, 0, 1))
    assert line == "y    4.2  light from Sol reaches Proxima Centauri"


def test_speed_text_drops_needless_decimals():
    assert viewer.format_speed(1.0) == "1 yr/s"
    assert viewer.format_speed(0.5) == "0.5 yr/s"
    assert viewer.format_speed(1 / 64) == "0.0156 yr/s"
    assert viewer.format_speed(4096.0) == "4096 yr/s"


def test_run_builds_a_real_plotter_and_shows_it(monkeypatch):
    """`run` is the only place a real Plotter is made; stub Plotter so nothing opens, and check the wiring."""
    created = {}

    class StubPlotter(FakePlotter):
        def __init__(self, **kwargs):
            super().__init__()
            created["kwargs"] = kwargs
            created["plotter"] = self

        def show(self, **kwargs):
            created["shown"] = kwargs

    monkeypatch.setattr(viewer.pv, "Plotter", StubPlotter)
    viewer.run([catalog.SOL, star("A", 3.0)], years_per_second=2.0, autostart=True)
    plotter = created["plotter"]
    assert created["shown"]["title"] == "lightspeed"
    before_close = created["shown"]["before_close_callback"]
    before_close(plotter)  # what pyvista calls first when the window closes
    clock_calls = dict(plotter.text_calls)
    plotter.timers[0][2](99)  # the straggler tick VTK still delivers
    assert plotter.text_calls == clock_calls
    assert len(plotter.timers) == 1
    assert "paused" not in plotter.texts["clock"][0]  # autostart


def test_a_tick_after_the_plotter_closes_does_nothing():
    """VTK delivers one more timer event after `q` has torn the window down; the viewer must not
    touch a plotter that has no render window any more, or pyvista raises from inside the callback."""
    view, sim, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    calls_before = dict(plotter.text_calls)
    plotter.render_window = None  # what pyvista's close() leaves behind
    clock.now += 5.0
    view.on_tick(2)
    assert sim.time_yr == 0.0
    assert plotter.text_calls == calls_before
    assert all(actor.visibility is False for actor in view.shells)


def test_build_advances_the_frame_before_every_render_too():
    """On macOS VTK's timers do not fire while the mouse button is held, but the trackball renders on
    every mouse move; hooking the render window's StartEvent keeps the shells growing mid-drag."""
    view, sim, plotter, clock = make_viewer()
    events = [name for name, _ in plotter.render_window.observers]
    assert events == ["StartEvent"]
    view.toggle()
    view.on_tick(1)
    clock.now += 0.1
    plotter.render_window.fire("StartEvent")
    assert sim.time_yr == pytest.approx(0.1)
    assert view.shells[0].scale == pytest.approx((0.1, 0.1, 0.1))


def test_a_long_gap_between_frames_pauses_the_clock_instead_of_jumping_it():
    """A drag with the mouse held still, or a hidden window, produces no frames; when they resume the
    simulation must not leap ahead by the whole gap."""
    sim = simulation.Simulation([catalog.SOL, star("A", 3.0)], years_per_second=2.0)
    plotter = FakePlotter()
    clock = FakeClock()
    view = viewer.Viewer(sim, plotter, clock=clock)  # the default cap
    view.build()
    view.toggle()
    view.on_tick(1)
    clock.now += 5.0
    view.on_tick(2)
    assert sim.time_yr == pytest.approx(2.0 * viewer.MAX_FRAME_SECONDS)
    clock.now += 0.1
    view.on_tick(3)
    assert sim.time_yr == pytest.approx(2.0 * viewer.MAX_FRAME_SECONDS + 0.2)


def test_stop_makes_every_later_tick_a_no_op():
    """`run()` wires stop() to pyvista's before_close_callback, which fires before close() tears the
    renderer down — earlier than the render window disappears, which is too late on macOS."""
    view, sim, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    calls_before = dict(plotter.text_calls)
    view.stop()
    clock.now += 5.0
    view.on_tick(2)
    assert sim.time_yr == 0.0
    assert plotter.text_calls == calls_before


def test_a_tick_after_a_real_plotter_closes_raises_nothing():
    """The real reproduction of the bug seen on `q`: close() then one more tick."""
    sim = simulation.Simulation([catalog.SOL, star("A", 3.0)])
    plotter = pyvista.Plotter(off_screen=True)
    view = viewer.Viewer(sim, plotter, clock=FakeClock())
    view.build()
    view.toggle()
    view.on_tick(1)
    plotter.close()
    view.clock.now += 5.0
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        view.on_tick(2)


def test_build_works_against_a_real_off_screen_plotter():
    """A CI-safe smoke test against real pyvista/VTK objects, not the fake — no show(),
    render(), or screenshot(), so nothing tries to put a window on screen."""
    plotter = pyvista.Plotter(off_screen=True)
    viewer.Viewer(simulation.Simulation([catalog.SOL, star("A", 3.0)]), plotter).build()
    assert len(plotter.renderer.actors) >= 4  # shells + points + labels + text overlays
