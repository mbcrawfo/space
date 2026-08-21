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
    raise AssertionError(
        "a test tried to open a window via pyvista.Plotter.show; drive the Viewer with a fake plotter instead"
    )


@pytest.fixture(scope="session", autouse=True)
def _no_window_session_guard():
    mp = MonkeyPatch()
    mp.setattr(pyvista.Plotter, "show", _explode)
    yield
    mp.undo()
