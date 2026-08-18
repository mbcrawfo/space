import io
import json
import urllib.error

import pytest

import catalog
from catalog import SimbadError, StarNotFound, simbad_lookup

# Real responses recorded from the live SIMBAD TAP service on 2026-08-16,
# built here from the recorded values for readability. The `metadata` block
# is identical across queries against this endpoint/column set; only `data`
# varies per object.
_REAL_METADATA = [
    {
        "name": "main_id",
        "description": "Main identifier for an object",
        "datatype": "CHAR",
        "arraysize": "*",
        "ucd": "meta.id;meta.main",
        "utype": "mango:MangoObject.identifier",
    },
    {
        "name": "plx_value",
        "description": "Parallax",
        "datatype": "DOUBLE",
        "unit": "mas",
        "ucd": "pos.parallax.trig",
        "utype": "mango:EpochPosition.parallax[CS.spaceSys=ICRS CT.epoch=J2000]",
    },
    {
        "name": "plx_err",
        "description": "Parallax error",
        "datatype": "FLOAT",
        "unit": "mas",
        "ucd": "stat.error;pos.parallax.trig",
    },
]

# Betelgeuse: real parallax is 6.55 +/- 0.83 mas (152.67 pc), recorded live.
BETELGEUSE_RESPONSE = json.dumps(
    {
        "metadata": _REAL_METADATA,
        "data": [["* alf Ori", 6.55, 0.83]],
    }
)

# Unknown identifier: SIMBAD returns an empty data list, recorded live.
EMPTY_RESPONSE = json.dumps({"metadata": _REAL_METADATA, "data": []})

# Eta Carinae: a real, catalogued object with no measured parallax. Recorded
# live — the null-parallax case is not hypothetical, it happens for a
# well-known star.
NULL_PARALLAX_RESPONSE = json.dumps(
    {
        "metadata": _REAL_METADATA,
        "data": [["* eta Car", None, None]],
    }
)

SHORT_ROW_RESPONSE = json.dumps({"data": [["* alf Ori"]]})

NUMERIC_STRING_PARALLAX_RESPONSE = json.dumps(
    {
        "data": [["* alf Ori", "5.95", "0.58"]],
    }
)

NON_NUMERIC_PARALLAX_RESPONSE = json.dumps(
    {
        "data": [["* alf Ori", "not-a-number", "0.58"]],
    }
)

NULL_ROW_RESPONSE = json.dumps({"data": [None]})

ZERO_PARALLAX_RESPONSE = json.dumps({"data": [["* alf Ori", 0, 0.1]]})

NEGATIVE_PARALLAX_RESPONSE = json.dumps({"data": [["* alf Ori", -1.2, 0.1]]})

VALID_PARALLAX_NULL_ERR_RESPONSE = json.dumps(
    {
        "data": [["* alf Ori", 5.95, None]],
    }
)


def stub_fetch(monkeypatch, response=None, error=None):
    def fake(url, data, timeout):
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(catalog, "_http_post", fake)


def test_lookup_converts_parallax_to_distance(monkeypatch):
    stub_fetch(monkeypatch, response=BETELGEUSE_RESPONSE)
    star = simbad_lookup("Betelgeuse")
    assert star.name == "* alf Ori"
    assert star.distance_pc == pytest.approx(1000 / 6.55)  # 152.67 pc
    assert star.distance_pc_err == pytest.approx(1000 * 0.83 / 6.55**2, rel=1e-6)
    assert star.source == "SIMBAD"


def test_lookup_of_an_unknown_object_is_a_miss(monkeypatch):
    stub_fetch(monkeypatch, response=EMPTY_RESPONSE)
    with pytest.raises(StarNotFound):
        simbad_lookup("zzzzzzzz")


def test_lookup_without_a_usable_parallax_is_a_miss(monkeypatch):
    stub_fetch(monkeypatch, response=NULL_PARALLAX_RESPONSE)
    with pytest.raises(StarNotFound):
        simbad_lookup("Eta Carinae")


def test_timeout_reports_the_timeout_value(monkeypatch):
    stub_fetch(monkeypatch, error=TimeoutError("timed out"))
    with pytest.raises(SimbadError) as excinfo:
        simbad_lookup("Betelgeuse", timeout=7.5)
    message = str(excinfo.value)
    assert "7.5" in message
    assert "respond" in message.lower()


def test_url_error_reports_could_not_reach(monkeypatch):
    stub_fetch(monkeypatch, error=urllib.error.URLError("no route to host"))
    with pytest.raises(SimbadError) as excinfo:
        simbad_lookup("Betelgeuse")
    message = str(excinfo.value)
    assert "could not reach" in message.lower()
    assert "no route to host" in message


def test_http_error_reports_status_and_body(monkeypatch):
    error = urllib.error.HTTPError(
        "url", 400, "Bad Request", {}, io.BytesIO(b"Bad column name: xyz")
    )
    stub_fetch(monkeypatch, error=error)
    with pytest.raises(SimbadError) as excinfo:
        simbad_lookup("Betelgeuse")
    message = str(excinfo.value)
    assert "400" in message
    assert "Bad column name: xyz" in message
    # Must be distinguishable from a plain connectivity failure.
    assert "could not reach" not in message.lower()


def test_http_error_truncates_a_long_body(monkeypatch):
    long_body = b"x" * 5000
    error = urllib.error.HTTPError("url", 500, "Server Error", {}, io.BytesIO(long_body))
    stub_fetch(monkeypatch, error=error)
    with pytest.raises(SimbadError) as excinfo:
        simbad_lookup("Betelgeuse")
    assert len(str(excinfo.value)) < 400


def test_http_error_falls_back_when_body_cannot_be_read(monkeypatch):
    class UnreadableFile:
        def read(self):
            raise OSError("stream already consumed")

        def close(self):
            pass

    error = urllib.error.HTTPError("url", 503, "Service Unavailable", {}, UnreadableFile())
    stub_fetch(monkeypatch, error=error)
    with pytest.raises(SimbadError) as excinfo:
        simbad_lookup("Betelgeuse")
    assert "503" in str(excinfo.value)


def test_malformed_response_becomes_a_simbad_error(monkeypatch):
    stub_fetch(monkeypatch, response="<html>not json</html>")
    with pytest.raises(SimbadError):
        simbad_lookup("Betelgeuse")


def test_row_shorter_than_expected_becomes_a_star_not_found(monkeypatch):
    stub_fetch(monkeypatch, response=SHORT_ROW_RESPONSE)
    with pytest.raises(StarNotFound):
        simbad_lookup("Betelgeuse")


def test_non_numeric_parallax_becomes_a_simbad_error(monkeypatch):
    stub_fetch(monkeypatch, response=NON_NUMERIC_PARALLAX_RESPONSE)
    with pytest.raises(SimbadError):
        simbad_lookup("Betelgeuse")


def test_numeric_string_parallax_is_still_coerced_and_succeeds(monkeypatch):
    # SIMBAD's JSON-over-HTTP path can hand back numbers as strings; the
    # coercion should accept those rather than treating them as malformed.
    stub_fetch(monkeypatch, response=NUMERIC_STRING_PARALLAX_RESPONSE)
    star = simbad_lookup("Betelgeuse")
    assert star.distance_pc == pytest.approx(1000 / 5.95)


def test_null_row_becomes_a_simbad_error(monkeypatch):
    stub_fetch(monkeypatch, response=NULL_ROW_RESPONSE)
    with pytest.raises(SimbadError):
        simbad_lookup("Betelgeuse")


def test_zero_parallax_is_a_miss(monkeypatch):
    stub_fetch(monkeypatch, response=ZERO_PARALLAX_RESPONSE)
    with pytest.raises(StarNotFound):
        simbad_lookup("Betelgeuse")


def test_negative_parallax_is_a_miss(monkeypatch):
    stub_fetch(monkeypatch, response=NEGATIVE_PARALLAX_RESPONSE)
    with pytest.raises(StarNotFound):
        simbad_lookup("Betelgeuse")


def test_valid_parallax_with_null_error_bar_still_resolves(monkeypatch):
    stub_fetch(monkeypatch, response=VALID_PARALLAX_NULL_ERR_RESPONSE)
    star = simbad_lookup("Betelgeuse")
    assert star.distance_pc == pytest.approx(1000 / 5.95)
    assert star.distance_pc_err is None


def test_resolve_falls_back_to_simbad_when_the_catalog_misses(monkeypatch):
    stub_fetch(monkeypatch, response=BETELGEUSE_RESPONSE)
    star = catalog.resolve("some obscure star")
    assert star.source == "SIMBAD"


def test_offline_never_calls_the_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("the network must not be touched in offline mode")

    monkeypatch.setattr(catalog, "_http_post", explode)
    with pytest.raises(StarNotFound):
        catalog.resolve("some obscure star", offline=True)


def test_catalog_hits_never_call_the_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("a catalog hit must not touch the network")

    monkeypatch.setattr(catalog, "_http_post", explode)
    assert catalog.resolve("Betelgeuse").name == "Betelgeuse"
