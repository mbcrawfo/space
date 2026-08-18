import json
import urllib.error

import pytest

from spacetime import __main__ as spacetime
from spacetime import catalog


def run(*args, capsys):
    """Run the CLI and hand back its exit code with whatever it printed."""
    code = spacetime.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_a_default_run_reports_the_three_headline_numbers(capsys):
    code, out, err = run("Sirius", "--offline", capsys=capsys)
    assert code == 0
    assert err == ""
    assert "Sirius (Alpha Canis Majoris)" in out
    assert "1.00 G, flip and burn at the midpoint" in out
    assert "98.30% of light speed" in out
    assert "Crew time    4.6 years" in out
    assert "Earth time   10.4 years" in out


def test_acceleration_changes_the_answer(capsys):
    code, out, _ = run("Sirius", "--accel", "3", "--offline", capsys=capsys)
    assert code == 0
    assert "3.00 G" in out
    assert "Crew time    2.2 years" in out
    assert "Earth time   9.2 years" in out


def test_the_short_acceleration_flag_works_too(capsys):
    code, out, _ = run("Sirius", "-a", "3", "--offline", capsys=capsys)
    assert code == 0
    assert "3.00 G" in out


def test_flyby_never_slows_down(capsys):
    code, out, _ = run("Sirius", "--flyby", "--offline", capsys=capsys)
    assert code == 0
    assert "burn all the way, no turnover" in out
    assert "99.49% of light speed" in out
    assert "Crew time    2.9 years" in out


def test_a_distant_star_never_reads_as_a_flat_hundred_percent(capsys):
    """99.99938% of c must not be rounded up into a physical impossibility."""
    code, out, _ = run("Betelgeuse", "--offline", capsys=capsys)
    assert code == 0
    assert "100.00% of light speed" not in out
    assert "99.99" in out


def test_verbose_adds_the_lorentz_factor_the_skipped_years_and_the_caveats(capsys):
    code, out, _ = run("Sirius", "--offline", "--verbose", capsys=capsys)
    assert code == 0
    assert "Peak γ       5.44" in out
    assert "Skipped      5.8 years" in out
    assert "Fuel is ignored" in out


def test_uncertainty_shows_a_range_when_the_star_has_error_bars(capsys):
    code, out, _ = run("Sirius", "--offline", "--uncertainty", capsys=capsys)
    assert code == 0
    crew_line = [line for line in out.splitlines() if "Crew time" in line][0]  # noqa: RUF015 - clarity over next()
    assert " to " in crew_line


def test_uncertainty_is_silent_for_a_star_without_error_bars(capsys, monkeypatch):
    star = catalog.Star(
        name="Nowhere",
        designation=None,
        distance_pc=10.0,
        distance_pc_err=None,
        source="test",
    )
    monkeypatch.setattr(catalog, "resolve", lambda name, *, offline=False: star)
    code, out, _ = run("Nowhere", "--offline", "--uncertainty", capsys=capsys)
    assert code == 0
    crew_line = [line for line in out.splitlines() if "Crew time" in line][0]  # noqa: RUF015 - clarity over next()
    assert " to " not in crew_line


def test_json_carries_the_same_values_under_stable_keys(capsys):
    code, out, _ = run("Sirius", "--offline", "--json", capsys=capsys)
    assert code == 0
    result = json.loads(out)
    assert result["name"] == "Sirius"
    assert result["accel_g"] == 1.0
    assert result["profile"] == "flip-and-burn"
    assert result["peak_velocity_c"] == pytest.approx(0.9829545435, rel=1e-6)
    assert result["crew_years"] == pytest.approx(4.6076540630, rel=1e-6)
    assert result["earth_years"] == pytest.approx(10.3585458636, rel=1e-6)
    assert "uncertainty" not in result


def test_json_includes_uncertainty_only_when_it_is_asked_for(capsys):
    _, out, _ = run("Sirius", "--offline", "--json", "--uncertainty", capsys=capsys)
    span = json.loads(out)["uncertainty"]
    assert span["crew_years"][0] < span["crew_years"][1]
    assert span["earth_years"][0] < span["earth_years"][1]
    assert span["peak_velocity_c"][0] < span["peak_velocity_c"][1]


def test_json_names_the_flyby_profile(capsys):
    _, out, _ = run("Sirius", "--offline", "--json", "--flyby", capsys=capsys)
    assert json.loads(out)["profile"] == "flyby"


def test_an_unknown_star_exits_one_and_suggests(capsys):
    code, _, err = run("Siriuz", "--offline", capsys=capsys)
    assert code == 1
    assert "Siriuz" in err
    assert "Did you mean" in err


def test_a_bad_acceleration_exits_two(capsys):
    code, _, err = run("Sirius", "--accel", "0", "--offline", capsys=capsys)
    assert code == 2
    assert "positive" in err


@pytest.mark.parametrize("value", ["-1", "nan", "inf"])
def test_every_unusable_acceleration_exits_two(value, capsys):
    code, _, _ = run("Sirius", "--accel", value, "--offline", capsys=capsys)
    assert code == 2


def test_the_acceleration_is_checked_before_the_network_is_touched(capsys, monkeypatch):
    """A bad number must not cost a SIMBAD round trip."""

    def explode(*args, **kwargs):
        raise AssertionError("resolve() was called despite an invalid acceleration")

    monkeypatch.setattr(catalog, "resolve", explode)
    code, _, _ = run("Sirius", "--accel", "0", capsys=capsys)
    assert code == 2


def test_a_simbad_failure_exits_three(capsys, monkeypatch):
    def unreachable(*args, **kwargs):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(catalog, "_http_post", unreachable)
    code, _, err = run("HD 999999", capsys=capsys)
    assert code == 3
    assert "--offline" in err


def test_offline_never_reaches_for_the_network(capsys):
    """conftest makes any real call explode, so reaching exit 1 proves it did not."""
    code, _, _ = run("HD 999999", "--offline", capsys=capsys)
    assert code == 1


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [
        (0.5, "50.00"),
        (0.9829544010, "98.30"),
        (0.9999938003, "99.999"),
        (0.99999999999, "99.999999999"),
    ],
)
def test_format_speed_widens_until_it_is_honest(fraction, expected):
    assert spacetime.format_speed(fraction) == expected


def help_text():
    return spacetime.build_parser().format_help()


def test_usage_names_the_module_form():
    assert "python -m spacetime" in help_text()


def test_help_documents_what_name_accepts():
    text = help_text()
    assert "HD 39801" in text  # a catalogue number
    assert "SIMBAD" in text  # where an uncatalogued name is resolved


def test_help_explains_that_acceleration_is_proper_acceleration():
    text = help_text()
    assert "proper acceleration" in text
    assert "default: 1.0" in text


def test_help_carries_worked_examples():
    text = help_text()
    assert "Examples:" in text
    assert "python -m spacetime Sirius" in text


def test_help_lists_every_exit_code():
    text = help_text()
    assert "Exit codes:" in text
    for code, meaning in [("0", "success"), ("1", "unknown star"), ("2", "acceleration"), ("3", "network")]:
        line = [ln for ln in text.splitlines() if ln.strip().startswith(code + " ")]
        assert line, f"no exit-code line for {code}"
        assert meaning in line[0].lower()


def test_a_bad_acceleration_points_at_what_would_work(capsys):
    code, _out, err = run("Sirius", "--accel", "0", "--offline", capsys=capsys)
    assert code == 2
    assert "positive" in err
    assert "--accel" in err


def argparse_error(capsys, *args):
    """Run the CLI expecting argparse to reject argv, and hand back stderr."""
    with pytest.raises(SystemExit) as exc_info:
        spacetime.main(list(args))
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""  # errors belong on stderr, help included
    return captured.err


def test_a_missing_name_prints_the_whole_help(capsys):
    err = argparse_error(capsys)
    assert "the following arguments are required: name" in err
    assert "Examples:" in err
    assert "Exit codes:" in err
    assert "--flyby" in err


def test_an_unparseable_acceleration_prints_the_whole_help(capsys):
    err = argparse_error(capsys, "Sirius", "--accel", "abc")
    assert "invalid float value: 'abc'" in err
    assert "Examples:" in err


def test_an_unrecognized_flag_prints_the_whole_help(capsys):
    err = argparse_error(capsys, "Sirius", "--nope")
    assert "unrecognized arguments: --nope" in err
    assert "Examples:" in err


def test_the_usage_line_is_not_printed_twice(capsys):
    assert argparse_error(capsys).count("usage: python -m spacetime") == 1


def test_an_out_of_range_acceleration_stays_concise(capsys):
    # A number argparse accepts but the model cannot use: the hint line is more
    # use than forty lines of help, so this path must not dump them.
    code, _out, err = run("Sirius", "--accel", "0", "--offline", capsys=capsys)
    assert code == 2
    assert "Try --accel 1" in err
    assert "Examples:" not in err
