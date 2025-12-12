"""
Core Three.js components.
"""

from .base import ThreeJSBase, Object3D
from .scene import Scene
from .camera import PerspectiveCamera, OrthographicCamera
from .controls import OrbitControls, TrackballControls
from .geometry import (
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
)
from .material import (
    Material,
    MeshBasicMaterial,
    MeshStandardMaterial,
    MeshPhongMaterial,
    MeshLambertMaterial,
    PointsMaterial,
    LineBasicMaterial,
    LineDashedMaterial,
    SpriteMaterial,
)
from .objects import Mesh, Points, Line, LineSegments, Group, Sprite
from .lights import (
    AmbientLight,
    DirectionalLight,
    PointLight,
    HemisphereLight,
    SpotLight,
)
from .helpers import AxesHelper, GridHelper
from .buffer import (
    BufferAttribute,
    Float32BufferAttribute,
    Uint32BufferAttribute,
    Uint16BufferAttribute,
    Int32BufferAttribute,
)
from .textures import TextTexture

__all__ = [
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
]
