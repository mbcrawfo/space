import pytest

import catalog
from catalog import StarNotFound, load_catalog, normalize, resolve


def test_normalize_collapses_case_spacing_and_punctuation():
    assert normalize("Barnard's Star") == "barnardsstar"
    assert normalize("  SIRIUS  ") == "sirius"
    assert normalize("61 Cygni") == "61cygni"
    assert normalize("HD 48915") == "hd48915"


def test_normalize_expands_greek_letters():
    assert normalize("α Orionis") == normalize("Alpha Orionis")
    assert normalize("β Cyg") == "betacyg"
    assert normalize("η Carinae") == "etacarinae"


def test_catalog_loads_and_every_entry_is_well_formed():
    stars = load_catalog()
    assert len(stars) >= 50
    for star in stars:
        assert star.name
        assert star.distance_pc > 0
        assert star.source
        if star.distance_pc_err is not None:
            assert star.distance_pc_err >= 0


def test_resolve_finds_a_star_by_its_common_name():
    star = resolve("Betelgeuse", offline=True)
    assert star.name == "Betelgeuse"
    assert star.distance_pc == pytest.approx(168.1)
    assert star.source == "Hipparcos (revised)"


def test_resolve_ignores_case_spacing_and_punctuation():
    for query in ["betelgeuse", "BETELGEUSE", "  Betelgeuse  "]:
        assert resolve(query, offline=True).name == "Betelgeuse"


def test_resolve_finds_a_star_by_designation_alias_or_catalogue_number():
    assert resolve("Alpha Orionis", offline=True).name == "Betelgeuse"
    assert resolve("α Ori", offline=True).name == "Betelgeuse"
    assert resolve("HD 39801", offline=True).name == "Betelgeuse"
    assert resolve("north star", offline=True).name == "Polaris"


def test_resolve_raises_with_suggestions_for_a_near_miss():
    with pytest.raises(StarNotFound) as excinfo:
        resolve("Betelgeus", offline=True)
    assert "Betelgeuse" in excinfo.value.suggestions


def test_resolve_raises_without_suggestions_for_nonsense():
    with pytest.raises(StarNotFound) as excinfo:
        resolve("zzzzzzzz", offline=True)
    assert excinfo.value.suggestions == []
    assert excinfo.value.name == "zzzzzzzz"


def test_load_index_is_cached_and_does_not_reread_the_catalog_file(monkeypatch):
    # Force a fresh index build, then confirm a second call reuses it
    # instead of reopening stars.json.
    monkeypatch.setattr(catalog, "_index_cache", None)
    first = catalog._load_index()

    real_open = open

    def explode(*args, **kwargs):
        raise AssertionError("_load_index must not reread the catalog once cached")

    monkeypatch.setattr("builtins.open", explode)
    second = catalog._load_index()
    monkeypatch.setattr("builtins.open", real_open)

    assert second is first
