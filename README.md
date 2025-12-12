# anythreejs

A Python / Three.js bridge for Jupyter notebooks, built on [anywidget](https://anywidget.dev/).

This comes out of the need to have a lightweight wrapper around Three.js which is easy to maintain and extend, while being compatible with existing codebases using [pythreejs](https://github.com/jupyter-widgets/pythreejs).

## Installation

```bash
pip install anythreejs
```

## Quick Start

```python
from anythreejs import (
    Renderer,
    Scene,
    PerspectiveCamera,
    OrbitControls,
    Mesh,
    BoxGeometry,
    MeshStandardMaterial,
    AmbientLight,
    DirectionalLight,
)

# Create a scene
scene = Scene(
    children=[
        Mesh(
            geometry=BoxGeometry(1, 1, 1),
            material=MeshStandardMaterial(color="#ff0c0cff", roughness=0.4),
        ),
        AmbientLight(intensity=0.4),
        DirectionalLight(position=[5, 5, 5], intensity=1),
    ],
    background="#e5e5faff",
)

camera = PerspectiveCamera(position=[3, 3, 3])
controls = OrbitControls(controlling=camera)

# Display the widget (renderer is the widget)
renderer = Renderer(
    camera=camera,
    scene=scene,
    controls=[controls],
    width=700,
    height=450,
)
renderer
```

## API Overview

anythreejs provides a subset of Three.js objects as Python classes. Currently we only cover the parts used by [plopp](https://github.com/scipp/plopp/). We should ideally automatically generate these classes from the Three.js documentation in the future.

## Renderer Options

```python
Renderer(
    scene=scene,           # Scene object
    camera=camera,         # Camera object
    controls=[controls],   # Controls list (e.g., OrbitControls)
    width=800,             # Canvas width in pixels
    height=600,            # Canvas height in pixels
    antialias=True,        # Enable antialiasing
    alpha=False,           # Canvas transparency
)
```

## Interaction

### Click Events

```python
import anythreejs as p3

renderer = p3.Renderer(camera=camera, scene=scene, controls=[controls])

def handle_click(change):
    info = change.get("new", {})
    if info:
        print(f"Clicked: {info.get('name')} at {info.get('point')}")

renderer.observe(handle_click, names=["_click_info"])
renderer
```

## pythreejs Compatibility

anythreejs tries to be API-compatible with the original `pythreejs`. For projects that already use pythreejs
(like [plopp](https://github.com/scipp/plopp)), you can switch with minimal changes:

```python
# Instead of:
# import pythreejs as p3

# Use:
import anythreejs as p3
```

### Example (pythreejs-style usage)

```python
import anythreejs as p3

# Create camera
camera = p3.PerspectiveCamera(aspect=800/600)
camera.position = [5, 5, 5]

# Create scene
axes = p3.AxesHelper()
scene = p3.Scene(children=[camera, axes], background="#f0f0f0")

# Create controls
controls = p3.OrbitControls(controlling=camera)

# Create renderer (this is the widget)
renderer = p3.Renderer(
    camera=camera,
    scene=scene,
    controls=[controls],
    width=800,
    height=600,
)

# Add objects dynamically
mesh = p3.Mesh(
    geometry=p3.BoxGeometry(1, 1, 1),
    material=p3.MeshStandardMaterial(color="#ff0000"),
)
scene.add(mesh)

# Display
renderer
```

## Credits

- Inspired by the original [pythreejs](https://github.com/jupyter-widgets/pythreejs)
- Built with [anywidget](https://anywidget.dev/)
- Powered by [Three.js](https://threejs.org/)
