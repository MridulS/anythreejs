"""Test fixtures: run ipywidgets without a kernel, capture the delta
messages a Renderer sends, and drive the browser harness."""

from pathlib import Path

import comm
import pytest
from comm.base_comm import BaseComm

TESTS_DIR = Path(__file__).parent
REPO_ROOT = TESTS_DIR.parent
HARNESS_ORIGIN = "http://anythreejs.test"

HARNESS_FILES = {
    "/index.html": (TESTS_DIR / "harness" / "index.html", "text/html"),
    "/harness.js": (TESTS_DIR / "harness" / "harness.js", "text/javascript"),
    "/widget.js": (
        REPO_ROOT / "src" / "anythreejs" / "static" / "widget.js",
        "text/javascript",
    ),
}


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


class HarnessDriver:
    """Python-side driver for the browser harness page."""

    def __init__(self, page, errors):
        self.page = page
        self.errors = errors

    def boot(self, renderer, **state):
        from harness_utils import snapshot_payload

        payload = {"scene_state": snapshot_payload(renderer), "state": state}
        return self.page.evaluate("(p) => window.harness.boot(p)", payload)

    def apply(self, sent):
        from harness_utils import messages_payload

        payload = messages_payload(sent)
        sent.clear()
        return self.page.evaluate("(m) => window.harness.applyMessages(m)", payload)

    def apply_timed(self, sent):
        from harness_utils import messages_payload

        payload = messages_payload(sent)
        sent.clear()
        return self.page.evaluate(
            "(m) => window.harness.applyMessagesTimed(m)", payload
        )

    def set_scene_state(self, renderer):
        from harness_utils import snapshot_payload

        return self.page.evaluate(
            "(p) => window.harness.setSceneState(p)", snapshot_payload(renderer)
        )

    def summary(self):
        return self.page.evaluate("window.harness.summary()")

    def object(self, uuid):
        return self.page.evaluate("(u) => window.harness.object(u)", uuid)

    def pixel(self, fx, fy):
        return self.page.evaluate(f"window.harness.readPixel({fx}, {fy})")

    def render_info(self):
        return self.page.evaluate("window.harness.renderInfo()")

    def saved_states(self):
        return self.page.evaluate("window.harness.savedStates()")

    def measure_fps(self, duration_ms=1000):
        return self.page.evaluate(f"window.harness.measureFps({duration_ms})")

    def set_auto_rotate(self, enabled):
        return self.page.evaluate("(v) => window.harness.setAutoRotate(v)", enabled)

    def screenshot(self):
        return self.page.evaluate("window.harness.screenshot()")

    def assert_clean(self):
        assert not self.errors, f"browser errors: {self.errors}"


@pytest.fixture
def harness(page):
    errors = []
    page.on("pageerror", lambda err: errors.append(f"pageerror: {err}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.error: {msg.text}")
        if msg.type == "error"
        else None,
    )

    def serve(route):
        path = route.request.url.split("anythreejs.test", 1)[1].split("?")[0]
        entry = HARNESS_FILES.get(path)
        if entry:
            route.fulfill(path=str(entry[0]), content_type=entry[1])
        else:
            route.abort()

    page.route(f"{HARNESS_ORIGIN}/*", serve)
    # The shipped bundle must never reach for the network.
    page.context.set_offline(True)

    page.goto(f"{HARNESS_ORIGIN}/index.html")
    page.wait_for_function("window.harnessReady === true")
    return HarnessDriver(page, errors)


@pytest.fixture
def track_wire(monkeypatch):
    """Record EVERY message crossing the comm — including trait syncs (the
    snapshot channel), which ``track_ops`` cannot see because it wraps
    only ``renderer.send``. That blind spot once hid a 28MB-per-toolbar-
    click resync. Entries: {"type", "json" bytes, "buffers" bytes}."""
    import json as _json

    records = []

    def publish_msg(self, msg_type, data=None, metadata=None, buffers=None, **keys):
        records.append(
            {
                "type": msg_type,
                "json": len(_json.dumps(data, default=str).encode()) if data else 0,
                "buffers": sum(
                    len(bytes(b)) if isinstance(b, memoryview) else len(b)
                    for b in (buffers or [])
                ),
            }
        )

    monkeypatch.setattr(DummyComm, "publish_msg", publish_msg)
    return records


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
