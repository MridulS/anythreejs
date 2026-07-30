"""Integration tests: plopp's 3D backend (the vendored checkout in
``external/plopp``, ported to anythreejs) must build real figures and
stream its runtime mutations through the delta protocol.

These need plopp + scipp, which are deliberately NOT in the lockfile
(external/ is a gitignored dev checkout). Install them into the venv with:

    uv pip install -e ./external/plopp scipp

The tests skip cleanly when plopp/scipp are absent.

plopp's own 3D test suites also pass against anythreejs; to run those too:

    uv pip install -e ./external/plopp scipp xarray h5py
    uv run --no-sync pytest \
        external/plopp/tests/plotting/scatter3d_test.py \
        external/plopp/tests/plotting/mesh3d_test.py \
        -W "ignore::PendingDeprecationWarning"

(The -W flag mutes a matplotlib deprecation triggered inside plopp's 2D
colormapper, unrelated to the 3D backend.)
"""

import numpy as np
import pytest

import anythreejs as p3

sc = pytest.importorskip("scipp")
pp = pytest.importorskip("plopp")

from plopp.data.testing import scatter  # noqa: E402


def all_ops(sent):
    return [op for message in sent for op in message["content"]["ops"]]


def assert_referential_integrity(state):
    """Every uuid referenced inside a spec must exist in the objects map."""
    objects = state["objects"]
    for spec in objects.values():
        for key in ("geometry", "material", "map"):
            ref = spec.get(key)
            if isinstance(ref, str):
                assert ref in objects, f"dangling {key} ref in {spec['type']}"
        for child in spec.get("children", []):
            assert child in objects, f"dangling child ref in {spec['type']}"
    if state["scene"] is not None:
        assert state["scene"] in objects
    if state["camera"] is not None:
        assert state["camera"] in objects
    for ctrl in state["controls"]:
        assert ctrl in objects


@pytest.fixture
def scatter_fig():
    return pp.scatter3d(scatter(), x="x", y="y", z="z")


def test_scatter3d_builds_on_anythreejs(scatter_fig):
    canvas = scatter_fig.view.canvas
    assert isinstance(canvas.renderer, p3.Renderer)

    # plopp adds artists after the Renderer exists (they arrive as delta
    # ops); get_state() must lazily fold them into the snapshot so
    # embedding/export sees the full scene.
    state = canvas.renderer.get_state()["_scene_state"]
    assert_referential_integrity(state)

    # The point cloud's positions travel as a binary float32 buffer.
    artist = next(iter(scatter_fig.artists.values()))
    entry = state["objects"][artist.geometry.uuid]["attributes"]["position"]
    assert entry["dtype"] == "float32"
    assert isinstance(entry["data"], memoryview)


def test_autoscale_positioned_camera(scatter_fig):
    canvas = scatter_fig.view.canvas
    # plopp's autoscale must have moved the camera off the default and
    # recorded a home position.
    assert not np.allclose(canvas.camera.position, (0, 0, 5))
    assert "reset" in canvas.camera_backup


def test_artist_opacity_flows_as_delta(scatter_fig, track_ops):
    renderer = scatter_fig.view.canvas.renderer
    sent = track_ops(renderer)

    artist = next(iter(scatter_fig.artists.values()))
    artist.opacity = 0.3

    ops = all_ops(sent)
    material_updates = {
        key: value
        for op in ops
        if op["op"] == "update" and op["uuid"] == artist.material.uuid
        for key, value in op["props"].items()
    }
    # plopp sets opacity and flips depthTest for translucent rendering.
    assert material_updates["opacity"] == 0.3
    assert material_updates["depthTest"] is False
    assert not any(op["op"] == "create" for op in ops)  # no rebuild


def test_colormap_array_update_emits_single_buffer_op(scatter_fig, track_ops):
    renderer = scatter_fig.view.canvas.renderer
    sent = track_ops(renderer)

    artist = next(iter(scatter_fig.artists.values()))
    colors = artist.geometry.attributes["color"]
    colors.array = np.zeros_like(colors.array)

    assert len(sent) == 1
    ops = all_ops(sent)
    assert len(ops) == 1
    assert ops[0]["op"] == "buffer"
    assert ops[0]["uuid"] == artist.geometry.uuid
    assert ops[0]["attribute"] == "color"
    assert len(sent[0]["buffers"]) == 1


def test_interactive_camera_pose_reaches_plopp(scatter_fig, track_ops):
    """plopp reads np.array(self.camera.position) for its camera logic —
    the interactive pose from JS must be visible there."""
    canvas = scatter_fig.view.canvas
    renderer = canvas.renderer
    sent = track_ops(renderer)

    renderer._camera_state = {
        "position": [9.0, 9.0, 9.0],
        "rotation": [0.1, 0.2, 0.3],
        "zoom": 1.0,
        "target": [1.0, 1.0, 1.0],
        "epoch": renderer._epoch,
    }

    assert np.allclose(canvas.camera.position, (9.0, 9.0, 9.0))
    assert np.allclose(canvas.controls.target, (1.0, 1.0, 1.0))
    assert sent == []  # applied silently, no echo


def test_home_after_interactive_orbit(scatter_fig, track_ops):
    """User orbits (JS pose sync-back), then presses home: the camera must
    snap back to the recorded reset position via delta ops."""
    canvas = scatter_fig.view.canvas
    renderer = canvas.renderer
    home_position = tuple(canvas.camera_backup["reset"])

    renderer._camera_state = {
        "position": [50.0, 50.0, 50.0],
        "target": [5.0, 5.0, 5.0],
        "epoch": renderer._epoch,
    }
    assert np.allclose(canvas.camera.position, (50.0, 50.0, 50.0))

    sent = track_ops(renderer)
    canvas.home()

    assert np.allclose(canvas.camera.position, home_position)
    ops = all_ops(sent)
    camera_ops = [op for op in ops if op["uuid"] == canvas.camera.uuid]
    controls_ops = [op for op in ops if op["uuid"] == canvas.controls.uuid]
    assert camera_ops, "home() must emit camera update ops"
    assert controls_ops, "home() must emit controls.target update ops"
    # Python-originated camera move bumps the epoch so the stale JS pose
    # (pre-home) cannot overwrite it.
    assert renderer._camera_epoch == renderer._epoch


def test_toggle_axes_emits_visibility_op(scatter_fig, track_ops):
    canvas = scatter_fig.view.canvas
    sent = track_ops(canvas.renderer)

    canvas.toggle_axes3d()

    ops = all_ops(sent)
    assert {
        "op": "update",
        "uuid": canvas.axes_3d.uuid,
        "props": {"visible": False},
    } in ops


def tetrahedron():
    vertices = sc.vectors(
        dims=["vertices"],
        values=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        unit="m",
    )
    faces = sc.array(
        dims=["faces", "corner"],
        values=np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]]),
    )
    return vertices, faces


def test_mesh3d_builds_on_anythreejs():
    vertices, faces = tetrahedron()
    fig = pp.mesh3d(vertices=vertices, faces=faces, color="red")

    (artist,) = fig.artists.values()
    # plopp indexes the 2D (N, 3) color array — shape must be preserved.
    assert np.array_equal(artist.geometry.attributes["color"].array[0, :], (1, 0, 0))

    state = fig.view.canvas.renderer.get_state()["_scene_state"]
    assert_referential_integrity(state)
    index_entry = state["objects"][artist.geometry.uuid]["index"]
    assert index_entry["dtype"] == "uint32"


def test_mesh3d_edges_share_source_geometry():
    vertices, faces = tetrahedron()
    fig = pp.mesh3d(vertices=vertices, faces=faces, edgecolor="black")

    (artist,) = fig.artists.values()
    state = fig.view.canvas.renderer.get_state()["_scene_state"]
    objects = state["objects"]

    edges_geometry_uuid = objects[artist.edges.uuid]["geometry"]
    # EdgesGeometry must reference the mesh's own geometry by uuid, not a copy.
    assert objects[edges_geometry_uuid]["geometry"] == artist.geometry.uuid
