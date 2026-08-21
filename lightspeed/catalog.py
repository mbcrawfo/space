"""The bundled catalogue of nearby stars, and where each one sits in space.

`stars.json` carries one entry per stellar *system* out to 20 light-years: a display
name, ICRS right ascension and declination in degrees, the distance in light-years, and
where the parallax came from. Sol is not in the file; `load()` puts it at the origin.
Positions are plain Cartesian light-years — one scene unit is one light-year, so the
tool never has to scale anything but the camera.
"""

import json
import math
import os
from dataclasses import dataclass

CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stars.json")

_FIELDS = {"name": str, "ra_deg": (int, float), "dec_deg": (int, float), "distance_ly": (int, float), "source": str}


class CatalogError(Exception):
    """The bundled catalogue is missing, unreadable, or carries an entry that cannot be placed."""


@dataclass(frozen=True)
class Star:
    name: str
    ra_deg: float
    dec_deg: float
    distance_ly: float
    source: str

    @property
    def position(self) -> tuple[float, float, float]:
        """Cartesian light-years: x toward the vernal equinox, z toward the north celestial pole."""
        ra = math.radians(self.ra_deg)
        dec = math.radians(self.dec_deg)
        flat = self.distance_ly * math.cos(dec)
        return (flat * math.cos(ra), flat * math.sin(ra), self.distance_ly * math.sin(dec))

    @property
    def label(self) -> str:
        if self.distance_ly == 0.0:
            return f"{self.name} (0 ly)"
        return f"{self.name} ({self.distance_ly:.1f} ly)"


SOL = Star(name="Sol", ra_deg=0.0, dec_deg=0.0, distance_ly=0.0, source="origin")


def _parse_entry(index: int, raw: object) -> Star:
    """Turn one JSON object into a Star, or say exactly which entry is wrong and why."""
    where = f"entry {index}"
    if isinstance(raw, dict) and isinstance(raw.get("name"), str) and raw["name"]:
        where += f" ({raw['name']})"
    if not isinstance(raw, dict):
        raise CatalogError(f"{where} in the star catalogue is not an object.")
    for field, kind in _FIELDS.items():
        if field not in raw:
            raise CatalogError(f"{where} in the star catalogue is missing '{field}'.")
        if not isinstance(raw[field], kind) or isinstance(raw[field], bool):
            raise CatalogError(
                f"{where} in the star catalogue has a non-{kind.__name__ if isinstance(kind, type) else 'numeric'} '{field}'."
            )
    name = raw["name"]
    if not name:
        raise CatalogError(f"{where} in the star catalogue has an empty name.")
    ra, dec, distance = float(raw["ra_deg"]), float(raw["dec_deg"]), float(raw["distance_ly"])
    if not (math.isfinite(ra) and 0.0 <= ra < 360.0):
        raise CatalogError(f"{where} in the star catalogue has right ascension {ra}, outside [0, 360).")
    if not (math.isfinite(dec) and -90.0 <= dec <= 90.0):
        raise CatalogError(f"{where} in the star catalogue has declination {dec}, outside [-90, 90].")
    if not (math.isfinite(distance) and distance > 0.0):
        raise CatalogError(
            f"{where} in the star catalogue has distance {distance}; it must be a positive, finite number of light-years."
        )
    return Star(name=name, ra_deg=ra, dec_deg=dec, distance_ly=distance, source=raw["source"])


def load(path: str | None = None) -> list[Star]:
    """Sol, then every catalogued star in file order (which is ascending distance)."""
    path = path or CATALOG_PATH
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as exc:
        raise CatalogError(f"Cannot read the star catalogue at {path}: {exc.strerror or exc}.") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"The star catalogue at {path} is not valid JSON: {exc}.") from exc
    if not isinstance(raw, list):
        raise CatalogError(f"The star catalogue at {path} must be a JSON list of stars.")
    return [SOL, *(_parse_entry(index, entry) for index, entry in enumerate(raw, start=1))]


def within(stars: list[Star], max_ly: float) -> list[Star]:
    """Every star no farther than `max_ly` from Sol (Sol included)."""
    return [star for star in stars if star.distance_ly <= max_ly]
