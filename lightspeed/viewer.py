"""The 3D scene: stars as points, labels, and one growing light front per star.

Everything here talks to a *plotter* — normally a `pyvista.Plotter`, in tests a fake that
records calls — so the scene logic can be exercised without a window. `run()` is the one
place the real plotter is created and shown.

Each star's front can be drawn as a camera-facing ring (the default — dozens of filled
translucent spheres wash out once they overlap), as a filled translucent sphere, or both;
`m` cycles the styles. `]` / `[` focus one star at a time, walking outward from Sol: its
ring is drawn bold and the circles where its front crosses every other front are drawn,
which is where the "interaction" actually is.

The mechanics, verified against pyvista 0.48 / VTK 9.6: filled shells are unit spheres whose
actors are scaled every frame (far cheaper than rewriting points); rings, the focus ring and
the crossing circles are three PolyDatas of fixed topology whose points are rewritten each
frame; per-ring brightness is a uint8 RGBA point array (`rgb=True` accepts four channels);
star colours live in a
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

import os
import sys
import time
from collections.abc import Callable, Sequence

import matplotlib
import numpy as np
import pyvista as pv

from . import geometry
from .catalog import Star
from .simulation import Arrival, Simulation

FRAME_MS = 33  # ~30 frames per second
HIGHLIGHT_SECONDS = 1.0  # wall-clock time a reached star stays lit
MAX_FRAME_SECONDS = 0.25  # a longer gap between frames pauses the clock rather than jumping it
LOG_HEIGHT_FRACTION = 0.30  # the share of the window's height the arrival log may fill

SOL_COLOR = (255, 220, 80)
STAR_COLOR = (235, 235, 235)
HIGHLIGHT_COLOR = (255, 80, 60)
SHELL_OPACITY = 0.07  # a filled shell on its own
FILL_OPACITY_WITH_RINGS = 0.03  # a filled shell behind its ring
SHELL_PALETTE = ("#4fc3f7", "#ce93d8", "#80cbc4", "#fff176", "#ffab91", "#a5d6a7", "#90caf9", "#f48fb1")
SHELL_STYLES = ("rings", "rings + fill", "fill", "off")
RING_SEGMENTS = 96
RING_LINE_WIDTH = 1.5
RING_MAX_ALPHA = 0.9
RING_MIN_ALPHA = 0.25
UNFOCUSED_RING_ALPHA = 0.35  # how much the other rings dim while one star is focused
FOCUS_RING_COLOR = "white"
FOCUS_LINE_WIDTH = 3.5
INTERSECTION_COLOR = "#ffd54f"
INTERSECTION_SEGMENTS = 64
INTERSECTION_OPACITY = 0.8
TEXT_COLOR = "white"
# VTK's embedded fonts stop at Latin-1, so the log's "↔" needs a fuller face. matplotlib — a
# pyvista dependency, so always installed — ships DejaVu Sans; the overlays use it. If it is
# ever missing, VTK's own font is used and the arrow renders as a blank.
_DEJAVU = os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
OVERLAY_FONT_FILE = _DEJAVU if os.path.exists(_DEJAVU) else None
CLOCK_FONT_SIZE = 24
OVERLAY_FONT_SIZE = 18  # the arrival log and the key legend
# pyvista's corner text in DejaVu Sans renders at about 2.27 px of line pitch per unit of font
# size (measured offscreen at 12, 18 and 24); the pitch does not change with the window's height.
LOG_LINE_PX = round(OVERLAY_FONT_SIZE * 2.27)
LABEL_FONT_SIZE = 15  # a star label's size when it is CAMERA_DISTANCE_LY from the camera
LABEL_MIN_FONT_SIZE = 8
LABEL_MAX_FONT_SIZE = 48
CAMERA_DISTANCE_LY = 55.0

HELP_TEXT = (
    "space  start / pause\n"
    "+ / -  faster / slower\n"
    "m      shell style: rings / rings + fill / fill / off\n"
    "] / [  focus next / previous star, out from Sol    \\  clear focus\n"
    "r      reset t = 0 and refit the camera\n"
    "drag   orbit    scroll  zoom    middle-drag  pan\n"
    "q      quit"
)


def format_speed(years_per_second: float) -> str:
    """'1 yr/s', '0.5 yr/s', '0.0156 yr/s' — as many decimals as the value needs, no more."""
    text = f"{years_per_second:.4f}".rstrip("0").rstrip(".")
    return f"{text} yr/s"


def ring_alpha(radius: float) -> float:
    """Rings fade as the fronts grow and crowd: full at 1 ly, a quarter by ~13 ly."""
    return float(np.clip(RING_MAX_ALPHA / np.sqrt(max(radius, 1.0)), RING_MIN_ALPHA, RING_MAX_ALPHA))


def format_arrival(sim: Simulation, arrival: Arrival) -> str:
    return f"{arrival.time_yr:5.1f} yr  {sim.stars[arrival.a].name} ↔ {sim.stars[arrival.b].name}"


class Viewer:
    def __init__(
        self,
        sim: Simulation,
        plotter,
        *,
        clock: Callable[[], float] = time.perf_counter,
        max_frame_seconds: float = MAX_FRAME_SECONDS,
    ):
        self.sim = sim
        self.plotter = plotter
        self.clock = clock
        self.max_frame_seconds = max_frame_seconds
        self.shells: list = []
        self.labels: list = []
        self.log_lines: list[str] = []
        self.style_index = 0
        self.focus: int | None = None
        self._rings: pv.PolyData | None = None
        self._ring_actor = None
        self._ring_base_rgba: np.ndarray | None = None
        self._focus_ring: pv.PolyData | None = None
        self._focus_actor = None
        self._crossings: pv.PolyData | None = None
        self._crossing_actor = None
        self._points: pv.PolyData | None = None
        self._base_colors: np.ndarray | None = None
        self._lit_until: np.ndarray = np.zeros(len(sim.stars))  # wall time each highlight expires; 0 = unlit
        self._last_tick: float | None = None
        self._stopped = False

    # -- building the scene -------------------------------------------------

    def build(self) -> None:
        self.plotter.set_background("black")
        self.plotter.enable_depth_peeling()
        self._add_shells()
        self._add_rings()
        self._add_stars()
        self._add_labels()
        self.plotter.add_text(
            HELP_TEXT,
            position="upper_right",  # the log owns the bottom edge; at this size the two would collide
            font_size=OVERLAY_FONT_SIZE,
            color=TEXT_COLOR,
            shadow=True,
            font_file=OVERLAY_FONT_FILE,
            name="help",
            render=False,
        )
        self._refresh_clock()
        self._refresh_log()
        self.plotter.add_key_event("space", self.toggle)
        self.plotter.add_key_event("plus", self.faster)
        self.plotter.add_key_event("equal", self.faster)
        self.plotter.add_key_event("minus", self.slower)
        self.plotter.add_key_event("r", self.reset)
        self.plotter.add_key_event("m", self.cycle_style)
        self.plotter.add_key_event("bracketright", self.focus_next)
        self.plotter.add_key_event("bracketleft", self.focus_previous)
        self.plotter.add_key_event("backslash", self.clear_focus)
        self.plotter.add_timer_event(max_steps=sys.maxsize, duration=FRAME_MS, callback=self.on_tick)
        # On macOS, VTK's timers do not fire while a mouse button is held, but the trackball camera
        # renders on every mouse move; advancing the frame at the start of every render keeps the
        # shells growing while the user orbits, instead of freezing and then leaping on release.
        self.plotter.render_window.AddObserver("StartEvent", self.on_render)
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

    def _add_rings(self) -> None:
        n = len(self.sim.stars)
        # Every star's ring in one line mesh; per-point RGBA carries each ring's colour and fade.
        self._rings = pv.PolyData(np.zeros((n * RING_SEGMENTS, 3)), lines=geometry.polyline_cells(n, RING_SEGMENTS))
        palette = np.array([pv.Color(c).int_rgb for c in SHELL_PALETTE], dtype=np.uint8)
        rgb = palette[np.arange(n) % len(palette)]
        self._ring_base_rgba = np.hstack([rgb, np.full((n, 1), 255, dtype=np.uint8)])
        self._rings["rgba"] = np.repeat(self._ring_base_rgba, RING_SEGMENTS, axis=0)
        self._ring_actor = self.plotter.add_mesh(self._rings, scalars="rgba", rgb=True, line_width=RING_LINE_WIDTH)
        self._ring_actor.visibility = False
        # The focused star's ring, drawn bold on its own; and the circles where its front
        # crosses every other front — one per other star, radius zero (invisible) until they meet.
        self._focus_ring = pv.PolyData(np.zeros((RING_SEGMENTS, 3)), lines=geometry.polyline_cells(1, RING_SEGMENTS))
        self._focus_actor = self.plotter.add_mesh(self._focus_ring, color=FOCUS_RING_COLOR, line_width=FOCUS_LINE_WIDTH)
        self._focus_actor.visibility = False
        if n > 1:
            self._crossings = pv.PolyData(
                np.zeros(((n - 1) * INTERSECTION_SEGMENTS, 3)),
                lines=geometry.polyline_cells(n - 1, INTERSECTION_SEGMENTS),
            )
            self._crossing_actor = self.plotter.add_mesh(
                self._crossings, color=INTERSECTION_COLOR, line_width=RING_LINE_WIDTH, opacity=INTERSECTION_OPACITY
            )
            self._crossing_actor.visibility = False

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
        # One screen-space label per star, anchored at the star, so each can take its own font
        # size: `_apply_label_sizes` grows a label as the camera approaches its star.
        for index, star in enumerate(self.sim.stars):
            label = pv.Label(star.label, position=star.position, size=LABEL_FONT_SIZE)
            label.prop.color = TEXT_COLOR
            self.plotter.add_actor(label, name=f"label-{index}", render=False)
            self.labels.append(label)
        self._apply_label_sizes()

    def _apply_label_sizes(self) -> None:
        """Size each label by its star's distance to the camera: base size at the default camera distance."""
        distances = np.linalg.norm(self.sim.positions - np.asarray(self.plotter.camera.position, dtype=float), axis=1)
        sizes = np.clip(
            LABEL_FONT_SIZE * CAMERA_DISTANCE_LY / np.maximum(distances, 1e-9), LABEL_MIN_FONT_SIZE, LABEL_MAX_FONT_SIZE
        )
        for label, size in zip(self.labels, sizes.round().astype(int), strict=True):
            if label.size != size:  # changing the size re-rasterises the text; skip when it would be a no-op
                label.size = int(size)

    # -- overlays -------------------------------------------------------------

    def _refresh_clock(self) -> None:
        state = "" if self.sim.running else "   [paused — press space]"
        focus = "" if self.focus is None else f"   focus: {self.sim.stars[self.focus].name}"
        text = f"t = {self.sim.time_yr:,.1f} yr   {format_speed(self.sim.years_per_second)}{focus}{state}"
        self.plotter.add_text(
            text,
            position="upper_left",
            font_size=CLOCK_FONT_SIZE,
            color=TEXT_COLOR,
            shadow=True,
            font_file=OVERLAY_FONT_FILE,
            name="clock",
            render=False,
        )

    def log_capacity(self) -> int:
        """How many log lines fit in the log's share of the window, at its current size — never fewer than one."""
        _width, height = self.plotter.window_size
        return max(1, int(LOG_HEIGHT_FRACTION * height / LOG_LINE_PX))

    def _refresh_log(self) -> None:
        self.plotter.add_text(
            "\n".join(reversed(self.log_lines)),  # newest arrival on top
            position="lower_left",
            font_size=OVERLAY_FONT_SIZE,
            color=TEXT_COLOR,
            shadow=True,
            font_file=OVERLAY_FONT_FILE,
            name="log",
            render=False,
        )

    def _log(self, line: str) -> None:
        # Append-only: on_tick refreshes the "log" text actor once per tick, not once per
        # arrival, so a burst of dozens of arrivals in one frame does not force dozens of
        # renders.
        self.log_lines.append(line)
        del self.log_lines[: -self.log_capacity()]

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
        self._apply_rings()
        self._refresh_log()
        self._refresh_clock()

    @property
    def style(self) -> str:
        return SHELL_STYLES[self.style_index]

    def cycle_style(self) -> None:
        self.style_index = (self.style_index + 1) % len(SHELL_STYLES)
        self._apply_radius()
        self._apply_rings()

    def focus_next(self) -> None:
        """None → Sol → the next star out … → None again; the catalogue is sorted by distance from Sol."""
        last = len(self.sim.stars) - 1
        self.focus = 0 if self.focus is None else (None if self.focus >= last else self.focus + 1)
        self._apply_rings()
        self._refresh_clock()

    def focus_previous(self) -> None:
        last = len(self.sim.stars) - 1
        self.focus = last if self.focus is None else (None if self.focus == 0 else self.focus - 1)
        self._apply_rings()
        self._refresh_clock()

    def clear_focus(self) -> None:
        self.focus = None
        self._apply_rings()
        self._refresh_clock()

    # -- the frame ------------------------------------------------------------

    def stop(self) -> None:
        """Make every later tick a no-op; `run()` calls this the moment the window starts closing."""
        self._stopped = True

    def on_render(self, *_args) -> None:
        """Render-window StartEvent observer: the frame also advances right before any render."""
        self.on_tick(0)

    def on_tick(self, step: int) -> None:  # noqa: ARG002 - signature fixed by pyvista's timer callback
        if self._stopped or self.plotter.render_window is None:
            # VTK still delivers timer events while `q` is closing the window, and pyvista tears
            # the renderer down before the render window goes away; touching either raises from
            # inside the callback. `stop()` is wired to pyvista's before_close_callback, which
            # fires before any of that; the render-window check covers a plotter closed directly.
            return
        now = self.clock()
        # the first frame measures from itself, not from build()
        # A gap longer than the cap — a drag with the mouse held still, a hidden window — means no
        # frames were drawn; the clock pauses for it rather than leaping ahead in one step.
        dt = 0.0 if self._last_tick is None else min(max(0.0, now - self._last_tick), self.max_frame_seconds)
        self._last_tick = now

        arrivals = self.sim.advance(dt)
        for arrival in arrivals:
            self._lit_until[[arrival.a, arrival.b]] = now + HIGHLIGHT_SECONDS  # both stars are reached at once
            self._log(format_arrival(self.sim, arrival))
        if arrivals:
            self._refresh_log()
        if arrivals or (self._lit_until > 0.0).any():
            self._apply_colors(now)
        if self.sim.running:
            self._apply_radius()
            self._refresh_clock()
        self._apply_label_sizes()  # the camera may have moved, running or not
        self._apply_rings()  # likewise: rings face the camera
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
        show_fill = radius > 0.0 and self.style in ("rings + fill", "fill")
        opacity = FILL_OPACITY_WITH_RINGS if self.style == "rings + fill" else SHELL_OPACITY
        for actor in self.shells:
            actor.visibility = show_fill
            actor.scale = (radius, radius, radius)
            if actor.prop.opacity != opacity:
                actor.prop.opacity = opacity

    def _apply_rings(self) -> None:
        """Re-aim every ring at the camera at the current radius, fade them, and draw the focus visuals."""
        if self._rings is None or self._ring_base_rgba is None or self._focus_ring is None:
            raise RuntimeError("Viewer.build() must run before the rings can change.")
        radius = self.sim.radius()
        show_rings = radius > 0.0 and self.style in ("rings", "rings + fill")
        show_focus = self.focus is not None and radius > 0.0 and self.style != "off"
        self._ring_actor.visibility = show_rings
        self._focus_actor.visibility = show_focus
        if self._crossing_actor is not None:
            self._crossing_actor.visibility = show_focus
        if not show_rings and not show_focus:
            return
        camera = np.asarray(self.plotter.camera.position, dtype=float)
        normals = geometry.facing_normals(self.sim.positions, camera)
        radii = np.full(len(self.sim.stars), radius)
        self._rings.points = geometry.circle_points(self.sim.positions, radii, normals, RING_SEGMENTS)
        alpha = np.full(len(self.sim.stars), ring_alpha(radius))
        if self.focus is not None:
            alpha *= UNFOCUSED_RING_ALPHA
            alpha[self.focus] = 0.0  # the bold focus ring stands in for it
        rgba = self._ring_base_rgba.copy()
        rgba[:, 3] = np.round(255 * alpha).astype(np.uint8)
        self._rings["rgba"][:] = np.repeat(rgba, RING_SEGMENTS, axis=0)
        if show_focus:
            focus = self.focus
            self._focus_ring.points = geometry.circle_points(
                self.sim.positions[[focus]], radii[[focus]], normals[[focus]], RING_SEGMENTS
            )
            if self._crossings is not None:
                others = np.delete(self.sim.positions, focus, axis=0)
                centers, circle_radii, circle_normals = geometry.intersection_circles(
                    self.sim.positions[focus], others, radius
                )
                self._crossings.points = geometry.circle_points(
                    centers, circle_radii, circle_normals, INTERSECTION_SEGMENTS
                )


def run(stars: Sequence[Star], *, years_per_second: float, autostart: bool) -> None:
    """Open the window and block until it is closed."""
    sim = Simulation(stars, years_per_second=years_per_second)
    if autostart:
        sim.start()
    plotter = pv.Plotter(window_size=(1280, 860))
    view = Viewer(sim, plotter)
    view.build()
    plotter.show(title="lightspeed", before_close_callback=lambda _plotter: view.stop())
