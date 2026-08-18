# starlight

When you look at a star, you are looking into the past. `starlight.py` tells you
how far into the past: give it a star and a date, and it reports when the light
you saw began its journey.

```
$ ./starlight.py Betelgeuse --on 2026-08-16
Betelgeuse (Alpha Orionis)
  Distance     548.3 ly  (168.1 pc, Hipparcos (revised))
  Observed     16 August 2026 CE
  Light left   6 May 1478 CE
```

## Usage

```
starlight.py NAME [--on DATE] [--uncertainty] [--json] [--verbose] [--offline]
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

## Exit codes

| Code | Meaning                                  |
| ---- | ----------------------------------------- |
| 0    | Success                                   |
| 1    | Unknown star                              |
| 2    | Malformed date                            |
| 3    | Network failure during the SIMBAD fallback |

## What the model ignores

The answer is the naive Earth-frame one. It ignores the star's radial motion,
which means its distance at emission differed slightly from its distance today;
it ignores proper motion; and it ignores gravitational and cosmological
effects. For every star here, those corrections are far smaller than the
uncertainty on the published distance — which `--uncertainty` will show you.

## Requirements

Python 3.10 or newer. No third-party runtime dependencies.

## Running it

`starlight` is a tool in the [space](../) monorepo, which uses `uv`. From the repo root:

```
uv run python starlight/starlight.py Betelgeuse --on 2026-08-16
```

Or from this directory, `./starlight.py Betelgeuse --on 2026-08-16` with any Python 3.10+.

## Tests

From the repo root:

```
uv sync
uv run pytest starlight
```

Tests never touch the network — the SIMBAD call is stubbed throughout, and
`conftest.py` installs an autouse fixture that makes any real call fail loudly.
