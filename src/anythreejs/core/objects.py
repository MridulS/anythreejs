"""
Renderable objects: Mesh, Points, Line, Sprite, Group.
"""

from typing import Any, Iterator, Optional
from .base import Object3D, ThreeJSBase


class RenderableObject(Object3D):
    """
    Base class for renderable objects with geometry and material.

    This eliminates code duplication between Mesh, Points, Line, and Line2.
    """

    _type = "RenderableObject"

    def __init__(
        self,
        geometry: Optional[ThreeJSBase] = None,
        material: Optional[ThreeJSBase] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._geometry = geometry
        self._material = material

    @property
    def geometry(self) -> Optional[ThreeJSBase]:
        """The geometry defining the shape of this object."""
        return self._geometry

    @geometry.setter
    def geometry(self, value: Optional[ThreeJSBase]):
        if value is self._geometry:
            return
        old = self._geometry
        self._geometry = value
        self._notify("geometry", old, value)

    @property
    def material(self) -> Optional[ThreeJSBase]:
        """The material defining the appearance of this object."""
        return self._material

    @material.setter
    def material(self, value: Optional[ThreeJSBase]):
        if value is self._material:
            return
        old = self._material
        self._material = value
        self._notify("material", old, value)

    def _owned_objects(self) -> Iterator[ThreeJSBase]:
        yield from super()._owned_objects()
        if self._geometry is not None:
            yield self._geometry
        if self._material is not None:
            yield self._material

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        """Serialize to dictionary including geometry and material."""
        data = super().to_dict(buffer_manager=buffer_manager, flat=flat)
        if self._geometry:
            data["geometry"] = (
                self._geometry.uuid
                if flat
                else self._geometry.to_dict(buffer_manager=buffer_manager)
            )
        if self._material:
            data["material"] = (
                self._material.uuid
                if flat
                else self._material.to_dict(buffer_manager=buffer_manager)
            )
        return data


class Mesh(RenderableObject):
    """Mesh combines geometry and material into a renderable object."""

    _type = "Mesh"


class Points(RenderableObject):
    """Renders geometry vertices as points (point cloud)."""

    _type = "Points"


class Line(RenderableObject):
    """Renders geometry as connected lines."""

    _type = "Line"


class LineSegments(Line):
    """Renders pairs of vertices as separate line segments."""

    _type = "LineSegments"


class Line2(RenderableObject):
    """Fat line with configurable width using LineGeometry and LineMaterial."""

    _type = "Line2"


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

    def __init__(self, material: Optional[ThreeJSBase] = None, **kwargs):
        super().__init__(**kwargs)
        self._material = material

    @property
    def material(self) -> Optional[ThreeJSBase]:
        """The sprite material."""
        return self._material

    @material.setter
    def material(self, value: Optional[ThreeJSBase]):
        if value is self._material:
            return
        old = self._material
        self._material = value
        self._notify("material", old, value)

    def _owned_objects(self) -> Iterator[ThreeJSBase]:
        yield from super()._owned_objects()
        if self._material is not None:
            yield self._material

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        """Serialize to dictionary including material."""
        data = super().to_dict(buffer_manager=buffer_manager, flat=flat)
        if self._material:
            data["material"] = (
                self._material.uuid
                if flat
                else self._material.to_dict(buffer_manager=buffer_manager)
            )
        return data
