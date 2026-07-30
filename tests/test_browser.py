"""Browser-level tests: widget.js running in real Chromium (Playwright).

The page hosts a FakeModel (tests/harness/harness.js) implementing the
anywidget model API surface widget.js uses. Every payload fed to the page
is produced by the *real* Python side — snapshots via renderer.get_state(),
delta ops captured from renderer.send — so the wire protocol is exercised
end-to-end without a Jupyter kernel. Assertions cover the reconstructed
three.js world, actual rendered pixels (gl.readPixels via software WebGL),
GPU resource counts (renderer.info.memory), and the interactive-orbit
camera sync-back round trip.

three.js is fetched from esm.sh on the first run and recorded into
tests/harness/.cache/esm.har (gitignored); subsequent runs replay it
offline. Requires `uv run playwright install chromium`; tests skip when
the browser is unavailable.
"""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pytest_playwright")

import anythreejs as p3  # noqa: E402
from harness_utils import messages_payload, snapshot_payload  # noqa: E402

TESTS_DIR = Path(__file__).parent
REPO_ROOT = TESTS_DIR.parent
ORIGIN = "http://anythreejs.test"

SERVED = {
    "/index.html": (TESTS_DIR / "harness" / "index.html", "text/html"),
    "/harness.js": (TESTS_DIR / "harness" / "harness.js", "text/javascript"),
    "/widget.js": (
        REPO_ROOT / "src" / "anythreejs" / "widget.js",
        "text/javascript",
    ),
}

HAR = TESTS_DIR / "harness" / ".cache" / "esm.har"
# Decided once per session: a missing HAR means this whole run records from
# the network; an existing HAR means the whole run replays it with the
# browser forced offline, so any gap in the recording fails loudly instead
# of silently falling back to the network. To re-record: delete .cache/.
RECORD_HAR = not HAR.exists()


class Driver:
    def __init__(self, page, errors):
        self.page = page
        self.errors = errors

    def boot(self, renderer, **state):
        payload = {"scene_state": snapshot_payload(renderer), "state": state}
        return self.page.evaluate("(p) => window.harness.boot(p)", payload)

    def apply(self, sent):
        payload = messages_payload(sent)
        sent.clear()
        return self.page.evaluate("(m) => window.harness.applyMessages(m)", payload)

    def set_scene_state(self, renderer):
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
        entry = SERVED.get(path)
        if entry:
            route.fulfill(path=str(entry[0]), content_type=entry[1])
        else:
            route.abort()

    page.route(f"{ORIGIN}/*", serve)

    HAR.parent.mkdir(exist_ok=True)
    page.route_from_har(str(HAR), url="**/esm.sh/**", update=RECORD_HAR)
    if not RECORD_HAR:
        page.context.set_offline(True)

    page.goto(f"{ORIGIN}/index.html")
    page.wait_for_function("window.harnessReady === true")
    return Driver(page, errors)


def box_fixture(color="#ff0000", background="#ffffff"):
    mesh = p3.Mesh(
        geometry=p3.BoxGeometry(1, 1, 1),
        material=p3.MeshBasicMaterial(color=color),
    )
    scene = p3.Scene(children=[mesh], background=background)
    camera = p3.PerspectiveCamera(position=[0, 0, 3], aspect=200 / 150)
    renderer = p3.Renderer(
        scene=scene, camera=camera, controls=[p3.OrbitControls(controlling=camera)]
    )
    return renderer, mesh


def assert_color(pixel, r, g, b, tolerance=40):
    assert abs(pixel[0] - r) < tolerance, pixel
    assert abs(pixel[1] - g) < tolerance, pixel
    assert abs(pixel[2] - b) < tolerance, pixel


def test_snapshot_builds_world_and_renders_pixels(harness):
    renderer, mesh = box_fixture()
    summary = harness.boot(renderer)

    assert summary["byType"]["Mesh"] == 1
    assert summary["byType"]["BoxGeometry"] == 1
    assert summary["byType"]["OrbitControls"] == 1
    assert summary["sceneNodes"] >= 3  # scene + mesh + camera

    assert_color(harness.pixel(0.5, 0.5), 255, 0, 0)  # red box
    assert_color(harness.pixel(0.03, 0.03), 255, 255, 255)  # white background
    harness.assert_clean()


def test_delta_color_update_changes_pixels(harness, track_ops):
    renderer, mesh = box_fixture(color="#00ff00")
    sent = track_ops(renderer)
    harness.boot(renderer)
    assert_color(harness.pixel(0.5, 0.5), 0, 255, 0)

    mesh.material.color = "#0000ff"
    harness.apply(sent)

    assert_color(harness.pixel(0.5, 0.5), 0, 0, 255)
    harness.assert_clean()


def test_add_remove_disposes_gpu_resources(harness, track_ops):
    scene = p3.Scene(background="#ffffff")
    camera = p3.PerspectiveCamera(position=[0, 0, 3], aspect=200 / 150)
    renderer = p3.Renderer(scene=scene, camera=camera)
    sent = track_ops(renderer)
    harness.boot(renderer)
    baseline = harness.render_info()

    mesh = p3.Mesh(
        geometry=p3.SphereGeometry(radius=1),
        material=p3.MeshBasicMaterial(color="#ff0000"),
    )
    scene.add(mesh)
    harness.apply(sent)

    grown = harness.render_info()
    assert grown["geometries"] == baseline["geometries"] + 1
    assert_color(harness.pixel(0.5, 0.5), 255, 0, 0)

    scene.remove(mesh)
    summary = harness.apply(sent)

    shrunk = harness.render_info()
    assert shrunk["geometries"] == baseline["geometries"]  # disposed, no leak
    assert summary["byType"].get("Mesh") is None  # gone from the registry too
    assert_color(harness.pixel(0.5, 0.5), 255, 255, 255)
    harness.assert_clean()


def test_buffer_op_updates_attribute_in_place(harness, track_ops):
    positions = p3.BufferAttribute(np.zeros((50, 3), dtype="float32"), itemSize=3)
    geometry = p3.BufferGeometry(attributes={"position": positions})
    points = p3.Points(geometry=geometry, material=p3.PointsMaterial(size=5))
    scene = p3.Scene(children=[points])
    camera = p3.PerspectiveCamera(position=[0, 0, 3])
    renderer = p3.Renderer(scene=scene, camera=camera)
    sent = track_ops(renderer)
    harness.boot(renderer)

    before = harness.object(geometry.uuid)
    assert before["attributes"]["position"]["length"] == 150
    assert before["boundingSphereRadius"] == 0

    spread = np.random.default_rng(3).random((50, 3)).astype("float32") * 4
    positions.array = spread
    harness.apply(sent)

    after = harness.object(geometry.uuid)
    assert after["attributes"]["position"]["length"] == 150
    assert after["attributes"]["position"]["first"] == pytest.approx(
        spread.reshape(-1)[:6].tolist()
    )
    assert after["boundingSphereRadius"] > 1
    harness.assert_clean()


def test_camera_ops_apply_and_carry_epoch(harness, track_ops):
    renderer, mesh = box_fixture()
    sent = track_ops(renderer)
    harness.boot(renderer)

    renderer.camera.position = [0, 0, 10]
    summary = harness.apply(sent)

    assert summary["camera"]["position"] == pytest.approx([0, 0, 10])
    assert summary["epoch"] == renderer._epoch
    harness.assert_clean()


def test_interactive_orbit_round_trip(harness, track_ops):
    """Drag on the canvas with the real mouse; the camera pose must arrive
    tagged with the current epoch, and feeding it back into the Python
    renderer must land on the Python camera and controls."""
    renderer, mesh = box_fixture()
    sent = track_ops(renderer)
    harness.boot(renderer)

    box = harness.page.locator("canvas").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    harness.page.mouse.move(cx, cy)
    harness.page.mouse.down()
    for step in range(1, 6):
        harness.page.mouse.move(cx + step * 12, cy + step * 6)
    harness.page.mouse.up()
    harness.page.wait_for_timeout(200)

    saved = [s for s in harness.saved_states() if "_camera_state" in s]
    assert saved, "orbit interaction must sync camera state back"
    state = saved[-1]["_camera_state"]
    assert state["epoch"] == renderer._epoch
    assert state["position"] != pytest.approx([0, 0, 3])  # camera moved

    renderer._camera_state = state
    assert list(renderer.camera.position) == pytest.approx(state["position"])
    assert list(renderer.controls[0].target) == pytest.approx(state["target"])
    assert sent == []  # applying the remote pose must not echo ops
    harness.assert_clean()


def test_scene_snapshot_swap_preserves_interactive_pose(harness):
    renderer, mesh = box_fixture(background="#ffffff")
    harness.boot(renderer)

    # Simulate an interactive JS-side pose the Python side doesn't know.
    harness.page.evaluate("window.harness.world.camera.position.set(2, 2, 2)")

    renderer.scene.background = "#000000"
    renderer.render()  # full resync -> fresh snapshot trait
    summary = harness.set_scene_state(renderer)

    assert summary["camera"]["position"] == pytest.approx([2, 2, 2])
    assert_color(harness.pixel(0.03, 0.03), 0, 0, 0)  # new background applied
    harness.assert_clean()


def test_hex8_colors_and_torus(harness):
    torus = p3.TorusGeometry(radius=1, tube=0.4)
    mesh = p3.Mesh(geometry=torus, material=p3.MeshBasicMaterial(color="#00ff00ff"))
    scene = p3.Scene(children=[mesh], background="#ffffff")
    camera = p3.PerspectiveCamera(position=[0, 0, 3], aspect=200 / 150)
    renderer = p3.Renderer(scene=scene, camera=camera)
    harness.boot(renderer)

    material_uuid = renderer._scene_state["objects"][mesh.uuid]["material"]
    assert harness.object(material_uuid)["colorHex"] == "00ff00"

    geometry = harness.object(torus.uuid)
    assert geometry["type"] == "TorusGeometry"
    assert geometry["parameters"]["radius"] == 1

    assert_color(harness.pixel(0.5, 0.5), 255, 255, 255)  # hole in the donut
    assert_color(harness.pixel(0.77, 0.5), 0, 255, 0)  # tube is green
    harness.assert_clean()


def test_every_catalog_type_builds_in_browser(harness):
    """Anti-drift gate: every type Python can produce must build a real
    three.js object in the JS registry. A missing JS case — the old
    TorusGeometry-renders-a-box bug — fails here by construction."""
    from anythreejs.core.spec import CATALOG

    scene = p3.Scene(background="#ffffff")
    checked = {}  # uuid -> catalog type name

    def register(obj, node):
        checked[obj.uuid] = obj._type
        scene.add(node)

    def line_points(n):
        return p3.BufferGeometry(
            attributes={
                "position": p3.BufferAttribute(np.zeros((n, 3), dtype="float32"))
            }
        )

    basic = p3.MeshBasicMaterial()
    box = p3.BoxGeometry()
    for name, entry in CATALOG.items():
        if name == "Material":
            continue  # abstract base, not a renderable JS type
        cls = getattr(p3, name)
        category = entry["category"]
        if category == "geometry":
            geometry = cls()
            register(geometry, p3.Mesh(geometry=geometry, material=basic))
        elif category == "material":
            material = cls()
            if name == "LineMaterial":
                node = p3.Line2(
                    geometry=p3.LineGeometry(
                        positions=np.array([[0, 0, 0], [1, 1, 1]], dtype="float32")
                    ),
                    material=material,
                )
            elif name == "SpriteMaterial":
                node = p3.Sprite(material=material)
            elif name == "PointsMaterial":
                node = p3.Points(geometry=line_points(3), material=material)
            elif name in ("LineBasicMaterial", "LineDashedMaterial"):
                node = p3.Line(geometry=line_points(2), material=material)
            else:
                node = p3.Mesh(geometry=box, material=material)
            register(material, node)
        elif category in ("light", "helper"):
            instance = cls()
            register(instance, instance)
        elif category == "texture":
            texture = cls(string="x") if name == "TextTexture" else cls()
            register(texture, p3.Sprite(material=p3.SpriteMaterial(map=texture)))

    camera = p3.PerspectiveCamera(position=[0, 0, 5])
    controls = [p3.OrbitControls(controlling=camera), p3.TrackballControls()]
    renderer = p3.Renderer(scene=scene, camera=camera, controls=controls)
    harness.boot(renderer)

    missing = [
        f"{type_name} ({uuid})"
        for uuid, type_name in checked.items()
        if harness.object(uuid) is None
    ]
    assert not missing, f"catalog types widget.js failed to build: {missing}"

    summary = harness.summary()
    assert summary["byType"]["OrbitControls"] == 1
    assert summary["byType"]["TrackballControls"] == 1
    harness.render_info()  # full render over everything must not error
    harness.assert_clean()


def test_plopp_scatter3d_renders_in_browser(harness):
    pytest.importorskip("scipp")
    pp = pytest.importorskip("plopp")
    from plopp.data.testing import scatter

    fig = pp.scatter3d(scatter(), x="x", y="y", z="z")
    renderer = fig.view.canvas.renderer
    summary = harness.boot(renderer, width=300, height=225)

    assert summary["byType"]["Points"] >= 1
    assert summary["byType"]["AxesHelper"] == 1
    assert summary["byType"].get("Sprite", 0) >= 3  # outline axis labels
    assert summary["registry"] > 10
    harness.render_info()  # a full render pass must not error
    harness.assert_clean()
