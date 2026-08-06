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
    # Generous bounds: JS-side work must stay well under a second.
    assert timings["applyMs"] < 1000
    assert timings["renderMs"] < 2000
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
    """Effective frame rate while the camera auto-orbits a point cloud."""
    renderer, _ = cloud_renderer(N_MEDIUM)
    harness.boot(renderer)
    harness.set_auto_rotate(True)
    result = harness.measure_fps(1000)
    harness.set_auto_rotate(False)

    report(
        f"orbit fps, {N_MEDIUM:,} points (software WebGL)",
        fps=f"{result['fps']:.0f}",
        frames=result["frames"],
    )
    # Floor set for 2-vCPU CI runners on SwiftShader; real GPUs are far
    # higher. This only catches catastrophic regressions by design.
    assert result["fps"] >= 2
    harness.assert_clean()
