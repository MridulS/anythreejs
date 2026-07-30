"""
Geometry classes for Three.js primitives.

All geometry classes use observable properties that trigger re-renders when changed.
"""

from functools import partial
from typing import Any, Iterator, Optional

from .base import ThreeJSBase
from .buffer import binary_wrapper


class _AttributesDict(dict):
    """Dict that notifies its geometry when an attribute's data changes,
    carrying the attribute name so the renderer can emit a targeted
    buffer op."""

    def __init__(self, geometry, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._geometry = geometry
        self._callbacks: dict[str, tuple] = {}
        for name, attr in self.items():
            self._setup_callback(name, attr)

    def _setup_callback(self, name, attr):
        if hasattr(attr, "_add_on_change"):
            callback = partial(self._on_change, name)
            attr._add_on_change(callback)
            self._callbacks[name] = (attr, callback)

    def _teardown_callback(self, name):
        entry = self._callbacks.pop(name, None)
        if entry is not None:
            attr, callback = entry
            if hasattr(attr, "_remove_on_change"):
                attr._remove_on_change(callback)

    def _teardown_all(self):
        for name in list(self._callbacks):
            self._teardown_callback(name)

    def _on_change(self, name):
        if self._geometry:
            self._geometry._notify("attribute_data", None, name)

    def __setitem__(self, key, value):
        self._teardown_callback(key)
        super().__setitem__(key, value)
        self._setup_callback(key, value)
        self._on_change(key)


def _serialize_attribute(attr, flat=False) -> Any:
    """Serialize a BufferAttribute-like or raw-array attribute value."""
    if hasattr(attr, "to_dict"):
        return attr.to_dict(flat=flat)
    if hasattr(attr, "array"):
        arr = attr.array
        item_size = getattr(attr, "itemSize", 3)
        if flat:
            data = binary_wrapper(arr, dtype="float32")
            data["itemSize"] = item_size
            data["normalized"] = getattr(attr, "normalized", False)
            return data
        if hasattr(arr, "tolist"):
            arr = arr.tolist()
        return {"array": arr, "itemSize": item_size}
    return attr


class BufferGeometry(ThreeJSBase):
    """Flexible geometry for custom vertex data (point clouds, custom meshes)."""

    _type = "BufferGeometry"

    def __init__(self, attributes: Optional[dict] = None, index=None, **kwargs):
        super().__init__(**kwargs)
        self._attributes = _AttributesDict(self, attributes or {})
        self._index = None
        self._index_callback = self._on_index_data
        self._set_index(index)

    def _on_index_data(self):
        self._notify("index_data", None, None)

    def _set_index(self, value):
        if hasattr(self._index, "_remove_on_change"):
            self._index._remove_on_change(self._index_callback)
        self._index = value
        if hasattr(value, "_add_on_change"):
            value._add_on_change(self._index_callback)

    @property
    def attributes(self) -> dict:
        return self._attributes

    @attributes.setter
    def attributes(self, value: dict):
        old = self._attributes
        if isinstance(old, _AttributesDict):
            old._teardown_all()
        self._attributes = _AttributesDict(self, value)
        self._notify("attributes", old, value)

    @property
    def index(self):
        return self._index

    @index.setter
    def index(self, value):
        old = self._index
        self._set_index(value)
        self._notify("index", old, value)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        data = {"type": self._type, "uuid": self._uuid}

        if self._attributes:
            data["attributes"] = {
                name: _serialize_attribute(attr, flat=flat)
                for name, attr in self._attributes.items()
            }

        if self._index is not None:
            index = self._index
            if hasattr(index, "to_dict") or hasattr(index, "array"):
                data["index"] = _serialize_attribute(index, flat=flat)
            elif flat:
                wrapper = binary_wrapper(index, dtype="uint32")
                wrapper["itemSize"] = 1
                data["index"] = wrapper
            else:
                data["index"] = index

        return data


def _validate_positive(value: float, name: str) -> float:
    """Validate that a value is positive."""
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def _validate_min_int(value: int, minimum: int, name: str) -> int:
    """Validate that an integer is at least a minimum value."""
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


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
        super().__init__(**kwargs)
        self._width = _validate_positive(width, "width")
        self._height = _validate_positive(height, "height")
        self._depth = _validate_positive(depth, "depth")
        self._widthSegments = _validate_min_int(widthSegments, 1, "widthSegments")
        self._heightSegments = _validate_min_int(heightSegments, 1, "heightSegments")
        self._depthSegments = _validate_min_int(depthSegments, 1, "depthSegments")

    @property
    def width(self) -> float:
        """Width of the box (X axis)."""
        return self._width

    @width.setter
    def width(self, value: float):
        old = self._width
        self._width = _validate_positive(value, "width")
        self._notify("width", old, self._width)

    @property
    def height(self) -> float:
        """Height of the box (Y axis)."""
        return self._height

    @height.setter
    def height(self, value: float):
        old = self._height
        self._height = _validate_positive(value, "height")
        self._notify("height", old, self._height)

    @property
    def depth(self) -> float:
        """Depth of the box (Z axis)."""
        return self._depth

    @depth.setter
    def depth(self, value: float):
        old = self._depth
        self._depth = _validate_positive(value, "depth")
        self._notify("depth", old, self._depth)

    @property
    def widthSegments(self) -> int:
        """Number of segments along the width."""
        return self._widthSegments

    @widthSegments.setter
    def widthSegments(self, value: int):
        old = self._widthSegments
        self._widthSegments = _validate_min_int(value, 1, "widthSegments")
        self._notify("widthSegments", old, self._widthSegments)

    @property
    def heightSegments(self) -> int:
        """Number of segments along the height."""
        return self._heightSegments

    @heightSegments.setter
    def heightSegments(self, value: int):
        old = self._heightSegments
        self._heightSegments = _validate_min_int(value, 1, "heightSegments")
        self._notify("heightSegments", old, self._heightSegments)

    @property
    def depthSegments(self) -> int:
        """Number of segments along the depth."""
        return self._depthSegments

    @depthSegments.setter
    def depthSegments(self, value: int):
        old = self._depthSegments
        self._depthSegments = _validate_min_int(value, 1, "depthSegments")
        self._notify("depthSegments", old, self._depthSegments)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "width": self._width,
            "height": self._height,
            "depth": self._depth,
            "widthSegments": self._widthSegments,
            "heightSegments": self._heightSegments,
            "depthSegments": self._depthSegments,
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
        super().__init__(**kwargs)
        self._radius = _validate_positive(radius, "radius")
        self._widthSegments = _validate_min_int(widthSegments, 3, "widthSegments")
        self._heightSegments = _validate_min_int(heightSegments, 2, "heightSegments")
        # Angles are passed through as-is: three.js accepts negative starts
        # and partial sweeps, and pythreejs never validated them.
        self._phiStart = phiStart
        self._phiLength = phiLength
        self._thetaStart = thetaStart
        self._thetaLength = thetaLength

    @property
    def radius(self) -> float:
        """Radius of the sphere."""
        return self._radius

    @radius.setter
    def radius(self, value: float):
        old = self._radius
        self._radius = _validate_positive(value, "radius")
        self._notify("radius", old, self._radius)

    @property
    def widthSegments(self) -> int:
        """Number of horizontal segments (minimum 3)."""
        return self._widthSegments

    @widthSegments.setter
    def widthSegments(self, value: int):
        old = self._widthSegments
        self._widthSegments = _validate_min_int(value, 3, "widthSegments")
        self._notify("widthSegments", old, self._widthSegments)

    @property
    def heightSegments(self) -> int:
        """Number of vertical segments (minimum 2)."""
        return self._heightSegments

    @heightSegments.setter
    def heightSegments(self, value: int):
        old = self._heightSegments
        self._heightSegments = _validate_min_int(value, 2, "heightSegments")
        self._notify("heightSegments", old, self._heightSegments)

    @property
    def phiStart(self) -> float:
        """Horizontal starting angle."""
        return self._phiStart

    @phiStart.setter
    def phiStart(self, value: float):
        old = self._phiStart
        self._phiStart = value
        self._notify("phiStart", old, self._phiStart)

    @property
    def phiLength(self) -> float:
        """Horizontal sweep angle size."""
        return self._phiLength

    @phiLength.setter
    def phiLength(self, value: float):
        old = self._phiLength
        self._phiLength = value
        self._notify("phiLength", old, self._phiLength)

    @property
    def thetaStart(self) -> float:
        """Vertical starting angle."""
        return self._thetaStart

    @thetaStart.setter
    def thetaStart(self, value: float):
        old = self._thetaStart
        self._thetaStart = value
        self._notify("thetaStart", old, self._thetaStart)

    @property
    def thetaLength(self) -> float:
        """Vertical sweep angle size."""
        return self._thetaLength

    @thetaLength.setter
    def thetaLength(self, value: float):
        old = self._thetaLength
        self._thetaLength = value
        self._notify("thetaLength", old, self._thetaLength)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "radius": self._radius,
            "widthSegments": self._widthSegments,
            "heightSegments": self._heightSegments,
            "phiStart": self._phiStart,
            "phiLength": self._phiLength,
            "thetaStart": self._thetaStart,
            "thetaLength": self._thetaLength,
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
        super().__init__(**kwargs)
        self._width = _validate_positive(width, "width")
        self._height = _validate_positive(height, "height")
        self._widthSegments = _validate_min_int(widthSegments, 1, "widthSegments")
        self._heightSegments = _validate_min_int(heightSegments, 1, "heightSegments")

    @property
    def width(self) -> float:
        """Width of the plane."""
        return self._width

    @width.setter
    def width(self, value: float):
        old = self._width
        self._width = _validate_positive(value, "width")
        self._notify("width", old, self._width)

    @property
    def height(self) -> float:
        """Height of the plane."""
        return self._height

    @height.setter
    def height(self, value: float):
        old = self._height
        self._height = _validate_positive(value, "height")
        self._notify("height", old, self._height)

    @property
    def widthSegments(self) -> int:
        """Number of segments along the width."""
        return self._widthSegments

    @widthSegments.setter
    def widthSegments(self, value: int):
        old = self._widthSegments
        self._widthSegments = _validate_min_int(value, 1, "widthSegments")
        self._notify("widthSegments", old, self._widthSegments)

    @property
    def heightSegments(self) -> int:
        """Number of segments along the height."""
        return self._heightSegments

    @heightSegments.setter
    def heightSegments(self, value: int):
        old = self._heightSegments
        self._heightSegments = _validate_min_int(value, 1, "heightSegments")
        self._notify("heightSegments", old, self._heightSegments)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "width": self._width,
            "height": self._height,
            "widthSegments": self._widthSegments,
            "heightSegments": self._heightSegments,
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
        super().__init__(**kwargs)
        if radiusTop < 0:
            raise ValueError(f"radiusTop must be non-negative, got {radiusTop}")
        if radiusBottom < 0:
            raise ValueError(f"radiusBottom must be non-negative, got {radiusBottom}")
        self._radiusTop = radiusTop
        self._radiusBottom = radiusBottom
        self._height = _validate_positive(height, "height")
        self._radialSegments = _validate_min_int(radialSegments, 3, "radialSegments")
        self._heightSegments = _validate_min_int(heightSegments, 1, "heightSegments")
        self._openEnded = openEnded
        self._thetaStart = thetaStart
        self._thetaLength = thetaLength

    @property
    def radiusTop(self) -> float:
        """Radius of the cylinder at the top."""
        return self._radiusTop

    @radiusTop.setter
    def radiusTop(self, value: float):
        if value < 0:
            raise ValueError(f"radiusTop must be non-negative, got {value}")
        old = self._radiusTop
        self._radiusTop = value
        self._notify("radiusTop", old, self._radiusTop)

    @property
    def radiusBottom(self) -> float:
        """Radius of the cylinder at the bottom."""
        return self._radiusBottom

    @radiusBottom.setter
    def radiusBottom(self, value: float):
        if value < 0:
            raise ValueError(f"radiusBottom must be non-negative, got {value}")
        old = self._radiusBottom
        self._radiusBottom = value
        self._notify("radiusBottom", old, self._radiusBottom)

    @property
    def height(self) -> float:
        """Height of the cylinder."""
        return self._height

    @height.setter
    def height(self, value: float):
        old = self._height
        self._height = _validate_positive(value, "height")
        self._notify("height", old, self._height)

    @property
    def radialSegments(self) -> int:
        """Number of segmented faces around the circumference (minimum 3)."""
        return self._radialSegments

    @radialSegments.setter
    def radialSegments(self, value: int):
        old = self._radialSegments
        self._radialSegments = _validate_min_int(value, 3, "radialSegments")
        self._notify("radialSegments", old, self._radialSegments)

    @property
    def heightSegments(self) -> int:
        """Number of rows of faces along the height."""
        return self._heightSegments

    @heightSegments.setter
    def heightSegments(self, value: int):
        old = self._heightSegments
        self._heightSegments = _validate_min_int(value, 1, "heightSegments")
        self._notify("heightSegments", old, self._heightSegments)

    @property
    def openEnded(self) -> bool:
        """Whether the ends of the cylinder are open or capped."""
        return self._openEnded

    @openEnded.setter
    def openEnded(self, value: bool):
        old = self._openEnded
        self._openEnded = bool(value)
        self._notify("openEnded", old, self._openEnded)

    @property
    def thetaStart(self) -> float:
        """Starting angle for the first segment."""
        return self._thetaStart

    @thetaStart.setter
    def thetaStart(self, value: float):
        old = self._thetaStart
        self._thetaStart = value
        self._notify("thetaStart", old, self._thetaStart)

    @property
    def thetaLength(self) -> float:
        """Central angle of the circular sector."""
        return self._thetaLength

    @thetaLength.setter
    def thetaLength(self, value: float):
        old = self._thetaLength
        self._thetaLength = value
        self._notify("thetaLength", old, self._thetaLength)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "radiusTop": self._radiusTop,
            "radiusBottom": self._radiusBottom,
            "height": self._height,
            "radialSegments": self._radialSegments,
            "heightSegments": self._heightSegments,
            "openEnded": self._openEnded,
            "thetaStart": self._thetaStart,
            "thetaLength": self._thetaLength,
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
        super().__init__(**kwargs)
        self._radius = _validate_positive(radius, "radius")
        self._tube = _validate_positive(tube, "tube")
        self._radialSegments = _validate_min_int(radialSegments, 2, "radialSegments")
        self._tubularSegments = _validate_min_int(tubularSegments, 3, "tubularSegments")
        self._arc = arc

    @property
    def radius(self) -> float:
        """Radius from the center of the torus to the center of the tube."""
        return self._radius

    @radius.setter
    def radius(self, value: float):
        old = self._radius
        self._radius = _validate_positive(value, "radius")
        self._notify("radius", old, self._radius)

    @property
    def tube(self) -> float:
        """Radius of the tube."""
        return self._tube

    @tube.setter
    def tube(self, value: float):
        old = self._tube
        self._tube = _validate_positive(value, "tube")
        self._notify("tube", old, self._tube)

    @property
    def radialSegments(self) -> int:
        """Number of segments in the radial direction (minimum 2)."""
        return self._radialSegments

    @radialSegments.setter
    def radialSegments(self, value: int):
        old = self._radialSegments
        self._radialSegments = _validate_min_int(value, 2, "radialSegments")
        self._notify("radialSegments", old, self._radialSegments)

    @property
    def tubularSegments(self) -> int:
        """Number of segments in the tubular direction (minimum 3)."""
        return self._tubularSegments

    @tubularSegments.setter
    def tubularSegments(self, value: int):
        old = self._tubularSegments
        self._tubularSegments = _validate_min_int(value, 3, "tubularSegments")
        self._notify("tubularSegments", old, self._tubularSegments)

    @property
    def arc(self) -> float:
        """Central angle (arc length in radians)."""
        return self._arc

    @arc.setter
    def arc(self, value: float):
        old = self._arc
        self._arc = value
        self._notify("arc", old, self._arc)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "radius": self._radius,
            "tube": self._tube,
            "radialSegments": self._radialSegments,
            "tubularSegments": self._tubularSegments,
            "arc": self._arc,
        }


class EdgesGeometry(ThreeJSBase):
    """Geometry that extracts edges from another geometry."""

    _type = "EdgesGeometry"

    def __init__(self, geometry=None, thresholdAngle: float = 1, **kwargs):
        super().__init__(**kwargs)
        self._geometry = geometry
        if thresholdAngle < 0:
            raise ValueError(
                f"thresholdAngle must be non-negative, got {thresholdAngle}"
            )
        self._thresholdAngle = thresholdAngle

    @property
    def geometry(self):
        """The source geometry to extract edges from."""
        return self._geometry

    @geometry.setter
    def geometry(self, value):
        old = self._geometry
        self._geometry = value
        self._notify("geometry", old, value)

    @property
    def thresholdAngle(self) -> float:
        """Angle threshold for edge detection (in degrees)."""
        return self._thresholdAngle

    @thresholdAngle.setter
    def thresholdAngle(self, value: float):
        if value < 0:
            raise ValueError(f"thresholdAngle must be non-negative, got {value}")
        old = self._thresholdAngle
        self._thresholdAngle = value
        self._notify("thresholdAngle", old, self._thresholdAngle)

    def _owned_objects(self) -> Iterator[ThreeJSBase]:
        if isinstance(self._geometry, ThreeJSBase):
            yield self._geometry

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        data = {
            "type": self._type,
            "uuid": self._uuid,
            "thresholdAngle": self._thresholdAngle,
        }
        if self._geometry:
            if flat:
                data["geometry"] = self._geometry.uuid
            else:
                data["geometry"] = self._geometry.to_dict(buffer_manager=buffer_manager)
        return data


class LineGeometry(ThreeJSBase):
    """Geometry for fat lines (Line2) with positions and optional colors."""

    _type = "LineGeometry"

    def __init__(self, positions=None, colors=None, **kwargs):
        super().__init__(**kwargs)
        self._positions = positions
        self._colors = colors

    @property
    def positions(self):
        """Array of positions for the line vertices."""
        return self._positions

    @positions.setter
    def positions(self, value):
        old = self._positions
        self._positions = value
        self._notify("positions", old, value)

    @property
    def colors(self):
        """Array of colors for the line vertices."""
        return self._colors

    @colors.setter
    def colors(self, value):
        old = self._colors
        self._colors = value
        self._notify("colors", old, value)

    @staticmethod
    def _serialize_array(value, flat):
        if flat:
            return binary_wrapper(value, dtype="float32")
        if hasattr(value, "tolist"):
            return value.tolist()
        return value

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        data = {
            "type": self._type,
            "uuid": self._uuid,
        }
        if self._positions is not None:
            data["positions"] = self._serialize_array(self._positions, flat)
        if self._colors is not None:
            data["colors"] = self._serialize_array(self._colors, flat)
        return data
