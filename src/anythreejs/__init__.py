"""
anythreejs - A modern Python/Three.js bridge for Jupyter

Quick start:
    from anythreejs import Renderer, Scene, PerspectiveCamera, OrbitControls
    from anythreejs import Mesh, BoxGeometry, MeshStandardMaterial, AmbientLight

    scene = Scene(background="#1a1a2e")
    scene.add(Mesh(BoxGeometry(1, 1, 1), MeshStandardMaterial(color="#ff6600")))
    scene.add(AmbientLight(intensity=0.5))

    camera = PerspectiveCamera(position=(0, 0, 5))
    controls = OrbitControls(controlling=camera)

    renderer = Renderer(camera=camera, scene=scene, controls=[controls])
    renderer  # Display in notebook

For pythreejs-style namespace imports:
    import anythreejs as p3
    # Then use p3.Scene, p3.Renderer, etc.
"""

from .renderer import Renderer
from .core import (
    # Base
    ThreeJSBase,
    Object3D,
    # Scene
    Scene,
    # Cameras
    PerspectiveCamera,
    OrthographicCamera,
    # Controls
    OrbitControls,
    TrackballControls,
    # Geometry
    BufferGeometry,
    BoxGeometry,
    BoxBufferGeometry,
    SphereGeometry,
    SphereBufferGeometry,
    PlaneGeometry,
    PlaneBufferGeometry,
    CylinderGeometry,
    CylinderBufferGeometry,
    TorusGeometry,
    EdgesGeometry,
    # Material
    Material,
    MeshBasicMaterial,
    MeshStandardMaterial,
    MeshPhongMaterial,
    MeshLambertMaterial,
    PointsMaterial,
    LineBasicMaterial,
    LineDashedMaterial,
    SpriteMaterial,
    # Objects
    Mesh,
    Points,
    Line,
    LineSegments,
    Group,
    Sprite,
    # Lights
    AmbientLight,
    DirectionalLight,
    PointLight,
    HemisphereLight,
    SpotLight,
    # Helpers
    AxesHelper,
    GridHelper,
    # Buffer
    BufferAttribute,
    Float32BufferAttribute,
    Uint32BufferAttribute,
    Uint16BufferAttribute,
    Int32BufferAttribute,
    # Textures
    TextTexture,
)

# Convenience alias for pythreejs-style imports: `import anythreejs as p3`
import sys as _sys

p3 = _sys.modules[__name__]

__version__ = "0.0.1"

__all__ = [
    # Renderer
    "Renderer",
    # Base
    "ThreeJSBase",
    "Object3D",
    # Scene
    "Scene",
    # Cameras
    "PerspectiveCamera",
    "OrthographicCamera",
    # Controls
    "OrbitControls",
    "TrackballControls",
    # Geometry
    "BufferGeometry",
    "BoxGeometry",
    "BoxBufferGeometry",
    "SphereGeometry",
    "SphereBufferGeometry",
    "PlaneGeometry",
    "PlaneBufferGeometry",
    "CylinderGeometry",
    "CylinderBufferGeometry",
    "TorusGeometry",
    "EdgesGeometry",
    # Material
    "Material",
    "MeshBasicMaterial",
    "MeshStandardMaterial",
    "MeshPhongMaterial",
    "MeshLambertMaterial",
    "PointsMaterial",
    "LineBasicMaterial",
    "LineDashedMaterial",
    "SpriteMaterial",
    # Objects
    "Mesh",
    "Points",
    "Line",
    "LineSegments",
    "Group",
    "Sprite",
    # Lights
    "AmbientLight",
    "DirectionalLight",
    "PointLight",
    "HemisphereLight",
    "SpotLight",
    # Helpers
    "AxesHelper",
    "GridHelper",
    # Buffer
    "BufferAttribute",
    "Float32BufferAttribute",
    "Uint32BufferAttribute",
    "Uint16BufferAttribute",
    "Int32BufferAttribute",
    # Textures
    "TextTexture",
    # Convenience alias
    "p3",
]
