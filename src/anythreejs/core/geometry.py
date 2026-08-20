"""
Geometry classes for Three.js primitives.

Parametric geometries (box, sphere, plane, cylinder, torus) are generated
from the declarative catalog in ``spec.py``. BufferGeometry, EdgesGeometry
and LineGeometry carry custom behavior (attribute change tracking,
source-geometry references, raw arrays) and stay hand-written.
"""

from functools import partial
from typing import Any, Iterator, Optional

from .base import ThreeJSBase
from .buffer import binary_wrapper
from .spec import make_class

__all__ = [
    "BufferGeometry",
    "BoxGeometry",
    "BoxBufferGeometry",
    "SphereGeometry",
    "SphereBufferGeometry",
    "PlaneGeometry",
    "PlaneBufferGeometry",
    "CylinderGeometry",
    "CylinderBufferGeometry",
    "CircleGeometry",
    "TorusGeometry",
    "EdgesGeometry",
    "LineGeometry",
]


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


BoxGeometry = make_class("BoxGeometry", ThreeJSBase)
SphereGeometry = make_class("SphereGeometry", ThreeJSBase)
PlaneGeometry = make_class("PlaneGeometry", ThreeJSBase)
CylinderGeometry = make_class("CylinderGeometry", ThreeJSBase)
CircleGeometry = make_class("CircleGeometry", ThreeJSBase)
TorusGeometry = make_class("TorusGeometry", ThreeJSBase)

# Aliases for pythreejs compatibility
BoxBufferGeometry = BoxGeometry
SphereBufferGeometry = SphereGeometry
PlaneBufferGeometry = PlaneGeometry
CylinderBufferGeometry = CylinderGeometry


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
