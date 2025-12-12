"""
Base classes for Three.js objects with observable properties.

All Three.js objects inherit from these base classes which provide:
- Property change observation (like ipywidgets traitlets)
- Serialization to dict for JSON transport to JavaScript
- UUID for object identification
"""

from typing import Any, Callable, Optional
import uuid


class ThreeJSBase:
    """
    Base class for all Three.js object representations.

    Provides observable properties and serialization.
    """

    _type: str = "Object3D"

    def __init__(self):
        self._uuid = str(uuid.uuid4())
        self._observers: dict[str, list[Callable]] = {}
        self._parent_renderer: Optional[Any] = None

    @property
    def uuid(self) -> str:
        return self._uuid

    def observe(self, handler: Callable, names: list[str] | str = None):
        """Register an observer for property changes."""
        if isinstance(names, str):
            names = [names]
        if names is None:
            names = ["_all"]
        for name in names:
            if name not in self._observers:
                self._observers[name] = []
            self._observers[name].append(handler)

    def unobserve(self, handler: Callable, names: list[str] | str = None):
        """Unregister an observer."""
        if isinstance(names, str):
            names = [names]
        if names is None:
            names = list(self._observers.keys())
        for name in names:
            if name in self._observers and handler in self._observers[name]:
                self._observers[name].remove(handler)

    def _notify(self, name: str, old: Any, new: Any):
        """Notify observers of a property change."""
        change = {"name": name, "old": old, "new": new, "owner": self}

        for handler in self._observers.get(name, []):
            handler(change)
        for handler in self._observers.get("_all", []):
            handler(change)

        if self._parent_renderer is not None:
            self._parent_renderer._request_render()

    def _set_renderer(self, renderer):
        """Set the parent renderer for sync."""
        self._parent_renderer = renderer

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON transport."""
        return {"type": self._type, "uuid": self._uuid}


class Object3D(ThreeJSBase):
    """
    Base class for all 3D objects with transform properties.
    """

    _type = "Object3D"

    def __init__(
        self,
        position: tuple | list = (0, 0, 0),
        rotation: tuple | list = (0, 0, 0),
        scale: tuple | list = (1, 1, 1),
        visible: bool = True,
        name: str = "",
        **kwargs,
    ):
        super().__init__()
        self._position = list(position)
        self._rotation = list(rotation)
        self._scale = list(scale)
        self._visible = visible
        self._name = name
        self._children: list["Object3D"] = []

    @property
    def position(self) -> tuple:
        return tuple(self._position)

    @position.setter
    def position(self, value):
        old = self._position
        self._position = list(value)
        self._notify("position", old, self._position)

    @property
    def rotation(self) -> list:
        return self._rotation

    @rotation.setter
    def rotation(self, value):
        old = self._rotation
        self._rotation = list(value)
        self._notify("rotation", old, self._rotation)

    @property
    def scale(self) -> list:
        return self._scale

    @scale.setter
    def scale(self, value):
        old = self._scale
        self._scale = list(value)
        self._notify("scale", old, self._scale)

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        old = self._visible
        self._visible = value
        self._notify("visible", old, value)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        old = self._name
        self._name = value
        self._notify("name", old, value)

    def rotateX(self, angle: float) -> "Object3D":
        """Rotate around X axis by angle (radians)."""
        self._rotation[0] += angle
        self._notify("rotation", None, self._rotation)
        return self

    def rotateY(self, angle: float) -> "Object3D":
        """Rotate around Y axis by angle (radians)."""
        self._rotation[1] += angle
        self._notify("rotation", None, self._rotation)
        return self

    def rotateZ(self, angle: float) -> "Object3D":
        """Rotate around Z axis by angle (radians)."""
        self._rotation[2] += angle
        self._notify("rotation", None, self._rotation)
        return self

    @property
    def children(self) -> list:
        return self._children

    def add(self, *objects: "Object3D"):
        """Add child objects. Handles both individual objects and lists."""
        for obj in objects:
            if isinstance(obj, (list, tuple)):
                self.add(*obj)
            elif obj not in self._children:
                self._children.append(obj)
                if self._parent_renderer:
                    obj._set_renderer(self._parent_renderer)
        self._notify("children", None, self._children)

    def remove(self, *objects: "Object3D"):
        """Remove child objects. Handles both individual objects and lists."""
        for obj in objects:
            if isinstance(obj, (list, tuple)):
                self.remove(*obj)
            elif obj in self._children:
                self._children.remove(obj)
                obj._set_renderer(None)
        self._notify("children", None, self._children)

    def _set_renderer(self, renderer):
        """Recursively set renderer on self and children."""
        super()._set_renderer(renderer)
        for child in self._children:
            child._set_renderer(renderer)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "position": self._position,
                "rotation": self._rotation,
                "scale": self._scale,
                "visible": self._visible,
                "name": self._name,
            }
        )
        if self._children:
            data["children"] = [child.to_dict() for child in self._children]
        return data
