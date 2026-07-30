"""
Material classes for Three.js.

All material classes are generated from the declarative catalog in
``spec.py`` — fields, defaults, validation, and serialization live there.
"""

from .base import ThreeJSBase
from .spec import SIDE_MAP, make_class

__all__ = [
    "SIDE_MAP",
    "Material",
    "MeshBasicMaterial",
    "MeshStandardMaterial",
    "MeshPhongMaterial",
    "MeshLambertMaterial",
    "PointsMaterial",
    "LineBasicMaterial",
    "LineDashedMaterial",
    "SpriteMaterial",
    "LineMaterial",
]

Material = make_class("Material", ThreeJSBase)
MeshBasicMaterial = make_class("MeshBasicMaterial", Material)
MeshStandardMaterial = make_class("MeshStandardMaterial", Material)
MeshPhongMaterial = make_class("MeshPhongMaterial", Material)
MeshLambertMaterial = make_class("MeshLambertMaterial", Material)
PointsMaterial = make_class("PointsMaterial", Material)
LineBasicMaterial = make_class("LineBasicMaterial", Material)
LineDashedMaterial = make_class("LineDashedMaterial", LineBasicMaterial)

# Sprite and fat-line materials are standalone (no side/depth fields).
SpriteMaterial = make_class("SpriteMaterial", ThreeJSBase)
LineMaterial = make_class("LineMaterial", ThreeJSBase)
