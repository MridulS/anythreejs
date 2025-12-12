"""
Camera controls for interactive manipulation.
"""

from typing import Any
from .base import ThreeJSBase


class OrbitControls(ThreeJSBase):
    """Orbit controls for camera manipulation."""

    _type = "OrbitControls"

    def __init__(
        self,
        controlling=None,
        target: tuple = (0, 0, 0),
        enableDamping: bool = True,
        dampingFactor: float = 0.05,
        enableZoom: bool = True,
        enableRotate: bool = True,
        enablePan: bool = True,
        autoRotate: bool = False,
        autoRotateSpeed: float = 2.0,
        **kwargs,
    ):
        super().__init__()
        self._controlling = controlling
        self._target = list(target)
        self._enableDamping = enableDamping
        self._dampingFactor = dampingFactor
        self._enableZoom = enableZoom
        self._enableRotate = enableRotate
        self._enablePan = enablePan
        self._autoRotate = autoRotate
        self._autoRotateSpeed = autoRotateSpeed

    @property
    def controlling(self):
        return self._controlling

    @controlling.setter
    def controlling(self, value):
        old = self._controlling
        self._controlling = value
        self._notify("controlling", old, value)

    @property
    def target(self) -> tuple:
        return tuple(self._target)

    @target.setter
    def target(self, value):
        old = self._target
        self._target = list(value)
        self._notify("target", old, self._target)

    @property
    def enableDamping(self) -> bool:
        return self._enableDamping

    @enableDamping.setter
    def enableDamping(self, value: bool):
        old = self._enableDamping
        self._enableDamping = value
        self._notify("enableDamping", old, value)

    @property
    def enableZoom(self) -> bool:
        return self._enableZoom

    @enableZoom.setter
    def enableZoom(self, value: bool):
        old = self._enableZoom
        self._enableZoom = value
        self._notify("enableZoom", old, value)

    @property
    def autoRotate(self) -> bool:
        return self._autoRotate

    @autoRotate.setter
    def autoRotate(self, value: bool):
        old = self._autoRotate
        self._autoRotate = value
        self._notify("autoRotate", old, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "target": self._target,
            "enableDamping": self._enableDamping,
            "dampingFactor": self._dampingFactor,
            "enableZoom": self._enableZoom,
            "enableRotate": self._enableRotate,
            "enablePan": self._enablePan,
            "autoRotate": self._autoRotate,
            "autoRotateSpeed": self._autoRotateSpeed,
        }


class TrackballControls(ThreeJSBase):
    """Trackball controls for camera manipulation."""

    _type = "TrackballControls"

    def __init__(self, controlling=None, target: tuple = (0, 0, 0), **kwargs):
        super().__init__()
        self._controlling = controlling
        self._target = list(target)

    @property
    def controlling(self):
        return self._controlling

    @controlling.setter
    def controlling(self, value):
        self._controlling = value

    @property
    def target(self) -> tuple:
        return tuple(self._target)

    @target.setter
    def target(self, value):
        old = self._target
        self._target = list(value)
        self._notify("target", old, self._target)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self._type, "target": self._target}


class Picker(ThreeJSBase):
    """
    Picker control for detecting mouse interactions with 3D objects.

    This control allows you to get information about objects and surface
    coordinates underneath the mouse cursor through raycasting.
    """

    _type = "Picker"

    def __init__(
        self,
        controlling=None,
        event: str = "click",
        lineThreshold: float = 1.0,
        pointThreshold: float = 1.0,
        all: bool = False,
        **kwargs,
    ):
        """
        Initialize a Picker control.

        Args:
            controlling: The object to perform picking on (typically a mesh or group)
            event: The DOM MouseEvent type to trigger the pick (e.g., 'click', 'dblclick', 'mousemove')
            lineThreshold: The threshold value for line picking
            pointThreshold: The threshold value for point picking
            all: Whether to send info on all object intersections or only the first one
        """
        super().__init__()
        self._controlling = controlling
        self._event = event
        self._lineThreshold = lineThreshold
        self._pointThreshold = pointThreshold
        self._all = all
        # Picker output properties (read-only, updated by raycasting)
        self._point = [0, 0, 0]
        self._distance = None
        self._face = [0, 0, 0]
        self._faceNormal = [0, 0, 0]
        self._faceIndex = None
        self._object = None
        self._uv = [0, 0]
        self._modifiers = None
        self._picked = []

    @property
    def controlling(self):
        return self._controlling

    @controlling.setter
    def controlling(self, value):
        old = self._controlling
        self._controlling = value
        self._notify("controlling", old, value)

    @property
    def event(self) -> str:
        return self._event

    @event.setter
    def event(self, value: str):
        old = self._event
        self._event = value
        self._notify("event", old, value)

    @property
    def lineThreshold(self) -> float:
        return self._lineThreshold

    @lineThreshold.setter
    def lineThreshold(self, value: float):
        old = self._lineThreshold
        self._lineThreshold = value
        self._notify("lineThreshold", old, value)

    @property
    def pointThreshold(self) -> float:
        return self._pointThreshold

    @pointThreshold.setter
    def pointThreshold(self, value: float):
        old = self._pointThreshold
        self._pointThreshold = value
        self._notify("pointThreshold", old, value)

    @property
    def all(self) -> bool:
        return self._all

    @all.setter
    def all(self, value: bool):
        old = self._all
        self._all = value
        self._notify("all", old, value)

    # Read-only properties (updated by raycasting)
    @property
    def point(self) -> tuple:
        """The coordinates of the picked point (all zero if no object picked)."""
        return tuple(self._point)

    @property
    def distance(self) -> float | None:
        """The distance from the camera of the picked point (None if no object picked)."""
        return self._distance

    @property
    def face(self) -> tuple:
        """The vertex indices of the picked face (all zero if no face picked)."""
        return tuple(self._face)

    @property
    def faceNormal(self) -> tuple:
        """The normal vector of the picked face (all zero if no face picked)."""
        return tuple(self._faceNormal)

    @property
    def faceIndex(self) -> int | None:
        """The index of the face picked (None if no face picked)."""
        return self._faceIndex

    @property
    def object(self):
        """The picked object (None if no object picked)."""
        return self._object

    @property
    def uv(self) -> tuple:
        """The UV coordinate picked (all zero if invalid pick)."""
        return tuple(self._uv)

    @property
    def modifiers(self) -> list | None:
        """The keyboard modifiers held at the pick event [SHIFT, CTRL, ALT, META]."""
        return self._modifiers

    @property
    def picked(self) -> list:
        """Array containing info for all intersections (if 'all' is True)."""
        return self._picked

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "event": self._event,
            "lineThreshold": self._lineThreshold,
            "pointThreshold": self._pointThreshold,
            "all": self._all,
            "point": self._point,
            "distance": self._distance,
            "face": self._face,
            "faceNormal": self._faceNormal,
            "faceIndex": self._faceIndex,
            "uv": self._uv,
        }
