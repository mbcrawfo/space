import json
import math

import pytest

from lightspeed import catalog


def star(name="Test", ra=0.0, dec=0.0, distance=1.0):
    return catalog.Star(name=name, ra_deg=ra, dec_deg=dec, distance_ly=distance, source="test")


def test_ra_zero_dec_zero_points_along_plus_x():
    assert star(ra=0.0, dec=0.0, distance=2.0).position == pytest.approx((2.0, 0.0, 0.0))


def test_ra_ninety_points_along_plus_y():
    assert star(ra=90.0, dec=0.0, distance=3.0).position == pytest.approx((0.0, 3.0, 0.0), abs=1e-12)


def test_the_north_celestial_pole_points_along_plus_z():
    assert star(ra=123.0, dec=90.0, distance=5.0).position == pytest.approx((0.0, 0.0, 5.0), abs=1e-12)


def test_the_position_preserves_the_distance():
    x, y, z = star(ra=217.4, dec=-62.7, distance=4.2465).position
    assert math.hypot(x, y, z) == pytest.approx(4.2465)


def test_sol_sits_at_the_origin():
    assert catalog.SOL.position == (0.0, 0.0, 0.0)
    assert catalog.SOL.distance_ly == 0.0


def test_labels_carry_the_name_and_one_decimal_distance():
    assert star(name="Proxima Centauri", distance=4.2465).label == "Proxima Centauri (4.2 ly)"
    assert catalog.SOL.label == "Sol (0 ly)"


def test_load_prepends_sol_and_reads_the_bundled_file():
    stars = catalog.load()
    assert stars[0] is catalog.SOL
    assert stars[1].name == "Proxima Centauri"
    assert len(stars) >= 81


def write_catalog(tmp_path, payload):
    path = tmp_path / "stars.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


GOOD = {"name": "A", "ra_deg": 10.0, "dec_deg": -5.0, "distance_ly": 4.0, "source": "t"}


def test_load_accepts_a_well_formed_entry(tmp_path):
    stars = catalog.load(write_catalog(tmp_path, [GOOD]))
    assert [s.name for s in stars] == ["Sol", "A"]


def test_load_raises_for_a_missing_file(tmp_path):
    with pytest.raises(catalog.CatalogError, match=r"stars\.json"):
        catalog.load(str(tmp_path / "nope" / "stars.json"))


def test_load_raises_for_unparseable_json(tmp_path):
    path = tmp_path / "stars.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(catalog.CatalogError, match="not valid JSON"):
        catalog.load(str(path))


def test_load_raises_when_the_file_is_not_a_list(tmp_path):
    with pytest.raises(catalog.CatalogError, match="list"):
        catalog.load(write_catalog(tmp_path, {"name": "A"}))


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "ra_deg": "ten"},
        {k: v for k, v in GOOD.items() if k != "dec_deg"},
        {**GOOD, "ra_deg": 360.0},
        {**GOOD, "ra_deg": -1.0},
        {**GOOD, "dec_deg": 91.0},
        {**GOOD, "distance_ly": 0.0},
        {**GOOD, "distance_ly": -3.0},
        {**GOOD, "distance_ly": float("inf")},
        {**GOOD, "name": ""},
    ],
)
def test_load_names_the_offending_entry(tmp_path, bad):
    with pytest.raises(catalog.CatalogError) as exc_info:
        catalog.load(write_catalog(tmp_path, [GOOD | {"name": "Fine"}, bad]))
    message = str(exc_info.value)
    assert "entry 2" in message or bad.get("name", "") in message


def test_within_keeps_sol_and_everything_closer_than_the_limit():
    stars = [
        catalog.SOL,
        star(name="near", distance=4.0),
        star(name="edge", distance=10.0),
        star(name="far", distance=10.1),
    ]
    assert [s.name for s in catalog.within(stars, 10.0)] == ["Sol", "near", "edge"]
