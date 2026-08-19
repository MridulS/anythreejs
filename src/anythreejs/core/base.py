"""
Base classes for Three.js objects with observable properties.

All Three.js objects inherit from these base classes which provide:
- Property change observation (like ipywidgets traitlets)
- Attachment to one or more Renderer widgets, which receive fine-grained
  change events and translate them into delta ops sent to JavaScript
- Serialization to dict for JSON transport (nested form for the snapshot
  produced with ``flat=False``, normalized uuid-referencing form with
  ``flat=True``)
- UUID for object identification across the Python/JS boundary
"""

from contextlib import contextmanager
from typing import Any, Callable, Iterator
import uuid
import warnings


class ThreeJSBase:
    """
    Base class for all Three.js object representations.

    Provides observable properties, renderer attachment, and serialization.
    """

    _type: str = "Object3D"

    def __init__(self, **kwargs):
        self._uuid = str(uuid.uuid4())
        self._observers: dict[str, list[Callable]] = {}
        self._renderers: set = set()
        self._hold_depth = 0
        self._pending_notifications: list[tuple[str, Any, Any]] = []
        self._batched_renderers: set = set()
        if kwargs:
            warnings.warn(
                f"{type(self).__name__}: ignoring unsupported arguments "
                f"{sorted(kwargs)}",
                stacklevel=3,
            )

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

    def unobserve_all(self, names: list[str] | str = None):
        """Unregister all observers, optionally for specific names only."""
        if names is None:
            self._observers.clear()
        else:
            if isinstance(names, str):
                names = [names]
            for name in names:
                if name in self._observers:
                    self._observers[name].clear()

    @contextmanager
    def hold_trait_notifications(self):
        """Context manager to hold notifications until exit, then batch them.

        Re-entrant: only the outermost context releases the held
        notifications. Attached renderers batch all resulting ops into a
        single message.
        """
        self._hold_depth += 1
        if self._hold_depth == 1:
            self._batched_renderers = set(self._renderers)
            for renderer in self._batched_renderers:
                renderer._begin_batch()
        try:
            yield
        finally:
            self._hold_depth -= 1
            if self._hold_depth == 0:
                pending = self._pending_notifications
                self._pending_notifications = []
                batched = self._batched_renderers
                self._batched_renderers = set()
                try:
                    for name, old, new in pending:
                        self._dispatch(name, old, new)
                finally:
                    for renderer in batched:
                        renderer._end_batch()

    def _notify(self, name: str, old: Any, new: Any):
        """Notify observers and attached renderers of a property change."""
        if self._hold_depth > 0:
            self._pending_notifications.append((name, old, new))
            return
        self._dispatch(name, old, new)

    def _dispatch(self, name: str, old: Any, new: Any):
        change = {"name": name, "old": old, "new": new, "owner": self}
        for handler in list(self._observers.get(name, [])):
            handler(change)
        for handler in list(self._observers.get("_all", [])):
            handler(change)
        for renderer in tuple(self._renderers):
            renderer._on_object_change(self, name, old, new)

    def _owned_objects(self) -> Iterator["ThreeJSBase"]:
        """Yield directly referenced ThreeJSBase objects (children, geometry,
        material, textures...). Used for renderer attachment, dependency
        ordering of create ops, and reachability GC."""
        return iter(())

    def _attach_renderer(self, renderer):
        """Attach a renderer to this object and everything it references."""
        if renderer in self._renderers:
            return
        self._renderers.add(renderer)
        renderer._register_object(self)
        for obj in self._owned_objects():
            obj._attach_renderer(renderer)

    def _detach_renderer(self, renderer):
        """Detach a renderer from this object only (non-recursive — shared
        subgraphs make recursive detach unsafe; the renderer's reachability
        GC is the authority for detaching entire subtrees)."""
        self._renderers.discard(renderer)
        renderer._unregister_object(self)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        """
        Serialize to dictionary for JSON transport.

        Args:
            buffer_manager: Unused, kept for backwards compatibility.
            flat: When True, referenced objects are serialized as uuid
                strings and array data as binary wrappers, for the
                normalized snapshot / delta protocol.
        """
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
        super().__init__(**kwargs)
        self._position = list(position)
        self._rotation = self._coerce_rotation(rotation)
        self._scale = list(scale)
        self._visible = visible
        self._name = name
        self._children: list["Object3D"] = []

    @staticmethod
    def _coerce_rotation(value) -> list:
        """Accept (x, y, z) or the pythreejs-style (x, y, z, order)."""
        value_list = list(value)
        if len(value_list) == 4 and isinstance(value_list[3], str):
            return value_list
        if len(value_list) != 3:
            raise ValueError(
                f"rotation must have 3 elements (x, y, z) or 4 elements "
                f"(x, y, z, order), got {len(value_list)}"
            )
        return value_list

    @property
    def position(self) -> tuple:
        return tuple(self._position)

    @position.setter
    def position(self, value):
        value_list = list(value)
        if len(value_list) != 3:
            raise ValueError(
                f"position must have exactly 3 elements, got {len(value_list)}"
            )
        if value_list == self._position:
            return
        old = self._position
        self._position = value_list
        self._notify("position", old, self._position)

    @property
    def rotation(self) -> tuple:
        return tuple(self._rotation)

    @rotation.setter
    def rotation(self, value):
        coerced = self._coerce_rotation(value)
        if coerced == self._rotation:
            return
        old = self._rotation
        self._rotation = coerced
        self._notify("rotation", old, self._rotation)

    @property
    def scale(self) -> tuple:
        return tuple(self._scale)

    @scale.setter
    def scale(self, value):
        value_list = list(value)
        if len(value_list) != 3:
            raise ValueError(
                f"scale must have exactly 3 elements, got {len(value_list)}"
            )
        if value_list == self._scale:
            return
        old = self._scale
        self._scale = value_list
        self._notify("scale", old, self._scale)

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        if value == self._visible:
            return
        old = self._visible
        self._visible = value
        self._notify("visible", old, value)

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str):
        if value == self._name:
            return
        old = self._name
        self._name = value
        self._notify("name", old, value)

    def rotateX(self, angle: float) -> "Object3D":
        """Rotate around X axis by angle (radians)."""
        old = self._rotation.copy()
        self._rotation[0] += angle
        self._notify("rotation", old, self._rotation)
        return self

    def rotateY(self, angle: float) -> "Object3D":
        """Rotate around Y axis by angle (radians)."""
        old = self._rotation.copy()
        self._rotation[1] += angle
        self._notify("rotation", old, self._rotation)
        return self

    def rotateZ(self, angle: float) -> "Object3D":
        """Rotate around Z axis by angle (radians)."""
        old = self._rotation.copy()
        self._rotation[2] += angle
        self._notify("rotation", old, self._rotation)
        return self

    @property
    def children(self) -> list:
        # A copy: in-place mutation would bypass renderer attachment and
        # delta emission. Use add()/remove().
        return list(self._children)

    def _flatten(self, objects) -> list["Object3D"]:
        flat = []
        for obj in objects:
            if isinstance(obj, (list, tuple)):
                flat.extend(self._flatten(obj))
            else:
                flat.append(obj)
        return flat

    def add(self, *objects: "Object3D"):
        """Add child objects. Handles both individual objects and lists."""
        added = []
        for obj in self._flatten(objects):
            if obj not in self._children:
                self._children.append(obj)
                added.append(obj)
        if added:
            for renderer in tuple(self._renderers):
                renderer._on_children_added(self, added)
            self._notify("children", None, self._children)

    def remove(self, *objects: "Object3D"):
        """Remove child objects. Handles both individual objects and lists."""
        removed = []
        for obj in self._flatten(objects):
            if obj in self._children:
                self._children.remove(obj)
                removed.append(obj)
        if removed:
            for renderer in tuple(self._renderers):
                renderer._on_children_removed(self, removed)
            self._notify("children", None, self._children)

    def _owned_objects(self) -> Iterator[ThreeJSBase]:
        return iter(self._children)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        data = super().to_dict(buffer_manager=buffer_manager, flat=flat)
        data.update(
            {
                "position": list(self._position),
                "rotation": list(self._rotation[:3]),
                "scale": list(self._scale),
                "visible": self._visible,
                "name": self._name,
            }
        )
        if len(self._rotation) == 4:
            data["rotationOrder"] = self._rotation[3]
        if self._children:
            if flat:
                data["children"] = [child.uuid for child in self._children]
            else:
                data["children"] = [
                    child.to_dict(buffer_manager=buffer_manager)
                    for child in self._children
                ]
        return data
