# lightspeed — design

**Date:** 2026-08-21
**Status:** approved, not yet implemented

## What it is

`lightspeed` is a 3D desktop visualization of light spreading out between the nearest
stars. It opens a window centred on Sol with roughly a hundred stellar systems out to
20 light-years placed at their true relative positions, each labelled with its name and
its distance from Earth. When the user starts the simulation, every star emits one
flash at the same instant, and each flash grows as a translucent sphere at one
light-year per simulated year. The user orbits, pans, and zooms the camera freely while
the shells cross one another and sweep over other stars; a star flashes when a shell
reaches it, and an on-screen log records the arrival.

It is pure Python on the desktop — a VTK window driven through PyVista — not a web page.

```
$ python -m lightspeed --speed 2
(a window opens; press space to start)
y    4.2  light from Proxima Centauri reaches Alpha Centauri
y    4.2  light from Alpha Centauri reaches Proxima Centauri
y    4.2  light from Sol reaches Proxima Centauri
y    4.2  light from Proxima Centauri reaches Sol
y    4.4  light from Sol reaches Alpha Centauri
...
```

Decisions made during brainstorming, in one place:

| Question | Decision |
| --- | --- |
| 3D stack | PyVista (VTK): orbit camera, 3D labels, translucent meshes, timer and key callbacks are all built in |
| Light model | One flash per star at t = 0; shells grow at 1 ly/yr of simulated time; sim clock on screen; speed adjustable with keys |
| Star data | Bundled catalogue in the package; no network at runtime |
| Arrival | Highlight plus arrival log: the reached star flashes, a line is shown on screen and printed to stdout |
| Scope | About 100 systems within 20 ly, one entry per system |

## Physics

The only physics is geometry. Light travels one light-year per year, so at simulated
time `t` years the wavefront from a star at position **p** is the sphere of radius `t`
centred on **p**, and it reaches another star at **q** at `t = |p − q|`. Every star
emits at `t = 0`, so all shells share one radius and the arrival schedule is the sorted
list of pairwise distances.

Positions come from equatorial ICRS coordinates and a distance:

```
x = d · cos(dec) · cos(ra)        x toward the vernal equinox
y = d · cos(dec) · sin(ra)
z = d · sin(dec)                  z toward the north celestial pole
```

with `d` in light-years (from parallax: `d_ly = 3.26156378 × 1000 / plx_mas`). One scene
unit is one light-year — the scaling the eye sees is the camera distance, not a
distortion, so relative positions stay accurate. Sol is the origin.

## Structure

```
lightspeed/
├── __init__.py        docstring only
├── __main__.py        CLI: build_parser(), _HelpOnErrorParser, main()
├── pyproject.toml     dependencies = ["numpy>=1.26", "pyvista>=0.44"]
├── README.md
├── conftest.py        autouse session guard: pyvista.Plotter.show explodes
├── stars.json         bundled catalogue, ~100 systems ≤ 20 ly, sorted by distance
├── catalog.py         Star, load(), within(), Cartesian conversion, labels
├── simulation.py      pure state: clock, speed, shell radius, arrival events
├── viewer.py          the PyVista scene: actors, text, timer, keys
└── tests/
```

### `stars.json`

A JSON array sorted by ascending distance. Each entry:

```json
{"name": "Proxima Centauri", "ra_deg": 217.42894, "dec_deg": -62.67949, "distance_ly": 4.2465, "source": "SIMBAD (Gaia DR3), 2026-08-21"}
```

- Sol is not in the file; `catalog.load()` prepends it at the origin.
- One entry per system: Alpha Centauri A+B is "Alpha Centauri", Proxima is its own
  entry (it is 0.2 ly from the pair), Sirius A+B is "Sirius", and so on, so binaries
  do not emit two coincident shells.
- Built once, at implementation time, by a throwaway script that queries SIMBAD's TAP
  service (`basic.ra`, `basic.dec`, `basic.plx_value` by identifier) for a curated list
  of display names, converts parallax to light-years, keeps entries within 20 ly, and
  writes the file. The script is not shipped; provenance lives in each entry's `source`
  and in the README.

### `catalog.py`

```python
@dataclass(frozen=True)
class Star:
    name: str
    ra_deg: float
    dec_deg: float
    distance_ly: float
    source: str

    @property
    def position(self) -> tuple[float, float, float]   # Cartesian, light-years
    @property
    def label(self) -> str                              # "Proxima Centauri (4.2 ly)"; Sol → "Sol (0 ly)"

class CatalogError(Exception): ...                      # missing/unreadable/invalid stars.json

SOL = Star("Sol", 0.0, 0.0, 0.0, "origin")
def load(path: str | None = None) -> list[Star]        # [SOL, *entries]; validates every field
def within(stars: list[Star], max_ly: float) -> list[Star]
```

`load()` raises `CatalogError` for a missing file, bad JSON, a non-list, an entry that
lacks a field or has one of the wrong type, RA outside `[0, 360)`, Dec outside
`[-90, 90]`, or a non-positive/non-finite distance. The message names the entry.

### `simulation.py`

Pure state over numpy; no VTK.

```python
@dataclass(frozen=True)
class Arrival:
    time_yr: float
    source: int        # index into the star list
    target: int

class Simulation:
    def __init__(self, stars: Sequence[Star], *, years_per_second: float = 1.0)
    stars: list[Star]
    positions: np.ndarray          # (n, 3)
    time_yr: float                 # 0.0 until started
    running: bool
    years_per_second: float

    def start() / pause() / toggle() / reset()
    def faster() / slower()        # ×2 / ÷2, clamped to [MIN_SPEED, MAX_SPEED] = [1/64, 4096]
    def advance(self, wall_dt_s: float) -> list[Arrival]
    def radius(self) -> float      # == time_yr
```

`advance()` does nothing and returns `[]` while paused. When running it adds
`wall_dt_s × years_per_second` to the clock and returns, in time order, every precomputed
`Arrival` whose `time_yr` lies in `(previous, now]`. Arrivals are precomputed in
`__init__` as all ordered pairs `i ≠ j` with `time_yr = |p_i − p_j|`, sorted; a cursor
walks them and `reset()` rewinds it. A negative or non-finite `wall_dt_s` raises
`ValueError`.

### `viewer.py`

```python
class Viewer:
    def __init__(self, sim: Simulation, plotter, *, clock: Callable[[], float] = time.perf_counter)
    def build(self) -> None
    def on_tick(self, step: int) -> None
    def toggle(self) / faster(self) / slower(self) / reset(self)

def run(stars: Sequence[Star], *, years_per_second: float, autostart: bool) -> None
```

The plotter is injected so tests can pass a recording fake; `run()` creates the real
`pyvista.Plotter`, builds, and calls `show()`. `build()` adds:

- **Stars** — one `pyvista.PolyData` of all positions with a uint8 `"rgb"` point array,
  added with `add_mesh(scalars="rgb", rgb=True, render_points_as_spheres=True)`. Sol is
  yellow, the rest white. A highlight sets that star's row to an accent colour and
  notes the wall time; rows revert after `HIGHLIGHT_SECONDS = 1.0` of wall time.
  Mutating the array in place followed by `plotter.render()` is sufficient (verified
  against pyvista 0.48 / VTK 9.6).
- **Labels** — `add_point_labels(positions, labels, shape=None, show_points=False,
  always_visible=True, text_color="white", font_size=10)`.
- **Shells** — one unit `pyvista.Sphere(radius=1.0)` per star via `add_mesh(opacity=0.12,
  color=<palette[i % len(palette)]>)`; the returned actor gets `position = star position`,
  `scale = (r, r, r)` every tick, and `visibility = r > 0`. Depth peeling is enabled so
  overlapping translucent shells composite correctly. Background black.
- **Text** — `add_text(..., name="clock", position="upper_left", color="white")`
  showing `t = 12.3 yr   2 yr/s   [paused]`; `name="log"` lower-left with the last eight
  arrival lines; `name="help"` lower-right with the key legend. Re-adding with the same
  name replaces the actor. pyvista's default theme draws text black, so every text call
  passes an explicit colour.
- **Timer** — `add_timer_event(max_steps=sys.maxsize, duration=33, callback=self.on_tick)`.
  `on_tick` measures wall `dt` with the injected clock, calls `sim.advance(dt)`, applies
  arrivals (highlight, log line, `print` to stdout), rescales shells, refreshes the clock
  and log text when they changed, expires stale highlights, and calls `plotter.render()`.
- **Keys** — `space` toggle, `plus`/`equal` faster, `minus` slower, `r` reset. Camera
  interaction is VTK's default trackball (left-drag orbit, scroll zoom, middle-drag pan;
  `q` closes). The initial camera looks at the origin from about 45 ly away along an
  oblique direction.

`viewer.py` imports `pyvista` at module top; `__main__.py` imports `viewer` inside
`main()` after validating arguments, so `--help` and bad command lines never pay the
VTK import.

### `__main__.py`

```
python -m lightspeed [--speed YEARS_PER_SECOND] [--within LY] [--autostart]
```

- `--speed` (default 1.0): simulated years per real second; positive and finite.
- `--within` (default 20.0): only systems closer than this; positive and finite.
- `--autostart`: start emitting immediately instead of waiting for space.

Exit codes: `0` the window was closed; `1` no stars within `--within`, or the bundled
catalogue is unreadable; `2` invalid `--speed`/`--within`, or a command line argparse
rejected. Value errors print what was wrong and a one-line hint, nothing else.

## What the model ignores

Proper motion (positions are today's, frozen); the light-travel time already baked
into those positions; relativistic effects; stellar radii, colours, and magnitudes;
and anything that would make light do something other than spread at 1 ly/yr.

## Testing

- `catalog`: Cartesian conversion at the axes, `|position| == distance`, `load()`
  prepends Sol and rejects each malformed shape with a `CatalogError` naming the entry,
  `within()`; an integrity test over the shipped JSON (fields, ranges, uniqueness,
  ordering, ≤ 20 ly, ~100 rows) and anchor values for Proxima, Sirius, Tau Ceti.
- `simulation`: arrival times equal pairwise distances and are sorted; `advance` emits
  exactly the arrivals in `(prev, now]`; nothing while paused; speed clamps; reset.
- `viewer`: a `FakePlotter`/`FakeActor` pair records every call; tests check actor
  counts, scaling, visibility, highlight and decay, log text, key handlers, timer
  registration — no VTK window. `conftest.py` makes `pyvista.Plotter.show` raise for
  the session so an accidental window fails loudly, the same shape as `starlight`'s
  network guard.
- `__main__`: help text, argparse errors print the full help once to stderr and exit 2,
  value errors stay concise and exit 2, empty selection exits 1, `viewer.run` is
  monkeypatched so `main()` is exercised end to end.

## Repo integration

- First tool in the repo with third-party runtime dependencies. Because `uv sync`
  only installs the workspace root's dependencies, a member's dependencies need
  `uv sync --all-packages`; CI, `CLAUDE.md`, and the READMEs change to say so.
- Root `pyproject.toml`: `members = ["lightspeed", "spacetime", "starlight"]`.
- Root `README.md` tools table gets a row.
- `uv.lock` grows by vtk, numpy, pyvista and their dependencies.

## Deliberately not built

Repeating pulses; nonlinear distance scaling; star colours and magnitudes; proper
motion; runtime SIMBAD refresh; screenshot or video export flags.
