"""When we look at a star, we see light that left it years ago.

Given a star and a date of observation, report the date — in Earth's frame of
reference — when that light began its journey.
"""

import argparse
import json
import re
import sys
from typing import NoReturn

from . import caldate, catalog, lighttime

CAVEAT = (
    "Light travel time uses the star's present catalogued distance. It ignores "
    "the star's radial motion, which made that distance slightly different when "
    "the light left — an effect far smaller than the distance uncertainty itself."
)


def build_result(star: catalog.Star, observation_jdn: int) -> dict:
    """Everything both output formats are built from."""
    emission = lighttime.emission_jdn(observation_jdn, star.distance_pc)
    result = {
        "name": star.name,
        "designation": star.designation,
        "distance_pc": star.distance_pc,
        "distance_ly": lighttime.to_light_years(star.distance_pc),
        "source": star.source,
        "observation_jdn": observation_jdn,
        "observation_date": caldate.format_date(observation_jdn),
        "emission_jdn": emission,
        "emission_date": caldate.format_date(emission),
        "travel_days": lighttime.travel_days(star.distance_pc),
        "travel_years": lighttime.travel_years(star.distance_pc),
    }

    if star.distance_pc_err:
        nearest = max(star.distance_pc - star.distance_pc_err, 0.0)
        farthest = star.distance_pc + star.distance_pc_err
        result["uncertainty"] = {
            "distance_pc_err": star.distance_pc_err,
            # A nearer star means the light left more recently.
            "latest_year": caldate.format_year(lighttime.emission_jdn(observation_jdn, nearest)),
            "earliest_year": caldate.format_year(lighttime.emission_jdn(observation_jdn, farthest)),
        }

    return result


def render(result: dict, *, uncertainty: bool, verbose: bool) -> str:
    heading = result["name"]
    if result["designation"] and result["designation"] != result["name"]:
        heading += f" ({result['designation']})"

    distance = f"{result['distance_ly']:,.1f} ly  ({result['distance_pc']:,.1f} pc, {result['source']})"

    left = result["emission_date"]
    if uncertainty and "uncertainty" in result:
        span = result["uncertainty"]
        left += f"  (between {span['earliest_year']} and {span['latest_year']})"

    lines = [
        heading,
        f"  Distance     {distance}",
        f"  Observed     {result['observation_date']}",
        f"  Light left   {left}",
    ]

    if verbose:
        lines.append(f"  Travel time  {result['travel_years']:,.1f} years ({result['travel_days']:,.0f} days)")
        lines.append("")
        lines.append(f"  {CAVEAT}")

    return "\n".join(lines)


# RawDescriptionHelpFormatter prints these two blocks verbatim, so they are
# hand-wrapped here rather than reflowed to the terminal width.
DESCRIPTION = """\
Find out when the light you see tonight left its star.

Subtracts the light travel time — the star's catalogued distance divided by c —
from the date you observed it, and reports the date, in Earth's frame, when that
light set out. Dates run on Julian Day Numbers over the proleptic Gregorian
calendar, so emission dates deep in BCE are reported exactly like any other."""

EXAMPLES = """\
Examples:
  python -m starlight Betelgeuse --on 2026-08-16   what left Betelgeuse that night
  python -m starlight "alpha ori" --uncertainty    the same star, with its error bars
  python -m starlight Sirius --on -0044-03-15      looking up on the Ides of March
  python -m starlight "HD 39801" --json --offline  machine-readable, bundled catalog

Exit codes:
  0  success
  1  unknown star — no catalog or SIMBAD match for NAME
  2  malformed date, or a command line argparse rejected
  3  network failure while falling back to SIMBAD
"""


class _HelpOnErrorParser(argparse.ArgumentParser):
    """An ArgumentParser that answers a bad command line with the full help.

    argparse's own error() prints the usage line alone, which names the flags
    but says nothing about what any of them accepts — which is exactly what a
    user who just got the command line wrong is missing. The help goes to
    stderr, not stdout, because this is still an error; the error message is
    printed after it so it stays the last thing on a scrolled terminal.
    """

    def error(self, message: str) -> NoReturn:
        self.print_help(sys.stderr)
        self.exit(2, f"\n{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _HelpOnErrorParser(
        prog="python -m starlight",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=DESCRIPTION,
        epilog=EXAMPLES,
    )
    parser.add_argument(
        "name",
        help=(
            "the star to look up: a common name, Bayer designation, or catalogue number. "
            "Matching is forgiving about spelling and Greek letters, so Betelgeuse, "
            "'alpha ori', 'α Orionis', and 'HD 39801' all resolve to the same star. "
            "Fifty stars ship with the tool; anything else is resolved through SIMBAD "
            "unless --offline is given. Quote names containing spaces."
        ),
    )
    parser.add_argument(
        "--on",
        dest="date",
        metavar="DATE",
        help=(
            "the date you observed the star, as YYYY-MM-DD. Prefix the year with a minus "
            "for BCE (-0044-03-15 is the Ides of March); there is no year 0, so 1 BCE is "
            "written -0001. Defaults to today."
        ),
    )
    parser.add_argument(
        "--uncertainty",
        action="store_true",
        help=(
            "add the span of emission years implied by the catalogued distance error bars. "
            "Silently does nothing for a star whose distance carries no error bar."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help=(
            "print the result as a JSON object under stable keys instead of the human-readable "
            "report, for piping into other tools. Carries the uncertainty range only when "
            "--uncertainty is also given."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "add the light travel time in years and days, and the caveats behind the number. "
            "Ignored under --json, whose output is the same either way."
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "never query SIMBAD: resolve NAME against the fifty bundled stars only. "
            "Makes an unknown star exit 1 immediately rather than costing a network round trip."
        ),
    )
    return parser


# A leading-minus BCE date, loosely shaped (`caldate.parse_date` does the
# real validation) — just enough to recognize "this looks like it was meant
# as --on's value", not "this is a valid date".
BCE_DATE_SHAPE = re.compile(r"^-\d{1,6}-\d{1,2}-\d{1,2}$")


def _normalize_argv(argv: list[str]) -> list[str]:
    """Join `--on VALUE` into `--on=VALUE` so a BCE date's leading minus isn't
    mistaken by argparse for another option.

    Only merges when the following token actually looks like a BCE date
    (`BCE_DATE_SHAPE`). Anything else — an ordinary date with no leading
    dash, a missing value at the end of argv, or `--on` immediately followed
    by another flag — is left alone, so it either parses normally or still
    hits argparse's own "expected one argument" error instead of being
    silently swallowed as a bogus date.

    Stops rewriting at the first bare `--`: argparse treats that token as
    the end-of-options marker, so a literal `--on` appearing after it is a
    positional value, not the flag, and must not be merged.
    """
    normalized = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--":
            normalized.extend(argv[i:])
            break
        if token == "--on" and i + 1 < len(argv) and BCE_DATE_SHAPE.match(argv[i + 1]):
            normalized.append(f"--on={argv[i + 1]}")
            i += 2
            continue
        normalized.append(token)
        i += 1
    return normalized


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(_normalize_argv(raw_argv))

    try:
        observation_jdn = caldate.today_jdn() if args.date is None else caldate.parse_date(args.date)
    except caldate.DateError as exc:
        print(exc, file=sys.stderr)
        # The DateError says what is wrong with this date; the reader still
        # needs the shape --on wants before they can fix it.
        print("Expected --on YYYY-MM-DD, with a leading minus for BCE years.", file=sys.stderr)
        return 2

    try:
        star = catalog.resolve(args.name, offline=args.offline)
    except catalog.StarNotFoundError as exc:
        print(exc, file=sys.stderr)
        if exc.suggestions:
            print(f"Did you mean: {', '.join(exc.suggestions)}?", file=sys.stderr)
        return 1
    except catalog.SimbadError as exc:
        print(exc, file=sys.stderr)
        print("Use --offline to search only the bundled catalog.", file=sys.stderr)
        return 3

    result = build_result(star, observation_jdn)

    if args.as_json:
        if not args.uncertainty:
            result.pop("uncertainty", None)
        print(json.dumps(result, indent=2))
    else:
        print(render(result, uncertainty=args.uncertainty, verbose=args.verbose))

    return 0


if __name__ == "__main__":
    sys.exit(main())
