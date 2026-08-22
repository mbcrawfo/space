# lightspeed

Light is slow on the scale of the stars. `lightspeed` opens a 3D window centred on Sol with
nearly ninety stellar systems out to 20 light-years, each at its true position relative
to Earth and labelled with its name and distance, and on your command lets every one of
them flash at once — then shows each flash growing as a ring of light at one
light-year per simulated year while you orbit the camera and watch the shells cross one
another and wash over other stars.

```
$ python -m lightspeed --within 5 --speed 2
(a window opens; press space, and the log in its lower-left corner fills in:)
  0.2 yr  Proxima Centauri ↔ Alpha Centauri
  4.2 yr  Sol ↔ Proxima Centauri
  4.4 yr  Sol ↔ Alpha Centauri
```

## Usage

```
python -m lightspeed [--speed YEARS_PER_SECOND] [--within LY] [--autostart]
```

- `--speed YEARS_PER_SECOND` — simulated years per real second once running; shells grow
  this many light-years per second (default: `1.0`).
- `--within LY` — show only systems no farther than this from Sol (default: `20.0`, which
  is everything bundled).
- `--autostart` — start the moment the window opens instead of waiting for space.

In the window:

| Key | Effect |
| --- | --- |
| `space` | start / pause |
| `+` / `-` | double / halve the speed |
| `m` | cycle the shell style: rings (default) → rings + fill → fill → off |
| `]` / `[` | focus the next / previous star, walking out from Sol; `\` clears the focus |
| `r` | reset to t = 0 and refit the camera |
| `q` | quit |
| drag / scroll / middle-drag | orbit / zoom / pan (VTK's trackball camera) |

The upper-left corner shows the simulated clock and speed, the lower-left the most recent
arrivals — newest first, as many as fit in the bottom third of the window — and the
upper-right the key legend. Star labels grow as the camera gets closer to
their star and shrink as it pulls away, so the stars you are looking at read first. VTK's
other default key bindings also remain active — `w` switches to wireframe, `s` back to
surface, `f` flies the camera to the point under the cursor, and so on.

## How it works

Every star is placed from its ICRS right ascension, declination, and distance:

```
x = d · cos(dec) · cos(ra)        x toward the vernal equinox
y = d · cos(dec) · sin(ra)
z = d · sin(dec)                  z toward the north celestial pole
```

with `d` in light-years, so one scene unit is one light-year and Sol is the origin. The
"scaling down" is entirely the camera — relative positions are exact.

At simulated time `t` the flash from a star at **p** is the sphere of radius `t` about
**p**, because light covers one light-year per year. It reaches a star at **q** when
`t = |p − q|`, so the arrival schedule is the sorted list of pairwise separations,
computed once. Each frame the viewer advances the clock by the real time elapsed times
`--speed`, resizes every front to the new radius, lights up any star a front has just
reached, and appends the arrival to the log.

Each front is drawn by default as a ring — the silhouette of its sphere, always turned to
face the camera — because dozens of filled translucent spheres wash each other out within
a few years of overlapping. Rings fade as they grow and crowd; `m` switches to filled
shells (or both, or none) if you prefer. Focusing a star with `]` / `[` draws its ring bold
and, in yellow, the circles where its front is crossing every other front — two equal
spheres whose centres are `d` apart and whose radius is `r` meet in a circle of radius
`√(r² − d²/4)` in the plane halfway between them — so the interactions are drawn, not
left to the eye. A frame is drawn on a timer and before every
render — including the renders the camera makes while you drag, so the shells keep growing
as you orbit — and a single frame never advances the clock by more than a quarter of a
second of real time, so a stall (a hidden window, a mouse held still) pauses the simulation
rather than making it leap.

## Exit codes

| Code | Meaning                                                                    |
| ---- | -------------------------------------------------------------------------- |
| 0    | The window was closed                                                      |
| 1    | No star within `--within`, or the bundled catalogue is unreadable or empty |
| 2    | Invalid `--speed` or `--within`, or a rejected command line                |

## What the model ignores

Proper motion — the stars sit where they are catalogued today and do not move over the
simulated centuries; the fact that those catalogued positions are themselves where the
stars *were* when their light left; relativity of any kind; stellar radii, colours, and
brightness (every star is a dot, Sol's is yellow); and the shells are drawn as ideal
spheres with no dimming, so a shell never fades no matter how far it has spread.

## Where the data comes from

`stars.json` holds one entry per stellar *system* (Alpha Centauri A+B is one entry,
Proxima is another) out to 20 ly: a display name, ICRS coordinates in degrees, the
distance in light-years, and a `source` naming the parallax's SIMBAD bibcode and the
query date. It was built once from SIMBAD's TAP service and is not refreshed at runtime;
the tool never touches the network.

## Running it

`lightspeed` is a tool in the [space](../) monorepo, which uses `uv`. It is the first tool
here with third-party dependencies — [PyVista](https://pyvista.org) (and with it VTK and
numpy) — so install with `--all-packages`, which pulls a ~100 MB VTK wheel on the first
run:

```
uv sync --all-packages
uv run python -m lightspeed
```

It needs a display: a desktop session on macOS, Windows, or Linux. It is a package, not a
loose script, so run it with `-m` from the repo root.

## Tests

From the repo root:

```
uv sync --all-packages
uv run pytest lightspeed
```

Tests never open a window — the viewer is driven through a recording fake plotter, and
`conftest.py` installs an autouse fixture that makes `pyvista.Plotter.show` fail loudly.
