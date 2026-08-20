"""End-to-end pipeline benchmarks: Python change -> wire -> JS apply ->
rendered frame, measured in the real browser.

Two caveats make these numbers conservative floors, not GPU benchmarks:
the harness moves payloads as base64 JSON through page.evaluate (production
uses zero-copy binary buffers over the comm), and rendering runs on
software WebGL (SwiftShader). Treat the reported values as regression
signals; the hard bounds are set generously so only algorithmic
regressions trip them.

Run with `-s` to see the measured numbers.
"""

import time

import numpy as np
import pytest

pytest.importorskip("pytest_playwright")

import anythreejs as p3  # noqa: E402

N_SMALL = 10_000
N_MEDIUM = 100_000
N_LARGE = 1_000_000


def report(name, **values):
    parts = ", ".join(f"{key}={value}" for key, value in values.items())
    print(f"\n[e2e] {name}: {parts}")


def cloud_renderer(n):
    rng = np.random.default_rng(7)
    geometry = p3.BufferGeometry(
        attributes={
            "position": p3.BufferAttribute(
                (rng.random((n, 3), dtype="float32") - 0.5) * 4, itemSize=3
            ),
            "color": p3.BufferAttribute(
                rng.random((n, 4), dtype="float32"), itemSize=4
            ),
        }
    )
    points = p3.Points(
        geometry=geometry,
        material=p3.PointsMaterial(size=2, vertexColors=True),
    )
    scene = p3.Scene(children=[points], background="#101020")
    camera = p3.PerspectiveCamera(position=[0, 0, 5], aspect=200 / 150)
    renderer = p3.Renderer(
        scene=scene, camera=camera, controls=[p3.OrbitControls(controlling=camera)]
    )
    return renderer, geometry


def test_boot_to_first_pixel(harness):
    """Snapshot -> built world -> first rendered frame."""
    for n in (N_MEDIUM, N_LARGE):
        renderer, _ = cloud_renderer(n)
        start = time.perf_counter()
        summary = harness.boot(renderer)
        wall = time.perf_counter() - start
        report(
            f"boot {n:,} points",
            total_s=f"{wall:.2f}",
            js_first_render_ms=f"{summary['firstRenderMs']:.0f}",
        )
        assert summary["byType"]["Points"] == 1
    harness.assert_clean()


def test_update_to_frame_latency(harness, track_ops):
    """One color-buffer update, applied and rendered."""
    renderer, geometry = cloud_renderer(N_MEDIUM)
    sent = track_ops(renderer)
    harness.boot(renderer)

    start = time.perf_counter()
    geometry.attributes["color"].array = np.zeros((N_MEDIUM, 4), dtype="float32")
    timings = harness.apply_timed(sent)
    wall = time.perf_counter() - start

    report(
        f"color update {N_MEDIUM:,} points",
        total_s=f"{wall:.3f}",
        js_apply_ms=f"{timings['applyMs']:.1f}",
        js_render_ms=f"{timings['renderMs']:.1f}",
    )
    # applyMs now excludes harness base64 decode, so this measures real
    # widget work (~0.3ms at 100k locally) — bound is CI headroom only.
    assert timings["applyMs"] < 50
    assert timings["renderMs"] < 500
    harness.assert_clean()


def test_fat_line_update_tick(harness, track_ops):
    """matplotgl pan tick: update every fat line's positions. The in-place
    instanced-buffer path keeps this linear in line count — the rebuild
    path (fresh LineGeometry + full-registry swap scan per line) made it
    O(lines^2), ~24ms at this scale and growing quadratically."""
    rng = np.random.default_rng(5)
    scene = p3.Scene(background="#000000")
    line_geometries = []
    for _ in range(100):
        geometry = p3.LineGeometry(positions=rng.random((100, 3)).astype("float32"))
        line_geometries.append(geometry)
        scene.add(p3.Line2(geometry=geometry, material=p3.LineMaterial(linewidth=2)))
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)
    harness.boot(renderer)

    probe = line_geometries[0]
    before = harness.object(probe.uuid)["attributes"]["instanceStart"]["first"]

    for geometry in line_geometries:
        geometry.positions = rng.random((100, 3)).astype("float32")
    timings = harness.apply_timed(sent)

    after = harness.object(probe.uuid)["attributes"]["instanceStart"]["first"]
    assert after != before  # the in-place write really landed

    report(
        "pan tick: 100 fat lines x 100 pts",
        js_apply_ms=f"{timings['applyMs']:.1f}",
    )
    assert timings["applyMs"] < 30  # rebuild path costs ~3x this on CI
    harness.assert_clean()


def test_edge_rebuilds_coalesce_per_message(harness, track_ops):
    """Multiple position ops on one source geometry within a message must
    trigger ONE derived-edges re-extraction, not one per op."""
    positions = p3.BufferAttribute(
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype="float32")
    )
    geometry = p3.BufferGeometry(
        attributes={"position": positions},
        index=p3.BufferAttribute(np.array([0, 1, 2], dtype="uint32"), itemSize=1),
    )
    scene = p3.Scene(
        children=[
            p3.Mesh(geometry=geometry, material=p3.MeshBasicMaterial()),
            p3.LineSegments(
                geometry=p3.EdgesGeometry(geometry),
                material=p3.LineBasicMaterial(),
            ),
        ]
    )
    renderer = p3.Renderer(scene=scene, camera=p3.PerspectiveCamera())
    sent = track_ops(renderer)
    harness.boot(renderer)

    rebuilds_before = harness.page.evaluate("window.harness.world.edgeRebuilds")
    with geometry.hold_trait_notifications():
        positions.array = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0]], dtype="float32")
        positions.array = np.array([[0, 0, 0], [3, 0, 0], [0, 3, 0]], dtype="float32")
    assert len(sent) == 1  # both ops in one message
    harness.apply(sent)
    rebuilds_after = harness.page.evaluate("window.harness.world.edgeRebuilds")

    assert rebuilds_after - rebuilds_before == 1
    harness.assert_clean()


def test_sustained_update_rate(harness, track_ops):
    """Colormap-slider style: repeated color updates through the whole
    pipeline (encode + transport + apply + render per iteration)."""
    renderer, geometry = cloud_renderer(N_SMALL)
    sent = track_ops(renderer)
    harness.boot(renderer)

    rounds = 30
    rng = np.random.default_rng(11)
    start = time.perf_counter()
    for _ in range(rounds):
        geometry.attributes["color"].array = rng.random((N_SMALL, 4)).astype("float32")
        harness.apply_timed(sent)
    elapsed = time.perf_counter() - start
    rate = rounds / elapsed

    report(
        f"sustained updates, {N_SMALL:,} points",
        rounds=rounds,
        seconds=f"{elapsed:.2f}",
        updates_per_s=f"{rate:.1f}",
    )
    assert rate > 2  # generous floor even for slow CI + b64 transport
    harness.assert_clean()


def test_orbit_fps(harness):
    """Effective frame rate while the camera auto-orbits a point cloud.

    10k points, not 100k: GitHub's 2-vCPU SwiftShader runners measured
    1.6fps at 100k — below any bound that could also catch regressions.
    At 10k the floor still trips on catastrophic per-frame regressions."""
    renderer, _ = cloud_renderer(N_SMALL)
    harness.boot(renderer)
    harness.set_auto_rotate(True)
    result = harness.measure_fps(1000)
    harness.set_auto_rotate(False)

    report(
        f"orbit fps, {N_SMALL:,} points (software WebGL)",
        fps=f"{result['fps']:.0f}",
        frames=result["frames"],
    )
    assert result["fps"] >= 2
    harness.assert_clean()
