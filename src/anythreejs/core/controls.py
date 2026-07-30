"""
Camera controls for interactive manipulation.
"""

from typing import Any
from .base import ThreeJSBase


def _controlling_ref(controlling):
    if controlling is None:
        return None
    return controlling.uuid if hasattr(controlling, "uuid") else controlling


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
        screenSpacePanning: bool = True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._controlling = controlling
        self._target = list(target)
        self._enableDamping = enableDamping
        self._dampingFactor = dampingFactor
        self._enableZoom = enableZoom
        self._enableRotate = enableRotate
        self._enablePan = enablePan
        self._autoRotate = autoRotate
        self._autoRotateSpeed = autoRotateSpeed
        self._screenSpacePanning = screenSpacePanning

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
    def dampingFactor(self) -> float:
        return self._dampingFactor

    @dampingFactor.setter
    def dampingFactor(self, value: float):
        old = self._dampingFactor
        self._dampingFactor = value
        self._notify("dampingFactor", old, value)

    @property
    def enableZoom(self) -> bool:
        return self._enableZoom

    @enableZoom.setter
    def enableZoom(self, value: bool):
        old = self._enableZoom
        self._enableZoom = value
        self._notify("enableZoom", old, value)

    @property
    def enableRotate(self) -> bool:
        return self._enableRotate

    @enableRotate.setter
    def enableRotate(self, value: bool):
        old = self._enableRotate
        self._enableRotate = value
        self._notify("enableRotate", old, value)

    @property
    def enablePan(self) -> bool:
        return self._enablePan

    @enablePan.setter
    def enablePan(self, value: bool):
        old = self._enablePan
        self._enablePan = value
        self._notify("enablePan", old, value)

    @property
    def autoRotate(self) -> bool:
        return self._autoRotate

    @autoRotate.setter
    def autoRotate(self, value: bool):
        old = self._autoRotate
        self._autoRotate = value
        self._notify("autoRotate", old, value)

    @property
    def autoRotateSpeed(self) -> float:
        return self._autoRotateSpeed

    @autoRotateSpeed.setter
    def autoRotateSpeed(self, value: float):
        old = self._autoRotateSpeed
        self._autoRotateSpeed = value
        self._notify("autoRotateSpeed", old, value)

    @property
    def screenSpacePanning(self) -> bool:
        return self._screenSpacePanning

    @screenSpacePanning.setter
    def screenSpacePanning(self, value: bool):
        old = self._screenSpacePanning
        self._screenSpacePanning = value
        self._notify("screenSpacePanning", old, value)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        data = {
            "type": self._type,
            "uuid": self._uuid,
            "target": list(self._target),
            "enableDamping": self._enableDamping,
            "dampingFactor": self._dampingFactor,
            "enableZoom": self._enableZoom,
            "enableRotate": self._enableRotate,
            "enablePan": self._enablePan,
            "autoRotate": self._autoRotate,
            "autoRotateSpeed": self._autoRotateSpeed,
            "screenSpacePanning": self._screenSpacePanning,
        }
        if self._controlling is not None:
            data["controlling"] = _controlling_ref(self._controlling)
        return data


class TrackballControls(ThreeJSBase):
    """Trackball controls for camera manipulation."""

    _type = "TrackballControls"

    def __init__(self, controlling=None, target: tuple = (0, 0, 0), **kwargs):
        super().__init__(**kwargs)
        self._controlling = controlling
        self._target = list(target)

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

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        data = {
            "type": self._type,
            "uuid": self._uuid,
            "target": list(self._target),
        }
        if self._controlling is not None:
            data["controlling"] = _controlling_ref(self._controlling)
        return data


class Picker(ThreeJSBase):
    """Picker for raycasting and mouse interaction with 3D objects."""

    _type = "Picker"

    def __init__(
        self,
        controlling=None,
        event: str = "click",
        all: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._controlling = controlling
        self._event = event
        self._all = all
        self._point: tuple | None = None
        self._face: tuple | None = None
        self._faceNormal: tuple | None = None
        self._faceIndex: int | None = None
        self._object: Any | None = None
        self._distance: float | None = None
        self._modifiers: list[str] = []

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
    def all(self) -> bool:
        return self._all

    @all.setter
    def all(self, value: bool):
        old = self._all
        self._all = value
        self._notify("all", old, value)

    @property
    def point(self) -> tuple | None:
        return self._point

    @point.setter
    def point(self, value):
        old = self._point
        self._point = tuple(value) if value is not None else None
        self._notify("point", old, self._point)

    @property
    def face(self) -> tuple | None:
        return self._face

    @face.setter
    def face(self, value):
        old = self._face
        self._face = tuple(value) if value is not None else None
        self._notify("face", old, self._face)

    @property
    def faceNormal(self) -> tuple | None:
        return self._faceNormal

    @faceNormal.setter
    def faceNormal(self, value):
        old = self._faceNormal
        self._faceNormal = tuple(value) if value is not None else None
        self._notify("faceNormal", old, self._faceNormal)

    @property
    def faceIndex(self) -> int | None:
        return self._faceIndex

    @faceIndex.setter
    def faceIndex(self, value: int | None):
        old = self._faceIndex
        self._faceIndex = value
        self._notify("faceIndex", old, value)

    @property
    def object(self):
        return self._object

    @object.setter
    def object(self, value):
        old = self._object
        self._object = value
        self._notify("object", old, value)

    @property
    def distance(self) -> float | None:
        return self._distance

    @distance.setter
    def distance(self, value: float | None):
        old = self._distance
        self._distance = value
        self._notify("distance", old, value)

    @property
    def modifiers(self) -> list[str]:
        return self._modifiers

    @modifiers.setter
    def modifiers(self, value: list[str]):
        old = self._modifiers
        self._modifiers = list(value)
        self._notify("modifiers", old, self._modifiers)

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        result = {
            "type": self._type,
            "uuid": self._uuid,
            "event": self._event,
            "all": self._all,
        }
        if self._controlling is not None:
            result["controlling"] = _controlling_ref(self._controlling)
        return result
