"""Integration tests: McStasScript's geometry viewer (3D neutron
instrument view) running on anythreejs as a pythreejs drop-in.

McStasScript imports pythreejs by name; the alias below resolves it to
anythreejs — the CI gate does the same for McStasScript's own test suite
via ``PYTHONPATH=tests/shims``. Its usage exercises what plopp/matplotgl
don't: quaternion-based component orientation, CircleGeometry, cone-via-
cylinder shapes, Group-scoped pickers with raycast tolerances, and
appending a picker through the controls setter after display.

Locally, McStasScript must be importable:

    uv pip install -e ./external/McStasScript

The tests skip cleanly when it is absent.
"""

import sys
import warnings
from types import SimpleNamespace

import numpy as np
import pytest

import anythreejs as p3

sys.modules.setdefault("pythreejs", p3)

pytest.importorskip("mcstasscript")

from mcstasscript.geometry_viewer.model.component import (  # noqa: E402
    ComponentModel,
)
from mcstasscript.geometry_viewer.renderer.pythreejs import (  # noqa: E402
    PyThreejsRenderer,
)
from mcstasscript.geometry_viewer.transform import Transform  # noqa: E402

IDENTITY_M4 = list(np.eye(4, dtype=float).reshape(-1))

# One component per drawcall kind mcdisplay emits.
COMPONENT_JSON = [
    ("a_box", [{"key": "box", "args": [0, 0, 0, 1, 2, 3, 0, 0, 1, 0]}]),
    ("a_cylinder", [{"key": "cylinder", "args": [0, 0, 0, 0.5, 2.0, 0, 0, 1, 0]}]),
    ("a_cone", [{"key": "cone", "args": [0, 0, 0, 0.5, 1.0, 0, 0, 1, 0]}]),
    ("a_circle", [{"key": "circle", "args": ["xy", 0, 0, 0, 0.8]}]),
    ("lines", [{"key": "multiline", "args": [0, 0, 0, 1, 1, 1, 2, 0, 0]}]),
]


def build_viewer():
    backend = PyThreejsRenderer(num_components=len(COMPONENT_JSON))
    visuals = []
    for index, (name, drawcalls) in enumerate(COMPONENT_JSON):
        comp = SimpleNamespace(name=name, component_name=f"{name}_type")
        model = ComponentModel(comp)
        model.load_geometry_from_mcdisplay_dict(
            {"m4": IDENTITY_M4, "drawcalls": drawcalls}, verbose=False
        )
        model.refresh_metadata()
        backend.register_component(model)
        visuals.extend(backend.render_component(model, index))
    renderer = backend.make_scene(children=visuals)
    return backend, visuals, renderer


def test_full_instrument_builds_on_anythreejs():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # no unknown-kwargs fallout anywhere
        backend, visuals, renderer = build_viewer()

    assert isinstance(renderer, p3.Renderer)
    assert len(visuals) == len(COMPONENT_JSON)

    state = renderer.get_state()["_scene_state"]
    objects = state["objects"]
    for visual in visuals:
        assert visual.uuid in objects
    types = {spec["type"] for spec in objects.values()}
    # box, cylinder, cone (cylinder geometry), circle, multiline
    assert {"BoxGeometry", "CylinderGeometry", "CircleGeometry"} <= types
    assert "LineSegments" in types
    for spec in objects.values():
        for key in ("geometry", "material", "map"):
            ref = spec.get(key)
            if isinstance(ref, str):
                assert ref in objects, f"dangling {key} ref in {spec['type']}"
        for child in spec.get("children", []):
            assert child in objects


def test_component_transforms_apply_quaternions(track_ops):
    backend, visuals, renderer = build_viewer()
    sent = track_ops(renderer)

    # 90 degrees about Y — McStasScript orients every component this way.
    quaternion = (0.0, np.sqrt(0.5), 0.0, np.sqrt(0.5))
    backend.apply_transform(
        visuals[0],
        Transform(position=np.array([1.0, 2.0, 3.0]), quaternion=quaternion),
    )

    assert visuals[0].position == (1.0, 2.0, 3.0)
    assert visuals[0].quaternion == pytest.approx(quaternion)

    ops = [op for message in sent for op in message["content"]["ops"]]
    quaternion_ops = [op for op in ops if "quaternion" in op.get("props", {})]
    assert quaternion_ops, "quaternion must flow as a delta op"
    assert quaternion_ops[0]["props"]["quaternion"] == pytest.approx(quaternion)

    spec = renderer.get_state()["_scene_state"]["objects"][visuals[0].uuid]
    assert spec["quaternion"] == pytest.approx(quaternion)


def test_component_picker_details_flow(track_ops):
    """The click-a-component flow: Group-scoped picker with raycast
    tolerances added through the controls setter AFTER display, and the
    object observer resolving the picked mesh back by Python identity."""
    pytest.importorskip("ipywidgets")
    backend, visuals, renderer = build_viewer()
    sent = track_ops(renderer)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # lineThreshold etc. must be accepted
        details = backend.create_component_details(renderer)

    picker = next(c for c in renderer.controls if c._type == "Picker")
    assert picker.lineThreshold is not None
    assert picker.pointThreshold is not None
    spec = picker.to_dict(flat=True)
    assert spec["lineThreshold"] == picker.lineThreshold
    assert spec["controlling"] == backend._component_group.uuid

    # Appending the picker used the incremental set_controls path.
    kinds = [op["op"] for message in sent for op in message["content"]["ops"]]
    assert "set_controls" in kinds

    # A click lands: picker.object resolves to the very object McStasScript
    # created (their component lookup maps by id()), and their observer
    # chain runs — resolving the mesh to its component details.
    renderer._picker_event = {
        "picker_uuid": picker.uuid,
        "point": [0.0, 0.0, 0.0],
        "object_uuid": visuals[0].uuid,
    }
    assert picker.object is visuals[0]
    assert "a_box" in details.value  # component text shown


def test_camera_navigator_flow(track_ops):
    """The component-navigator dropdown repositions camera and target."""
    backend, visuals, renderer = build_viewer()
    camera = renderer.camera
    controls = renderer.controls[0]
    sent = track_ops(renderer)

    camera.position = (5.0, 4.0, 3.0)
    camera.lookAt((1.0, 0.0, 0.0))
    controls.target = (1.0, 0.0, 0.0)

    assert len(sent) == 3
    assert renderer._camera_epoch == renderer._epoch
