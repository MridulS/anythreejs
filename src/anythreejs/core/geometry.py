"""
Geometry classes for Three.js primitives.
"""

from typing import Any, Optional
from .base import ThreeJSBase


class _AttributesDict(dict):
    """Dict that notifies geometry when attributes change."""

    def __init__(self, geometry, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._geometry = geometry
        for attr in self.values():
            self._setup_callback(attr)

    def _setup_callback(self, attr):
        if hasattr(attr, "_set_on_change"):
            attr._set_on_change(self._on_change)

    def _on_change(self):
        if self._geometry:
            self._geometry._notify("attributes", None, self)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._setup_callback(value)
        self._on_change()


class BufferGeometry(ThreeJSBase):
    """Flexible geometry for custom vertex data (point clouds, custom meshes)."""

    _type = "BufferGeometry"

    def __init__(self, attributes: Optional[dict] = None, index=None, **kwargs):
        super().__init__()
        self._attributes = _AttributesDict(self, attributes or {})
        self._index = index

    @property
    def attributes(self) -> dict:
        return self._attributes

    @attributes.setter
    def attributes(self, value: dict):
        old = self._attributes
        self._attributes = _AttributesDict(self, value)
        self._notify("attributes", old, value)

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, value):
        old = self._index
        self._index = value
        self._notify("index", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = {"type": self._type, "uuid": self._uuid}

        if self._attributes:
            attrs = {}
            for name, attr in self._attributes.items():
                if hasattr(attr, "to_dict"):
                    attrs[name] = attr.to_dict()
                elif hasattr(attr, "array"):
                    arr = attr.array
                    if hasattr(arr, "tolist"):
                        arr = arr.tolist()
                    attrs[name] = {
                        "array": arr,
                        "itemSize": getattr(attr, "itemSize", 3),
                    }
                else:
                    attrs[name] = attr
            data["attributes"] = attrs

        if self._index is not None:
            if hasattr(self._index, "to_dict"):
                data["index"] = self._index.to_dict()
            elif hasattr(self._index, "array"):
                arr = self._index.array
                if hasattr(arr, "tolist"):
                    arr = arr.tolist()
                data["index"] = arr
            else:
                data["index"] = self._index

        return data


class BoxGeometry(ThreeJSBase):
    """Box geometry with specified dimensions."""

    _type = "BoxGeometry"

    def __init__(
        self,
        width: float = 1,
        height: float = 1,
        depth: float = 1,
        widthSegments: int = 1,
        heightSegments: int = 1,
        depthSegments: int = 1,
        **kwargs,
    ):
        super().__init__()
        self.width = width
        self.height = height
        self.depth = depth
        self.widthSegments = widthSegments
        self.heightSegments = heightSegments
        self.depthSegments = depthSegments

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "width": self.width,
            "height": self.height,
            "depth": self.depth,
            "widthSegments": self.widthSegments,
            "heightSegments": self.heightSegments,
            "depthSegments": self.depthSegments,
        }


# Alias for pythreejs compatibility
BoxBufferGeometry = BoxGeometry


class SphereGeometry(ThreeJSBase):
    """Sphere geometry."""

    _type = "SphereGeometry"

    def __init__(
        self,
        radius: float = 1,
        widthSegments: int = 32,
        heightSegments: int = 16,
        phiStart: float = 0,
        phiLength: float = 6.283185307179586,
        thetaStart: float = 0,
        thetaLength: float = 3.141592653589793,
        **kwargs,
    ):
        super().__init__()
        self.radius = radius
        self.widthSegments = widthSegments
        self.heightSegments = heightSegments
        self.phiStart = phiStart
        self.phiLength = phiLength
        self.thetaStart = thetaStart
        self.thetaLength = thetaLength

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "radius": self.radius,
            "widthSegments": self.widthSegments,
            "heightSegments": self.heightSegments,
            "phiStart": self.phiStart,
            "phiLength": self.phiLength,
            "thetaStart": self.thetaStart,
            "thetaLength": self.thetaLength,
        }


SphereBufferGeometry = SphereGeometry


class PlaneGeometry(ThreeJSBase):
    """Plane geometry."""

    _type = "PlaneGeometry"

    def __init__(
        self,
        width: float = 1,
        height: float = 1,
        widthSegments: int = 1,
        heightSegments: int = 1,
        **kwargs,
    ):
        super().__init__()
        self.width = width
        self.height = height
        self.widthSegments = widthSegments
        self.heightSegments = heightSegments

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "width": self.width,
            "height": self.height,
            "widthSegments": self.widthSegments,
            "heightSegments": self.heightSegments,
        }


PlaneBufferGeometry = PlaneGeometry


class CylinderGeometry(ThreeJSBase):
    """Cylinder geometry."""

    _type = "CylinderGeometry"

    def __init__(
        self,
        radiusTop: float = 1,
        radiusBottom: float = 1,
        height: float = 1,
        radialSegments: int = 32,
        heightSegments: int = 1,
        openEnded: bool = False,
        thetaStart: float = 0,
        thetaLength: float = 6.283185307179586,
        **kwargs,
    ):
        super().__init__()
        self.radiusTop = radiusTop
        self.radiusBottom = radiusBottom
        self.height = height
        self.radialSegments = radialSegments
        self.heightSegments = heightSegments
        self.openEnded = openEnded
        self.thetaStart = thetaStart
        self.thetaLength = thetaLength

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "radiusTop": self.radiusTop,
            "radiusBottom": self.radiusBottom,
            "height": self.height,
            "radialSegments": self.radialSegments,
            "heightSegments": self.heightSegments,
            "openEnded": self.openEnded,
            "thetaStart": self.thetaStart,
            "thetaLength": self.thetaLength,
        }


CylinderBufferGeometry = CylinderGeometry


class TorusGeometry(ThreeJSBase):
    """Torus (donut) geometry."""

    _type = "TorusGeometry"

    def __init__(
        self,
        radius: float = 1,
        tube: float = 0.4,
        radialSegments: int = 16,
        tubularSegments: int = 100,
        arc: float = 6.283185307179586,
        **kwargs,
    ):
        super().__init__()
        self.radius = radius
        self.tube = tube
        self.radialSegments = radialSegments
        self.tubularSegments = tubularSegments
        self.arc = arc

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "radius": self.radius,
            "tube": self.tube,
            "radialSegments": self.radialSegments,
            "tubularSegments": self.tubularSegments,
            "arc": self.arc,
        }


class EdgesGeometry(ThreeJSBase):
    """Geometry that extracts edges from another geometry."""

    _type = "EdgesGeometry"

    def __init__(self, geometry=None, thresholdAngle: float = 1, **kwargs):
        super().__init__()
        self._geometry = geometry
        self.thresholdAngle = thresholdAngle

    @property
    def geometry(self):
        return self._geometry

    @geometry.setter
    def geometry(self, value):
        old = self._geometry
        self._geometry = value
        self._notify("geometry", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "type": self._type,
            "uuid": self._uuid,
            "thresholdAngle": self.thresholdAngle,
        }
        if self._geometry:
            data["geometry"] = self._geometry.to_dict()
        return data
