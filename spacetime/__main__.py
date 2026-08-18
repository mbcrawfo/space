"""How long a trip to another star takes, and for whom.

Given a destination and an acceleration held constant for the whole burn,
report the peak speed reached, the years the crew lives through, and the years
that pass at home while they do.
"""

import argparse
import json
import sys
from typing import NoReturn

from . import catalog, relativity

CAVEAT = (
    "Fuel is ignored entirely: a perfect photon rocket flying the Proxima "
    "flip-and-burn needs a mass ratio near 40, and nothing less ideal does "
    "better. Earth and the star are assumed mutually at rest at the star's "
    "present catalogued distance, so the star's own motion over the trip is "
    "not modelled, and the flip is instantaneous."
)

PROFILE_DESCRIPTIONS = {
    "flip-and-burn": "flip and burn at the midpoint",
    "flyby": "burn all the way, no turnover",
}


def format_speed(fraction: float) -> str:
    """A fraction of c as a percentage, with enough decimals to stay honest.

    Two decimals turn Betelgeuse's 99.99938% into a flat "100.00%", which is
    not a speed anything can reach. Widen until the rounded figure is still
    below 100.
    """
    percent = fraction * 100.0
    for places in range(2, 13):
        text = f"{percent:.{places}f}"
        if float(text) < 100.0:
            return text
    return f"{percent:.12f}"


def build_result(star: catalog.Star, accel_g: float, *, flyby: bool) -> dict:
    """Everything both output formats are built from."""
    distance_ly = star.distance_pc * relativity.LY_PER_PC
    trip = relativity.solve(distance_ly, accel_g, flyby=flyby)

    result = {
        "name": star.name,
        "designation": star.designation,
        "distance_pc": star.distance_pc,
        "distance_ly": distance_ly,
        "source": star.source,
        "accel_g": accel_g,
        "profile": "flyby" if flyby else "flip-and-burn",
        "peak_velocity_c": trip.peak_velocity_c,
        "peak_lorentz": trip.peak_lorentz,
        "crew_years": trip.crew_years,
        "earth_years": trip.earth_years,
    }

    # A nearer star is a shorter trip at a lower peak speed, so the near bound
    # is the low end of all three ranges. Skipped when the error bar swallows
    # the distance, which would leave nothing to fly.
    nearest_pc = star.distance_pc - (star.distance_pc_err or 0.0)
    if star.distance_pc_err and nearest_pc > 0.0:
        near = relativity.solve(nearest_pc * relativity.LY_PER_PC, accel_g, flyby=flyby)
        farthest_pc = star.distance_pc + star.distance_pc_err
        far = relativity.solve(farthest_pc * relativity.LY_PER_PC, accel_g, flyby=flyby)
        result["uncertainty"] = {
            "distance_pc_err": star.distance_pc_err,
            "peak_velocity_c": [near.peak_velocity_c, far.peak_velocity_c],
            "crew_years": [near.crew_years, far.crew_years],
            "earth_years": [near.earth_years, far.earth_years],
        }

    return result


def render(result: dict, *, uncertainty: bool, verbose: bool) -> str:
    heading = result["name"]
    if result["designation"] and result["designation"] != result["name"]:
        heading += f" ({result['designation']})"

    speed = f"{format_speed(result['peak_velocity_c'])}% of light speed"
    crew = f"{result['crew_years']:,.1f} years"
    earth = f"{result['earth_years']:,.1f} years"

    span = result.get("uncertainty") if uncertainty else None
    if span:
        low, high = span["peak_velocity_c"]
        speed += f"  ({format_speed(low)} to {format_speed(high)}%)"
        low, high = span["crew_years"]
        crew += f"  ({low:,.1f} to {high:,.1f})"
        low, high = span["earth_years"]
        earth += f"  ({low:,.1f} to {high:,.1f})"

    lines = [
        heading,
        f"  Distance     {result['distance_ly']:,.1f} ly  ({result['distance_pc']:,.1f} pc, {result['source']})",
        f"  Profile      {result['accel_g']:,.2f} G, {PROFILE_DESCRIPTIONS[result['profile']]}",
        f"  Peak speed   {speed}",
        f"  Crew time    {crew}",
        f"  Earth time   {earth}",
    ]

    if verbose:
        skipped = result["earth_years"] - result["crew_years"]
        lines.append(f"  Peak γ       {result['peak_lorentz']:,.2f}")
        lines.append(f"  Skipped      {skipped:,.1f} years")
        lines.append("")
        lines.append(f"  {CAVEAT}")

    return "\n".join(lines)


# RawDescriptionHelpFormatter prints these two blocks verbatim, so they are
# hand-wrapped here rather than reflowed to the terminal width.
DESCRIPTION = """\
Work out how long a trip to another star takes, for the crew and for Earth.

Flies the ship at a constant proper acceleration — Earth-normal gravity on deck
at 1 G — and reports the peak speed it reaches, the years the crew ages, and the
years that pass at home meanwhile. The gap between the last two is time dilation:
at 1 G to Betelgeuse the crew ages 12 years while Earth ages 550."""

EXAMPLES = """\
Examples:
  python -m spacetime Sirius                    the default 1 G flip-and-burn
  python -m spacetime Sirius -a 3 --verbose     3 G, with the Lorentz factor
  python -m spacetime "alpha ori" --flyby       no turnover — pass at full speed
  python -m spacetime Proxima --json --offline  machine-readable, no network

Exit codes:
  0  success
  1  unknown star — no catalog or SIMBAD match for NAME
  2  invalid acceleration, or a command line argparse rejected
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
        prog="python -m spacetime",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=DESCRIPTION,
        epilog=EXAMPLES,
    )
    parser.add_argument(
        "name",
        help=(
            "the destination star: a common name, Bayer designation, or catalogue number. "
            "Matching is forgiving about spelling and Greek letters, so Betelgeuse, "
            "'alpha ori', 'α Orionis', and 'HD 39801' all resolve to the same star. "
            "Fifty stars ship with the tool; anything else is resolved through SIMBAD "
            "unless --offline is given. Quote names containing spaces."
        ),
    )
    parser.add_argument(
        "-a",
        "--accel",
        type=float,
        default=1.0,
        metavar="G",
        help=(
            "proper acceleration — what a scale on deck reads — in multiples of Earth "
            "gravity, held constant for the whole burn. Must be a positive, finite number; "
            "1.0 is comfortable, 3.0 is punishing, and higher only shortens crew time so far, "
            "because the trip cannot beat the light-crossing time Earth sees. (default: 1.0)"
        ),
    )
    parser.add_argument(
        "--flyby",
        action="store_true",
        help=(
            "burn the whole way and pass the star at peak speed, instead of the default "
            "flip-and-burn, which flips at the midpoint and arrives at rest. A flyby is "
            "faster and reaches a higher speed, but nothing aboard stops to look."
        ),
    )
    parser.add_argument(
        "--uncertainty",
        action="store_true",
        help=(
            "add the span of speeds and times implied by the catalogued distance error bars. "
            "Silently does nothing for a star whose distance carries no error bar."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help=(
            "print the result as a JSON object under stable keys instead of the human-readable "
            "report, for piping into other tools. Carries the uncertainty ranges only when "
            "--uncertainty is also given."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "add the peak Lorentz factor, the years of home time the crew skips, and the "
            "caveats behind the numbers. Ignored under --json, whose output is the same "
            "either way."
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Checked before the lookup, so a bad number costs no network round trip.
    try:
        relativity.validate_acceleration(args.accel)
    except relativity.TripError as exc:
        print(exc, file=sys.stderr)
        # The TripError says what is wrong with this value; the reader still
        # needs to know what --accel would accept before they can fix it.
        print("Try --accel 1 for Earth-normal gravity on deck.", file=sys.stderr)
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

    try:
        result = build_result(star, args.accel, flyby=args.flyby)
    except relativity.TripError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.as_json:
        if not args.uncertainty:
            result.pop("uncertainty", None)
        print(json.dumps(result, indent=2))
    else:
        print(render(result, uncertainty=args.uncertainty, verbose=args.verbose))

    return 0


if __name__ == "__main__":
    sys.exit(main())
