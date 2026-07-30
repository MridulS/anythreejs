"""Test fixtures: run ipywidgets without a kernel and capture the delta
messages a Renderer sends."""

import comm
import pytest
from comm.base_comm import BaseComm


class DummyComm(BaseComm):
    """A comm that swallows messages (no kernel in tests)."""

    def publish_msg(self, msg_type, data=None, metadata=None, buffers=None, **keys):
        pass


def _create_comm(*args, **kwargs):
    return DummyComm(*args, **kwargs)


comm.create_comm = _create_comm


# --- Browser harness fixtures (pytest-playwright) -------------------------


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Allow software WebGL in headless Chromium."""
    args = [*browser_type_launch_args.get("args", []), "--enable-unsafe-swiftshader"]
    return {**browser_type_launch_args, "args": args}


@pytest.fixture(scope="session")
def browser(launch_browser):
    """Skip browser tests cleanly when Chromium isn't installed."""
    try:
        browser = launch_browser()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"playwright browser unavailable: {exc}")
    yield browser
    browser.close()


@pytest.fixture
def track_ops():
    """Replace ``renderer.send`` with a recorder; returns the list that
    collects ``{"content": ..., "buffers": ...}`` entries for every delta
    message the renderer flushes."""

    def _track(renderer):
        sent = []

        def send(content, buffers=None):
            sent.append({"content": content, "buffers": buffers})

        renderer.send = send
        return sent

    return _track
