# spacetime

A trip to another star is not just far, it is slow — even close to the speed of light,
the nearest stars are years away. `spacetime` works out how long a trip actually takes,
under constant acceleration, for the crew flying it and for the people left on Earth.

```
$ python -m spacetime Sirius --offline
Sirius (Alpha Canis Majoris)
  Distance     8.6 ly  (2.6 pc, Hipparcos)
  Profile      1.00 G, flip and burn at the midpoint
  Peak speed   98.30% of light speed
  Crew time    4.6 years
  Earth time   10.4 years
```

## Usage

```
python -m spacetime NAME [-a G] [--flyby] [--uncertainty] [--json] [--verbose] [--offline]
```

- `NAME` — a common name, Bayer designation, or catalogue number. Spelling is
  forgiving: `Betelgeuse`, `alpha ori`, `α Orionis`, and `HD 39801` all work.
- `-a G`, `--accel G` — proper acceleration in G, held constant for the whole burn
  (default: `1.0`).
- `--flyby` — burn the whole way and pass the star, instead of flipping at the midpoint.
- `--uncertainty` — show the range implied by the distance error bars.
- `--json` — emit machine-readable JSON.
- `--verbose` — show the peak Lorentz factor, the years skipped, and the modelling
  caveats.
- `--offline` — never query SIMBAD; use the bundled catalog only.

## How it works

Acceleration here is *proper* acceleration — what a scale on deck reads — held constant
for the whole burn. A ship at a constant 1 G does not approach `c` in a year: its
coordinate acceleration, as measured from Earth, falls away as it speeds up. Constant
proper acceleration is also the only reading under which "1 G" means what a reader
expects, namely Earth-normal gravity on deck for the whole trip.

There are two flight profiles. The default is a flip-and-burn: the ship accelerates
through the first half of the distance, flips, decelerates through the second half, and
arrives at rest, so its peak speed is at the midpoint. `--flyby` accelerates the whole
way and passes the destination without stopping, so its peak speed is at arrival.

Earth and the destination are treated as mutually at rest, and the distance used is the
destination's present catalogued distance in Earth's frame. For a ship starting at rest
and accelerating through a distance `d` at proper acceleration `a`, the standard
relativistic-rocket results are:

```
gamma = 1 + a*d/c**2             the Lorentz factor reached
v/c   = sqrt(1 - 1/gamma**2)     the speed reached
t     = sqrt((d/c)**2 + 2*d/a)   elapsed coordinate time, on Earth
tau   = (c/a) * arccosh(gamma)   elapsed proper time, on deck
```

The flip-and-burn profile applies these to half the distance and doubles both times; the
flyby profile applies them to the whole distance directly.

```
$ python -m spacetime Betelgeuse --offline --verbose
Betelgeuse (Alpha Orionis)
  Distance     548.3 ly  (168.1 pc, Hipparcos (revised))
  Profile      1.00 G, flip and burn at the midpoint
  Peak speed   99.999% of light speed
  Crew time    12.3 years
  Earth time   550.2 years
  Peak γ       283.99
  Skipped      537.9 years

  Fuel is ignored entirely: a perfect photon rocket flying the Proxima flip-and-burn
  needs a mass ratio near 1600, and nothing less ideal does better. Earth and the star
  are assumed mutually at rest at the star's present catalogued distance, so the star's
  own motion over the trip is not modelled, and the flip is instantaneous.
```

## Exit codes

| Code | Meaning                                    |
| ---- | ------------------------------------------- |
| 0    | Success                                    |
| 1    | Unknown star                               |
| 2    | Invalid acceleration                       |
| 3    | Network failure during the SIMBAD fallback |

## What the model ignores

Fuel, first and plainly: nothing here accounts for the propellant a trip would take. A
perfect photon rocket flying the Proxima flip-and-burn needs a mass ratio near 1600 —
1600 kg of ship and fuel at departure for every 1 kg that arrives — and any rocket less
ideal than a photon rocket does worse. This tool reports the trip a ship *could* fly
under constant proper acceleration, not one anyone could build or fuel.

Beyond that: the star's own motion over the course of a years- or centuries-long trip is
not modelled, since Earth and the destination are treated as mutually at rest at the
star's present catalogued distance; the flip at the midpoint of a flip-and-burn is
instantaneous, not a deceleration-then-reacceleration that takes time itself; drag from
the interstellar medium at relativistic speed is not modelled; and gravity wells — the
Sun's, the destination's, anything in between — are ignored, so the acceleration is
constant all the way rather than lower near departure and arrival.

## The duplicated catalog

`catalog.py` and `stars.json` are copies of `starlight`'s. The repo's tools do not import
each other, so shared code is duplicated rather than factored into a common dependency.
The cost is real and worth stating plainly: a distance corrected in one tool's catalog is
not corrected in the other's until someone copies the fix across by hand.

## Running it

`spacetime` is a tool in the [space](../) monorepo, which uses `uv`. From the repo root:

```
uv run python -m spacetime Betelgeuse --offline
```

It is a package, not a loose script, so run it with `-m` from the repo root — the
directory above this one has to be on `sys.path`. It needs Python 3.10 or newer and has
no third-party runtime dependencies.

## Tests

From the repo root:

```
uv sync
uv run pytest spacetime
```

Tests never touch the network — the SIMBAD call is stubbed throughout, and
`conftest.py` installs an autouse fixture that makes any real call fail loudly.
