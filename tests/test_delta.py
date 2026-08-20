"""Delta op emission: updates, batching, creates, GC, buffer ops."""

import numpy as np

import anythreejs as p3


def ops_of(message):
    return message["content"]["ops"]


def test_property_change_emits_single_update_op(track_ops):
    material = p3.MeshStandardMaterial(color="#ffffff")
    mesh = p3.Mesh(geometry=p3.BoxGeometry(), material=material)
    scene = p3.Scene(children=[mesh])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    material.color = "#00ff00"

    assert len(sent) == 1
    assert sent[0]["content"]["kind"] == "ops"
    assert sent[0]["content"]["epoch"] == 1
    assert ops_of(sent[0]) == [
        {"op": "update", "uuid": material.uuid, "props": {"color": "#00ff00"}}
    ]


def test_hold_trait_notifications_batches_ops(track_ops):
    camera = p3.PerspectiveCamera()
    renderer = p3.Renderer(scene=p3.Scene(), camera=camera)
    sent = track_ops(renderer)

    with camera.hold_trait_notifications():
        camera.fov = 60
        camera.near = 0.5
        camera.far = 500

    assert len(sent) == 1
    assert len(ops_of(sent[0])) == 3
    assert {op["uuid"] for op in ops_of(sent[0])} == {camera.uuid}


def test_hold_sync_batches_ops_but_notifies_immediately(track_ops):
    """ipywidgets Widget.hold_sync semantics: one outgoing message, but
    observers fire during the block (unlike hold_trait_notifications).
    McStasScript's camera navigator wraps camera+controls moves in it."""
    camera = p3.PerspectiveCamera()
    controls = p3.OrbitControls(controlling=camera)
    renderer = p3.Renderer(scene=p3.Scene(), camera=camera, controls=[controls])
    sent = track_ops(renderer)

    seen = []
    camera.observe(lambda change: seen.append(change["name"]), names=["position"])

    with camera.hold_sync(), controls.hold_sync():
        camera.position = [5.0, 4.0, 3.0]
        assert seen == ["position"]  # observer fired inside the block
        controls.target = [1.0, 0.0, 0.0]
        assert sent == []  # nothing flushed yet

    assert len(sent) == 1  # one message for both objects' ops
    ops = ops_of(sent[0])
    assert {op["uuid"] for op in ops} == {camera.uuid, controls.uuid}


def test_exec_three_obj_method_emits_invoke_op(track_ops):
    """pythreejs API: exec_three_obj_method invokes a method on the
    JS-side object (McStasScript calls controls.update this way)."""
    camera = p3.PerspectiveCamera()
    controls = p3.OrbitControls(controlling=camera)
    renderer = p3.Renderer(scene=p3.Scene(), camera=camera, controls=[controls])
    sent = track_ops(renderer)

    controls.exec_three_obj_method("update")

    assert ops_of(sent[0]) == [
        {"op": "invoke", "uuid": controls.uuid, "method": "update", "args": []}
    ]
    assert renderer._camera_epoch == renderer._epoch


def test_nested_hold_releases_once(track_ops):
    camera = p3.PerspectiveCamera()
    renderer = p3.Renderer(scene=p3.Scene(), camera=camera)
    sent = track_ops(renderer)

    with camera.hold_trait_notifications():
        camera.fov = 60
        with camera.hold_trait_notifications():
            camera.near = 0.5
        assert sent == []  # inner exit must not flush
        camera.far = 800

    assert len(sent) == 1
    assert len(ops_of(sent[0])) == 3


def test_add_emits_creates_then_child_add(track_ops):
    scene = p3.Scene()
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    geometry = p3.BoxGeometry()
    material = p3.MeshBasicMaterial()
    mesh = p3.Mesh(geometry=geometry, material=material)
    scene.add(mesh)

    assert len(sent) == 1
    ops = ops_of(sent[0])
    assert [op["op"] for op in ops] == ["create", "create", "create", "child_add"]
    created = [op["uuid"] for op in ops[:3]]
    assert set(created) == {geometry.uuid, material.uuid, mesh.uuid}
    assert created.index(mesh.uuid) == 2  # dependencies created first
    assert ops[-1] == {"op": "child_add", "uuid": scene.uuid, "child": mesh.uuid}
    assert mesh.uuid in renderer._known


def test_remove_gc_disposes_unreachable(track_ops):
    geometry = p3.BoxGeometry()
    material = p3.MeshBasicMaterial()
    mesh = p3.Mesh(geometry=geometry, material=material)
    scene = p3.Scene(children=[mesh])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    scene.remove(mesh)

    assert len(sent) == 1
    ops = ops_of(sent[0])
    assert ops[0] == {"op": "child_remove", "uuid": scene.uuid, "child": mesh.uuid}
    removed = {op["uuid"] for op in ops if op["op"] == "remove"}
    assert removed == {mesh.uuid, geometry.uuid, material.uuid}
    assert mesh.uuid not in renderer._known


def test_shared_material_survives_gc(track_ops):
    material = p3.MeshBasicMaterial()
    mesh1 = p3.Mesh(geometry=p3.BoxGeometry(), material=material)
    mesh2 = p3.Mesh(geometry=p3.BoxGeometry(), material=material)
    scene = p3.Scene(children=[mesh1, mesh2])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    scene.remove(mesh1)

    removed = {op["uuid"] for op in ops_of(sent[0]) if op["op"] == "remove"}
    assert mesh1.uuid in removed
    assert material.uuid not in removed  # still used by mesh2


def test_attribute_array_update_emits_buffer_op(track_ops):
    attr = p3.BufferAttribute(np.zeros((4, 4), dtype="float32"), itemSize=4)
    geometry = p3.BufferGeometry(attributes={"color": attr})
    points = p3.Points(geometry=geometry, material=p3.PointsMaterial())
    scene = p3.Scene(children=[points])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    attr.array = np.ones((4, 4))

    assert len(sent) == 1
    message = sent[0]
    ops = ops_of(message)
    assert len(ops) == 1
    op = ops[0]
    assert op["op"] == "buffer"
    assert op["uuid"] == geometry.uuid
    assert op["attribute"] == "color"
    assert op["value"]["dtype"] == "float32"
    assert op["value"]["data"] == {"__buffer__": 0}
    assert message["buffers"] is not None and len(message["buffers"]) == 1
    assert np.frombuffer(message["buffers"][0], dtype="float32").tolist() == [1.0] * 16


def test_shared_attribute_notifies_all_geometries(track_ops):
    attr = p3.BufferAttribute(np.zeros(6, dtype="float32"), itemSize=3)
    g1 = p3.BufferGeometry(attributes={"position": attr})
    g2 = p3.BufferGeometry(attributes={"position": attr})
    scene = p3.Scene(
        children=[
            p3.Points(geometry=g1, material=p3.PointsMaterial()),
            p3.Points(geometry=g2, material=p3.PointsMaterial()),
        ]
    )
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    attr.array = np.ones(6)

    assert len(sent) == 2  # one buffer op per geometry sharing the attribute
    assert {ops_of(m)[0]["uuid"] for m in sent} == {g1.uuid, g2.uuid}


def test_reference_assignment_creates_and_collects(track_ops):
    old_geometry = p3.BoxGeometry()
    mesh = p3.Mesh(geometry=old_geometry, material=p3.MeshBasicMaterial())
    scene = p3.Scene(children=[mesh])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    new_geometry = p3.SphereGeometry()
    mesh.geometry = new_geometry

    assert len(sent) == 1
    ops = ops_of(sent[0])
    assert [op["op"] for op in ops] == ["create", "update", "remove"]
    assert ops[0]["uuid"] == new_geometry.uuid
    assert ops[1] == {
        "op": "update",
        "uuid": mesh.uuid,
        "props": {"geometry": new_geometry.uuid},
    }
    assert ops[2]["uuid"] == old_geometry.uuid


def test_line_geometry_positions_update(track_ops):
    line_geometry = p3.LineGeometry(positions=np.zeros((3, 3)))
    line = p3.Line2(geometry=line_geometry, material=p3.LineMaterial())
    scene = p3.Scene(children=[line])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    line_geometry.positions = np.ones((3, 3))

    assert len(sent) == 1
    op = ops_of(sent[0])[0]
    assert op["op"] == "update"
    assert op["uuid"] == line_geometry.uuid
    assert op["props"]["positions"]["dtype"] == "float32"
    assert op["props"]["positions"]["data"] == {"__buffer__": 0}


def test_get_state_folds_delta_ops_into_snapshot(track_ops):
    """Objects added after construction travel as ops; kernel-side state
    export must still see them, without re-syncing the live JS world."""
    scene = p3.Scene()
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    mesh = p3.Mesh(geometry=p3.BoxGeometry(), material=p3.MeshBasicMaterial())
    scene.add(mesh)
    assert mesh.uuid not in renderer._scene_state["objects"]  # trait is stale

    state = renderer.get_state()["_scene_state"]
    assert mesh.uuid in state["objects"]
    assert len(sent) == 1  # the lazy refresh emitted nothing new


def test_clearing_geometry_collects_old_resource(track_ops):
    """Regression: mesh.geometry = None once skipped GC — the orphaned
    geometry stayed in _known and kept emitting, while JS silently ignored
    the null and kept rendering it."""
    geometry = p3.BoxGeometry()
    mesh = p3.Mesh(geometry=geometry, material=p3.MeshBasicMaterial())
    scene = p3.Scene(children=[mesh])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    mesh.geometry = None

    ops = ops_of(sent[0])
    assert {"op": "update", "uuid": mesh.uuid, "props": {"geometry": None}} in ops
    assert {"op": "remove", "uuid": geometry.uuid} in ops
    assert geometry.uuid not in renderer._known
    assert renderer not in geometry._renderers


def test_render_after_get_state_still_syncs(track_ops):
    """Regression: get_state()'s quiet snapshot injection once made a
    later render() compare equal and emit no trait change — the one
    public recovery tool silently failed after any autosave."""
    renderer = p3.Renderer(scene=p3.Scene(), camera=p3.PerspectiveCamera())
    track_ops(renderer)

    changes = []
    renderer.observe(lambda change: changes.append(change), names=["_scene_state"])

    renderer.scene.background = "#123456"  # delta op: snapshot now stale
    renderer.get_state()  # the autosave / new-client path injects quietly
    renderer.render()

    assert changes, "render() must emit a real _scene_state change"


def test_data_texture_update_preserves_dtype(track_ops):
    """Regression: _json_safe once forced every ndarray to float32, turning
    uint8 image updates into blown-out float textures on the JS side."""
    image = np.zeros((4, 4, 4), dtype="uint8")
    texture = p3.DataTexture(data=image)
    mesh = p3.Mesh(
        geometry=p3.PlaneGeometry(), material=p3.MeshBasicMaterial(map=texture)
    )
    renderer = p3.Renderer(
        scene=p3.Scene(children=[mesh]), camera=p3.PerspectiveCamera()
    )
    sent = track_ops(renderer)

    texture.data = np.full((4, 4, 4), 255, dtype="uint8")

    op = ops_of(sent[0])[0]
    assert op["props"]["data"]["dtype"] == "uint8"
    # 64-bit floats still narrow to what WebGL can hold.
    texture.data = np.zeros((4, 4, 4), dtype="float64")
    assert ops_of(sent[1])[0]["props"]["data"]["dtype"] == "float32"


def test_closed_renderer_detaches_and_stops_emitting(track_ops):
    """Regression: attached objects kept dead renderers alive and kept
    emitting ops through their closed comms."""
    material = p3.MeshBasicMaterial()
    scene = p3.Scene(children=[p3.Mesh(p3.BoxGeometry(), material)])
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)

    renderer.close()

    assert material._renderers == set()
    material.color = "#123456"
    assert sent == []


def test_scene_replacement_refreshes_snapshot(track_ops):
    renderer = p3.Renderer(scene=p3.Scene(), camera=p3.PerspectiveCamera())
    track_ops(renderer)

    light = p3.AmbientLight()
    new_scene = p3.Scene(children=[light])
    renderer.scene = new_scene

    state = renderer._scene_state
    assert state["scene"] == new_scene.uuid
    assert light.uuid in state["objects"]
