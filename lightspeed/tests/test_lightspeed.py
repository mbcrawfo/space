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
