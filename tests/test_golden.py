"""Golden-image regression tests: reference scenes rendered in the browser
harness are compared full-frame against committed PNG baselines.

These catch *our* rendering regressions (protocol, builders, three.js
upgrades). Baselines are per-platform (`<scene>.<platform>.png`): software
WebGL output and — for the text scene — font rasterization differ between
macOS and Linux, so each platform compares only against its own baselines.
A missing baseline is written on first run and the test skips; commit the
PNGs it creates (CI uploads freshly written Linux baselines as an
artifact for promotion). To regenerate after an intentional rendering
change:  GOLDEN_UPDATE=1 uv run pytest tests/test_golden.py
"""

import base64
import os
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pytest_playwright")
Image = pytest.importorskip("PIL.Image")

import anythreejs as p3  # noqa: E402

GOLDEN_DIR = Path(__file__).parent / "golden"
PLATFORM = {"darwin": "darwin", "win32": "windows"}.get(sys.platform, "linux")

MEAN_DIFF_LIMIT = 8.0  # mean absolute channel difference (0-255)
HOT_PIXEL_LIMIT = 0.02  # fraction of pixels allowed to differ by > 30


def scene_box():
    mesh = p3.Mesh(
        geometry=p3.BoxGeometry(1, 1, 1),
        material=p3.MeshBasicMaterial(color="#cc2222"),
        rotation=[0.4, 0.6, 0.0],
    )
    scene = p3.Scene(children=[mesh], background="#f5f5f5")
    camera = p3.PerspectiveCamera(position=[0, 0, 3], aspect=200 / 150)
    return p3.Renderer(scene=scene, camera=camera)


def scene_torus_lit():
    mesh = p3.Mesh(
        geometry=p3.TorusGeometry(radius=1, tube=0.35),
        material=p3.MeshStandardMaterial(color="#3377cc", roughness=0.4),
        rotation=[0.9, 0.2, 0.0],
    )
    scene = p3.Scene(
        children=[
            mesh,
            p3.AmbientLight(intensity=0.4),
            p3.DirectionalLight(position=[5, 5, 5], intensity=1.2),
        ],
        background="#101018",
    )
    camera = p3.PerspectiveCamera(position=[0, 0, 3.2], aspect=200 / 150)
    return p3.Renderer(scene=scene, camera=camera)


def scene_points():
    n = 4000
    rng = np.random.default_rng(42)
    positions = (rng.random((n, 3), dtype="float32") - 0.5) * 3
    colors = np.ones((n, 4), dtype="float32")
    colors[:, 0] = positions[:, 0] / 3 + 0.5
    colors[:, 1] = positions[:, 1] / 3 + 0.5
    colors[:, 2] = 0.8
    geometry = p3.BufferGeometry(
        attributes={
            "position": p3.BufferAttribute(positions, itemSize=3),
            "color": p3.BufferAttribute(colors, itemSize=4),
        }
    )
    points = p3.Points(
        geometry=geometry,
        material=p3.PointsMaterial(size=4, vertexColors=True, sizeAttenuation=False),
    )
    scene = p3.Scene(children=[points], background="#181818")
    camera = p3.PerspectiveCamera(position=[0, 0, 4], aspect=200 / 150)
    return p3.Renderer(scene=scene, camera=camera)


def scene_line2():
    theta = np.linspace(0, 4 * np.pi, 120, dtype="float32")
    positions = np.stack(
        [np.cos(theta), np.sin(theta), theta / (4 * np.pi) - 0.5], axis=1
    )
    line = p3.Line2(
        geometry=p3.LineGeometry(positions=positions),
        material=p3.LineMaterial(color="#22cc66", linewidth=6),
    )
    scene = p3.Scene(children=[line], background="#ffffff")
    camera = p3.PerspectiveCamera(position=[0, 0, 3], aspect=200 / 150)
    return p3.Renderer(scene=scene, camera=camera)


def scene_sprite_text():
    sprite = p3.Sprite(
        material=p3.SpriteMaterial(
            map=p3.TextTexture(string="anythreejs", color="#222266", size=64),
            transparent=True,
        ),
        scale=[2.4, 0.6, 1.0],
    )
    scene = p3.Scene(children=[sprite], background="#eeeedd")
    camera = p3.PerspectiveCamera(position=[0, 0, 3], aspect=200 / 150)
    return p3.Renderer(scene=scene, camera=camera)


SCENES = {
    "box": scene_box,
    "torus_lit": scene_torus_lit,
    "points": scene_points,
    "line2": scene_line2,
    "sprite_text": scene_sprite_text,
}


def frame_array(shot) -> np.ndarray:
    raw = base64.b64decode(shot["b64"])
    return (
        np.frombuffer(raw, dtype=np.uint8)
        .reshape(shot["height"], shot["width"], 4)[:, :, :3]
        .astype(np.int16)
    )


@pytest.mark.parametrize("name", list(SCENES))
def test_golden(harness, name):
    renderer = SCENES[name]()
    harness.boot(renderer)
    frame = frame_array(harness.screenshot())
    harness.assert_clean()

    path = GOLDEN_DIR / f"{name}.{PLATFORM}.png"
    if os.environ.get("GOLDEN_UPDATE") or not path.exists():
        GOLDEN_DIR.mkdir(exist_ok=True)
        Image.fromarray(frame.astype(np.uint8)).save(path)
        pytest.skip(f"baseline written: {path} — commit it")

    baseline = np.asarray(Image.open(path)).astype(np.int16)[:, :, :3]
    assert baseline.shape == frame.shape, "canvas size changed"

    diff = np.abs(frame - baseline)
    mean_diff = float(diff.mean())
    hot_fraction = float((diff.max(axis=2) > 30).mean())
    assert mean_diff < MEAN_DIFF_LIMIT, f"mean diff {mean_diff:.2f}"
    assert hot_fraction < HOT_PIXEL_LIMIT, f"{hot_fraction:.2%} pixels changed"
