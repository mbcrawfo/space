import json

import pytest

from starlight import __main__ as starlight
from starlight import catalog


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("CLI tests must not touch the network")

    monkeypatch.setattr(catalog, "_http_post", explode)


def run(capsys, *args):
    code = starlight.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_reports_the_emission_date_for_a_known_star(capsys):
    code, out, err = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline")
    assert code == 0
    assert "Betelgeuse" in out
    assert "Alpha Orionis" in out
    assert "16 August 2026 CE" in out
    assert "548.3 ly" in out
    # 168.1 pc -> 548.268871418 ly -> 200255 days before JDN 2461269
    assert "6 May 1478 CE" in out
    assert err == ""


def test_distant_stars_report_a_bce_emission_date(capsys):
    code, out, _ = run(capsys, "Eta Carinae", "--on", "2026-08-16", "--offline")
    assert code == 0
    assert "15 November 5477 BCE" in out  # 2026 minus about 7502 years


def test_nearby_star_light_left_within_living_memory(capsys):
    code, out, _ = run(capsys, "Proxima Centauri", "--on", "2026-08-16", "--offline")
    assert code == 0
    assert "2022 CE" in out  # 4.24 years earlier


def test_uncertainty_flag_adds_a_range(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--uncertainty")
    assert code == 0
    assert "between" in out
    assert "1388 CE" in out and "1568 CE" in out  # +/- 27.5 pc is about 90 years


def test_verbose_flag_shows_source_and_caveat(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--verbose")
    assert code == 0
    assert "Hipparcos (revised)" in out
    assert "radial" in out.lower()


def test_json_flag_emits_machine_readable_output(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--json")
    assert code == 0
    result = json.loads(out)
    assert result["name"] == "Betelgeuse"
    assert result["distance_pc"] == pytest.approx(168.1)
    assert result["distance_ly"] == pytest.approx(548.2, abs=0.5)
    assert result["observation_date"] == "16 August 2026 CE"
    assert result["observation_jdn"] == 2461269
    assert result["emission_date"].endswith("1478 CE")
    assert result["travel_years"] == pytest.approx(548.2, abs=0.5)
    assert result["source"] == "Hipparcos (revised)"
    assert "uncertainty" not in result


def test_json_with_uncertainty_includes_the_range(capsys):
    code, out, _ = run(capsys, "Betelgeuse", "--on", "2026-08-16", "--offline", "--uncertainty", "--json")
    assert code == 0
    result = json.loads(out)
    assert result["uncertainty"]["earliest_year"].endswith("BCE") is False
    assert "1388 CE" in result["uncertainty"]["earliest_year"]
    assert "1568 CE" in result["uncertainty"]["latest_year"]


def test_observation_date_defaults_to_today(capsys):
    code, out, _ = run(capsys, "Sirius", "--offline")
    assert code == 0
    assert "Sirius" in out


def test_unknown_star_exits_1_with_suggestions(capsys):
    code, out, err = run(capsys, "Betelgeus", "--offline")
    assert code == 1
    assert out == ""
    assert "Betelgeuse" in err
    assert "No star named 'Betelgeus' was found." in err
    # main() must not rebuild this sentence separately from StarNotFoundError's
    # own message — printing exc directly means there is exactly one copy.
    assert err.count("No star named") == 1


def test_malformed_date_exits_2(capsys):
    code, out, err = run(capsys, "Sirius", "--on", "not-a-date", "--offline")
    assert code == 2
    assert out == ""
    assert "YYYY-MM-DD" in err


def test_network_failure_exits_3(capsys, monkeypatch):
    def fail(*args, **kwargs):
        raise catalog.SimbadError("Could not reach SIMBAD: no route to host")

    monkeypatch.setattr(catalog, "simbad_lookup", fail)
    code, _out, err = run(capsys, "some obscure star")
    assert code == 3
    assert "--offline" in err


def test_large_distance_pc_is_not_rendered_in_scientific_notation(capsys, monkeypatch):
    # A SIMBAD object with a small parallax yields a large distance_pc.
    # ,.4g would render that as "1.235e+04 pc"; ,.1f must not.
    def fake(name, *, offline=False):
        return catalog.Star(
            name="Some Obscure Star",
            designation=None,
            distance_pc=12345.6,
            distance_pc_err=None,
            source="SIMBAD",
        )

    monkeypatch.setattr(catalog, "resolve", fake)
    code, out, _err = run(capsys, "some obscure star", "--on", "2026-08-16")
    assert code == 0
    assert "12,345.6 pc" in out
    assert "e+" not in out


def test_bce_observation_dates_are_accepted(capsys):
    code, out, _ = run(capsys, "Sirius", "--on", "-0044-03-15", "--offline")
    assert code == 0
    assert "15 March 44 BCE" in out


def test_on_flag_accepts_equals_syntax_too(capsys):
    code, out, err = run(capsys, "Sirius", "--on=2026-08-16", "--offline")
    assert code == 0
    assert "16 August 2026 CE" in out
    assert err == ""


def test_on_flag_still_defaults_to_today_style_dates_without_a_leading_minus(capsys):
    # A guard against the --on normalization corrupting an ordinary date.
    code, out, err = run(capsys, "Sirius", "--on", "2026-08-16", "--offline")
    assert code == 0
    assert "16 August 2026 CE" in out
    assert err == ""


def test_on_flag_with_no_value_at_the_end_of_argv_is_argparses_own_error(capsys):
    with pytest.raises(SystemExit) as exc_info:
        starlight.main(["Sirius", "--on"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--on" in captured.err


def test_on_flag_with_no_value_before_another_flag_is_argparses_own_error(capsys):
    # --on immediately followed by another recognized flag must not swallow
    # that flag as a bogus date value.
    with pytest.raises(SystemExit) as exc_info:
        starlight.main(["Sirius", "--on", "--offline"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--on" in captured.err


def test_on_flag_followed_by_a_non_date_flag_is_argparses_own_error(capsys):
    # A flag in --on's value position must not be mistaken for a date-shaped
    # value just because BCE_DATE_SHAPE happens not to be checked against it.
    with pytest.raises(SystemExit) as exc_info:
        starlight.main(["Sirius", "--on", "--json"])
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--on" in captured.err


def test_normalize_argv_stops_rewriting_after_a_bare_dashdash():
    # A literal "--on" appearing after "--" is a positional value, not the
    # flag, and must not be merged with the token that follows it.
    argv = ["Sirius", "--", "--on", "-0044-03-15"]
    assert starlight._normalize_argv(argv) == argv


def test_normalize_argv_still_merges_before_a_bare_dashdash():
    result = starlight._normalize_argv(["--on", "-0044-03-15", "--", "extra"])
    assert result == ["--on=-0044-03-15", "--", "extra"]


def test_explicit_empty_on_value_is_a_malformed_date_not_todays_date(capsys):
    code, out, _err = run(capsys, "Sirius", "--on=", "--offline")
    assert code == 2
    assert out == ""


def help_text():
    return starlight.build_parser().format_help()


def test_usage_names_the_module_form_not_a_loose_script():
    # __main__.py uses relative imports and carries no shebang, so a
    # "starlight.py" in the usage line points at something unrunnable.
    text = help_text()
    assert "python -m starlight" in text
    assert "starlight.py" not in text


def test_errors_name_the_module_form_too(capsys):
    with pytest.raises(SystemExit):
        starlight.main([])
    assert "python -m starlight: error:" in capsys.readouterr().err


def test_help_documents_what_name_accepts():
    text = help_text()
    assert "HD 39801" in text  # a catalogue number
    assert "SIMBAD" in text  # where an uncatalogued name is resolved


def test_help_documents_the_bce_date_form():
    assert "-0044-03-15" in help_text()


def test_help_carries_worked_examples():
    text = help_text()
    assert "Examples:" in text
    assert "python -m starlight Betelgeuse --on 2026-08-16" in text


def test_help_lists_every_exit_code():
    text = help_text()
    assert "Exit codes:" in text
    for code, meaning in [("0", "success"), ("1", "unknown star"), ("2", "malformed date"), ("3", "network")]:
        line = [ln for ln in text.splitlines() if ln.strip().startswith(code + " ")]
        assert line, f"no exit-code line for {code}"
        assert meaning in line[0].lower()


def test_a_malformed_date_points_at_the_expected_form(capsys):
    code, _out, err = run(capsys, "Sirius", "--on", "not-a-date", "--offline")
    assert code == 2
    assert "YYYY-MM-DD" in err


def test_an_out_of_range_date_still_points_at_the_expected_form(capsys):
    # The DateError itself says only "13 is not a month", so the hint line is
    # what tells the reader the shape --on wants.
    code, _out, err = run(capsys, "Sirius", "--on", "2026-13-01", "--offline")
    assert code == 2
    assert "13 is not a month" in err
    assert "YYYY-MM-DD" in err


def argparse_error(capsys, *args):
    """Run the CLI expecting argparse to reject argv, and hand back stderr."""
    with pytest.raises(SystemExit) as exc_info:
        starlight.main(list(args))
    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert captured.out == ""  # errors belong on stderr, help included
    return captured.err


def test_a_missing_name_prints_the_whole_help(capsys):
    err = argparse_error(capsys)
    assert "the following arguments are required: name" in err
    assert "Examples:" in err
    assert "Exit codes:" in err
    assert "--uncertainty" in err


def test_a_flag_with_no_value_prints_the_whole_help(capsys):
    err = argparse_error(capsys, "Sirius", "--on")
    assert "expected one argument" in err
    assert "Examples:" in err


def test_an_unrecognized_flag_prints_the_whole_help(capsys):
    err = argparse_error(capsys, "Sirius", "--nope")
    assert "unrecognized arguments: --nope" in err
    assert "Examples:" in err


def test_the_usage_line_is_not_printed_twice(capsys):
    # print_help() already opens with usage; argparse's own error() prints it
    # separately, and the override must not leave both in place.
    assert argparse_error(capsys).count("usage: python -m starlight") == 1


def test_a_bad_date_stays_concise_rather_than_dumping_the_help(capsys):
    # The hint line is more use here than forty lines of help, and burying it
    # under them is the failure this guards against.
    code, _out, err = run(capsys, "Sirius", "--on", "not-a-date", "--offline")
    assert code == 2
    assert "Expected --on YYYY-MM-DD" in err
    assert "Examples:" not in err
