"""Browser-level tests: widget.js running in real Chromium (Playwright).

The page hosts a FakeModel (tests/harness/harness.js) implementing the
anywidget model API surface widget.js uses. Every payload fed to the page
is produced by the *real* Python side — snapshots via renderer.get_state(),
delta ops captured from renderer.send — so the wire protocol is exercised
end-to-end without a Jupyter kernel. Assertions cover the reconstructed
three.js world, actual rendered pixels (gl.readPixels via software WebGL),
GPU resource counts (renderer.info.memory), and the interactive-orbit
camera sync-back round trip.

The page loads the *shipped* widget bundle (src/anythreejs/static/widget.js,
three.js included) with the browser forced offline — so these tests also
prove the bundle is fully self-contained, which is what air-gapped
deployments rely on. Requires `uv run playwright install chromium`; tests
skip when the browser is unavailable.
"""

import numpy as np
import pytest

pytest.importorskip("pytest_playwright")

import anythreejs as p3  # noqa: E402

# The shared `harness` fixture (tests/conftest.py) serves the shipped
# bundle from a virtual origin with the browser forced offline.


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


def test_data_texture_update_renders_correctly(harness, track_ops):
    """Regression: a uint8 image update must still render as uint8 —
    the float32 coercion bug turned updated textures white."""
    red = np.zeros((8, 8, 4), dtype="uint8")
    red[..., 0] = 255
    red[..., 3] = 255
    texture = p3.DataTexture(data=red)
    plane = p3.Mesh(
        geometry=p3.PlaneGeometry(4, 4),
        material=p3.MeshBasicMaterial(map=texture),
    )
    scene = p3.Scene(children=[plane], background="#ffffff")
    camera = p3.PerspectiveCamera(position=[0, 0, 2], aspect=200 / 150)
    renderer = p3.Renderer(scene=scene, camera=camera)
    sent = track_ops(renderer)
    harness.boot(renderer)
    assert_color(harness.pixel(0.5, 0.5), 255, 0, 0)

    blue = np.zeros((8, 8, 4), dtype="uint8")
    blue[..., 2] = 255
    blue[..., 3] = 255
    texture.data = blue
    harness.apply(sent)

    assert_color(harness.pixel(0.5, 0.5), 0, 0, 255)
    harness.assert_clean()


def test_camera_replacement_adopts_new_pose(harness):
    """Regression: pose preservation across snapshot swaps must not apply
    when the camera itself was replaced — the new camera's Python-set
    position wins."""
    renderer, mesh = box_fixture()
    harness.boot(renderer)
    harness.page.evaluate("window.harness.world.camera.position.set(2, 2, 2)")

    renderer.camera = p3.PerspectiveCamera(position=[0, 0, 9], aspect=200 / 150)
    summary = harness.set_scene_state(renderer)

    assert summary["camera"]["position"] == pytest.approx([0, 0, 9])
    harness.assert_clean()


def test_late_attribute_survives_rebuild(harness, track_ops):
    """Regression: an attribute added to a geometry serialized without any
    attributes was applied in place but never merged into the JS-side spec,
    so a later rebuild silently dropped it."""
    geometry = p3.BufferGeometry()  # empty: snapshot spec has no attributes
    points = p3.Points(geometry=geometry, material=p3.PointsMaterial(size=5))
    scene = p3.Scene(children=[points])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)
    harness.boot(renderer)

    geometry.attributes["position"] = p3.BufferAttribute(
        np.zeros((10, 3), dtype="float32")
    )
    harness.apply(sent)
    assert harness.object(geometry.uuid)["attributes"]["position"]["length"] == 30

    harness.page.evaluate(f"window.harness.world.rebuildResource('{geometry.uuid}')")
    after = harness.object(geometry.uuid)
    assert after["attributes"]["position"]["length"] == 30
    harness.assert_clean()


def test_directional_light_target_aims_the_light(harness):
    """Regression: the light's target Object3D is not in the scene graph,
    so without a manual matrixWorld update three.js silently ignored any
    non-origin target and always aimed the light at the origin."""

    def lit_plane(target):
        plane = p3.Mesh(
            geometry=p3.PlaneGeometry(2, 2),
            material=p3.MeshLambertMaterial(color="#ffffff"),
        )
        scene = p3.Scene(
            children=[
                plane,
                p3.DirectionalLight(position=[0, 0, 5], intensity=3, target=target),
            ],
            background="#000000",
        )
        camera = p3.PerspectiveCamera(position=[0, 0, 3], aspect=200 / 150)
        return p3.Renderer(scene=scene, camera=camera)

    harness.boot(lit_plane([0, 0, 0]))
    head_on = harness.pixel(0.5, 0.5)[0]

    harness.boot(lit_plane([50, 0, 0]))  # aimed far sideways: grazing light
    grazing = harness.pixel(0.5, 0.5)[0]

    # Before the fix both rendered identically (target ignored). sRGB
    # encoding lifts the grazing value, so the contract is the contrast.
    assert head_on > 150, (head_on, grazing)
    assert head_on - grazing > 100, (head_on, grazing)
    harness.assert_clean()


def test_point_line_materials_honor_base_props_at_build(harness):
    """Regression: buildMaterial dropped visible/side/depthTest/depthWrite
    for Points/LineBasic/LineDashed materials, so construction-time state
    (and any live state, after a resync) fell back to three.js defaults."""
    line_material = p3.LineBasicMaterial(depthTest=False, visible=False)
    points_material = p3.PointsMaterial(size=3, visible=False)
    positions = p3.BufferAttribute(np.zeros((2, 3), dtype="float32"))
    scene = p3.Scene(
        children=[
            p3.Line(
                geometry=p3.BufferGeometry(attributes={"position": positions}),
                material=line_material,
            ),
            p3.Points(
                geometry=p3.BufferGeometry(attributes={"position": positions}),
                material=points_material,
            ),
        ]
    )
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    harness.boot(renderer)

    built_line = harness.object(line_material.uuid)
    assert built_line["depthTest"] is False
    assert built_line["visible"] is False
    assert harness.object(points_material.uuid)["visible"] is False
    harness.assert_clean()


def test_lit_material_texture_map_builds(harness):
    """map= on MeshStandardMaterial must reach the built three.js
    material (was dropped at both the catalog and buildMaterial layers)."""
    image = np.full((4, 4, 4), 255, dtype="uint8")
    material = p3.MeshStandardMaterial(map=p3.DataTexture(data=image))
    scene = p3.Scene(children=[p3.Mesh(geometry=p3.BoxGeometry(), material=material)])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    harness.boot(renderer)

    assert harness.object(material.uuid)["hasMap"] is True
    harness.assert_clean()


def test_clearing_geometry_clears_pixels(harness, track_ops):
    """mesh.geometry = None must actually empty the mesh in the browser
    (the null update was once silently ignored)."""
    renderer, mesh = box_fixture()
    sent = track_ops(renderer)
    harness.boot(renderer)
    assert_color(harness.pixel(0.5, 0.5), 255, 0, 0)

    mesh.geometry = None
    harness.apply(sent)

    assert_color(harness.pixel(0.5, 0.5), 255, 255, 255)  # background
    harness.assert_clean()


def test_incremental_controls_and_camera_swap_via_ops(harness, track_ops):
    """Controls/camera replacement now travels as small ops (set_controls/
    set_camera) instead of a full snapshot resync — the browser must apply
    them without a world rebuild, honoring the new spec target."""
    renderer, mesh = box_fixture()
    sent = track_ops(renderer)
    harness.boot(renderer)
    harness.page.evaluate("window.harness.world.controlsTarget.set(9, 9, 9)")

    renderer.controls = [
        p3.OrbitControls(controlling=renderer.camera, target=(10, 0, 0)),
        p3.Picker(event="click"),
    ]
    summary = harness.apply(sent)
    assert summary["byType"]["OrbitControls"] == 1  # old one removed
    target = harness.page.evaluate(
        "[...window.harness.world.views][0].controls.target.toArray()"
    )
    assert target == pytest.approx([10, 0, 0])

    # Re-aim at the origin first — otherwise the pixel assertion below
    # races the controls legitimately rotating the new camera toward the
    # (10, 0, 0) target set above (this race masqueraded as a cold-start
    # flake more than once).
    renderer.controls[0].target = (0, 0, 0)
    renderer.camera = p3.PerspectiveCamera(position=[0, 0, 9], aspect=200 / 150)
    summary = harness.apply(sent)
    assert summary["camera"]["position"] == pytest.approx([0, 0, 9])
    assert_color(harness.pixel(0.5, 0.5), 255, 0, 0)  # still renders
    harness.assert_clean()


def test_controls_replacement_adopts_spec_target(harness):
    """Regression: the interactive controls-target latch survived full
    resyncs, so a NEW controls object's Python-set target was ignored and
    then clobbered back by the next sync."""
    renderer, mesh = box_fixture()
    harness.boot(renderer)
    # Simulate an interactive target the Python side doesn't know about.
    harness.page.evaluate("window.harness.world.controlsTarget.set(9, 9, 9)")

    renderer.controls = [
        p3.OrbitControls(controlling=renderer.camera, target=(10, 0, 0))
    ]
    harness.set_scene_state(renderer)

    target = harness.page.evaluate(
        "[...window.harness.world.views][0].controls.target.toArray()"
    )
    assert target == pytest.approx([10, 0, 0])
    harness.assert_clean()


def test_vertex_colors_are_treated_as_srgb(harness, track_ops):
    """Issue #3: vertex colors come from matplotlib in sRGB, but three.js
    r152+ interprets the attribute as linear — without conversion a 0.5
    gray washed out to 188. It must render ~128, through both the build
    path and the buffer-update path."""
    n = 4
    colors = np.full((n, 4), 0.5, dtype="float32")
    colors[:, 3] = 1.0
    attr = p3.BufferAttribute(colors, itemSize=4)
    geometry = p3.BufferGeometry(
        attributes={
            "position": p3.BufferAttribute(np.zeros((n, 3), dtype="float32")),
            "color": attr,
        }
    )
    points = p3.Points(
        geometry=geometry,
        material=p3.PointsMaterial(size=100, vertexColors=True, sizeAttenuation=False),
    )
    scene = p3.Scene(children=[points], background="#000000")
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera(position=[0, 0, 3]))
    sent = track_ops(renderer)
    harness.boot(renderer)

    built = harness.pixel(0.5, 0.5)[0]
    assert 110 < built < 146, built  # washed-out rendered 188

    quarter = np.full((n, 4), 0.25, dtype="float32")
    quarter[:, 3] = 1.0
    attr.array = quarter
    harness.apply(sent)

    updated = harness.pixel(0.5, 0.5)[0]
    assert 50 < updated < 80, updated  # washed-out rendered ~137


def test_text_textures_are_square_by_default(harness):
    """Issue #4: pythreejs draws text into a square canvas by default, so
    a default-scale 1:1 sprite shows it unsquashed — plopp's axis labels
    rely on that."""
    assert p3.TextTexture().to_dict()["squareTexture"] is True

    texture = p3.TextTexture(string="temperature", size=64)
    sprite = p3.Sprite(material=p3.SpriteMaterial(map=texture, transparent=True))
    scene = p3.Scene(children=[sprite], background="#000000")
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera(position=[0, 0, 3]))
    harness.boot(renderer)

    dims = harness.page.evaluate(
        f"""() => {{
          const texture = window.harness.world.objects.get("{texture.uuid}");
          return [texture.image.width, texture.image.height];
        }}"""
    )
    assert dims[0] == dims[1]
    harness.assert_clean()


def test_exec_three_obj_method_invokes_in_browser(harness, track_ops):
    """The invoke op must call real methods on registry objects and on the
    per-view controls instances."""
    renderer, mesh = box_fixture()
    sent = track_ops(renderer)
    harness.boot(renderer)

    mesh.exec_three_obj_method("translateX", 1.5)
    renderer.controls[0].exec_three_obj_method("update")
    harness.apply(sent)

    assert harness.object(mesh.uuid)["position"] == pytest.approx([1.5, 0.0, 0.0])
    harness.assert_clean()


def test_quaternion_orients_objects(harness, track_ops):
    """McStasScript orients components via quaternions: they must apply at
    build and via delta updates. A long thin bar rotated 90 degrees about
    Z reads vertical, then horizontal again after resetting to identity."""
    half = float(np.sqrt(0.5))
    mesh = p3.Mesh(
        geometry=p3.BoxGeometry(2, 0.2, 0.2),
        material=p3.MeshBasicMaterial(color="#ff0000"),
        quaternion=(0.0, 0.0, half, half),  # 90 degrees about Z
    )
    scene = p3.Scene(children=[mesh], background="#ffffff")
    camera = p3.PerspectiveCamera(position=[0, 0, 4], aspect=200 / 150)
    renderer = p3.Renderer(scene=scene, camera=camera)
    sent = track_ops(renderer)
    harness.boot(renderer)

    assert harness.object(mesh.uuid)["quaternion"] == pytest.approx(
        [0.0, 0.0, half, half]
    )
    assert_color(harness.pixel(0.5, 0.7), 255, 0, 0)  # vertical bar
    assert_color(harness.pixel(0.7, 0.5), 255, 255, 255)  # sides are empty

    mesh.quaternion = (0.0, 0.0, 0.0, 1.0)
    harness.apply(sent)

    assert_color(harness.pixel(0.7, 0.5), 255, 0, 0)  # horizontal again
    assert_color(harness.pixel(0.5, 0.7), 255, 255, 255)
    harness.assert_clean()


def test_edges_follow_source_geometry(harness, track_ops):
    """EdgesGeometry entries rebuild when their source geometry's
    positions change (previously a documented limitation: edges froze at
    their construction-time shape)."""
    positions = p3.BufferAttribute(
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype="float32")
    )
    geometry = p3.BufferGeometry(
        attributes={"position": positions},
        index=p3.BufferAttribute(np.array([0, 1, 2], dtype="uint32"), itemSize=1),
    )
    mesh = p3.Mesh(geometry=geometry, material=p3.MeshBasicMaterial())
    edges = p3.LineSegments(
        geometry=p3.EdgesGeometry(geometry),
        material=p3.LineBasicMaterial(color="#000000"),
    )
    scene = p3.Scene(children=[mesh, edges])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)
    harness.boot(renderer)

    edges_uuid = edges.geometry.uuid
    assert harness.object(edges_uuid)["boundingSphereRadius"] < 2

    positions.array = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], dtype="float32")
    harness.apply(sent)

    # The derived edges rebuilt from the moved source geometry.
    assert harness.object(edges_uuid)["boundingSphereRadius"] > 4
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
