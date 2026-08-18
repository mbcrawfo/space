"""Session-wide guarantee that the test suite never touches the network.

`catalog._http_post` is the only seam through which any test could reach
SIMBAD. This patches it to explode for the whole session, structurally,
rather than relying on every test file remembering to stub it itself.
Individual tests override it as needed (via the function-scoped `monkeypatch`
fixture, which restores this session-level patch once the test ends) to
supply a canned response or a simulated failure.
"""

import pytest
from _pytest.monkeypatch import MonkeyPatch

import catalog


def _explode(*args, **kwargs):
    raise AssertionError("a test tried to reach the network via catalog._http_post; stub it with monkeypatch instead")


@pytest.fixture(scope="session", autouse=True)
def _no_network_session_guard():
    mp = MonkeyPatch()
    mp.setattr(catalog, "_http_post", _explode)
    yield
    mp.undo()
