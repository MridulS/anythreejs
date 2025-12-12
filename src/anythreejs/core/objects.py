"""
Renderable objects: Mesh, Points, Line, Sprite, Group.
"""

from typing import Any
from .base import Object3D


class Mesh(Object3D):
    """Mesh combines geometry and material into a renderable object."""

    _type = "Mesh"

    def __init__(self, geometry=None, material=None, **kwargs):
        super().__init__(**kwargs)
        self._geometry = geometry
        self._material = material

    @property
    def geometry(self):
        return self._geometry

    @geometry.setter
    def geometry(self, value):
        old = self._geometry
        self._geometry = value
        if value and self._parent_renderer:
            value._set_renderer(self._parent_renderer)
        self._notify("geometry", old, value)

    @property
    def material(self):
        return self._material

    @material.setter
    def material(self, value):
        old = self._material
        self._material = value
        if value and self._parent_renderer:
            value._set_renderer(self._parent_renderer)
        self._notify("material", old, value)

    def _set_renderer(self, renderer):
        super()._set_renderer(renderer)
        if self._geometry:
            self._geometry._set_renderer(renderer)
        if self._material:
            self._material._set_renderer(renderer)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self._geometry:
            data["geometry"] = self._geometry.to_dict()
        if self._material:
            data["material"] = self._material.to_dict()
        return data


class Points(Object3D):
    """Renders geometry vertices as points (point cloud)."""

    _type = "Points"

    def __init__(self, geometry=None, material=None, **kwargs):
        super().__init__(**kwargs)
        self._geometry = geometry
        self._material = material

    @property
    def geometry(self):
        return self._geometry

    @geometry.setter
    def geometry(self, value):
        old = self._geometry
        self._geometry = value
        if value and self._parent_renderer:
            value._set_renderer(self._parent_renderer)
        self._notify("geometry", old, value)

    @property
    def material(self):
        return self._material

    @material.setter
    def material(self, value):
        old = self._material
        self._material = value
        if value and self._parent_renderer:
            value._set_renderer(self._parent_renderer)
        self._notify("material", old, value)

    def _set_renderer(self, renderer):
        super()._set_renderer(renderer)
        if self._geometry:
            self._geometry._set_renderer(renderer)
        if self._material:
            self._material._set_renderer(renderer)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self._geometry:
            data["geometry"] = self._geometry.to_dict()
        if self._material:
            data["material"] = self._material.to_dict()
        return data


class Line(Object3D):
    """Renders geometry as connected lines."""

    _type = "Line"

    def __init__(self, geometry=None, material=None, **kwargs):
        super().__init__(**kwargs)
        self._geometry = geometry
        self._material = material

    @property
    def geometry(self):
        return self._geometry

    @geometry.setter
    def geometry(self, value):
        old = self._geometry
        self._geometry = value
        if value and self._parent_renderer:
            value._set_renderer(self._parent_renderer)
        self._notify("geometry", old, value)

    @property
    def material(self):
        return self._material

    @material.setter
    def material(self, value):
        old = self._material
        self._material = value
        if value and self._parent_renderer:
            value._set_renderer(self._parent_renderer)
        self._notify("material", old, value)

    def _set_renderer(self, renderer):
        super()._set_renderer(renderer)
        if self._geometry:
            self._geometry._set_renderer(renderer)
        if self._material:
            self._material._set_renderer(renderer)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self._geometry:
            data["geometry"] = self._geometry.to_dict()
        if self._material:
            data["material"] = self._material.to_dict()
        return data


class LineSegments(Line):
    """Renders pairs of vertices as separate line segments."""

    _type = "LineSegments"


class Group(Object3D):
    """Container for grouping multiple objects."""

    _type = "Group"

    def __init__(self, children=None, **kwargs):
        super().__init__(**kwargs)
        if children:
            for child in children:
                self.add(child)


class Sprite(Object3D):
    """2D sprite that always faces the camera."""

    _type = "Sprite"

    def __init__(self, material=None, **kwargs):
        super().__init__(**kwargs)
        self._material = material

    @property
    def material(self):
        return self._material

    @material.setter
    def material(self, value):
        old = self._material
        self._material = value
        self._notify("material", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self._material:
            data["material"] = self._material.to_dict()
        return data
