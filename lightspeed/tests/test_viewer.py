import math
import warnings

import numpy as np
import pytest
import pyvista

from lightspeed import catalog, simulation, viewer


class FakeProp:
    def __init__(self, opacity=1.0, line_width=1.0):
        self.opacity = opacity
        self.line_width = line_width


class FakeActor:
    def __init__(self, **kwargs):
        self.position = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.visibility = True
        self.prop = FakeProp(opacity=kwargs.get("opacity", 1.0), line_width=kwargs.get("line_width", 1.0))


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


class FakeCamera:
    def __init__(self):
        self.position = (0.0, 0.0, viewer.CAMERA_DISTANCE_LY)


class FakePlotter:
    """Records every call the Viewer makes; knows nothing about VTK."""

    def __init__(self):
        self.meshes = []  # (mesh, kwargs)
        self.actors = []
        self.texts = {}  # name -> (text, kwargs)
        self.text_calls = {}  # name -> count of add_text calls for that name
        self.keys = {}  # key -> callback
        self.timers = []  # (max_steps, duration, callback)
        self.named_actors = {}  # name -> (actor, render) for add_actor
        self.camera = FakeCamera()
        self.background = None
        self.depth_peeling = False
        self.renders = 0
        self.camera_position = None
        self.render_window = FakeRenderWindow()  # None once the plotter has been closed, as in pyvista
        self.window_size = (1280, 860)

    def add_mesh(self, mesh, **kwargs):
        actor = FakeActor(**kwargs)
        self.meshes.append((mesh, kwargs))
        self.actors.append(actor)
        return actor

    def add_actor(self, actor, *, name=None, render=True):
        self.named_actors[name] = (actor, render)
        return actor

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
    return [(m, kw) for m, kw in plotter.meshes if kw.get("smooth_shading")]


def ring_mesh(plotter):
    (mesh, kwargs), actor = next(
        ((m, kw), a) for (m, kw), a in zip(plotter.meshes, plotter.actors, strict=True) if kw.get("scalars") == "rgba"
    )
    return mesh, kwargs, actor


def line_actor(plotter, color):
    return next(a for (m, kw), a in zip(plotter.meshes, plotter.actors, strict=True) if kw.get("color") == color)


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
    points = [(m, kw) for m, kw in plotter.meshes if kw.get("render_points_as_spheres")]
    assert len(points) == 1
    mesh, kwargs = points[0]
    assert kwargs["scalars"] == "rgb"
    assert kwargs["render_points_as_spheres"] is True
    assert mesh.n_points == 3
    assert tuple(mesh["rgb"][0]) == viewer.SOL_COLOR
    assert tuple(mesh["rgb"][1]) == viewer.STAR_COLOR


def label_actors(plotter):
    return [actor for name, (actor, _render) in sorted(plotter.named_actors.items()) if name.startswith("label-")]


def test_build_labels_every_star_with_name_and_distance():
    view, sim, plotter, _ = make_viewer()
    labels = label_actors(plotter)
    assert [label.input for label in labels] == ["Sol (0 ly)", "A (3.0 ly)", "B (7.0 ly)"]
    for label, position in zip(labels, sim.positions, strict=True):
        assert label.position == pytest.approx(tuple(position))
    assert all(
        render is False for _actor, render in plotter.named_actors.values()
    )  # 88 renders at build time would be slow
    assert view.labels == labels


def test_labels_are_base_size_at_the_reference_distance_and_grow_as_the_camera_nears():
    view, _, plotter, clock = make_viewer()
    # Sol sits at the focal point, CAMERA_DISTANCE_LY from the default camera: the base size exactly.
    assert view.labels[0].size == viewer.LABEL_FONT_SIZE
    plotter.camera.position = (0.0, 0.0, viewer.CAMERA_DISTANCE_LY / 2)
    clock.now += 0.01
    view.on_tick(1)
    assert view.labels[0].size == 2 * viewer.LABEL_FONT_SIZE
    plotter.camera.position = (0.0, 0.0, 0.5)  # right on top of Sol: clamped, not astronomical
    view.on_tick(2)
    assert view.labels[0].size == viewer.LABEL_MAX_FONT_SIZE
    plotter.camera.position = (0.0, 0.0, 10 * viewer.CAMERA_DISTANCE_LY)
    view.on_tick(3)
    assert view.labels[0].size == viewer.LABEL_MIN_FONT_SIZE


def test_label_sizes_follow_the_camera_even_while_paused():
    view, _, plotter, _ = make_viewer()
    before = view.labels[1].size
    plotter.camera.position = tuple(p / 3 for p in plotter.camera.position)
    view.on_tick(1)
    assert view.labels[1].size > before


def test_overlay_text_uses_a_font_that_has_the_arrow():
    _, _, plotter, _ = make_viewer()
    assert viewer.OVERLAY_FONT_FILE is not None and viewer.OVERLAY_FONT_FILE.endswith("DejaVuSans.ttf")
    for name in ("clock", "log", "help"):
        assert plotter.texts[name][1]["font_file"] == viewer.OVERLAY_FONT_FILE


def test_overlay_text_is_readable_from_across_the_room():
    _, _, plotter, _ = make_viewer()
    assert plotter.texts["clock"][1]["font_size"] == viewer.CLOCK_FONT_SIZE == 24
    assert plotter.texts["log"][1]["font_size"] == viewer.OVERLAY_FONT_SIZE == 18
    assert plotter.texts["help"][1]["font_size"] == viewer.OVERLAY_FONT_SIZE == 18


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
    assert set(plotter.keys) == {
        "space",
        "plus",
        "equal",
        "minus",
        "r",
        "m",
        "bracketright",
        "bracketleft",
        "backslash",
    }
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
    _, _, rings = ring_mesh(plotter)
    assert rings.visibility is True
    for actor in view.shells:
        assert actor.visibility is False  # the default style draws rings, not filled shells
        assert actor.scale == pytest.approx((1.0, 1.0, 1.0))  # but the fills track the radius regardless
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


def test_an_arrival_highlights_both_stars_and_logs_one_line():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    mesh = next(m for m, kw in plotter.meshes if kw.get("render_points_as_spheres"))
    assert tuple(mesh["rgb"][1]) == viewer.HIGHLIGHT_COLOR  # A was reached by Sol's light
    assert tuple(mesh["rgb"][0]) == viewer.HIGHLIGHT_COLOR  # and Sol by A's
    assert tuple(mesh["rgb"][2]) == viewer.STAR_COLOR
    assert view.log_lines == ["  3.0 yr  Sol ↔ A"]
    assert plotter.texts["log"][0] == "\n".join(reversed(view.log_lines))


def test_a_highlight_fades_back_after_highlight_seconds():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    mesh = next(m for m, kw in plotter.meshes if kw.get("render_points_as_spheres"))
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
    clock.now += 10.0  # far enough for all three pair arrivals to land in this one tick
    view.on_tick(2)
    assert len(view.log_lines) == 3
    assert plotter.text_calls["log"] == 1


def test_the_log_shows_the_newest_arrival_first():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 4.5
    view.on_tick(2)  # the 3.0 ly pair, then the 4.0 ly pair
    assert view.log_lines[-1] == "  4.0 yr  A ↔ B"
    assert plotter.texts["log"][0].splitlines()[0] == "  4.0 yr  A ↔ B"
    assert plotter.texts["log"][0] == "\n".join(reversed(view.log_lines))


def test_the_log_keeps_as_many_lines_as_fit_in_its_share_of_the_window():
    view, _, plotter, _ = make_viewer()
    # 30 % of an 860 px window at 41 px a line is 6 lines; a taller window holds more.
    assert view.log_capacity() == int(viewer.LOG_HEIGHT_FRACTION * 860 / viewer.LOG_LINE_PX) == 6
    plotter.window_size = (1280, 1720)
    assert view.log_capacity() == 12
    plotter.window_size = (1280, 40)
    assert view.log_capacity() == 1  # never zero: the newest arrival always shows


def test_the_log_drops_the_oldest_lines_beyond_its_capacity():
    view, _, plotter, _ = make_viewer()
    capacity = view.log_capacity()
    for i in range(capacity + 3):
        view._log(f"line {i}")  # append-only: does not touch plotter.texts by itself
    assert view.log_lines == [f"line {i}" for i in range(3, capacity + 3)]
    view._refresh_log()
    assert plotter.texts["log"][0] == "\n".join(reversed(view.log_lines))


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
    mesh = next(m for m, kw in plotter.meshes if kw.get("render_points_as_spheres"))
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
    assert line == "  4.2 yr  Sol ↔ Proxima Centauri"


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


# -- rings, styles and focus --------------------------------------------------


def test_build_adds_one_camera_facing_ring_per_star_hidden_until_light_is_emitted():
    view, sim, plotter, clock = make_viewer()
    mesh, kwargs, actor = ring_mesh(plotter)
    assert mesh.n_points == 3 * viewer.RING_SEGMENTS
    assert kwargs["rgb"] is True and mesh["rgba"].shape == (3 * viewer.RING_SEGMENTS, 4)
    assert actor.visibility is False
    view.toggle()
    view.on_tick(1)
    clock.now += 2.0
    view.on_tick(2)
    assert actor.visibility is True
    camera = np.asarray(plotter.camera.position)
    for index, center in enumerate(sim.positions):
        ring = mesh.points[index * viewer.RING_SEGMENTS : (index + 1) * viewer.RING_SEGMENTS]
        assert np.linalg.norm(ring - center, axis=1) == pytest.approx(np.full(viewer.RING_SEGMENTS, 2.0), abs=1e-5)
        towards_camera = camera - center
        assert np.abs((ring - center) @ towards_camera) == pytest.approx(np.zeros(viewer.RING_SEGMENTS), abs=1e-4)


def test_rings_fade_as_the_shells_grow():
    view, _, plotter, clock = make_viewer()
    mesh, _, _ = ring_mesh(plotter)
    view.toggle()
    view.on_tick(1)
    clock.now += 1.0
    view.on_tick(2)
    young = int(mesh["rgba"][0, 3])
    clock.now += 8.0
    view.on_tick(3)
    old = int(mesh["rgba"][0, 3])
    assert young == round(255 * viewer.ring_alpha(1.0)) > old == round(255 * viewer.ring_alpha(9.0))
    assert viewer.ring_alpha(100.0) == viewer.RING_MIN_ALPHA


def test_m_cycles_the_shell_style():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 1.0
    view.on_tick(2)
    _, _, rings = ring_mesh(plotter)
    fills = view.shells
    assert view.style == "rings" and rings.visibility and not any(a.visibility for a in fills)
    plotter.keys["m"]()
    assert view.style == "rings + fill" and rings.visibility and all(a.visibility for a in fills)
    assert fills[0].prop.opacity == viewer.FILL_OPACITY_WITH_RINGS
    plotter.keys["m"]()
    assert view.style == "fill" and not rings.visibility and all(a.visibility for a in fills)
    assert fills[0].prop.opacity == viewer.SHELL_OPACITY
    plotter.keys["m"]()
    assert view.style == "off" and not rings.visibility and not any(a.visibility for a in fills)
    plotter.keys["m"]()
    assert view.style == "rings"


def test_focus_walks_out_from_sol_and_back_to_none():
    view, _, plotter, _ = make_viewer()
    assert view.focus is None
    plotter.keys["bracketright"]()
    assert view.focus == 0 and "focus: Sol" in plotter.texts["clock"][0]
    plotter.keys["bracketright"]()
    assert view.focus == 1 and "focus: A" in plotter.texts["clock"][0]
    plotter.keys["bracketright"]()
    plotter.keys["bracketright"]()
    assert view.focus is None and "focus" not in plotter.texts["clock"][0]
    plotter.keys["bracketleft"]()
    assert view.focus == 2  # previous from none wraps to the farthest star
    plotter.keys["bracketleft"]()
    assert view.focus == 1
    plotter.keys["backslash"]()
    assert view.focus is None


def test_focus_draws_a_bold_ring_and_the_crossings_with_every_other_shell():
    view, _, plotter, clock = make_viewer()  # Sol, A at 3 ly, B at 7 ly
    mesh, _, _ = ring_mesh(plotter)
    focus_ring = line_actor(plotter, viewer.FOCUS_RING_COLOR)
    crossings = line_actor(plotter, viewer.INTERSECTION_COLOR)
    view.toggle()
    view.on_tick(1)
    clock.now += 4.0
    view.on_tick(2)  # r = 4: Sol's shell overlaps A's (3 apart) and B's (7 apart)
    assert focus_ring.visibility is False and crossings.visibility is False
    plotter.keys["bracketright"]()
    view.on_tick(3)
    assert focus_ring.visibility is True and crossings.visibility is True
    assert focus_ring.prop.line_width == viewer.FOCUS_LINE_WIDTH
    assert int(mesh["rgba"][0, 3]) == 0  # Sol's ordinary ring gives way to the bold one
    assert int(mesh["rgba"][viewer.RING_SEGMENTS, 3]) == round(
        255 * viewer.ring_alpha(4.0) * viewer.UNFOCUSED_RING_ALPHA
    )
    circles = view._crossings.points.reshape(2, viewer.INTERSECTION_SEGMENTS, 3)
    # with A: centres 3 apart, both radius 4 → circle of radius sqrt(16 - 2.25) about (1.5, 0, 0), in the plane x = 1.5
    assert np.linalg.norm(circles[0] - [1.5, 0.0, 0.0], axis=1) == pytest.approx(
        np.full(viewer.INTERSECTION_SEGMENTS, math.sqrt(16 - 2.25))
    )
    assert circles[0][:, 0] == pytest.approx(np.full(viewer.INTERSECTION_SEGMENTS, 1.5))
    # with B: 7 apart → radius sqrt(16 - 12.25) about (3.5, 0, 0)
    assert np.linalg.norm(circles[1] - [3.5, 0.0, 0.0], axis=1) == pytest.approx(
        np.full(viewer.INTERSECTION_SEGMENTS, math.sqrt(16 - 12.25))
    )
    plotter.keys["backslash"]()
    view.on_tick(4)
    assert focus_ring.visibility is False and crossings.visibility is False
    assert int(mesh["rgba"][0, 3]) == round(255 * viewer.ring_alpha(4.0))


def test_the_off_style_hides_the_focus_visuals_too():
    view, _, plotter, clock = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 4.0
    view.on_tick(2)
    plotter.keys["bracketright"]()
    for _ in range(3):
        plotter.keys["m"]()
    assert view.style == "off"
    view.on_tick(3)
    assert line_actor(plotter, viewer.FOCUS_RING_COLOR).visibility is False
    assert line_actor(plotter, viewer.INTERSECTION_COLOR).visibility is False
