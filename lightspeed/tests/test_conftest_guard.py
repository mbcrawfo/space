import pytest
import pyvista


def test_opening_a_window_in_the_test_suite_fails_loudly():
    """conftest.py patches Plotter.show for the whole session; an accidental window must not slip through."""
    plotter = pyvista.Plotter(off_screen=True)
    with pytest.raises(AssertionError, match=r"Plotter\.show"):
        plotter.show()
