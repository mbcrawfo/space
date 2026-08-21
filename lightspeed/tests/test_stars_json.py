import json
import math
import os

import pytest

STARS_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stars.json")
FIELDS = {"name": str, "ra_deg": float, "dec_deg": float, "distance_ly": float, "source": str}


def load_raw():
    with open(STARS_JSON, encoding="utf-8") as handle:
        return json.load(handle)


def test_the_catalog_is_a_list_of_well_typed_entries():
    entries = load_raw()
    assert isinstance(entries, list)
    for entry in entries:
        assert set(entry) == set(FIELDS), entry
        for field, kind in FIELDS.items():
            assert isinstance(entry[field], kind), (entry["name"], field)


def test_every_coordinate_is_in_range_and_finite():
    for entry in load_raw():
        assert 0.0 <= entry["ra_deg"] < 360.0, entry["name"]
        assert -90.0 <= entry["dec_deg"] <= 90.0, entry["name"]
        assert 0.0 < entry["distance_ly"] <= 20.0, entry["name"]
        assert all(math.isfinite(entry[f]) for f in ("ra_deg", "dec_deg", "distance_ly")), entry["name"]


def test_names_are_unique_and_sol_is_not_in_the_file():
    names = [entry["name"] for entry in load_raw()]
    assert len(names) == len(set(names))
    assert "Sol" not in names


def test_entries_are_sorted_by_distance():
    distances = [entry["distance_ly"] for entry in load_raw()]
    assert distances == sorted(distances)


def test_there_are_roughly_a_hundred_systems():
    assert 80 <= len(load_raw()) <= 130


@pytest.mark.parametrize(
    ("name", "distance_ly"),
    [
        ("Proxima Centauri", 4.25),
        ("Alpha Centauri", 4.37),
        ("Barnard's Star", 5.96),
        ("Sirius", 8.6),
        ("Tau Ceti", 11.9),
    ],
)
def test_anchor_distances_are_sane(name, distance_ly):
    """Catches a transcription slip (parsecs left as parsecs, a wrong identifier) before it reaches the screen."""
    by_name = {entry["name"]: entry for entry in load_raw()}
    assert name in by_name
    assert by_name[name]["distance_ly"] == pytest.approx(distance_ly, abs=0.1)
