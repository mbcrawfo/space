"""The 3D scene: stars as points, labels, one growing translucent shell per star.

Everything here talks to a *plotter* — normally a `pyvista.Plotter`, in tests a fake that
records calls — so the scene logic can be exercised without a window. `run()` is the one
place the real plotter is created and shown.

The mechanics, verified against pyvista 0.48 / VTK 9.6: shells are unit spheres whose
actors are scaled every frame (far cheaper than rewriting points); star colours live in a
uint8 "rgb" point array that is mutated in place; text overlays are re-added under the
same name, which replaces the previous actor; and every piece of text carries an explicit
colour, because pyvista's default theme draws text black.

pyvista's `Timer.execute` renders the window itself right after invoking the timer
callback (and it does this every `FRAME_MS`, even while paused), so neither `on_tick` nor
any key handler calls `plotter.render()` — that would be a second full render per frame,
and at this window size and depth-peeling setting a render is tens of milliseconds, so a
second one roughly halves the achievable frame rate. Every text overlay is also added
with `render=False` for the same reason: `add_text`'s default is to render immediately,
and text changes only need to appear by the next timer-driven render, not sooner.
"""

import sys
import time
from collections.abc import Callable, Sequence

import numpy as np
import pyvista as pv

from .catalog import Star
from .simulation import Arrival, Simulation

FRAME_MS = 33  # ~30 frames per second
HIGHLIGHT_SECONDS = 1.0  # wall-clock time a reached star stays lit
LOG_LINES = 8

SOL_COLOR = (255, 220, 80)
STAR_COLOR = (235, 235, 235)
HIGHLIGHT_COLOR = (255, 80, 60)
SHELL_OPACITY = 0.07
SHELL_PALETTE = ("#4fc3f7", "#ce93d8", "#80cbc4", "#fff176", "#ffab91", "#a5d6a7", "#90caf9", "#f48fb1")
TEXT_COLOR = "white"
CAMERA_DISTANCE_LY = 55.0

HELP_TEXT = (
    "space  start / pause\n"
    "+ / -  faster / slower\n"
    "r      reset t = 0 and refit the camera\n"
    "drag   orbit    scroll  zoom    middle-drag  pan\n"
    "q      quit"
)


def format_speed(years_per_second: float) -> str:
    """'1 yr/s', '0.5 yr/s', '0.0156 yr/s' — as many decimals as the value needs, no more."""
    text = f"{years_per_second:.4f}".rstrip("0").rstrip(".")
    return f"{text} yr/s"


def format_arrival(sim: Simulation, arrival: Arrival) -> str:
    source = sim.stars[arrival.source].name
    target = sim.stars[arrival.target].name
    return f"y {arrival.time_yr:6.1f}  light from {source} reaches {target}"


class Viewer:
    def __init__(self, sim: Simulation, plotter, *, clock: Callable[[], float] = time.perf_counter, out=None):
        self.sim = sim
        self.plotter = plotter
        self.clock = clock
        self.out = sys.stdout if out is None else out
        self.shells: list = []
        self.log_lines: list[str] = []
        self._points: pv.PolyData | None = None
        self._base_colors: np.ndarray | None = None
        self._lit_until: np.ndarray = np.zeros(len(sim.stars))  # wall time each highlight expires; 0 = unlit
        self._last_tick: float | None = None

    # -- building the scene -------------------------------------------------

    def build(self) -> None:
        self.plotter.set_background("black")
        self.plotter.enable_depth_peeling()
        self._add_shells()
        self._add_stars()
        self._add_labels()
        self.plotter.add_text(
            HELP_TEXT, position="lower_right", font_size=9, color=TEXT_COLOR, shadow=True, name="help", render=False
        )
        self._refresh_clock()
        self._refresh_log()
        self.plotter.add_key_event("space", self.toggle)
        self.plotter.add_key_event("plus", self.faster)
        self.plotter.add_key_event("equal", self.faster)
        self.plotter.add_key_event("minus", self.slower)
        self.plotter.add_key_event("r", self.reset)
        self.plotter.add_timer_event(max_steps=sys.maxsize, duration=FRAME_MS, callback=self.on_tick)
        eye = np.array([0.55, -0.65, 0.5])
        eye = tuple(eye / np.linalg.norm(eye) * CAMERA_DISTANCE_LY)
        self.plotter.camera_position = [eye, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)]

    def _add_shells(self) -> None:
        unit = pv.Sphere(radius=1.0)
        for index, position in enumerate(self.sim.positions):
            color = SHELL_PALETTE[index % len(SHELL_PALETTE)]
            actor = self.plotter.add_mesh(unit.copy(), color=color, opacity=SHELL_OPACITY, smooth_shading=True)
            actor.position = tuple(float(v) for v in position)
            actor.visibility = False
            self.shells.append(actor)

    def _add_stars(self) -> None:
        colors = np.tile(np.array(STAR_COLOR, dtype=np.uint8), (len(self.sim.stars), 1))
        for index, star in enumerate(self.sim.stars):
            if star.distance_ly == 0.0:
                colors[index] = SOL_COLOR
        self._base_colors = colors.copy()
        self._points = pv.PolyData(self.sim.positions.copy())
        self._points["rgb"] = colors
        self.plotter.add_mesh(self._points, scalars="rgb", rgb=True, render_points_as_spheres=True, point_size=12)

    def _add_labels(self) -> None:
        self.plotter.add_point_labels(
            self.sim.positions.copy(),
            [star.label for star in self.sim.stars],
            shape=None,
            show_points=False,
            always_visible=True,
            text_color=TEXT_COLOR,
            font_size=10,
        )

    # -- overlays -------------------------------------------------------------

    def _refresh_clock(self) -> None:
        state = "" if self.sim.running else "   [paused — press space]"
        text = f"t = {self.sim.time_yr:,.1f} yr   {format_speed(self.sim.years_per_second)}{state}"
        self.plotter.add_text(
            text, position="upper_left", font_size=12, color=TEXT_COLOR, shadow=True, name="clock", render=False
        )

    def _refresh_log(self) -> None:
        self.plotter.add_text(
            "\n".join(self.log_lines),
            position="lower_left",
            font_size=9,
            color=TEXT_COLOR,
            shadow=True,
            name="log",
            render=False,
        )

    def _log(self, line: str) -> None:
        # Append-only: on_tick refreshes the "log" text actor once per tick, not once per
        # arrival, so a burst of dozens of arrivals in one frame does not force dozens of
        # renders.
        self.log_lines.append(line)
        del self.log_lines[:-LOG_LINES]

    # -- key handlers ---------------------------------------------------------

    def toggle(self) -> None:
        self.sim.toggle()
        self._refresh_clock()

    def faster(self) -> None:
        self.sim.faster()
        self._refresh_clock()

    def slower(self) -> None:
        self.sim.slower()
        self._refresh_clock()

    def reset(self) -> None:
        self.sim.reset()
        self.log_lines.clear()
        self._lit_until[:] = 0.0
        self._apply_colors()
        self._apply_radius()
        self._refresh_log()
        self._refresh_clock()

    # -- the frame ------------------------------------------------------------

    def on_tick(self, step: int) -> None:  # noqa: ARG002 - signature fixed by pyvista's timer callback
        now = self.clock()
        # the first frame measures from itself, not from build()
        dt = 0.0 if self._last_tick is None else max(0.0, now - self._last_tick)
        self._last_tick = now

        arrivals = self.sim.advance(dt)
        for arrival in arrivals:
            self._lit_until[arrival.target] = now + HIGHLIGHT_SECONDS
            line = format_arrival(self.sim, arrival)
            self._log(line)
            print(line, file=self.out)
        if arrivals:
            self._refresh_log()
        if arrivals or (self._lit_until > 0.0).any():
            self._apply_colors(now)
        if self.sim.running:
            self._apply_radius()
            self._refresh_clock()
        # No self.plotter.render() here: pyvista's Timer.execute renders the window right
        # after this callback returns (every FRAME_MS, even while paused), so rendering
        # again here would be a second full render per frame.

    def _apply_colors(self, now: float | None = None) -> None:
        if self._points is None or self._base_colors is None:
            raise RuntimeError("Viewer.build() must run before colours can change.")
        now = self.clock() if now is None else now
        expired = (self._lit_until > 0.0) & (self._lit_until <= now)
        self._lit_until[expired] = 0.0
        lit = self._lit_until > 0.0
        colors = self._base_colors.copy()
        colors[lit] = HIGHLIGHT_COLOR
        self._points["rgb"][:] = colors

    def _apply_radius(self) -> None:
        radius = self.sim.radius()
        for actor in self.shells:
            actor.visibility = radius > 0.0
            actor.scale = (radius, radius, radius)


def run(stars: Sequence[Star], *, years_per_second: float, autostart: bool) -> None:
    """Open the window and block until it is closed."""
    sim = Simulation(stars, years_per_second=years_per_second)
    if autostart:
        sim.start()
    plotter = pv.Plotter(window_size=(1280, 860))
    Viewer(sim, plotter).build()
    plotter.show(title="lightspeed")
