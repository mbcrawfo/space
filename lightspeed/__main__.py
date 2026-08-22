"""Watch light spread between the nearest stars.

Opens a 3D window centred on Sol with the catalogued systems out to 20 light-years at
their true relative positions. On space, every star emits one flash; each grows as a
translucent sphere at one light-year per simulated year while you orbit the camera.
"""

import argparse
import math
import sys
from typing import NoReturn

from . import catalog

# RawDescriptionHelpFormatter prints these two blocks verbatim, so they are
# hand-wrapped here rather than reflowed to the terminal width.
DESCRIPTION = """\
Watch light spread out between the nearest stars, in 3D.

Opens a window centred on Sol with nearly ninety stellar systems out to 20 light-years,
each at its true position relative to Earth and labelled with its name and distance. One
scene unit is one light-year, so the layout is accurate and only the camera scales it.
Press space and every star emits a single flash at the same instant; each flash grows as
a translucent sphere at one light-year per year of simulated time. When two stars' light
reaches each other — both crossings happen at the same instant — both flash red and
a log line records the pair and the year. The window stays open until you close it
(q)."""

EXAMPLES = """\
Examples:
  python -m lightspeed                          the default: 1 yr/s, every star
  python -m lightspeed --speed 0.5              slow motion, half a year per second
  python -m lightspeed --within 12 --autostart  two dozen nearest, already running

Keys in the window:
  space  start / pause          + / -  faster / slower (×2 / ÷2)
  m      shell style: rings (default) / rings + fill / fill / off
  ] / [  focus the next / previous star, out from Sol; \\ clears the focus
  r      reset t = 0, refit the camera    q  quit
  drag to orbit, scroll to zoom, middle-drag to pan

Exit codes:
  0  the window was closed
  1  no star within --within, or the catalogue is unreadable or empty
  2  invalid --speed or --within, or a command line argparse rejected
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
        prog="python -m lightspeed",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=DESCRIPTION,
        epilog=EXAMPLES,
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        metavar="YEARS_PER_SECOND",
        help=(
            "how many simulated years pass per real second once the simulation is running; "
            "shells grow this many light-years per second. Must be a positive, finite number. "
            "At 1 the light from Sol reaches Proxima Centauri after about four seconds; at 0.25 "
            "it takes seventeen. The + and - keys double and halve it while the window is open. "
            "(default: 1.0)"
        ),
    )
    parser.add_argument(
        "--within",
        type=float,
        default=20.0,
        metavar="LY",
        help=(
            "show only the systems no farther than this many light-years from Sol. Must be a "
            "positive, finite number; anything above 20 shows the whole bundled catalogue, "
            "because nothing farther is bundled, and a value that leaves only Sol is an error. "
            "(default: 20.0)"
        ),
    )
    parser.add_argument(
        "--autostart",
        action="store_true",
        help=(
            "start the simulation the moment the window opens instead of waiting for space. "
            "Space still pauses and resumes afterwards."
        ),
    )
    return parser


def validate_positive(flag: str, value: float) -> None:
    """Raise ValueError naming `flag` unless `value` is a positive, finite number."""
    if not (math.isfinite(value) and value > 0.0):
        raise ValueError(f"{flag} must be a positive, finite number, not {value}.")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Both checks come before the catalogue is read or VTK imported, so a bad
    # number costs nothing. The ValueError says what is wrong; the hint says
    # what would work.
    try:
        validate_positive("--speed", args.speed)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        print("Try --speed 1 for one simulated year per second.", file=sys.stderr)
        return 2
    try:
        validate_positive("--within", args.within)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        print("Try --within 20 for every bundled star.", file=sys.stderr)
        return 2

    try:
        stars = catalog.load()
    except catalog.CatalogError as exc:
        print(exc, file=sys.stderr)
        return 1

    if len(stars) < 2:
        print("The bundled star catalogue is empty; nothing to show.", file=sys.stderr)
        return 1

    selected = catalog.within(stars, args.within)
    if len(selected) < 2:
        nearest = stars[1]
        print(f"No catalogued star lies within {args.within:g} ly of Sol.", file=sys.stderr)
        print(f"The nearest is {nearest.name} at {nearest.distance_ly:.2f} ly; try --within 5.", file=sys.stderr)
        return 1

    from . import viewer  # deferred: importing VTK is slow and --help should not pay for it

    viewer.run(selected, years_per_second=args.speed, autostart=args.autostart)
    return 0


if __name__ == "__main__":
    sys.exit(main())
