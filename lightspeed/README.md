# lightspeed

Light is slow on the scale of the stars. `lightspeed` opens a 3D window centred on Sol with
nearly ninety stellar systems out to 20 light-years, each at its true position relative
to Earth and labelled with its name and distance, and on your command lets every one of
them flash at once — then shows each flash growing as a translucent sphere at one
light-year per simulated year while you orbit the camera and watch the shells cross one
another and wash over other stars.

```
$ python -m lightspeed --within 5 --speed 2
(a window opens; press space to start)
y    0.2  light from Proxima Centauri reaches Alpha Centauri
y    0.2  light from Alpha Centauri reaches Proxima Centauri
y    4.2  light from Sol reaches Proxima Centauri
y    4.2  light from Proxima Centauri reaches Sol
y    4.4  light from Sol reaches Alpha Centauri
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
| `r` | reset to t = 0 |
| `q` | quit |
| drag / scroll / middle-drag | orbit / zoom / pan (VTK's trackball camera) |

The upper-left corner shows the simulated clock and speed, the lower-left the last eight
arrivals, the lower-right the key legend. Every arrival is also printed to stdout.

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
`--speed`, rescales every shell to the new radius, lights up any star a shell has just
reached, and appends the arrival to the log.

## Exit codes

| Code | Meaning                                                                     |
| ---- | ---------------------------------------------------------------------------- |
| 0    | The window was closed                                                       |
| 1    | No star within `--within`, or the bundled catalogue is unreadable or empty  |
| 2    | Invalid `--speed` or `--within`, or a rejected command line                 |

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
