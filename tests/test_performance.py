"""Performance contracts for the delta protocol.

Most assertions here are *deterministic* (bytes on the wire, what gets
re-serialized) so they can't flake; the few wall-clock bounds are set 10-50x
above expected so they only trip on algorithmic regressions (O(1) -> O(N)).

Run with `-s` to see the measured numbers:

    uv run pytest tests/test_performance.py -s
"""

import json
import time

import numpy as np

import anythreejs as p3

N_LARGE = 1_000_000
N_MEDIUM = 100_000


def report(name, **values):
    parts = ", ".join(f"{key}={value}" for key, value in values.items())
    print(f"\n[perf] {name}: {parts}")


def message_cost(message):
    """(JSON bytes, binary buffer bytes) of one delta message."""
    content = len(json.dumps(message["content"]).encode())
    buffers = sum(b.nbytes for b in (message["buffers"] or []))
    return content, buffers


def make_cloud(n):
    rng = np.random.default_rng(1)
    geometry = p3.BufferGeometry(
        attributes={
            "position": p3.BufferAttribute(
                rng.random((n, 3), dtype="float32"), itemSize=3
            ),
            "color": p3.BufferAttribute(np.ones((n, 4), dtype="float32"), itemSize=4),
        }
    )
    material = p3.PointsMaterial(size=2, vertexColors=True)
    points = p3.Points(geometry=geometry, material=material)
    scene = p3.Scene(children=[points, p3.AmbientLight()])
    camera = p3.PerspectiveCamera(position=[3, 3, 3])
    renderer = p3.Renderer(
        scene=scene, camera=camera, controls=[p3.OrbitControls(controlling=camera)]
    )
    return renderer, geometry, material


def test_scalar_update_wire_cost_is_constant(track_ops):
    """A one-float change on a million-point scene must cost ~100 bytes."""
    renderer, geometry, material = make_cloud(N_LARGE)
    sent = track_ops(renderer)

    material.size = 3

    assert len(sent) == 1
    content_bytes, buffer_bytes = message_cost(sent[0])
    report(
        "scalar update on 1M-point scene",
        json_bytes=content_bytes,
        buffer_bytes=buffer_bytes,
    )
    assert buffer_bytes == 0
    assert content_bytes < 1000


def test_delta_vs_full_snapshot_ratio(track_ops):
    """The delta must be orders of magnitude smaller than what the old
    protocol re-sent on every change (the full nested-JSON scene)."""
    renderer, geometry, material = make_cloud(N_MEDIUM)
    sent = track_ops(renderer)

    old_protocol_bytes = len(json.dumps(renderer.scene.to_dict()).encode())

    material.opacity = 0.7
    delta_bytes, _ = message_cost(sent[0])

    report(
        "delta vs old full-snapshot cost (100k points)",
        old_bytes=old_protocol_bytes,
        delta_bytes=delta_bytes,
        ratio=f"{old_protocol_bytes / delta_bytes:,.0f}x",
    )
    assert delta_bytes * 10_000 < old_protocol_bytes


def test_unrelated_change_does_not_reserialize_geometry(track_ops):
    """O(1) proof without timing: a material change must never call the big
    geometry's serializer."""
    renderer, geometry, material = make_cloud(N_MEDIUM)
    sent = track_ops(renderer)

    calls = {"n": 0}
    original = geometry.to_dict

    def counting_to_dict(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    geometry.to_dict = counting_to_dict

    material.color = "#123456"
    material.opacity = 0.4
    renderer.camera.position = [1, 2, 3]

    assert calls["n"] == 0
    assert len(sent) == 3


def test_color_update_sends_exactly_one_buffer(track_ops):
    """Updating the color attribute re-sends colors — and only colors."""
    renderer, geometry, material = make_cloud(N_LARGE)
    sent = track_ops(renderer)

    start = time.perf_counter()
    geometry.attributes["color"].array = np.zeros((N_LARGE, 4), dtype="float32")
    elapsed = time.perf_counter() - start

    assert len(sent) == 1
    content_bytes, buffer_bytes = message_cost(sent[0])
    expected = N_LARGE * 4 * 4  # n * rgba * float32
    report(
        "color buffer update (1M points)",
        buffer_mb=f"{buffer_bytes / 1e6:.1f}",
        json_bytes=content_bytes,
        seconds=f"{elapsed:.3f}",
        throughput_mb_s=f"{buffer_bytes / 1e6 / max(elapsed, 1e-9):,.0f}",
    )
    assert buffer_bytes == expected  # positions NOT re-sent
    assert content_bytes < 1000
    assert elapsed < 1.0  # generous; expected ~ms (one contiguous copy)


def test_picker_events_are_free_on_huge_scenes(track_ops):
    """The old protocol re-serialized the whole scene per picker event; now
    100 mousemove picker events must emit nothing and take ~no time."""
    renderer, geometry, material = make_cloud(N_LARGE)
    picker = p3.Picker(controlling=None, event="mousemove")
    renderer.controls = renderer.controls + [picker]
    sent = track_ops(renderer)

    start = time.perf_counter()
    for i in range(100):
        renderer._picker_event = {
            "picker_uuid": picker.uuid,
            "point": [float(i), 0.0, 0.0],
            "distance": float(i),
            "modifiers": [],
        }
    elapsed = time.perf_counter() - start

    report(
        "100 picker events on 1M-point scene",
        seconds=f"{elapsed:.4f}",
        per_event_us=f"{elapsed / 100 * 1e6:.0f}",
    )
    assert sent == []
    assert elapsed < 1.0


def test_camera_sync_back_is_free(track_ops):
    """Interactive orbiting streams camera state; applying it must not
    serialize anything."""
    renderer, geometry, material = make_cloud(N_LARGE)
    sent = track_ops(renderer)

    start = time.perf_counter()
    for i in range(100):
        renderer._camera_state = {
            "position": [float(i), 3.0, 3.0],
            "rotation": [0.0, 0.0, 0.0],
            "zoom": 1.0,
            "target": [0.0, 0.0, 0.0],
            "epoch": 0,
        }
    elapsed = time.perf_counter() - start

    report(
        "100 camera sync-backs on 1M-point scene",
        seconds=f"{elapsed:.4f}",
        per_event_us=f"{elapsed / 100 * 1e6:.0f}",
    )
    assert sent == []
    assert elapsed < 1.0


def test_scalar_update_latency(track_ops):
    """Median emission latency of a scalar op on a big scene."""
    renderer, geometry, material = make_cloud(N_LARGE)
    track_ops(renderer)

    samples = []
    for i in range(200):
        start = time.perf_counter()
        material.size = 2 + (i % 2)
        samples.append(time.perf_counter() - start)
    median = sorted(samples)[len(samples) // 2]

    report("scalar op emission latency", median_us=f"{median * 1e6:.0f}")
    assert median < 0.005  # 5ms bound; expected tens of microseconds


def test_controls_swap_is_incremental(track_wire):
    """Regression (critical review finding): assigning renderer.controls
    once triggered a full snapshot resync, re-shipping every scene buffer
    (28MB at 1M points) — matplotgl does this on every zoom-toolbar
    toggle. It must now cost a few hundred bytes of ops."""
    renderer, geometry, material = make_cloud(N_LARGE)
    track_wire.clear()  # construction traffic is not under test

    renderer.controls = renderer.controls + [p3.Picker(event="click")]

    json_bytes = sum(r["json"] for r in track_wire)
    buffer_bytes = sum(r["buffers"] for r in track_wire)
    report(
        "controls swap on 1M-point scene",
        json_bytes=json_bytes,
        buffer_bytes=buffer_bytes,
    )
    assert buffer_bytes == 0  # scene buffers must NOT be re-shipped
    assert json_bytes < 20_000


def test_camera_swap_is_incremental(track_wire):
    """Same contract for camera replacement."""
    renderer, geometry, material = make_cloud(N_LARGE)
    track_wire.clear()

    renderer.camera = p3.PerspectiveCamera(position=[9, 9, 9])

    buffer_bytes = sum(r["buffers"] for r in track_wire)
    json_bytes = sum(r["json"] for r in track_wire)
    report(
        "camera swap on 1M-point scene",
        json_bytes=json_bytes,
        buffer_bytes=buffer_bytes,
    )
    assert buffer_bytes == 0
    assert json_bytes < 20_000


def test_artist_removal_is_not_quadratic(track_ops):
    """Regression: per-removal full-graph GC made clearing K artists
    O(K*N) — 326ms for 800 locally, >1s on CI. Refcounted release is
    O(removed subtree) per artist."""
    scene = p3.Scene()
    artists = []
    for _ in range(800):
        artist = p3.Points(
            geometry=p3.BufferGeometry(
                attributes={
                    "position": p3.BufferAttribute(np.zeros((3, 3), dtype="float32"))
                }
            ),
            material=p3.PointsMaterial(),
        )
        scene.add(artist)
        artists.append(artist)
    camera = p3.PerspectiveCamera()
    renderer = p3.Renderer(scene=scene, camera=camera)
    track_ops(renderer)

    start = time.perf_counter()
    for artist in artists:
        scene.remove(artist)
    elapsed = time.perf_counter() - start

    report(
        "remove 800 artists one-by-one",
        seconds=f"{elapsed:.3f}",
        per_remove_us=f"{elapsed / 800 * 1e6:.0f}",
    )
    assert elapsed < 0.25  # the quadratic path cannot fit under this
    assert renderer._known == {scene.uuid, camera.uuid}  # fully collected


def test_reference_swap_does_not_walk_scene(track_ops):
    """Swapping one mesh's geometry must not scale with scene size (the
    old GC walked every live object per swap)."""
    scene = p3.Scene()
    for _ in range(400):
        scene.add(
            p3.Points(
                geometry=p3.BufferGeometry(
                    attributes={
                        "position": p3.BufferAttribute(
                            np.zeros((3, 3), dtype="float32")
                        )
                    }
                ),
                material=p3.PointsMaterial(),
            )
        )
    mesh = p3.Mesh(geometry=p3.BoxGeometry(), material=p3.MeshBasicMaterial())
    scene.add(mesh)
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    track_ops(renderer)

    start = time.perf_counter()
    for _ in range(100):
        mesh.geometry = p3.BoxGeometry()
    elapsed = time.perf_counter() - start

    report(
        "100 geometry swaps on 1200-object scene",
        seconds=f"{elapsed:.3f}",
        per_swap_us=f"{elapsed / 100 * 1e6:.0f}",
    )
    assert elapsed < 0.03  # full-walk GC costs ~3x this even locally


def test_redundant_assignment_is_silent(track_ops):
    """traitlets semantics: assigning an unchanged value must emit
    nothing (each redundant set used to cost a comm message)."""
    renderer, geometry, material = make_cloud(N_MEDIUM)
    sent = track_ops(renderer)

    material.size = 2  # constructed with size=2
    renderer.camera.position = [3, 3, 3]  # constructed at [3, 3, 3]
    material.color = material.color

    assert sent == []


def test_full_resync_wall_time_at_scale(track_ops):
    """render() serializes per-object with zero-copy buffer wrappers, and
    the traitlets equality check must short-circuit on the resync counter
    BEFORE deep-comparing megabytes of memoryview content. The snapshot
    dict's key order is load-bearing for that short-circuit — this pins
    it."""
    renderer, geometry, material = make_cloud(N_LARGE)
    track_ops(renderer)

    start = time.perf_counter()
    renderer.render()
    renderer.render()
    elapsed = time.perf_counter() - start

    report("2x render() at 1M points", seconds=f"{elapsed:.4f}")
    assert elapsed < 0.1  # deep-comparing the buffers costs far more


def test_initial_snapshot_build_time():
    """Full snapshot serialization of a 1M-point scene stays cheap because
    array data is wrapped as memoryviews, not JSON."""
    start = time.perf_counter()
    renderer, geometry, material = make_cloud(N_LARGE)
    elapsed = time.perf_counter() - start

    report("renderer construction, 1M points", seconds=f"{elapsed:.3f}")
    assert elapsed < 5.0  # generous; expected well under a second
