"""Integration tests: matplotgl (matplotlib-style 2D plotting on three.js).

Locally these run against the vendored port in ``external/matplotgl``; in
CI they run against *unmodified upstream* scipp/matplotgl (still
pythreejs-importing) through the ``tests/shims`` alias — the port diff is
six import lines, so both paths exercise the same code.

matplotgl exercises the paths plopp doesn't: OrthographicCamera zoom/pan,
ShaderMaterial scatter markers, and mousemove pickers. Its own 37-test
suite also passes against anythreejs; run it with:

    uv run --no-sync pytest external/matplotgl/tests

These need matplotgl installed (deliberately not in the lockfile):

    uv pip install -e ./external/matplotgl

The tests skip cleanly when matplotgl is absent.
"""

import numpy as np
import pytest

import anythreejs as p3

mgl = pytest.importorskip("matplotgl")
import matplotgl.pyplot as plt  # noqa: E402


def test_figure_builds_on_anythreejs_with_referential_integrity():
    fig, ax = plt.subplots()
    x = np.linspace(0, 10, 50)
    ax.plot(x, np.sin(x))

    assert isinstance(ax.renderer, p3.Renderer)
    state = ax.renderer.get_state()["_scene_state"]
    objects = state["objects"]
    for spec in objects.values():
        for key in ("geometry", "material", "map"):
            ref = spec.get(key)
            if isinstance(ref, str):
                assert ref in objects, f"dangling {key} ref in {spec['type']}"
        for child in spec.get("children", []):
            assert child in objects


def test_scatter_markers_use_shader_material():
    fig, ax = plt.subplots()
    rng = np.random.default_rng(0)
    ax.scatter(rng.random(100), rng.random(100), c=rng.random(100))

    state = ax.renderer.get_state()["_scene_state"]
    types = {spec["type"] for spec in state["objects"].values()}
    assert "ShaderMaterial" in types
    shader_spec = next(
        spec for spec in state["objects"].values() if spec["type"] == "ShaderMaterial"
    )
    assert "gl_" in shader_spec["fragmentShader"]  # real GLSL made it through


def test_ortho_zoom_flows_as_batched_camera_ops(track_ops):
    """matplotgl zooms by moving OrthographicCamera bounds under a hold —
    that must arrive as one message of camera ops and bump the camera
    epoch so stale interactive poses can't undo it."""
    fig, ax = plt.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    renderer = ax.renderer
    sent = track_ops(renderer)

    with ax.camera.hold_trait_notifications():
        ax.camera.left = -5.0
        ax.camera.right = 5.0
        ax.camera.bottom = -5.0
        ax.camera.top = 5.0

    assert len(sent) == 1
    ops = sent[0]["content"]["ops"]
    assert {op["uuid"] for op in ops} == {ax.camera.uuid}
    assert len(ops) == 4
    assert renderer._camera_epoch == renderer._epoch


def test_picker_mousemove_updates_without_resync(track_ops):
    """matplotgl's cursor readout observes picker.point on mousemove —
    high-frequency events must not emit any ops."""
    fig, ax = plt.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    renderer = ax.renderer
    picker = next(ctrl for ctrl in renderer.controls if ctrl._type == "Picker")
    sent = track_ops(renderer)

    seen = []
    picker.observe(lambda change: seen.append(change["new"]), names=["point"])
    for i in range(50):
        renderer._picker_event = {
            "picker_uuid": picker.uuid,
            "point": [float(i), 0.0, 0.0],
        }

    assert len(seen) == 50
    assert sent == []
