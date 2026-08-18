# starlight

When you look at a star, you are looking into the past. `starlight` tells you
how far into the past: give it a star and a date, and it reports when the light
you saw began its journey.

```
$ python -m starlight Betelgeuse --on 2026-08-16
Betelgeuse (Alpha Orionis)
  Distance     548.3 ly  (168.1 pc, Hipparcos (revised))
  Observed     16 August 2026 CE
  Light left   6 May 1478 CE
```

## Usage

```
python -m starlight NAME [--on DATE] [--uncertainty] [--json] [--verbose] [--offline]
```

- `NAME` — a common name, Bayer designation, or catalogue number. Spelling is
  forgiving: `Betelgeuse`, `alpha ori`, `α Orionis`, and `HD 39801` all work.
- `--on DATE` — observation date as `YYYY-MM-DD`, with a leading minus for BCE
  years (`-0044-03-15` is the Ides of March). Defaults to today.
- `--uncertainty` — show the range implied by the distance error bars.
- `--json` — machine-readable output.
- `--verbose` — travel time, distance provenance, and modelling caveats.
- `--offline` — never query SIMBAD.

## How it works

The emission date is the observation date minus the light travel time,
`distance / c`, using the star's present catalogued distance.

Two things make that harder than it sounds. First, `datetime` cannot represent
years before 1 CE, and light from Eta Carinae left it in 5477 BCE — so all
date arithmetic runs on Julian Day Numbers over the proleptic Gregorian
calendar, which extends backwards without limit. Second, star names have no
canonical spelling, so names are matched in a normalized form with Greek
letters spelled out.

Fifty stars ship in `stars.json`. Anything else is looked up in SIMBAD, which
resolves common names, Bayer designations, and catalogue numbers itself;
`--offline` disables that fallback.

`spacetime`, another tool in this repo, carries a copy of `catalog.py` and `stars.json`.
Tools here do not import each other, so a distance corrected here has to be copied across
to `spacetime` by hand.

## Exit codes

| Code | Meaning                                    |
| ---- | ------------------------------------------ |
| 0    | Success                                    |
| 1    | Unknown star                               |
| 2    | Malformed date, or a rejected command line |
| 3    | Network failure during the SIMBAD fallback |

## What the model ignores

The answer is the naive Earth-frame one. It ignores the star's radial motion,
which means its distance at emission differed slightly from its distance today;
it ignores proper motion; and it ignores gravitational and cosmological
effects. For every star here, those corrections are far smaller than the
uncertainty on the published distance — which `--uncertainty` will show you.

## Running it

`starlight` is a tool in the [space](../) monorepo, which uses `uv`. From the repo root:

```
uv run python -m starlight Betelgeuse --on 2026-08-16
```

It is a package, not a loose script, so run it with `-m` from the repo root — the directory
above this one has to be on `sys.path`. It needs Python 3.10 or newer and has no
third-party runtime dependencies.

## Tests

From the repo root:

```
uv sync
uv run pytest starlight
```

Tests never touch the network — the SIMBAD call is stubbed throughout, and
`conftest.py` installs an autouse fixture that makes any real call fail loudly.
