"""
Light classes for Three.js scenes.

Generated from the declarative catalog in ``spec.py``; transforms
(position/rotation/scale) come from the ``Object3D`` base.
"""

from .base import Object3D
from .spec import make_class

__all__ = [
    "AmbientLight",
    "DirectionalLight",
    "PointLight",
    "HemisphereLight",
    "SpotLight",
]

AmbientLight = make_class("AmbientLight", Object3D)
DirectionalLight = make_class("DirectionalLight", Object3D)
PointLight = make_class("PointLight", Object3D)
HemisphereLight = make_class("HemisphereLight", Object3D)
SpotLight = make_class("SpotLight", Object3D)
