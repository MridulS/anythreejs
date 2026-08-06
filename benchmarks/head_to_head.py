"""Head-to-head kernel-side benchmark: anythreejs vs the original pythreejs.

Builds identical plopp-style scenes in both libraries over a no-op comm and
measures what actually differs architecturally:

- construction time for an N-point cloud (pythreejs opens a comm per object)
- construction time for an object-heavy scene (50 text sprites, outline-like)
- per-update kernel cost of a color-array change (median of 20)
- serialized widget state size (what a saved notebook carries)

Run:

    uv run --no-sync --with pythreejs python benchmarks/head_to_head.py

pythreejs is deliberately not a project dependency; `--with` layers it into
an ephemeral environment. Rendering is not measured here (pythreejs ships
its own JS stack that needs a live Jupyter frontend); this is the
kernel-side comparison only.
"""

import json
import time

import numpy as np

# ---------------------------------------------------------------------------
# Run both libraries without a kernel.
# ---------------------------------------------------------------------------
import comm
from comm.base_comm import BaseComm


class DummyComm(BaseComm):
    def publish_msg(self, msg_type, data=None, metadata=None, buffers=None, **keys):
        pass


comm.create_comm = lambda *args, **kwargs: DummyComm(*args, **kwargs)

from ipywidgets import Widget  # noqa: E402
from ipywidgets.widgets.widget import _remove_buffers  # noqa: E402


def state_size(widget) -> tuple[int, int]:
    """(json_bytes, buffer_bytes) of one widget's serialized *scene* state.

    anywidget delivers the widget's own JS through the `_esm`/`_css` traits
    (a fixed ~600 kB per Renderer, replacing pythreejs's separately
    installed labextension), so those are excluded here to compare what the
    scene itself costs."""
    state, _, buffers = _remove_buffers(widget.get_state())
    state = {k: v for k, v in state.items() if k not in ("_esm", "_css")}
    json_bytes = len(json.dumps(state, default=str).encode())
    buffer_bytes = sum(
        len(bytes(b)) if isinstance(b, memoryview) else len(b) for b in buffers
    )
    return json_bytes, buffer_bytes


def build_cloud(p3, n, rng):
    geometry = p3.BufferGeometry(
        attributes={
            "position": p3.BufferAttribute(
                array=rng.random((n, 3)).astype("float32"), itemSize=3
            ),
            "color": p3.BufferAttribute(
                array=rng.random((n, 4)).astype("float32"), itemSize=4
            ),
        }
    )
    points = p3.Points(
        geometry=geometry,
        material=p3.PointsMaterial(size=2, vertexColors="VertexColors"),
    )
    scene = p3.Scene(children=[points, p3.AmbientLight()])
    camera = p3.PerspectiveCamera(position=[3, 3, 3], aspect=4 / 3)
    renderer = p3.Renderer(
        camera=camera,
        scene=scene,
        controls=[p3.OrbitControls(controlling=camera)],
        width=600,
        height=400,
    )
    return renderer, geometry


def build_object_heavy(p3, n_sprites):
    """Outline-style scene: many small labeled objects."""
    children = [p3.AxesHelper()]
    for i in range(n_sprites):
        children.append(
            p3.Sprite(
                material=p3.SpriteMaterial(
                    map=p3.TextTexture(string=f"label-{i}", color="black"),
                    transparent=True,
                ),
                position=[i * 0.1, 0.0, 0.0],
            )
        )
    scene = p3.Scene(children=children)
    camera = p3.PerspectiveCamera(position=[3, 3, 3])
    return p3.Renderer(
        camera=camera,
        scene=scene,
        controls=[p3.OrbitControls(controlling=camera)],
    )


def measure(p3, label):
    rng = np.random.default_rng(1)
    results = {"library": label}

    # -- construction: 100k point cloud ------------------------------------
    before = set(Widget.widgets)
    start = time.perf_counter()
    renderer, geometry = build_cloud(p3, 100_000, rng)
    results["build_100k_s"] = time.perf_counter() - start
    new_widgets = [w for k, w in Widget.widgets.items() if k not in before]
    results["widgets_per_cloud"] = len(new_widgets)

    # -- serialized state of that scene ------------------------------------
    json_bytes = buffer_bytes = 0
    for widget in new_widgets or [renderer]:
        j, b = state_size(widget)
        json_bytes += j
        buffer_bytes += b
    results["state_json_kb"] = json_bytes / 1e3
    results["state_buffers_mb"] = buffer_bytes / 1e6

    # -- per-update cost: color array change -------------------------------
    samples = []
    for _ in range(20):
        colors = rng.random((100_000, 4)).astype("float32")
        start = time.perf_counter()
        geometry.attributes["color"].array = colors
        samples.append(time.perf_counter() - start)
    results["update_100k_ms"] = sorted(samples)[len(samples) // 2] * 1e3

    # -- construction: object-heavy scene ----------------------------------
    before = set(Widget.widgets)
    start = time.perf_counter()
    build_object_heavy(p3, 50)
    results["build_50_sprites_s"] = time.perf_counter() - start
    results["widgets_per_sprite_scene"] = sum(
        1 for k in Widget.widgets if k not in before
    )

    return results


def main():
    import anythreejs

    rows = [measure(anythreejs, "anythreejs")]
    try:
        import pythreejs
    except ImportError:
        print("pythreejs not available — run with: uv run --with pythreejs ...")
        pythreejs = None
    if pythreejs is not None:
        rows.append(measure(pythreejs, "pythreejs"))

    columns = [
        ("library", "library", "{}"),
        ("build_100k_s", "build 100k cloud (s)", "{:.3f}"),
        ("widgets_per_cloud", "widgets created", "{}"),
        ("update_100k_ms", "color update (ms, median)", "{:.1f}"),
        ("state_json_kb", "state JSON (kB)", "{:.1f}"),
        ("state_buffers_mb", "state buffers (MB)", "{:.1f}"),
        ("build_50_sprites_s", "build 50-sprite scene (s)", "{:.3f}"),
        ("widgets_per_sprite_scene", "widgets (sprite scene)", "{}"),
    ]
    header = " | ".join(title for _, title, _ in columns)
    print("\n" + header)
    print("-" * len(header))
    for row in rows:
        print(
            " | ".join(
                fmt.format(row[key]).rjust(len(title)) for key, title, fmt in columns
            )
        )


if __name__ == "__main__":
    main()
