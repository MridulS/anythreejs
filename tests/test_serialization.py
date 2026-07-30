"""Snapshot (normalized) and legacy (nested) serialization."""

import numpy as np
import pytest

import anythreejs as p3


def test_snapshot_is_normalized():
    geometry = p3.BoxGeometry(1, 2, 3)
    material = p3.MeshStandardMaterial(color="#ff0000")
    mesh = p3.Mesh(geometry=geometry, material=material)
    light = p3.AmbientLight(intensity=0.4)
    scene = p3.Scene(children=[mesh, light], background="#101010")
    camera = p3.PerspectiveCamera(position=[3, 3, 3])
    controls = p3.OrbitControls(controlling=camera)
    renderer = p3.Renderer(scene=scene, camera=camera, controls=[controls])

    state = renderer._scene_state
    objects = state["objects"]
    for obj in (scene, camera, controls, mesh, light, geometry, material):
        assert obj.uuid in objects

    assert state["scene"] == scene.uuid
    assert state["camera"] == camera.uuid
    assert state["controls"] == [controls.uuid]

    mesh_spec = objects[mesh.uuid]
    assert mesh_spec["geometry"] == geometry.uuid
    assert mesh_spec["material"] == material.uuid

    scene_spec = objects[scene.uuid]
    assert scene_spec["children"] == [mesh.uuid, light.uuid]
    assert scene_spec["background"] == "#101010"

    controls_spec = objects[controls.uuid]
    assert controls_spec["controlling"] == camera.uuid


def test_snapshot_buffers_are_binary():
    positions = np.arange(9, dtype="float64").reshape(3, 3)
    geometry = p3.BufferGeometry(
        attributes={"position": p3.BufferAttribute(positions, itemSize=3)}
    )
    points = p3.Points(geometry=geometry, material=p3.PointsMaterial())
    scene = p3.Scene(children=[points])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())

    spec = renderer._scene_state["objects"][geometry.uuid]
    entry = spec["attributes"]["position"]
    assert entry["dtype"] == "float32"
    assert entry["itemSize"] == 3
    assert isinstance(entry["data"], memoryview)
    assert np.frombuffer(entry["data"], dtype="float32").tolist() == list(range(9))


def test_edges_geometry_flat_references_source():
    box = p3.BoxGeometry()
    edges = p3.EdgesGeometry(box)
    lines = p3.LineSegments(geometry=edges, material=p3.LineBasicMaterial())
    scene = p3.Scene(children=[lines])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())

    objects = renderer._scene_state["objects"]
    assert objects[edges.uuid]["geometry"] == box.uuid
    assert box.uuid in objects  # source serialized once, by reference


def test_sprite_material_map_flat_reference():
    texture = p3.TextTexture(string="hi", color="black")
    sprite = p3.Sprite(material=p3.SpriteMaterial(map=texture, transparent=True))
    scene = p3.Scene(children=[sprite])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())

    objects = renderer._scene_state["objects"]
    material_uuid = objects[sprite.uuid]["material"]
    assert objects[material_uuid]["map"] == texture.uuid
    assert objects[texture.uuid]["string"] == "hi"


def test_nested_to_dict_unchanged():
    mesh = p3.Mesh(geometry=p3.BoxGeometry(), material=p3.MeshBasicMaterial())
    scene = p3.Scene(children=[mesh])
    data = scene.to_dict()
    assert data["children"][0]["type"] == "Mesh"
    assert data["children"][0]["geometry"]["type"] == "BoxGeometry"


def test_buffer_attribute_dtype_and_count():
    attr = p3.BufferAttribute(np.zeros((4, 4), dtype="float64"), itemSize=4)
    assert attr.array.dtype == np.dtype("float32")  # float64 narrows
    assert attr.count == 4
    attr.array = np.ones((4, 4), dtype="float64")
    assert attr.array.dtype == np.dtype("float32")


def test_buffer_attribute_dtype_follows_array():
    # pythreejs semantics: an integer index array stays integer.
    index = p3.BufferAttribute(np.array([0, 1, 2], dtype="uint32"))
    assert index.array.dtype == np.dtype("uint32")
    assert index.to_dict(flat=True)["dtype"] == "uint32"

    wide = p3.BufferAttribute(np.array([0, 1], dtype="int64"))
    assert wide.array.dtype == np.dtype("int32")

    explicit = p3.BufferAttribute([0, 1, 2], dtype="uint16")
    assert explicit.array.dtype == np.dtype("uint16")


def test_rotation_four_tuple():
    obj = p3.Object3D(rotation=(0.1, 0.2, 0.3, "ZYX"))
    assert obj.rotation == (0.1, 0.2, 0.3, "ZYX")
    spec = obj.to_dict(flat=True)
    assert spec["rotation"] == [0.1, 0.2, 0.3]
    assert spec["rotationOrder"] == "ZYX"

    with pytest.raises(ValueError):
        p3.Object3D(rotation=(1, 2))


def test_unknown_kwargs_warn():
    with pytest.warns(UserWarning, match="unsupported arguments"):
        p3.BoxGeometry(bogus=1)


def test_negative_sphere_angles_allowed():
    geometry = p3.SphereGeometry(thetaStart=-1.5, phiStart=-0.5)
    assert geometry.thetaStart == -1.5
    assert geometry.phiStart == -0.5


def test_pythreejs_surface_for_plopp_and_matplotgl():
    names = [
        "Group",
        "EdgesGeometry",
        "BufferAttribute",
        "LineSegments",
        "LineBasicMaterial",
        "Sprite",
        "PlaneBufferGeometry",
        "BufferGeometry",
        "TextTexture",
        "SpriteMaterial",
        "Scene",
        "Renderer",
        "PointsMaterial",
        "Points",
        "PerspectiveCamera",
        "OrbitControls",
        "MeshBasicMaterial",
        "Mesh",
        "BoxBufferGeometry",
        "AxesHelper",
        "Picker",
        "Object3D",
        "OrthographicCamera",
        "DataTexture",
        "LineMaterial",
        "LineGeometry",
        "Line2",
        "Line",
        "TorusGeometry",
    ]
    for name in names:
        assert hasattr(p3, name), name
