# Starlight — Design

**Date:** 2026-08-16
**Status:** Approved, ready for implementation planning

## Purpose

When we look at a star, we see light that left it years ago. `starlight.py`
takes the name of a star or system and a date of observation, and reports the
date — in Earth's frame of reference — when that light left the star.

## Scope

A stdlib-only Python CLI plus a bundled star catalog. No third-party runtime
dependencies. Development and testing use pytest.

Out of scope: sky position, visibility from a given location, apparent
magnitude, and any relativistic modelling beyond the naive light-travel time
described below.

## Physical model and its assumptions

The emission date is the observation date minus the light travel time:

```
travel_days = distance_pc x 3.26156378 (ly per pc) x 365.25 (days per Julian year)
emission_JDN = observation_JDN - round(travel_days)
```

This is the naive Earth-frame answer. It uses the star's *present* catalogued
distance, and therefore ignores:

- **Radial motion.** The star's distance at emission differed slightly from its
  distance today. For every star in the bundled catalog this difference is far
  smaller than the published distance uncertainty.
- **Proper motion**, which changes the star's apparent position but not the
  path length in any way that matters here.
- **Gravitational and cosmological effects**, which are negligible at these
  distances.

These assumptions are stated in the README and surfaced by `--verbose`. They
are documented rather than modelled: correcting for them would imply a
precision the source astrometry does not support.

Distances are stored in parsecs because that is the unit published by the
astrometric surveys the catalog draws from. Light-years are derived for
display.

## Architecture

Four modules. The split exists so the calendar arithmetic — the part most
likely to be subtly wrong — can be tested in isolation from argument parsing
and from the network.

```
starlight.py     CLI entry point: argparse, orchestration, output formatting
caldate.py       Proleptic Gregorian <-> Julian Day Number; BCE-aware parse/format
lighttime.py     The physical model: constants, travel time, emission date
catalog.py       Catalog loading, name/alias resolution, SIMBAD fallback
stars.json       Bundled catalog data
test_caldate.py
test_catalog.py
test_starlight.py
```

`starlight.py` is the script the user invokes. It owns no astronomy and no
calendar math; it resolves a name through `catalog`, converts dates through
`caldate`, and formats the result.

### caldate.py

Date handling cannot use `datetime`: its minimum year is 1 CE, and light from
Eta Carinae (~7,500 ly) left well before that. All arithmetic goes through
Julian Day Numbers over the proleptic Gregorian calendar, which extends
backward indefinitely.

Public interface:

- `parse_date(text) -> JDN` — accepts `YYYY-MM-DD`, with an optional leading
  `-` for BCE years (`-0044-03-15`). Raises `ValueError` with a clear message
  on malformed input or an impossible date (e.g. 30 February).
- `format_date(jdn) -> str` — renders as `6 April 1478 CE` / `12 March 5484 BCE`.
- `today() -> JDN`.

Conversion is integer arithmetic using the standard proleptic Gregorian
algorithm, so it has no range limit in either direction.

**Year numbering:** the astronomical convention is used internally (year 0
exists and is 1 BCE), but output uses the historical convention — the year
after 1 BCE is 1 CE, and no year 0 is ever printed. This conversion happens
only at the formatting and parsing boundaries.

### catalog.py

`stars.json` holds an array of entries:

```json
{
  "name": "Betelgeuse",
  "designation": "Alpha Orionis",
  "aliases": ["alpha ori", "a ori", "hd 39801", "hip 27989"],
  "distance_pc": 168.1,
  "distance_pc_err": 27.5,
  "source": "Gaia DR3"
}
```

Fifty entries covering naked-eye stars, the nearest stars, and
well-known named systems (Sirius, Proxima Centauri, Polaris, Betelgeuse,
Vega, Rigel, Eta Carinae, and similar). Each entry records the survey its
distance came from.

Public interface:

- `resolve(name, *, offline=False) -> Star` — returns a record with name,
  distance, uncertainty, and source.
- Raises `StarNotFoundError` carrying near-miss suggestions.

Resolution order:

1. Normalise the query: casefold, strip punctuation and whitespace, map common
   Greek letter spellings to a canonical form (`α` / `alpha` / `a`).
2. Match against name, designation, and alias keys.
3. On a miss, if `offline` is false, query SIMBAD (below).
4. On a further miss, raise `StarNotFoundError` with `difflib.get_close_matches`
   suggestions drawn from the bundled names.

### SIMBAD fallback

A single ADQL query to the SIMBAD TAP sync endpoint over `urllib`, joining the
identifier table so that catalogue designations resolve. Distance derives from
parallax as `distance_pc = 1000 / plx_mas`.

- Attempted only when the bundled catalog misses.
- Suppressed entirely by `--offline`.
- 10 second timeout. Network failure, timeout, malformed response, an unknown
  identifier, and a null or non-positive parallax each produce a distinct,
  plain-language error — never a traceback.
- Results are used for the current run only. No caching, no writes to
  `stars.json`.

This is the only network access the tool makes, and it sends only the star
name the user typed.

## Interface

```
starlight.py NAME [--on DATE] [--uncertainty] [--json] [--verbose] [--offline]
```

- `NAME` — star or system name; positional, required.
- `--on DATE` — observation date, `YYYY-MM-DD`, optional leading `-` for BCE.
  Defaults to today.
- `--uncertainty` — add the range implied by the distance error bars.
- `--json` — machine-readable output.
- `--verbose` — show parallax-derived distance, source survey, and the
  frame-of-reference caveat.
- `--offline` — never touch the network.

Default output:

```
$ starlight.py Betelgeuse --on 2026-08-16
Betelgeuse (Alpha Orionis)
  Distance     548.3 ly  (168.1 pc, Hipparcos (revised))
  Observed     16 August 2026 CE
  Light left   6 May 1478 CE
```

With `--uncertainty`:

```
  Light left   6 May 1478 CE  (between 1388 CE and 1568 CE)
```

`--json` emits a single object with the resolved name, `distance_pc`,
`distance_ly`, `source`, observation and emission dates as both formatted
strings and JDNs, and travel time in days and years. The uncertainty range is
included whenever `--uncertainty` is also passed.

### Errors and exit codes

| Condition | Exit | Behaviour |
|---|---|---|
| Success | 0 | Result printed |
| Unknown star | 1 | Message plus near-match suggestions |
| Malformed date | 2 | Message naming the expected format |
| Network failure during fallback | 3 | Message suggesting `--offline` |

All errors go to stderr as plain sentences.

## Testing

Test-driven, pytest, no live network.

- **caldate:** round-trips across the 1 BCE / 1 CE boundary; Gregorian leap
  year rules including 1900 and 2000; known anchors (2000-01-01 CE = JDN
  2451545); rejection of impossible dates; formatting on both sides of the era
  boundary.
- **Travel time:** hand-computed values for a near star (Proxima) and a distant
  one (Eta Carinae, landing in BCE); the pc-to-ly and Julian-year constants.
- **catalog:** exact, alias, and Greek-letter matches; case and punctuation
  insensitivity; near-match suggestions on a miss; `--offline` suppresses the
  network path entirely.
- **SIMBAD:** parsing exercised against a recorded response fixture; each
  failure mode (timeout, HTTP error, unknown identifier, null parallax) mapped
  to its message. The HTTP call is stubbed; tests never reach the network.
- **CLI:** smoke tests for default, `--json`, and `--uncertainty` output, and
  for each exit code.
