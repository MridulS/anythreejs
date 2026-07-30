"""
Helper objects for visualization (axes, grids).

Generated from the declarative catalog in ``spec.py``.
"""

from .base import Object3D
from .spec import make_class

__all__ = ["AxesHelper", "GridHelper"]

AxesHelper = make_class("AxesHelper", Object3D)
GridHelper = make_class("GridHelper", Object3D)
