"""Validate the snapshot and delta payloads against the real widget wire
machinery: ipywidgets must extract our memoryviews into binary buffers and
the remaining payload must be strictly JSON-serializable."""

import json

import numpy as np
from ipywidgets.widgets.widget import _remove_buffers

import anythreejs as p3


def build_renderer():
    positions = np.random.default_rng(0).random((100, 3))
    geometry = p3.BufferGeometry(
        attributes={
            "position": p3.BufferAttribute(positions, itemSize=3),
            "color": p3.BufferAttribute(np.ones((100, 4)), itemSize=4),
        }
    )
    points = p3.Points(geometry=geometry, material=p3.PointsMaterial(size=2))
    texture = p3.DataTexture(
        data=np.zeros((8, 8, 4), dtype="uint8"), format="RGBAFormat"
    )
    imshow = p3.Mesh(
        geometry=p3.PlaneGeometry(2, 2),
        material=p3.MeshBasicMaterial(map=texture),
    )
    scene = p3.Scene(children=[points, imshow, p3.AmbientLight()])
    camera = p3.PerspectiveCamera(position=[3, 3, 3])
    controls = p3.OrbitControls(controlling=camera)
    return p3.Renderer(scene=scene, camera=camera, controls=[controls]), geometry


def test_snapshot_buffers_extracted_and_state_json_clean():
    renderer, geometry = build_renderer()

    state = renderer.get_state()
    cleaned, buffer_paths, buffers = _remove_buffers(state)

    # The position, color, and texture arrays must travel as binary buffers.
    assert len(buffers) >= 3
    scene_state_paths = [p for p in buffer_paths if p[0] == "_scene_state"]
    assert any(geometry.uuid in path for path in scene_state_paths)

    # What remains must be plain JSON.
    json.dumps(cleaned)


def test_delta_message_json_clean(track_ops):
    renderer, geometry = build_renderer()
    sent = track_ops(renderer)

    geometry.attributes["color"].array = np.zeros((100, 4))

    assert len(sent) == 1
    message = sent[0]
    json.dumps(message["content"])  # placeholders only, no raw binary
    assert all(isinstance(b, memoryview) for b in message["buffers"])
