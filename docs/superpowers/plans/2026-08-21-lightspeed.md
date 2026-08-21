# lightspeed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new tool, `lightspeed`, that opens a 3D desktop window centred on Sol, places ~100 nearby star systems at their true relative positions with name-and-distance labels, and on the user's command shows one flash of light from every star growing as a translucent sphere at 1 ly/yr while the user orbits and zooms the camera.

**Architecture:** Four flat modules inside the `lightspeed/` package: `catalog.py` (bundled `stars.json` → `Star` objects with Cartesian positions), `simulation.py` (pure numpy state: clock, speed, shell radius, precomputed arrival events), `viewer.py` (the PyVista scene, built against an injected plotter so tests never open a window), and `__main__.py` (the argparse CLI in the house style). Tests drive the viewer through a recording `FakePlotter`; a conftest guard makes a real `Plotter.show()` fail loudly.

**Tech Stack:** Python ≥ 3.10, numpy, pyvista 0.48 (VTK 9.6), pytest, ruff, uv workspace.

**Spec:** `docs/superpowers/specs/2026-08-21-lightspeed-design.md`

## Global Constraints

- **Repo rules are in `CLAUDE.md` — read it first.** Tools never import each other. Modules are flat in the package (`lightspeed/catalog.py`, not `lightspeed/src/...`). `tests/` has no `__init__.py`.
- **Ruff is the only linter/formatter**: line length 120, double quotes; `uv run ruff check . && uv run ruff format .` must be clean before every commit. Suppress narrowly (`# noqa: RULE - reason`), never bare `# noqa`. Exception classes end in `Error`.
- **No network and no windows in tests.** Nothing in `lightspeed/tests/` may reach the network or call `pyvista.Plotter.show`.
- **Dependencies:** `lightspeed/pyproject.toml` declares `["numpy>=1.26", "pyvista>=0.44"]` and `[tool.uv] package = false`. Because members are virtual, install with **`uv sync --all-packages`** (plain `uv sync` installs only the root's deps).
- **CLI standard** (CLAUDE.md "CLI help and error output"): `prog="python -m lightspeed"`, `RawDescriptionHelpFormatter`, hand-wrapped `DESCRIPTION`/`EXAMPLES` at ~88 columns, `_HelpOnErrorParser` (own copy), `help=` on every argument naming the accepted values, the default, and the effect; argparse errors print the whole help to stderr then exit 2; value errors stay concise with a "Try …" hint.
- **Work on branch `lightspeed`** (already created). Commit after each task with a short imperative subject, body if useful, and the trailers `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01TodP5hXaNGoukNqAthNUzA`.
- Verified against the installed pyvista 0.48.4 / VTK 9.6.2 (do not change these idioms without re-verifying): `add_timer_event(max_steps, duration, callback)` — callback receives `step`; `add_key_event(key, callback)` — callback takes no arguments; `add_text(text, position=..., font_size=..., color=..., name=...)` — same `name` replaces the previous actor, and **text must get an explicit `color`** (default theme draws it black); `add_mesh(polydata, scalars="rgb", rgb=True, render_points_as_spheres=True, point_size=...)` — mutating `polydata["rgb"]` in place then `plotter.render()` re-colours the points; `Actor.position`, `Actor.scale`, `Actor.visibility` are settable properties; `add_point_labels(points, labels, shape=None, show_points=False, always_visible=True, text_color=..., font_size=...)`; `enable_depth_peeling()`; `set_background("black")`; `camera_position = [(eye), (focal), (up)]`.

---

### Task 1: Package scaffold, workspace wiring, and the no-window guard

**Files:**
- Already present (created while planning; verify contents): `lightspeed/pyproject.toml`, `lightspeed/__init__.py`, root `pyproject.toml` (`members = ["lightspeed", "spacetime", "starlight"]`), `uv.lock` (already resynced).
- Create: `lightspeed/conftest.py`, `lightspeed/tests/test_conftest_guard.py`
- Modify: `.github/workflows/ci.yml` (the `Install dependencies` step)

**Interfaces:**
- Produces: the importable package `lightspeed`, a venv where `import pyvista` works, and a session-wide guard that `pyvista.Plotter.show` raises `AssertionError` inside the test suite.

- [ ] **Step 1: Verify the scaffold that already exists**

```bash
cat lightspeed/pyproject.toml lightspeed/__init__.py
grep members pyproject.toml
uv sync --all-packages
uv run python -c "import pyvista, numpy; print(pyvista.__version__, numpy.__version__)"
```

Expected: `pyproject.toml` has `dependencies = ["numpy>=1.26", "pyvista>=0.44"]` and `package = false`; members list includes `"lightspeed"`; the import prints `0.48.x 2.x`. If `lightspeed/pyproject.toml` or `__init__.py` are missing, create them exactly as shown in the spec's Structure section (`__init__.py` is a two-line docstring: `"""A 3D view of light spreading out from the nearest stars.\n\nRun it with ``python -m lightspeed``; see ``__main__`` for the CLI.\n"""`).

- [ ] **Step 2: Write the failing guard test**

`lightspeed/tests/test_conftest_guard.py`:

```python
import pytest
import pyvista


def test_opening_a_window_in_the_test_suite_fails_loudly():
    """conftest.py patches Plotter.show for the whole session; an accidental window must not slip through."""
    plotter = pyvista.Plotter(off_screen=True)
    with pytest.raises(AssertionError, match="Plotter.show"):
        plotter.show()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `uv run pytest lightspeed/tests/test_conftest_guard.py -v`
Expected: FAIL — `DID NOT RAISE` (or a VTK render of an empty off-screen window, which returns normally).

- [ ] **Step 4: Write the guard**

`lightspeed/conftest.py`:

```python
"""Session-wide guarantee that the test suite never opens a render window.

`pyvista.Plotter.show` is the only call that would put a VTK window on screen (or, in
CI, fail for want of a display). This patches it to explode for the whole session,
structurally, rather than relying on every test file remembering not to call it. The
viewer is built against an injected plotter precisely so tests can pass a recording
fake and never need the real thing.
"""

import pytest
import pyvista
from _pytest.monkeypatch import MonkeyPatch


def _explode(*args, **kwargs):
    raise AssertionError("a test tried to open a window via pyvista.Plotter.show; drive the Viewer with a fake plotter instead")


@pytest.fixture(scope="session", autouse=True)
def _no_window_session_guard():
    mp = MonkeyPatch()
    mp.setattr(pyvista.Plotter, "show", _explode)
    yield
    mp.undo()
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest lightspeed/tests/test_conftest_guard.py -v`
Expected: PASS.

- [ ] **Step 6: Make CI install member dependencies**

In `.github/workflows/ci.yml` change the install step:

```yaml
      - name: Install dependencies
        run: uv sync --all-packages --locked
```

Do not touch the pinned action SHAs.

- [ ] **Step 7: Lint, format, full suite**

Run: `uv run ruff check . && uv run ruff format . && uv run pytest -q`
Expected: no lint errors, formatter changes nothing (or only your new files), all tests pass (197 existing + 1).

- [ ] **Step 8: Commit**

```bash
git add lightspeed/pyproject.toml lightspeed/__init__.py lightspeed/conftest.py lightspeed/tests/test_conftest_guard.py pyproject.toml uv.lock .github/workflows/ci.yml
git commit -m "Scaffold the lightspeed tool and guard tests against opening windows"
```

---

### Task 2: The bundled star catalogue (`stars.json`)

**Files:**
- Create: `lightspeed/stars.json`
- Create: `lightspeed/tests/test_stars_json.py`
- Scratch (not committed): `<scratchpad>/build_catalog.py`

**Interfaces:**
- Produces: `lightspeed/stars.json` — a JSON array of objects `{"name": str, "ra_deg": float, "dec_deg": float, "distance_ly": float, "source": str}` sorted by ascending `distance_ly`, every entry ≤ 20.0 ly, names unique, ~100 entries. `catalog.load()` (Task 3) reads exactly this shape.

- [ ] **Step 1: Write the failing integrity test**

`lightspeed/tests/test_stars_json.py`:

```python
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
    [("Proxima Centauri", 4.25), ("Alpha Centauri", 4.37), ("Barnard's Star", 5.96), ("Sirius", 8.6), ("Tau Ceti", 11.9)],
)
def test_anchor_distances_are_sane(name, distance_ly):
    """Catches a transcription slip (parsecs left as parsecs, a wrong identifier) before it reaches the screen."""
    by_name = {entry["name"]: entry for entry in load_raw()}
    assert name in by_name
    assert by_name[name]["distance_ly"] == pytest.approx(distance_ly, abs=0.1)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest lightspeed/tests/test_stars_json.py -v`
Expected: FAIL with `FileNotFoundError` for `stars.json`.

- [ ] **Step 3: Write the one-off build script in the scratchpad (NOT in the repo)**

Save as `<scratchpad>/build_catalog.py` (use the scratchpad directory from your environment). It queries SIMBAD's TAP service — the same endpoint `starlight/catalog.py` uses — one identifier at a time, and keeps what resolves within 20 ly.

```python
"""One-off: build lightspeed/stars.json from SIMBAD. Not shipped; provenance is in each entry's `source`."""

import json
import sys
import urllib.parse
import urllib.request

LY_PER_PC = 3.26156378
TAP = "https://simbad.cds.unistra.fr/simbad/sim-tap/sync"
TODAY = "2026-08-21"
MAX_LY = 20.0

# (display name, SIMBAD identifier). One entry per *system*; the identifier picks the
# primary so a binary yields one position. Candidates beyond 20 ly are harmless — the
# distance filter drops them — and brown dwarfs without a SIMBAD parallax are reported.
CANDIDATES = [
    ("Proxima Centauri", "Proxima Centauri"),
    ("Alpha Centauri", "alf Cen A"),
    ("Barnard's Star", "Barnard's star"),
    ("Luhman 16", "Luhman 16"),
    ("WISE 0855-0714", "WISE J085510.83-071442.5"),
    ("Wolf 359", "Wolf 359"),
    ("Lalande 21185", "Lalande 21185"),
    ("Sirius", "Sirius"),
    ("Luyten 726-8", "BL Cet"),
    ("Ross 154", "Ross 154"),
    ("Ross 248", "Ross 248"),
    ("Epsilon Eridani", "eps Eri"),
    ("Lacaille 9352", "Lacaille 9352"),
    ("Ross 128", "Ross 128"),
    ("EZ Aquarii", "EZ Aqr"),
    ("61 Cygni", "61 Cyg A"),
    ("Procyon", "Procyon"),
    ("Struve 2398", "HD 173739"),
    ("Groombridge 34", "GX And"),
    ("DX Cancri", "DX Cnc"),
    ("Epsilon Indi", "eps Ind"),
    ("Tau Ceti", "tau Cet"),
    ("GJ 1061", "GJ 1061"),
    ("YZ Ceti", "YZ Cet"),
    ("Luyten's Star", "Luyten's star"),
    ("Teegarden's Star", "Teegarden's star"),
    ("Kapteyn's Star", "Kapteyn's star"),
    ("Lacaille 8760", "Lacaille 8760"),
    ("SCR 1845-6357", "SCR J1845-6357"),
    ("Kruger 60", "Kruger 60"),
    ("DENIS 1048-3956", "DENIS J1048.0-3956"),
    ("UGPS 0722-05", "UGPS J072227.51-054031.2"),
    ("Ross 614", "Ross 614"),
    ("Wolf 1061", "Wolf 1061"),
    ("Van Maanen's Star", "van Maanen's star"),
    ("Gliese 1", "Gl 1"),
    ("Wolf 424", "Wolf 424"),
    ("TZ Arietis", "TZ Ari"),
    ("Gliese 687", "Gl 687"),
    ("LHS 292", "LHS 292"),
    ("Gliese 674", "Gl 674"),
    ("GJ 1245", "G 208-44"),
    ("Gliese 440", "Gl 440"),
    ("Gliese 876", "Gl 876"),
    ("LHS 288", "LHS 288"),
    ("GJ 1002", "GJ 1002"),
    ("Gliese 412", "Gl 412"),
    ("Groombridge 1618", "Groombridge 1618"),
    ("AD Leonis", "AD Leo"),
    ("Gliese 832", "Gl 832"),
    ("Gliese 682", "Gl 682"),
    ("DENIS 0255-4700", "DENIS J025503.3-470049"),
    ("EI Cancri", "GJ 1116"),
    ("Altair", "Altair"),
    ("GJ 1005", "GJ 1005"),
    ("EV Lacertae", "EV Lac"),
    ("70 Ophiuchi", "70 Oph"),
    ("Stein 2051", "G 175-34"),
    ("Gliese 445", "Gl 445"),
    ("Gliese 526", "Gl 526"),
    ("Gliese 251", "Gl 251"),
    ("Gliese 205", "Gl 205"),
    ("Gliese 229", "Gl 229"),
    ("Sigma Draconis", "sig Dra"),
    ("Gliese 693", "Gl 693"),
    ("Gliese 752", "Gl 752"),
    ("Gliese 754", "Gl 754"),
    ("Gliese 588", "Gl 588"),
    ("Eta Cassiopeiae", "eta Cas"),
    ("36 Ophiuchi", "36 Oph"),
    ("Gliese 570", "Gl 570"),
    ("LHS 1723", "LHS 1723"),
    ("Gliese 213", "Gl 213"),
    ("82 Eridani", "82 Eri"),
    ("Delta Pavonis", "del Pav"),
    ("LP 816-60", "LP 816-60"),
    ("GJ 3379", "GJ 3379"),
    ("LHS 2090", "LHS 2090"),
    ("WISE 1639-6847", "WISE J163940.83-684738.6"),
    ("WISE 0350-5658", "WISE J035000.32-565830.2"),
    ("SIMP 0136+0933", "SIMP J013656.5+093347"),
    ("WISE 1506+7027", "WISE J150649.97+702736.0"),
    ("LSR 1835+3259", "LSR J1835+3259"),
    ("GJ 3622", "GJ 3622"),
    ("Gliese 784", "Gl 784"),
    ("Gliese 908", "Gl 908"),
    ("Gliese 555", "Gl 555"),
    ("Gliese 783", "Gl 783"),
    ("Gliese 338", "Gl 338"),
    ("Gliese 581", "Gl 581"),
    ("YZ Canis Minoris", "YZ CMi"),
    ("DENIS 0817-6155", "DENIS J081730.0-615520"),
    ("WISE 0410+1502", "WISE J041022.71+150248.5"),
    ("WISE 1541-2250", "WISE J154151.65-225024.9"),
    ("WISE 1405+5534", "WISE J140518.40+553421.4"),
    ("2MASS 0937+2931", "2MASS J09373487+2931409"),
    ("WISE 1741+2553", "WISE J174124.26+255319.5"),
    ("2MASS 1540-5101", "2MASS J15404341-5101357"),
    ("LHS 3003", "LHS 3003"),
    ("Gliese 625", "Gl 625"),
    ("Wolf 629", "Wolf 629"),
    ("Wolf 630", "Gl 644"),
    ("GJ 1128", "GJ 1128"),
    ("Gliese 402", "Gl 402"),
    ("Gliese 408", "Gl 408"),
    ("LP 944-20", "LP 944-20"),
    ("GJ 1156", "GJ 1156"),
    ("GJ 1151", "GJ 1151"),
    ("Wolf 922", "Wolf 922"),
    ("LTT 1445", "LTT 1445"),
    ("LHS 1070", "LHS 1070"),
    ("Gliese 667", "Gl 667"),
    ("LHS 2065", "LHS 2065"),
    ("WISE 2000+3629", "WISE J200050.19+362950.1"),
]


def query(identifier: str):
    escaped = identifier.replace("'", "''")
    adql = (
        "SELECT TOP 1 b.main_id, b.ra, b.dec, b.plx_value, b.plx_bibcode "
        "FROM basic AS b JOIN ident AS i ON b.oid = i.oidref "
        f"WHERE i.id = '{escaped}'"
    )
    payload = urllib.parse.urlencode({"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "json", "QUERY": adql}).encode()
    request = urllib.request.Request(TAP, data=payload, headers={"User-Agent": "space-lightspeed-catalog-build/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.loads(response.read())["data"]
    return rows[0] if rows else None


def main() -> int:
    kept, dropped = [], []
    for name, identifier in CANDIDATES:
        row = query(identifier)
        if row is None or row[1] is None or row[2] is None or not row[3]:
            dropped.append((name, identifier, "no SIMBAD match or no parallax"))
            continue
        _main_id, ra, dec, plx, bibcode = row
        distance_ly = LY_PER_PC * 1000.0 / plx
        if distance_ly > MAX_LY:
            dropped.append((name, identifier, f"{distance_ly:.2f} ly"))
            continue
        kept.append(
            {
                "name": name,
                "ra_deg": round(float(ra), 5),
                "dec_deg": round(float(dec), 5),
                "distance_ly": round(distance_ly, 4),
                "source": f"SIMBAD plx {bibcode or 'unknown'}, queried {TODAY}",
            }
        )
        print(f"kept    {name:22s} {distance_ly:6.2f} ly", file=sys.stderr)
    kept.sort(key=lambda entry: entry["distance_ly"])
    for name, identifier, why in dropped:
        print(f"dropped {name:22s} ({identifier}): {why}", file=sys.stderr)
    print(f"{len(kept)} kept, {len(dropped)} dropped", file=sys.stderr)
    with open("lightspeed/stars.json", "w", encoding="utf-8") as handle:
        json.dump(kept, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run it **from the repo root** so it writes `lightspeed/stars.json`:

Run: `uv run python <scratchpad>/build_catalog.py`
Expected: stderr lists ~95–110 kept entries and the dropped ones; `lightspeed/stars.json` exists. Read the stderr: a "dropped … no SIMBAD match" for a *well-known star* (Sirius, Procyon, Altair, an Alpha Centauri) means the identifier is wrong — fix the identifier in `CANDIDATES` and rerun. Dropped brown dwarfs and > 20 ly candidates are expected.

If SIMBAD is unreachable after a few retries, stop and report it rather than inventing numbers.

- [ ] **Step 4: Eyeball the result**

Run: `uv run python -c "import json; e=json.load(open('lightspeed/stars.json')); print(len(e)); [print(f'{x[\"distance_ly\"]:6.2f} {x[\"name\"]}') for x in e]"`
Expected: Proxima ≈ 4.25 first, Alpha Centauri ≈ 4.37, Barnard's ≈ 5.96, Sirius ≈ 8.6, Procyon ≈ 11.4, Altair ≈ 16.7; last entries just under 20.

- [ ] **Step 5: Run the integrity test**

Run: `uv run pytest lightspeed/tests/test_stars_json.py -v`
Expected: all PASS. If the count test fails because fewer than 80 survived, add more candidates (any system from the RECONS nearest-star list within 20 ly) and rerun the script.

- [ ] **Step 6: Lint/format and commit**

Run: `uv run ruff check . && uv run ruff format . && uv run pytest lightspeed -q`

```bash
git add lightspeed/stars.json lightspeed/tests/test_stars_json.py
git commit -m "Bundle the nearest-star catalogue for lightspeed"
```

---

### Task 3: `catalog.py` — stars, positions, labels

**Files:**
- Create: `lightspeed/catalog.py`
- Create: `lightspeed/tests/test_catalog.py`

**Interfaces:**
- Consumes: `lightspeed/stars.json` (Task 2).
- Produces:
  ```python
  @dataclass(frozen=True)
  class Star: name: str; ra_deg: float; dec_deg: float; distance_ly: float; source: str
      position -> tuple[float, float, float]   # property, light-years
      label -> str                              # property
  class CatalogError(Exception)
  SOL: Star
  CATALOG_PATH: str
  def load(path: str | None = None) -> list[Star]
  def within(stars: list[Star], max_ly: float) -> list[Star]
  ```

- [ ] **Step 1: Write the failing tests**

`lightspeed/tests/test_catalog.py`:

```python
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
    with pytest.raises(catalog.CatalogError, match="stars.json"):
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
    stars = [catalog.SOL, star(name="near", distance=4.0), star(name="edge", distance=10.0), star(name="far", distance=10.1)]
    assert [s.name for s in catalog.within(stars, 10.0)] == ["Sol", "near", "edge"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest lightspeed/tests/test_catalog.py -q`
Expected: FAIL with `ImportError: cannot import name 'catalog'` (module does not exist).

- [ ] **Step 3: Write `catalog.py`**

```python
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
            raise CatalogError(f"{where} in the star catalogue has a non-{kind.__name__ if isinstance(kind, type) else 'numeric'} '{field}'.")
    name = raw["name"]
    if not name:
        raise CatalogError(f"{where} in the star catalogue has an empty name.")
    ra, dec, distance = float(raw["ra_deg"]), float(raw["dec_deg"]), float(raw["distance_ly"])
    if not (math.isfinite(ra) and 0.0 <= ra < 360.0):
        raise CatalogError(f"{where} in the star catalogue has right ascension {ra}, outside [0, 360).")
    if not (math.isfinite(dec) and -90.0 <= dec <= 90.0):
        raise CatalogError(f"{where} in the star catalogue has declination {dec}, outside [-90, 90].")
    if not (math.isfinite(distance) and distance > 0.0):
        raise CatalogError(f"{where} in the star catalogue has distance {distance}; it must be a positive, finite number of light-years.")
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
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest lightspeed/tests/test_catalog.py -q`
Expected: all PASS. If `test_load_names_the_offending_entry` fails on the `"name": ""` case, note that the message for an empty name says `entry 2` — which the test accepts.

- [ ] **Step 5: Lint/format and commit**

Run: `uv run ruff check . && uv run ruff format . && uv run pytest lightspeed -q`

```bash
git add lightspeed/catalog.py lightspeed/tests/test_catalog.py
git commit -m "Add the lightspeed catalogue loader and star positions"
```

---

### Task 4: `simulation.py` — the clock and the arrival schedule

**Files:**
- Create: `lightspeed/simulation.py`
- Create: `lightspeed/tests/test_simulation.py`

**Interfaces:**
- Consumes: `catalog.Star` (`.position`, `.name`) from Task 3.
- Produces:
  ```python
  MIN_SPEED = 1 / 64; MAX_SPEED = 4096.0
  @dataclass(frozen=True) class Arrival: time_yr: float; source: int; target: int
  class Simulation:
      __init__(self, stars: Sequence[Star], *, years_per_second: float = 1.0)
      stars: list[Star]; positions: np.ndarray (n,3); time_yr: float; running: bool; years_per_second: float
      start() pause() toggle() reset() faster() slower()
      advance(wall_dt_s: float) -> list[Arrival]
      radius() -> float
  ```

- [ ] **Step 1: Write the failing tests**

`lightspeed/tests/test_simulation.py`:

```python
import math

import numpy as np
import pytest

from lightspeed import catalog, simulation


def star(name, x, y=0.0, z=0.0):
    """A star at Cartesian (x, y, z) light-years, built by way of RA/Dec so the catalog math is exercised."""
    distance = math.hypot(x, y, z)
    if distance == 0.0:
        return catalog.SOL
    dec = math.degrees(math.asin(z / distance))
    ra = math.degrees(math.atan2(y, x)) % 360.0
    return catalog.Star(name=name, ra_deg=ra, dec_deg=dec, distance_ly=distance, source="test")


def line_of_three():
    return [catalog.SOL, star("A", 3.0), star("B", 7.0)]


def test_positions_are_an_n_by_three_array_in_star_order():
    sim = simulation.Simulation(line_of_three())
    assert sim.positions.shape == (3, 3)
    assert sim.positions[1] == pytest.approx([3.0, 0.0, 0.0])
    assert sim.positions[2] == pytest.approx([7.0, 0.0, 0.0])


def test_arrivals_are_every_ordered_pair_sorted_by_distance():
    sim = simulation.Simulation(line_of_three())
    schedule = [(round(a.time_yr, 9), a.source, a.target) for a in sim.arrivals]
    assert schedule == [(3.0, 0, 1), (3.0, 1, 0), (4.0, 1, 2), (4.0, 2, 1), (7.0, 0, 2), (7.0, 2, 0)]


def test_it_starts_paused_at_time_zero():
    sim = simulation.Simulation(line_of_three())
    assert sim.time_yr == 0.0
    assert sim.running is False
    assert sim.radius() == 0.0


def test_advancing_while_paused_changes_nothing():
    sim = simulation.Simulation(line_of_three())
    assert sim.advance(10.0) == []
    assert sim.time_yr == 0.0


def test_advancing_while_running_moves_the_clock_at_the_chosen_speed():
    sim = simulation.Simulation(line_of_three(), years_per_second=2.0)
    sim.start()
    sim.advance(0.5)
    assert sim.time_yr == pytest.approx(1.0)
    assert sim.radius() == pytest.approx(1.0)


def test_advance_returns_exactly_the_arrivals_in_the_step():
    sim = simulation.Simulation(line_of_three())
    sim.start()
    assert sim.advance(2.9) == []
    first = sim.advance(0.2)  # now 3.1: the two 3.0 ly arrivals
    assert [(a.source, a.target) for a in first] == [(0, 1), (1, 0)]
    second = sim.advance(4.0)  # now 7.1: the 4.0 and 7.0 arrivals
    assert [(a.source, a.target) for a in second] == [(1, 2), (2, 1), (0, 2), (2, 0)]
    assert sim.advance(100.0) == []


def test_an_arrival_exactly_at_the_new_time_counts():
    sim = simulation.Simulation(line_of_three())
    sim.start()
    assert [(a.source, a.target) for a in sim.advance(3.0)] == [(0, 1), (1, 0)]


def test_reset_rewinds_the_clock_and_the_schedule_and_pauses():
    sim = simulation.Simulation(line_of_three())
    sim.start()
    sim.advance(5.0)
    sim.reset()
    assert sim.time_yr == 0.0
    assert sim.running is False
    sim.start()
    assert [(a.source, a.target) for a in sim.advance(3.5)] == [(0, 1), (1, 0)]


def test_toggle_flips_running():
    sim = simulation.Simulation(line_of_three())
    sim.toggle()
    assert sim.running is True
    sim.toggle()
    assert sim.running is False


def test_faster_and_slower_double_and_halve_within_the_clamps():
    sim = simulation.Simulation(line_of_three(), years_per_second=1.0)
    sim.faster()
    assert sim.years_per_second == 2.0
    sim.slower()
    sim.slower()
    assert sim.years_per_second == 0.5
    for _ in range(20):
        sim.faster()
    assert sim.years_per_second == simulation.MAX_SPEED
    for _ in range(40):
        sim.slower()
    assert sim.years_per_second == simulation.MIN_SPEED


@pytest.mark.parametrize("speed", [0.0, -1.0, float("nan"), float("inf")])
def test_a_bad_initial_speed_is_rejected(speed):
    with pytest.raises(ValueError, match="positive, finite"):
        simulation.Simulation(line_of_three(), years_per_second=speed)


@pytest.mark.parametrize("dt", [-0.1, float("nan"), float("inf")])
def test_a_bad_wall_step_is_rejected(dt):
    sim = simulation.Simulation(line_of_three())
    sim.start()
    with pytest.raises(ValueError, match="wall-clock"):
        sim.advance(dt)


def test_a_single_star_has_no_arrivals():
    sim = simulation.Simulation([catalog.SOL])
    sim.start()
    assert sim.arrivals == []
    assert sim.advance(50.0) == []


def test_arrival_times_match_the_real_catalogue_pairwise_distances():
    stars = catalog.load()[:10]
    sim = simulation.Simulation(stars)
    for arrival in sim.arrivals:
        expected = np.linalg.norm(sim.positions[arrival.source] - sim.positions[arrival.target])
        assert arrival.time_yr == pytest.approx(expected)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest lightspeed/tests/test_simulation.py -q`
Expected: FAIL with `ImportError: cannot import name 'simulation'`.

- [ ] **Step 3: Write `simulation.py`**

```python
"""The simulation: one flash from every star at t = 0, spreading at one light-year a year.

Pure state over numpy, with no knowledge of how it is drawn. The viewer owns a
`Simulation`, feeds it wall-clock seconds, and asks for the shell radius and for the
arrivals that fell inside each step. Because every star emits at the same instant and
light goes one light-year per year, the shell radius is simply the clock, and the
wavefront from star i reaches star j at exactly their separation in light-years — so the
whole arrival schedule is the sorted list of pairwise distances, worked out once.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from .catalog import Star

MIN_SPEED = 1.0 / 64.0
MAX_SPEED = 4096.0


@dataclass(frozen=True)
class Arrival:
    """The moment the wavefront from star `source` sweeps over star `target`."""

    time_yr: float
    source: int
    target: int


def _check_speed(years_per_second: float) -> float:
    if not (math.isfinite(years_per_second) and years_per_second > 0.0):
        raise ValueError(f"Speed must be a positive, finite number of years per second, not {years_per_second}.")
    return float(years_per_second)


class Simulation:
    def __init__(self, stars: Sequence[Star], *, years_per_second: float = 1.0):
        self.stars = list(stars)
        self.positions = np.array([star.position for star in self.stars], dtype=float).reshape(len(self.stars), 3)
        self.years_per_second = _check_speed(years_per_second)
        self.time_yr = 0.0
        self.running = False
        self.arrivals = self._schedule()
        self._next = 0  # index into self.arrivals of the first arrival not yet delivered

    def _schedule(self) -> list[Arrival]:
        n = len(self.stars)
        if n < 2:
            return []
        separations = np.linalg.norm(self.positions[:, None, :] - self.positions[None, :, :], axis=2)
        sources, targets = np.nonzero(~np.eye(n, dtype=bool))
        times = separations[sources, targets]
        order = np.lexsort((targets, sources, times))  # by time, then source, then target
        return [Arrival(float(times[k]), int(sources[k]), int(targets[k])) for k in order]

    def start(self) -> None:
        self.running = True

    def pause(self) -> None:
        self.running = False

    def toggle(self) -> None:
        self.running = not self.running

    def reset(self) -> None:
        self.running = False
        self.time_yr = 0.0
        self._next = 0

    def faster(self) -> None:
        self.years_per_second = min(self.years_per_second * 2.0, MAX_SPEED)

    def slower(self) -> None:
        self.years_per_second = max(self.years_per_second / 2.0, MIN_SPEED)

    def radius(self) -> float:
        """Every shell's radius in light-years — the clock, since light does one light-year a year."""
        return self.time_yr

    def advance(self, wall_dt_s: float) -> list[Arrival]:
        """Move the clock by `wall_dt_s` real seconds and return the arrivals that fell in the step, in order."""
        if not (math.isfinite(wall_dt_s) and wall_dt_s >= 0.0):
            raise ValueError(f"The wall-clock step must be a non-negative, finite number of seconds, not {wall_dt_s}.")
        if not self.running:
            return []
        self.time_yr += wall_dt_s * self.years_per_second
        start = self._next
        while self._next < len(self.arrivals) and self.arrivals[self._next].time_yr <= self.time_yr:
            self._next += 1
        return self.arrivals[start : self._next]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest lightspeed/tests/test_simulation.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint/format and commit**

Run: `uv run ruff check . && uv run ruff format . && uv run pytest lightspeed -q`

```bash
git add lightspeed/simulation.py lightspeed/tests/test_simulation.py
git commit -m "Add the lightspeed simulation clock and arrival schedule"
```

---

### Task 5: `viewer.py` — the PyVista scene

**Files:**
- Create: `lightspeed/viewer.py`
- Create: `lightspeed/tests/test_viewer.py`

**Interfaces:**
- Consumes: `simulation.Simulation` (`stars`, `positions`, `time_yr`, `running`, `years_per_second`, `start()`, `toggle()`, `reset()`, `faster()`, `slower()`, `advance(dt) -> list[Arrival]`, `radius()`), `simulation.Arrival` (`time_yr`, `source`, `target`), `catalog.Star` (`name`, `label`, `position`).
- Produces:
  ```python
  HIGHLIGHT_SECONDS = 1.0; LOG_LINES = 8; FRAME_MS = 33
  class Viewer:
      __init__(self, sim, plotter, *, clock=time.perf_counter, out=sys.stdout)
      build() -> None; on_tick(step: int) -> None
      toggle() faster() slower() reset()
      shells: list   # one actor per star
      log_lines: list[str]
  def format_arrival(sim, arrival) -> str     # "y    4.2  light from Sol reaches Proxima Centauri"
  def run(stars, *, years_per_second: float, autostart: bool) -> None
  ```

- [ ] **Step 1: Write the failing tests, with the fake plotter**

`lightspeed/tests/test_viewer.py`:

```python
import io

import numpy as np
import pytest

from lightspeed import catalog, simulation, viewer


class FakeActor:
    def __init__(self):
        self.position = (0.0, 0.0, 0.0)
        self.scale = (1.0, 1.0, 1.0)
        self.visibility = True


class FakePlotter:
    """Records every call the Viewer makes; knows nothing about VTK."""

    def __init__(self):
        self.meshes = []  # (mesh, kwargs)
        self.actors = []
        self.texts = {}  # name -> (text, kwargs)
        self.keys = {}  # key -> callback
        self.timers = []  # (max_steps, duration, callback)
        self.labels = None
        self.background = None
        self.depth_peeling = False
        self.renders = 0
        self.camera_position = None

    def add_mesh(self, mesh, **kwargs):
        actor = FakeActor()
        self.meshes.append((mesh, kwargs))
        self.actors.append(actor)
        return actor

    def add_point_labels(self, points, labels, **kwargs):
        self.labels = (np.asarray(points), list(labels), kwargs)

    def add_text(self, text, **kwargs):
        self.texts[kwargs["name"]] = (text, kwargs)

    def add_key_event(self, key, callback):
        self.keys[key] = callback

    def add_timer_event(self, max_steps, duration, callback):
        self.timers.append((max_steps, duration, callback))

    def enable_depth_peeling(self, *args, **kwargs):
        self.depth_peeling = True

    def set_background(self, color, **kwargs):
        self.background = color

    def render(self):
        self.renders += 1


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def star(name, x):
    return catalog.Star(name=name, ra_deg=0.0, dec_deg=0.0, distance_ly=x, source="test")


def make_viewer(speed=1.0):
    sim = simulation.Simulation([catalog.SOL, star("A", 3.0), star("B", 7.0)], years_per_second=speed)
    plotter = FakePlotter()
    clock = FakeClock()
    out = io.StringIO()
    view = viewer.Viewer(sim, plotter, clock=clock, out=out)
    view.build()
    return view, sim, plotter, clock, out


def shell_meshes(plotter):
    return [(m, kw) for m, kw in plotter.meshes if kw.get("opacity") is not None]


def test_build_adds_one_translucent_unit_shell_per_star_placed_at_the_star():
    view, sim, plotter, _, _ = make_viewer()
    shells = shell_meshes(plotter)
    assert len(shells) == 3
    assert len(view.shells) == 3
    for (mesh, kwargs), actor, position in zip(shells, view.shells, sim.positions, strict=True):
        assert 0.0 < kwargs["opacity"] < 0.5
        assert np.linalg.norm(mesh.points, axis=1).max() == pytest.approx(1.0, abs=1e-6)
        assert actor.position == pytest.approx(tuple(position))
        assert actor.visibility is False  # nothing has been emitted yet


def test_build_adds_the_star_points_with_sol_in_yellow():
    _, _, plotter, _, _ = make_viewer()
    points = [(m, kw) for m, kw in plotter.meshes if kw.get("rgb")]
    assert len(points) == 1
    mesh, kwargs = points[0]
    assert kwargs["scalars"] == "rgb"
    assert kwargs["render_points_as_spheres"] is True
    assert mesh.n_points == 3
    assert tuple(mesh["rgb"][0]) == viewer.SOL_COLOR
    assert tuple(mesh["rgb"][1]) == viewer.STAR_COLOR


def test_build_labels_every_star_with_name_and_distance():
    _, _, plotter, _, _ = make_viewer()
    points, labels, kwargs = plotter.labels
    assert labels == ["Sol (0 ly)", "A (3.0 ly)", "B (7.0 ly)"]
    assert points.shape == (3, 3)
    assert kwargs["always_visible"] is True
    assert kwargs["shape"] is None
    assert kwargs["show_points"] is False
    assert kwargs["text_color"] is not None


def test_build_sets_up_the_scene_the_overlays_the_keys_and_the_timer():
    _, _, plotter, _, _ = make_viewer()
    assert plotter.background == "black"
    assert plotter.depth_peeling is True
    assert plotter.camera_position is not None
    assert {"clock", "log", "help"} <= set(plotter.texts)
    for _text, kwargs in plotter.texts.values():
        assert kwargs.get("color") is not None  # the default theme draws text black on black
    assert "paused" in plotter.texts["clock"][0]
    assert "space" in plotter.texts["help"][0]
    assert set(plotter.keys) == {"space", "plus", "equal", "minus", "r"}
    assert len(plotter.timers) == 1
    max_steps, duration, callback = plotter.timers[0]
    assert max_steps > 10**6
    assert duration == viewer.FRAME_MS
    assert callable(callback)


def test_ticking_while_paused_keeps_shells_hidden_and_still_renders():
    view, sim, plotter, clock, _ = make_viewer()
    clock.now += 1.0
    plotter.timers[0][2](1)  # the registered timer callback is view.on_tick
    assert sim.time_yr == 0.0
    assert all(actor.visibility is False for actor in view.shells)
    assert plotter.renders == 1


def test_space_starts_and_ticks_grow_every_shell_to_the_clock():
    view, sim, plotter, clock, _ = make_viewer(speed=2.0)
    plotter.keys["space"]()
    assert sim.running is True
    clock.now += 0.5  # 0.5 s × 2 yr/s = 1 yr
    view.on_tick(1)
    assert sim.time_yr == pytest.approx(1.0)
    for actor in view.shells:
        assert actor.visibility is True
        assert actor.scale == pytest.approx((1.0, 1.0, 1.0))
    assert "t =" in plotter.texts["clock"][0]
    assert "1.0" in plotter.texts["clock"][0]
    assert "paused" not in plotter.texts["clock"][0]


def test_the_first_tick_after_build_does_not_jump_the_clock():
    """build() happens long before the window appears; the first frame must measure from the first tick, not from build()."""
    view, sim, _, clock, _ = make_viewer()
    view.toggle()
    clock.now += 1000.0
    view.on_tick(1)
    assert sim.time_yr == 0.0
    clock.now += 1.0
    view.on_tick(2)
    assert sim.time_yr == pytest.approx(1.0)


def test_an_arrival_highlights_the_target_logs_a_line_and_prints_it():
    view, _, plotter, clock, out = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    mesh = [m for m, kw in plotter.meshes if kw.get("rgb")][0]
    assert tuple(mesh["rgb"][1]) == viewer.HIGHLIGHT_COLOR  # A was reached by Sol's light
    assert tuple(mesh["rgb"][0]) == viewer.HIGHLIGHT_COLOR  # and Sol by A's
    assert tuple(mesh["rgb"][2]) == viewer.STAR_COLOR
    assert view.log_lines == ["y    3.0  light from Sol reaches A", "y    3.0  light from A reaches Sol"]
    assert plotter.texts["log"][0] == "\n".join(view.log_lines)
    assert out.getvalue().splitlines() == view.log_lines


def test_a_highlight_fades_back_after_highlight_seconds():
    view, _, plotter, clock, _ = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    mesh = [m for m, kw in plotter.meshes if kw.get("rgb")][0]
    clock.now += viewer.HIGHLIGHT_SECONDS / 2
    view.on_tick(3)
    assert tuple(mesh["rgb"][1]) == viewer.HIGHLIGHT_COLOR
    clock.now += viewer.HIGHLIGHT_SECONDS
    view.on_tick(4)
    assert tuple(mesh["rgb"][1]) == viewer.STAR_COLOR
    assert tuple(mesh["rgb"][0]) == viewer.SOL_COLOR  # Sol goes back to its own colour, not white


def test_the_log_keeps_only_the_last_lines():
    view, _, plotter, clock, _ = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 10.0
    view.on_tick(2)  # all six arrivals
    assert len(view.log_lines) == 6
    view.log_lines.clear()
    for i in range(viewer.LOG_LINES + 3):
        view._log(f"line {i}")
    assert view.log_lines == [f"line {i}" for i in range(3, viewer.LOG_LINES + 3)]
    assert plotter.texts["log"][0] == "\n".join(view.log_lines)


def test_plus_equal_and_minus_change_the_speed_and_the_clock_text():
    _, sim, plotter, _, _ = make_viewer()
    plotter.keys["plus"]()
    assert sim.years_per_second == 2.0
    assert "2 yr/s" in plotter.texts["clock"][0]
    plotter.keys["equal"]()
    assert sim.years_per_second == 4.0
    plotter.keys["minus"]()
    assert sim.years_per_second == 2.0


def test_r_resets_the_clock_hides_the_shells_and_clears_the_log_and_highlights():
    view, sim, plotter, clock, _ = make_viewer()
    view.toggle()
    view.on_tick(1)
    clock.now += 3.5
    view.on_tick(2)
    plotter.keys["r"]()
    mesh = [m for m, kw in plotter.meshes if kw.get("rgb")][0]
    assert sim.time_yr == 0.0
    assert sim.running is False
    assert all(actor.visibility is False for actor in view.shells)
    assert view.log_lines == []
    assert plotter.texts["log"][0] == ""
    assert tuple(mesh["rgb"][1]) == viewer.STAR_COLOR
    assert "paused" in plotter.texts["clock"][0]


def test_format_arrival_reads_like_a_log_line():
    sim = simulation.Simulation([catalog.SOL, star("Proxima Centauri", 4.2465)])
    line = viewer.format_arrival(sim, simulation.Arrival(4.2465, 0, 1))
    assert line == "y    4.2  light from Sol reaches Proxima Centauri"


def test_speed_text_drops_needless_decimals():
    assert viewer.format_speed(1.0) == "1 yr/s"
    assert viewer.format_speed(0.5) == "0.5 yr/s"
    assert viewer.format_speed(1 / 64) == "0.0156 yr/s"
    assert viewer.format_speed(4096.0) == "4096 yr/s"


def test_run_builds_a_real_plotter_and_shows_it(monkeypatch):
    """`run` is the only place a real Plotter is made; stub Plotter so nothing opens, and check the wiring."""
    created = {}

    class StubPlotter(FakePlotter):
        def __init__(self, **kwargs):
            super().__init__()
            created["kwargs"] = kwargs
            created["plotter"] = self

        def show(self, **kwargs):
            created["shown"] = kwargs

    monkeypatch.setattr(viewer.pv, "Plotter", StubPlotter)
    viewer.run([catalog.SOL, star("A", 3.0)], years_per_second=2.0, autostart=True)
    plotter = created["plotter"]
    assert created["shown"]["title"] == "lightspeed"
    assert len(plotter.timers) == 1
    assert "paused" not in plotter.texts["clock"][0]  # autostart
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest lightspeed/tests/test_viewer.py -q`
Expected: FAIL with `ImportError: cannot import name 'viewer'`.

- [ ] **Step 3: Write `viewer.py`**

```python
"""The 3D scene: stars as points, labels, one growing translucent shell per star.

Everything here talks to a *plotter* — normally a `pyvista.Plotter`, in tests a fake that
records calls — so the scene logic can be exercised without a window. `run()` is the one
place the real plotter is created and shown.

The mechanics, verified against pyvista 0.48 / VTK 9.6: shells are unit spheres whose
actors are scaled every frame (far cheaper than rewriting points); star colours live in a
uint8 "rgb" point array that is mutated in place; text overlays are re-added under the
same name, which replaces the previous actor; and every piece of text carries an explicit
colour, because pyvista's default theme draws text black.
"""

import sys
import time
from collections.abc import Callable, Sequence

import numpy as np
import pyvista as pv

from .catalog import Star
from .simulation import Arrival, Simulation

FRAME_MS = 33  # ~30 frames per second
HIGHLIGHT_SECONDS = 1.0  # wall-clock time a reached star stays lit
LOG_LINES = 8

SOL_COLOR = (255, 220, 80)
STAR_COLOR = (235, 235, 235)
HIGHLIGHT_COLOR = (255, 80, 60)
SHELL_OPACITY = 0.12
SHELL_PALETTE = ("#4fc3f7", "#ce93d8", "#80cbc4", "#fff176", "#ffab91", "#a5d6a7", "#90caf9", "#f48fb1")
TEXT_COLOR = "white"
CAMERA_DISTANCE_LY = 45.0

HELP_TEXT = (
    "space  start / pause\n"
    "+ / -  faster / slower\n"
    "r      reset\n"
    "drag   orbit    scroll  zoom    middle-drag  pan\n"
    "q      quit"
)


def format_speed(years_per_second: float) -> str:
    """'1 yr/s', '0.5 yr/s', '0.0156 yr/s' — as many decimals as the value needs, no more."""
    text = f"{years_per_second:.4f}".rstrip("0").rstrip(".")
    return f"{text} yr/s"


def format_arrival(sim: Simulation, arrival: Arrival) -> str:
    source = sim.stars[arrival.source].name
    target = sim.stars[arrival.target].name
    return f"y {arrival.time_yr:6.1f}  light from {source} reaches {target}"


class Viewer:
    def __init__(self, sim: Simulation, plotter, *, clock: Callable[[], float] = time.perf_counter, out=None):
        self.sim = sim
        self.plotter = plotter
        self.clock = clock
        self.out = sys.stdout if out is None else out
        self.shells: list = []
        self.log_lines: list[str] = []
        self._points: pv.PolyData | None = None
        self._base_colors: np.ndarray | None = None
        self._lit_until: np.ndarray = np.zeros(len(sim.stars))  # wall time each highlight expires; 0 = unlit
        self._last_tick: float | None = None

    # -- building the scene -------------------------------------------------

    def build(self) -> None:
        self.plotter.set_background("black")
        self.plotter.enable_depth_peeling()
        self._add_shells()
        self._add_stars()
        self._add_labels()
        self.plotter.add_text(HELP_TEXT, position="lower_right", font_size=9, color=TEXT_COLOR, name="help")
        self._refresh_clock()
        self._refresh_log()
        self.plotter.add_key_event("space", self.toggle)
        self.plotter.add_key_event("plus", self.faster)
        self.plotter.add_key_event("equal", self.faster)
        self.plotter.add_key_event("minus", self.slower)
        self.plotter.add_key_event("r", self.reset)
        self.plotter.add_timer_event(max_steps=sys.maxsize, duration=FRAME_MS, callback=self.on_tick)
        eye = np.array([0.55, -0.65, 0.5])
        eye = tuple(eye / np.linalg.norm(eye) * CAMERA_DISTANCE_LY)
        self.plotter.camera_position = [eye, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0)]

    def _add_shells(self) -> None:
        unit = pv.Sphere(radius=1.0)
        for index, position in enumerate(self.sim.positions):
            color = SHELL_PALETTE[index % len(SHELL_PALETTE)]
            actor = self.plotter.add_mesh(unit.copy(), color=color, opacity=SHELL_OPACITY, smooth_shading=True)
            actor.position = tuple(float(v) for v in position)
            actor.visibility = False
            self.shells.append(actor)

    def _add_stars(self) -> None:
        colors = np.tile(np.array(STAR_COLOR, dtype=np.uint8), (len(self.sim.stars), 1))
        for index, star in enumerate(self.sim.stars):
            if star.distance_ly == 0.0:
                colors[index] = SOL_COLOR
        self._base_colors = colors.copy()
        self._points = pv.PolyData(self.sim.positions.copy())
        self._points["rgb"] = colors
        self.plotter.add_mesh(self._points, scalars="rgb", rgb=True, render_points_as_spheres=True, point_size=9)

    def _add_labels(self) -> None:
        self.plotter.add_point_labels(
            self.sim.positions.copy(),
            [star.label for star in self.sim.stars],
            shape=None,
            show_points=False,
            always_visible=True,
            text_color=TEXT_COLOR,
            font_size=10,
        )

    # -- overlays -------------------------------------------------------------

    def _refresh_clock(self) -> None:
        state = "" if self.sim.running else "   [paused — press space]"
        text = f"t = {self.sim.time_yr:,.1f} yr   {format_speed(self.sim.years_per_second)}{state}"
        self.plotter.add_text(text, position="upper_left", font_size=12, color=TEXT_COLOR, name="clock")

    def _refresh_log(self) -> None:
        self.plotter.add_text("\n".join(self.log_lines), position="lower_left", font_size=9, color=TEXT_COLOR, name="log")

    def _log(self, line: str) -> None:
        self.log_lines.append(line)
        del self.log_lines[:-LOG_LINES]
        self._refresh_log()

    # -- key handlers ---------------------------------------------------------

    def toggle(self) -> None:
        self.sim.toggle()
        self._refresh_clock()

    def faster(self) -> None:
        self.sim.faster()
        self._refresh_clock()

    def slower(self) -> None:
        self.sim.slower()
        self._refresh_clock()

    def reset(self) -> None:
        self.sim.reset()
        self.log_lines.clear()
        self._lit_until[:] = 0.0
        self._apply_colors()
        self._apply_radius()
        self._refresh_log()
        self._refresh_clock()

    # -- the frame ------------------------------------------------------------

    def on_tick(self, step: int) -> None:  # noqa: ARG002 - signature fixed by pyvista's timer callback
        now = self.clock()
        if self._last_tick is None:
            dt = 0.0  # the first frame measures from itself, not from build()
        else:
            dt = max(0.0, now - self._last_tick)
        self._last_tick = now

        arrivals = self.sim.advance(dt)
        for arrival in arrivals:
            self._lit_until[arrival.target] = now + HIGHLIGHT_SECONDS
            line = format_arrival(self.sim, arrival)
            self._log(line)
            print(line, file=self.out)
        if arrivals or (self._lit_until > 0.0).any():
            self._apply_colors(now)
        if self.sim.running:
            self._apply_radius()
            self._refresh_clock()
        self.plotter.render()

    def _apply_colors(self, now: float | None = None) -> None:
        assert self._points is not None and self._base_colors is not None
        now = self.clock() if now is None else now
        expired = (self._lit_until > 0.0) & (self._lit_until <= now)
        self._lit_until[expired] = 0.0
        lit = self._lit_until > 0.0
        colors = self._base_colors.copy()
        colors[lit] = HIGHLIGHT_COLOR
        self._points["rgb"][:] = colors

    def _apply_radius(self) -> None:
        radius = self.sim.radius()
        for actor in self.shells:
            actor.visibility = radius > 0.0
            actor.scale = (radius, radius, radius)


def run(stars: Sequence[Star], *, years_per_second: float, autostart: bool) -> None:
    """Open the window and block until it is closed."""
    sim = Simulation(stars, years_per_second=years_per_second)
    if autostart:
        sim.start()
    plotter = pv.Plotter(window_size=(1280, 860))
    Viewer(sim, plotter).build()
    plotter.show(title="lightspeed")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest lightspeed/tests/test_viewer.py -q`
Expected: all PASS. Notes if something fails: `_apply_colors` writes through `self._points["rgb"][:] = colors` — a pyvista_ndarray view — which is what makes the fake's `mesh["rgb"]` and the real mapper both see the change; do not replace it with `self._points["rgb"] = colors` (that still works for VTK but the tests read the same array object either way, so both pass — keep the slice form because it was the one verified to re-render).

- [ ] **Step 5: Smoke-render offscreen (no window) to see the scene**

Write to `<scratchpad>/smoke.py` and run with `uv run python <scratchpad>/smoke.py` from the repo root:

```python
import pyvista as pv
from lightspeed import catalog, simulation, viewer

pv.OFF_SCREEN = True
sim = simulation.Simulation(catalog.load(), years_per_second=1.0)
plotter = pv.Plotter(off_screen=True, window_size=(1280, 860))
view = viewer.Viewer(sim, plotter)
view.build()
view.toggle()
view.on_tick(1)
view._last_tick -= 6.0  # pretend six seconds passed → t = 6 yr
view.on_tick(2)
plotter.screenshot("<scratchpad>/smoke.png")
print("t =", sim.time_yr, "log:", view.log_lines[-3:])
```

Open `<scratchpad>/smoke.png` (the Read tool renders PNGs). Expected: a black field, ~100 labelled white points with a yellow Sol, a clutch of translucent 6-ly shells around every star, the clock reading `t = 6.0 yr`, a log in the lower left naming Proxima/Alpha Centauri/Sol arrivals, the legend lower right. If text is missing, a colour is missing somewhere; if shells are opaque blobs, opacity or depth peeling was lost.

- [ ] **Step 6: Lint/format and commit**

Run: `uv run ruff check . && uv run ruff format . && uv run pytest lightspeed -q`

```bash
git add lightspeed/viewer.py lightspeed/tests/test_viewer.py
git commit -m "Add the lightspeed PyVista viewer"
```

---

### Task 6: `__main__.py` — the CLI

**Files:**
- Create: `lightspeed/__main__.py`
- Create: `lightspeed/tests/test_lightspeed.py`

**Interfaces:**
- Consumes: `catalog.load()`, `catalog.within()`, `catalog.CatalogError`; `viewer.run(stars, *, years_per_second, autostart)` (imported lazily inside `main()`).
- Produces: `build_parser() -> argparse.ArgumentParser`, `main(argv: list[str] | None = None) -> int`, `validate_positive(name: str, value: float) -> None` (raises `ValueError`).

- [ ] **Step 1: Write the failing tests**

`lightspeed/tests/test_lightspeed.py`:

```python
import pytest

from lightspeed import __main__ as lightspeed
from lightspeed import catalog


@pytest.fixture
def run_stub(monkeypatch):
    """Replace viewer.run so main() never opens a window; record what it was asked to show."""
    calls = []

    def fake_run(stars, *, years_per_second, autostart):
        calls.append({"stars": stars, "years_per_second": years_per_second, "autostart": autostart})

    import lightspeed.viewer as viewer_module

    monkeypatch.setattr(viewer_module, "run", fake_run)
    return calls


def run(*args, capsys):
    code = lightspeed.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_a_default_run_shows_every_bundled_star_and_waits_for_space(run_stub, capsys):
    code, _, err = run(capsys=capsys)
    assert code == 0
    assert err == ""
    assert len(run_stub) == 1
    call = run_stub[0]
    assert call["stars"][0] is catalog.SOL
    assert len(call["stars"]) == len(catalog.load())
    assert call["years_per_second"] == 1.0
    assert call["autostart"] is False


def test_speed_within_and_autostart_reach_the_viewer(run_stub, capsys):
    code, _, _ = run("--speed", "2.5", "--within", "10", "--autostart", capsys=capsys)
    assert code == 0
    call = run_stub[0]
    assert call["years_per_second"] == 2.5
    assert call["autostart"] is True
    assert all(star.distance_ly <= 10.0 for star in call["stars"])
    assert len(call["stars"]) < len(catalog.load())
    assert len(call["stars"]) > 5


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_a_bad_speed_exits_two_concisely_with_a_hint(run_stub, capsys, value):
    code, out, err = run("--speed", value, capsys=capsys)
    assert code == 2
    assert out == ""
    assert "positive, finite" in err
    assert "Try --speed 1" in err
    assert "Examples:" not in err
    assert run_stub == []


@pytest.mark.parametrize("value", ["0", "-5", "nan"])
def test_a_bad_within_exits_two_concisely_with_a_hint(run_stub, capsys, value):
    code, _, err = run("--within", value, capsys=capsys)
    assert code == 2
    assert "positive, finite" in err
    assert "Try --within 20" in err
    assert "Examples:" not in err
    assert run_stub == []


def test_a_within_that_leaves_only_sol_exits_one(run_stub, capsys):
    code, _, err = run("--within", "0.5", capsys=capsys)
    assert code == 1
    assert "No catalogued star lies within 0.5 ly" in err
    assert "Proxima Centauri" in err  # the hint names the nearest star and its distance
    assert run_stub == []


def test_an_unreadable_catalogue_exits_one(run_stub, capsys, monkeypatch):
    def broken(path=None):
        raise catalog.CatalogError("The star catalogue at /x/stars.json is not valid JSON: boom.")

    monkeypatch.setattr(catalog, "load", broken)
    code, _, err = run(capsys=capsys)
    assert code == 1
    assert "not valid JSON" in err
    assert run_stub == []


def test_validate_positive_accepts_normal_numbers():
    lightspeed.validate_positive("--speed", 0.25)
    lightspeed.validate_positive("--within", 20.0)


def help_text():
    return lightspeed.build_parser().format_help()


def test_usage_names_the_module_form():
    assert "python -m lightspeed" in help_text()


def test_help_says_what_the_tool_computes():
    text = help_text()
    assert "light-year" in text
    assert "one light-year per year" in text or "1 ly/yr" in text or "a light-year a year" in text


def test_help_documents_every_flag_with_its_default():
    text = help_text()
    assert "--speed" in text and "default: 1.0" in text
    assert "--within" in text and "default: 20.0" in text
    assert "--autostart" in text and "space" in text


def test_help_carries_worked_examples_and_the_key_legend():
    text = help_text()
    assert "Examples:" in text
    assert "python -m lightspeed --speed" in text
    assert "Keys in the window:" in text
    assert "space" in text


def test_help_lists_every_exit_code():
    text = help_text()
    assert "Exit codes:" in text
    for code, meaning in [("0", "closed"), ("1", "no star"), ("2", "invalid")]:
        line = [ln for ln in text.splitlines() if ln.strip().startswith(code + " ")]
        assert line, f"no exit-code line for {code}"
        assert meaning in line[0].lower()


def argparse_error(capsys, *args):
    with pytest.raises(SystemExit) as exc_info:
        lightspeed.main(list(args))
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""
    return captured.err


def test_an_unparseable_speed_prints_the_whole_help(capsys):
    err = argparse_error(capsys, "--speed", "fast")
    assert "invalid float value: 'fast'" in err
    assert "Examples:" in err
    assert "Exit codes:" in err


def test_an_unrecognized_flag_prints_the_whole_help(capsys):
    err = argparse_error(capsys, "--nope")
    assert "unrecognized arguments: --nope" in err
    assert "Examples:" in err


def test_the_usage_line_is_not_printed_twice(capsys):
    assert argparse_error(capsys, "--nope").count("usage: python -m lightspeed") == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest lightspeed/tests/test_lightspeed.py -q`
Expected: FAIL with `ImportError` / `ModuleNotFoundError: lightspeed.__main__`.

- [ ] **Step 3: Write `__main__.py`**

```python
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

Opens a window centred on Sol with about a hundred stellar systems out to 20
light-years, each at its true position relative to Earth and labelled with its name
and distance. One scene unit is one light-year, so the layout is accurate and only
the camera scales it. Press space and every star emits a single flash at the same
instant; each flash grows as a translucent sphere at one light-year per simulated
year. When a shell sweeps over another star that star flashes red, and a log line
says whose light reached whom and in what year. The window stays open until you
close it (q)."""

EXAMPLES = """\
Examples:
  python -m lightspeed                          the default: 1 year per second, all stars
  python -m lightspeed --speed 0.5              slow motion, half a year per second
  python -m lightspeed --within 12 --autostart  the 30-odd nearest systems, running at once

Keys in the window:
  space  start / pause          + / -  faster / slower (×2 / ÷2)
  r      reset to t = 0         q      quit
  drag to orbit, scroll to zoom, middle-drag to pan

Exit codes:
  0  the window was closed
  1  no star lies within --within, or the bundled catalogue is unreadable
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
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest lightspeed/tests/test_lightspeed.py -q`
Expected: all PASS.

- [ ] **Step 5: Check the help and the error paths by hand**

```bash
uv run python -m lightspeed --help
uv run python -m lightspeed --speed 0; echo "exit $?"
uv run python -m lightspeed --within 0.1; echo "exit $?"
uv run python -m lightspeed --nope 2>&1 | tail -3; echo
```

Expected: full help with examples, key legend and exit codes; `exit 2` with the two-line hint; `exit 1` naming Proxima; the unrecognized flag shows the help then the error line.

- [ ] **Step 6: Lint/format and commit**

Run: `uv run ruff check . && uv run ruff format . && uv run pytest -q`

```bash
git add lightspeed/__main__.py lightspeed/tests/test_lightspeed.py
git commit -m "Add the lightspeed command-line interface"
```

---

### Task 7: Documentation

**Files:**
- Create: `lightspeed/README.md`
- Modify: `README.md` (tools table + getting-started sync command), `CLAUDE.md` (commands + adding-a-tool step 4 + a note on dependencies)

**Interfaces:** none (prose only). Read `spacetime/README.md` first to copy its section order and tone.

- [ ] **Step 1: Write `lightspeed/README.md`**

```markdown
# lightspeed

Light is slow on the scale of the stars. `lightspeed` opens a 3D window centred on Sol with
about a hundred stellar systems out to 20 light-years, each at its true position relative
to Earth and labelled with its name and distance, and on your command lets every one of
them flash at once — then shows each flash growing as a translucent sphere at one
light-year per simulated year while you orbit the camera and watch the shells cross one
another and wash over other stars.

```
$ python -m lightspeed --speed 2
(a window opens; press space to start)
y    4.2  light from Proxima Centauri reaches Alpha Centauri
y    4.2  light from Alpha Centauri reaches Proxima Centauri
y    4.2  light from Sol reaches Proxima Centauri
y    4.2  light from Proxima Centauri reaches Sol
y    4.4  light from Sol reaches Alpha Centauri
```

## Usage

```
python -m lightspeed [--speed YEARS_PER_SECOND] [--within LY] [--autostart]
```

- `--speed YEARS_PER_SECOND` — simulated years per real second once running; shells grow
  this many light-years per second (default: `1.0`).
- `--within LY` — show only systems no farther than this from Sol (default: `20.0`, which
  is everything bundled).
- `--autostart` — start the moment the window opens instead of waiting for space.

In the window:

| Key | Effect |
| --- | --- |
| `space` | start / pause |
| `+` / `-` | double / halve the speed |
| `r` | reset to t = 0 |
| `q` | quit |
| drag / scroll / middle-drag | orbit / zoom / pan (VTK's trackball camera) |

The upper-left corner shows the simulated clock and speed, the lower-left the last eight
arrivals, the lower-right the key legend. Every arrival is also printed to stdout.

## How it works

Every star is placed from its ICRS right ascension, declination, and distance:

```
x = d · cos(dec) · cos(ra)        x toward the vernal equinox
y = d · cos(dec) · sin(ra)
z = d · sin(dec)                  z toward the north celestial pole
```

with `d` in light-years, so one scene unit is one light-year and Sol is the origin. The
"scaling down" is entirely the camera — relative positions are exact.

At simulated time `t` the flash from a star at **p** is the sphere of radius `t` about
**p**, because light covers one light-year per year. It reaches a star at **q** when
`t = |p − q|`, so the arrival schedule is the sorted list of pairwise separations,
computed once. Each frame the viewer advances the clock by the real time elapsed times
`--speed`, rescales every shell to the new radius, lights up any star a shell has just
reached, and appends the arrival to the log.

## Exit codes

| Code | Meaning                                                               |
| ---- | --------------------------------------------------------------------- |
| 0    | The window was closed                                                 |
| 1    | No star within `--within`, or the bundled catalogue is unreadable     |
| 2    | Invalid `--speed` or `--within`, or a rejected command line           |

## What the model ignores

Proper motion — the stars sit where they are catalogued today and do not move over the
simulated centuries; the fact that those catalogued positions are themselves where the
stars *were* when their light left; relativity of any kind; stellar radii, colours, and
brightness (every star is a dot, Sol's is yellow); and the shells are drawn as ideal
spheres with no dimming, so a shell never fades no matter how far it has spread.

## Where the data comes from

`stars.json` holds one entry per stellar *system* (Alpha Centauri A+B is one entry,
Proxima is another) out to 20 ly: a display name, ICRS coordinates in degrees, the
distance in light-years, and a `source` naming the parallax's SIMBAD bibcode and the
query date. It was built once from SIMBAD's TAP service and is not refreshed at runtime;
the tool never touches the network.

## Running it

`lightspeed` is a tool in the [space](../) monorepo, which uses `uv`. It is the first tool
here with third-party dependencies — [PyVista](https://pyvista.org) (and with it VTK and
numpy) — so install with `--all-packages`, which pulls a ~100 MB VTK wheel on the first
run:

```
uv sync --all-packages
uv run python -m lightspeed
```

It needs a display: a desktop session on macOS, Windows, or Linux. It is a package, not a
loose script, so run it with `-m` from the repo root.

## Tests

From the repo root:

```
uv sync --all-packages
uv run pytest lightspeed
```

Tests never open a window — the viewer is driven through a recording fake plotter, and
`conftest.py` installs an autouse fixture that makes `pyvista.Plotter.show` fail loudly.
```

- [ ] **Step 2: Update the root `README.md`**

Add to the tools table after the spacetime row:

```markdown
| [`lightspeed`](lightspeed/) | Shows light spreading out between the nearest stars, in 3D. |
```

and change the getting-started block's first line to:

```bash
uv sync --all-packages                        # create the venv from uv.lock, every tool's deps included
```

- [ ] **Step 3: Update `CLAUDE.md`**

In "Commands", change `uv sync                          # create/update the venv from uv.lock` to
`uv sync --all-packages           # create/update the venv from uv.lock (members' deps too)`, and
add `uv run python -m lightspeed                  # run a tool with a window` after the starlight example.
In "Adding a tool", step 1, after the TOML block, add a sentence: *A tool may declare third-party
`dependencies`; they install into the shared venv with `uv sync --all-packages` (plain `uv sync`
only installs the root's).* In step 4, change `uv sync` to `uv sync --all-packages`. In "CI", change
`uv sync --locked` to `uv sync --all-packages --locked`. In "Repo shape" the sentence "The only
shared things are the toolchain and the config in the root `pyproject.toml`" stays true — do not
edit it.

- [ ] **Step 4: Verify docs and commit**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q` (prose changes must not break anything) and `grep -n "all-packages" CLAUDE.md README.md .github/workflows/ci.yml lightspeed/README.md` (every file mentions it).

```bash
git add lightspeed/README.md README.md CLAUDE.md
git commit -m "Document lightspeed and the --all-packages install"
```

---

### Task 8: Final verification

**Files:** none new.

- [ ] **Step 1: The full gate**

Run: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
Expected: clean, clean, all green (≈197 + ~80 new).

- [ ] **Step 2: Re-run the offscreen smoke render** from Task 5 Step 5 and look at the PNG once more after the CLI/doc changes.

- [ ] **Step 3: A real window (the one interactive check)**

Run: `uv run python -m lightspeed --speed 2` — confirm the window opens centred on Sol with labelled stars, orbit/zoom work, space starts the shells, the clock advances, Proxima lights up at ~4.2 yr with a log line, `+`/`-` change speed, `r` resets, `q` exits 0. If no display is available, say so in the report rather than claiming it was checked.

- [ ] **Step 4: Report** what passed, what was looked at, and anything skipped.

## Self-Review

- Spec coverage: catalogue (T2/T3), physics/positions (T3), simulation (T4), viewer with labels/shells/highlight/log/keys/timer/camera (T5), CLI with exit codes and help (T6), repo integration incl. `--all-packages` and CI (T1/T7), docs (T7), guard (T1). Deliberately-not-built items have no task — correct.
- Type consistency: `Simulation.radius()` (singular) is used by the viewer; `Arrival(time_yr, source, target)` matches between T4 and T5; `viewer.run(stars, *, years_per_second, autostart)` matches T5 and T6; `catalog.within(stars, max_ly)` matches T3 and T6; constants `SOL_COLOR`, `STAR_COLOR`, `HIGHLIGHT_COLOR`, `HIGHLIGHT_SECONDS`, `LOG_LINES`, `FRAME_MS` are defined in T5 and referenced by its tests.
- Placeholders: none — every code step is complete as written.
