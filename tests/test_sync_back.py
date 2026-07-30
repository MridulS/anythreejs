"""JS -> Python state: camera pose sync-back and picker events must apply
to the Python objects (firing observers) WITHOUT echoing ops back to JS."""

import anythreejs as p3


def test_camera_state_applies_without_echo(track_ops):
    camera = p3.PerspectiveCamera(position=[0, 0, 5])
    controls = p3.OrbitControls(controlling=camera)
    renderer = p3.Renderer(scene=p3.Scene(), camera=camera, controls=[controls])
    sent = track_ops(renderer)

    seen = []
    camera.observe(lambda change: seen.append(change["new"]), names=["position"])

    renderer._camera_state = {
        "position": [1.0, 2.0, 3.0],
        "rotation": [0.0, 0.5, 0.0],
        "zoom": 1.0,
        "target": [4.0, 5.0, 6.0],
        "epoch": 0,
    }

    assert camera.position == (1.0, 2.0, 3.0)
    assert camera.rotation == (0.0, 0.5, 0.0)
    assert controls.target == (4.0, 5.0, 6.0)
    assert seen == [[1.0, 2.0, 3.0]]  # observer fired exactly once
    assert sent == []  # and nothing echoed back to JS


def test_stale_camera_state_dropped(track_ops):
    camera = p3.PerspectiveCamera(position=[0, 0, 5])
    renderer = p3.Renderer(scene=p3.Scene(), camera=camera)
    sent = track_ops(renderer)

    camera.position = [9, 9, 9]  # Python-originated: bumps the camera epoch
    assert len(sent) == 1
    assert renderer._camera_epoch == 1

    renderer._camera_state = {"position": [1, 1, 1], "epoch": 0}
    assert camera.position == (9, 9, 9)  # stale update was dropped


def test_python_camera_update_bumps_camera_epoch(track_ops):
    camera = p3.PerspectiveCamera()
    material = p3.MeshBasicMaterial()
    scene = p3.Scene(children=[p3.Mesh(p3.BoxGeometry(), material)])
    renderer = p3.Renderer(scene=scene, camera=camera)
    track_ops(renderer)

    material.color = "#123456"  # non-camera op: epoch moves, camera epoch not
    assert renderer._epoch == 1
    assert renderer._camera_epoch == 0

    camera.position = [1, 2, 3]
    assert renderer._epoch == 2
    assert renderer._camera_epoch == 2


def test_controls_target_update_counts_as_camera_op(track_ops):
    camera = p3.PerspectiveCamera()
    controls = p3.OrbitControls(controlling=camera)
    renderer = p3.Renderer(scene=p3.Scene(), camera=camera, controls=[controls])
    sent = track_ops(renderer)

    controls.target = [1.0, 2.0, 3.0]

    assert len(sent) == 1
    op = sent[0]["content"]["ops"][0]
    assert op["op"] == "update"
    assert op["uuid"] == controls.uuid
    assert op["props"] == {"target": [1.0, 2.0, 3.0]}
    assert renderer._camera_epoch == renderer._epoch


def test_picker_event_updates_picker_without_ops(track_ops):
    mesh = p3.Mesh(geometry=p3.BoxGeometry(), material=p3.MeshBasicMaterial())
    scene = p3.Scene(children=[mesh])
    picker = p3.Picker(controlling=mesh, event="mousemove")
    renderer = p3.Renderer(
        scene=scene, camera=p3.PerspectiveCamera(), controls=[picker]
    )
    sent = track_ops(renderer)

    seen = []
    picker.observe(lambda change: seen.append(change["new"]), names=["point"])

    renderer._picker_event = {
        "picker_uuid": picker.uuid,
        "point": [1.0, 2.0, 3.0],
        "distance": 2.5,
        "faceIndex": 7,
        "modifiers": ["shift"],
        "object_uuid": mesh.uuid,
    }

    assert picker.point == (1.0, 2.0, 3.0)
    assert picker.distance == 2.5
    assert picker.faceIndex == 7
    assert picker.modifiers == ["shift"]
    assert picker.object is mesh
    assert seen == [(1.0, 2.0, 3.0)]
    assert sent == []  # picker events must not trigger any resync
