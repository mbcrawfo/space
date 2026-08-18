"""Star name resolution against the bundled catalog.

Names arrive from humans in every possible spelling: `Betelgeuse`, `alpha ori`,
`α Orionis`, `HD 39801`. Everything is compared in a normalized form —
casefolded, Greek letters spelled out, punctuation and spacing dropped.

``spacetime`` carries a copy of this module and ``stars.json``, so a correction here has
to be copied across by hand.
"""

import difflib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stars.json")
SIMBAD_TAP_URL = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
SIMBAD_TIMEOUT = 10.0

GREEK_LETTERS = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "ο": "omicron",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "ς": "sigma",
    "τ": "tau",
    "υ": "upsilon",
    "φ": "phi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
}


@dataclass(frozen=True)
class Star:
    name: str
    designation: str | None
    distance_pc: float
    distance_pc_err: float | None
    source: str


class StarNotFoundError(Exception):
    """Raised when a name matches nothing, with near misses if there are any."""

    def __init__(self, name: str, suggestions: list[str]):
        self.name = name
        self.suggestions = suggestions
        super().__init__(f"No star named {name!r} was found.")


class SimbadError(Exception):
    """Raised when SIMBAD cannot be reached or answers with nonsense."""


def _http_post(url: str, data: bytes, timeout: float) -> str:
    """POST and return the body as text. Seam for tests to stub."""
    request = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def simbad_lookup(name: str, *, timeout: float = SIMBAD_TIMEOUT) -> Star:
    """Look a name up in SIMBAD and derive its distance from parallax.

    Sends only the name the user typed. Results are used for this run alone —
    nothing is cached and `stars.json` is never written to.
    """
    escaped = name.replace("'", "''")
    query = (
        "SELECT TOP 1 b.main_id, b.plx_value, b.plx_err "
        "FROM basic AS b JOIN ident AS i ON b.oid = i.oidref "
        f"WHERE i.id = '{escaped}'"
    )
    payload = urllib.parse.urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "json",
            "QUERY": query,
        }
    ).encode("utf-8")

    try:
        body = _http_post(SIMBAD_TAP_URL, payload, timeout)
    except TimeoutError:
        raise SimbadError(f"SIMBAD did not respond within {timeout} seconds.") from None
    except urllib.error.HTTPError as exc:
        detail = f"HTTP {exc.code} ({exc.reason})"
        try:
            body_text = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body_text = ""
        if body_text:
            detail += f": {body_text[:200]}"
        raise SimbadError(f"SIMBAD returned an error: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SimbadError(f"Could not reach SIMBAD: {exc}") from exc

    try:
        rows = json.loads(body)["data"]
    except (ValueError, KeyError, TypeError) as exc:
        raise SimbadError("SIMBAD returned a response that could not be read.") from exc

    if not rows:
        raise StarNotFoundError(name, [])

    try:
        row = rows[0]
        main_id, plx_value, plx_err = row[0], row[1], row[2]
        plx_value = None if plx_value is None else float(plx_value)
        plx_err = None if plx_err is None else float(plx_err)
    except IndexError:
        raise StarNotFoundError(name, []) from None
    except (ValueError, KeyError, TypeError) as exc:
        raise SimbadError("SIMBAD returned a response that could not be read.") from exc

    if not plx_value or plx_value <= 0:
        raise StarNotFoundError(name, [])

    distance_pc = 1000.0 / plx_value
    distance_err = (1000.0 * plx_err / plx_value**2) if plx_err is not None else None

    return Star(
        name=main_id,
        designation=None,
        distance_pc=distance_pc,
        distance_pc_err=distance_err,
        source="SIMBAD",
    )


def normalize(name: str) -> str:
    """Reduce a name to its comparison form."""
    expanded = "".join(GREEK_LETTERS.get(ch, ch) for ch in name.strip())
    return "".join(ch for ch in expanded.casefold() if ch.isalnum())


_catalog_cache: list[Star] | None = None


def load_catalog(path: str | None = None) -> list[Star]:
    """Load the bundled catalog. Cached, since it never changes at runtime."""
    global _catalog_cache
    if path is None and _catalog_cache is not None:
        return _catalog_cache

    with open(path or CATALOG_PATH, encoding="utf-8") as handle:
        raw = json.load(handle)

    stars = [
        Star(
            name=entry["name"],
            designation=entry.get("designation"),
            distance_pc=float(entry["distance_pc"]),
            distance_pc_err=(float(entry["distance_pc_err"]) if entry.get("distance_pc_err") is not None else None),
            source=entry["source"],
        )
        for entry in raw
    ]
    if path is None:
        _catalog_cache = stars
    return stars


def _index(stars: list[Star], raw_entries: list[dict]) -> dict[str, Star]:
    index: dict[str, Star] = {}
    for star, entry in zip(stars, raw_entries, strict=True):
        keys = [star.name, star.designation or "", *entry.get("aliases", [])]
        for key in keys:
            if key:
                index.setdefault(normalize(key), star)
    return index


_index_cache: dict[str, Star] | None = None


def _load_index() -> dict[str, Star]:
    global _index_cache
    if _index_cache is None:
        with open(CATALOG_PATH, encoding="utf-8") as handle:
            raw = json.load(handle)
        _index_cache = _index(load_catalog(), raw)
    return _index_cache


def _suggestions(name: str, stars: list[Star]) -> list[str]:
    names = [star.name for star in stars]
    by_normalized = {normalize(n): n for n in names}
    close = difflib.get_close_matches(normalize(name), list(by_normalized), n=3, cutoff=0.75)
    return [by_normalized[key] for key in close]


def resolve(name: str, *, offline: bool = False) -> Star:
    """Resolve a star name to a `Star`, consulting SIMBAD if the catalog misses."""
    index = _load_index()
    star = index.get(normalize(name))
    if star is not None:
        return star

    if not offline:
        try:
            return simbad_lookup(name)
        except StarNotFoundError:
            raise StarNotFoundError(name, _suggestions(name, load_catalog())) from None

    raise StarNotFoundError(name, _suggestions(name, load_catalog()))
