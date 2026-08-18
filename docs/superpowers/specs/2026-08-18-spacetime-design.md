# spacetime — design

**Date:** 2026-08-18
**Status:** approved, not yet implemented

## What it is

A tool in the `space` monorepo that answers: if we left today for a given star under
constant acceleration, how fast would we get, how long would the crew live through, and
how much time would pass on Earth?

```
$ python -m spacetime Sirius
Sirius (Alpha Canis Majoris)
  Distance     8.6 ly  (2.6 pc, Hipparcos)
  Profile      1.00 G, flip and burn at the midpoint
  Peak speed   98.30% of light speed
  Crew time    4.6 years
  Earth time   10.4 years
```

The inputs are a destination star and an acceleration in G. The three headline outputs are
peak speed as a percentage of `c`, elapsed proper time for the crew, and elapsed coordinate
time on Earth.

## Physics

Acceleration is **proper** acceleration — what a scale on deck reads, held constant for the
whole burn. A ship at a constant 1 G proper acceleration does not approach `c` in a year;
its coordinate acceleration falls away as it speeds up. Constant proper acceleration is also
the only reading under which "1 G" means what a reader expects: Earth-normal gravity on deck
for the whole trip.

Earth and the star are treated as mutually at rest, and `d` is the star's present catalogued
distance in Earth's frame. For a ship starting at rest and accelerating through a distance
`d` at proper acceleration `a`:

| quantity            | formula                    |
| ------------------- | -------------------------- |
| Lorentz factor      | γ = 1 + a·d/c²             |
| speed               | v/c = √(1 − 1/γ²)          |
| coordinate time     | t = √( (d/c)² + 2d/a )     |
| proper time         | τ = (c/a)·arccosh(γ)       |

These are the standard relativistic-rocket results; γ = 1 + a·d/c² is what makes the set
tidy, since every other quantity follows from γ and the two times.

### Profiles

**Flip and burn** (default) — accelerate for the first half of the distance, flip, decelerate
for the second half, arrive at rest. Apply the formulas to a leg of `d = D/2` and double both
times. Peak speed is reached at the midpoint flip.

**Flyby** (`--flyby`) — accelerate over the whole distance `D` and pass the star without
stopping. Apply the formulas once. Peak speed is reached at arrival.

### Reference values

Computed at 1.00 G, with `g₀ = 9.80665 m/s²`, `c = 299792458 m/s`,
`1 pc = 3.26156378 ly`, and a Julian year of 365.25 days. These are the fixtures the tests
assert against.

| star             | distance   | profile | peak speed  | crew time  | Earth time  |
| ---------------- | ---------- | ------- | ----------- | ---------- | ----------- |
| Proxima Centauri | 4.2433 ly  | flip    | 94.9600 % c | 3.5410 yr  | 5.8692 yr   |
| Proxima Centauri | 4.2433 ly  | flyby   | 98.2576 % c | 2.2931 yr  | 5.1212 yr   |
| Sirius           | 8.6007 ly  | flip    | 98.2955 % c | 4.6077 yr  | 10.3585 yr  |
| Sirius           | 8.6007 ly  | flyby   | 99.4863 % c | 2.8877 yr  | 9.5203 yr   |
| Betelgeuse       | 548.269 ly | flip    | 99.9994 % c | 12.2873 yr | 550.2029 yr |

The Betelgeuse row is the point of the tool: 12 years on deck, five and a half centuries at
home.

### Numerical care

- `arccosh(1 + x)` is evaluated as `log1p(x + √(x·(x+2)))` rather than `math.acosh(1 + x)`.
  Forming `1 + x` first discards precision when `x` is small — a low acceleration or a very
  near target — and the `log1p` form keeps it.
- Acceleration must be finite and strictly positive. Zero acceleration is a trip that never
  ends, and negative acceleration is not a direction, so both are rejected at the boundary
  rather than allowed to produce an infinity or a NaN deeper in.
- Distance must be finite and strictly positive; the catalogue cannot currently produce a
  non-positive distance, but the physics module does not assume its caller checked.

## Structure

```
spacetime/
├── __init__.py
├── __main__.py       # CLI
├── pyproject.toml    # workspace member metadata
├── conftest.py       # autouse fixture: any real network call fails loudly
├── catalog.py        # star name -> distance (duplicated from starlight)
├── relativity.py     # the physics; pure functions, no I/O
├── stars.json        # 50-star catalogue (duplicated from starlight)
├── README.md
└── tests/
    ├── test_relativity.py
    ├── test_catalog.py
    ├── test_simbad.py
    └── test_spacetime.py
```

### `relativity.py`

Pure functions and a frozen dataclass. No argparse, no printing, no file or network access.

```python
G0 = 9.80665                  # m/s^2, standard gravity
C = 299792458.0               # m/s
LY_PER_PC = 3.26156378
SECONDS_PER_JULIAN_YEAR = 365.25 * 86400.0

@dataclass(frozen=True)
class Trip:
    distance_ly: float
    accel_g: float
    flyby: bool
    peak_velocity_c: float    # fraction of c, not a percentage
    peak_lorentz: float
    crew_years: float
    earth_years: float

class TripError(ValueError):
    """Raised for an acceleration or distance the model cannot use."""

def solve(distance_ly: float, accel_g: float, *, flyby: bool = False) -> Trip
```

`solve` is the whole public surface. A private single-leg helper holds the four formulas and
`solve` applies it once or twice depending on the profile.

### `catalog.py` and `stars.json`

A copy of `starlight`'s resolver: forgiving name matching (casefolded, Greek letters spelled
out, punctuation dropped), the bundled 50-star catalogue, a SIMBAD TAP fallback for anything
not bundled, `StarNotFoundError` carrying did-you-mean suggestions, and `SimbadError` for
network trouble. `_http_post` stays the single network seam, and `conftest.py` carries over
the session-scoped autouse fixture that replaces it with a function that raises.

Duplication is what `CLAUDE.md` prescribes — tools in this repo do not import each other —
but it has a cost worth stating rather than hiding: there are now two copies of the star
data, and a distance corrected in one will not be corrected in the other. The tool's README
says so.

Only the parts `spacetime` uses are carried over. `starlight`'s `caldate` and `lighttime`
modules have nothing to do with this tool and are not copied.

### `__main__.py`

```
python -m spacetime NAME [-a G] [--flyby] [--uncertainty] [--json] [--verbose] [--offline]
```

- `NAME` — star name, designation, or catalogue number; same forgiving matching as `starlight`.
- `-a`, `--accel` — proper acceleration in G. Default `1.0`.
- `--flyby` — burn the whole way and pass the star, instead of flipping at the midpoint.
- `--uncertainty` — show the range implied by the catalogued distance error bars.
- `--json` — machine-readable output.
- `--verbose` — peak Lorentz factor, the Earth-minus-crew gap, and the modelling caveats.
- `--offline` — never query SIMBAD; bundled catalogue only.

The module follows `starlight`'s split: `build_result(star, accel_g, flyby)` produces the
dict both output modes are built from, and `render(result, ...)` turns it into text. `main`
parses, resolves, computes, prints, and returns an exit code.

`--uncertainty` re-runs `solve` at `distance ± distance_pc_err` and reports the resulting
spans for peak speed, crew time, and Earth time. A nearer star means a shorter trip and a
lower peak speed, so the near bound gives the low end of all three. Stars whose catalogue
entry has no error bar simply produce no uncertainty block, exactly as in `starlight`.

Exit codes match `starlight`'s scheme:

| code | meaning                                    |
| ---- | ------------------------------------------ |
| 0    | success                                    |
| 1    | unknown star                               |
| 2    | invalid acceleration                       |
| 3    | network failure during the SIMBAD fallback |

### Output

Human-readable:

```
Sirius (Alpha Canis Majoris)
  Distance     8.6 ly  (2.6 pc, Hipparcos)
  Profile      1.00 G, flip and burn at the midpoint
  Peak speed   98.30% of light speed
  Crew time    4.6 years
  Earth time   10.4 years
```

With `--verbose`, three more lines and the caveat paragraph: peak Lorentz factor, the
Earth-minus-crew gap phrased as years skipped, and the note that fuel is ignored.

The JSON mode emits the same values under stable keys — `distance_ly`, `distance_pc`,
`source`, `accel_g`, `profile`, `peak_velocity_c`, `peak_lorentz`, `crew_years`,
`earth_years`, and an `uncertainty` object when requested — with `peak_velocity_c` a
fraction rather than the displayed percentage.

## What the model ignores

Stated in the README and behind `--verbose`, because each one is a reason the number is not
a travel plan:

- **Fuel.** The largest omission by far. A perfect photon rocket doing the Proxima
  flip-and-burn needs a mass ratio around 1600; anything less ideal is worse. The tool
  reports the trip a ship *could* fly, not one anybody can build.
- **Stellar motion.** Earth and the star are assumed mutually at rest, at the star's
  present catalogued distance. Over the centuries a distant target takes in Earth's frame,
  the star's own proper and radial motion is a real effect and is not modelled.
- **The flip is instantaneous**, and so is engine start and shutdown.
- **Nothing else is in the way** — no interstellar medium, no shielding, no navigation.
- **No gravity wells.** Departure and arrival are from and to free space at rest.

## Testing

`relativity.py` carries the interesting tests, since it is the part with a right answer:

- The reference table above, to a fixed tolerance.
- **Newtonian limit** — at an acceleration and distance small enough that `v ≪ c`, the
  flip-and-burn peak speed converges on `√(a·D)` and the crew and Earth times converge on
  each other.
- **Invariants**, asserted across a spread of distances and accelerations: crew time is never
  greater than Earth time; peak speed is always strictly below `c`; `--flyby` is always
  faster than flip-and-burn in both clocks and always reaches a higher peak speed; both times
  decrease monotonically with acceleration and increase monotonically with distance.
- **Boundaries** — zero, negative, NaN, and infinite accelerations raise `TripError`, as do
  non-positive distances.

`catalog.py` reuses `starlight`'s test approach: name normalization, alias and designation
matching, suggestions on a near miss, and a SIMBAD fallback exercised entirely through a
stubbed `_http_post`, including its parse failures and error paths.

The CLI tests cover each exit code, the default 1 G, `--flyby`, `--uncertainty` (present with
error bars, absent without), the JSON shape, and `--offline` refusing to reach the network.

No test touches the network; `conftest.py` enforces it structurally rather than by
convention.

## Repo integration

- `spacetime/pyproject.toml` declares `requires-python = ">=3.10"`, no dependencies, and
  `package = false`.
- `spacetime` is added to `[tool.uv.workspace] members` in the root `pyproject.toml`. That is
  the only registration needed — ruff's `src` and pytest's `pythonpath` are both `["."]`.
- The root `README.md` tool table gains a `spacetime` row.
- No `[tool.ruff]` section in the tool's `pyproject.toml`; the root config is repo-wide.
- `uv sync` to refresh `uv.lock`, then `ruff check`, `ruff format`, and `pytest` must all be
  clean before the work is done.

## Deliberately not built

- **Fuel and mass ratio in the output.** It belongs in the caveats, not the headline numbers.
- **Multi-leg itineraries**, coasting phases, or a non-constant acceleration schedule.
- **A shared star catalogue tool.** The repo's rule is that tools do not import each other;
  promoting the catalogue would require `starlight` to import it, which the rule forbids.
