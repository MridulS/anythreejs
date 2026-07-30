"""
Camera controls for interactive manipulation.

OrbitControls and TrackballControls are generated from the declarative
catalog in ``spec.py``. Picker carries JS-fed hit state and stays
hand-written.
"""

from typing import Any

from .base import ThreeJSBase
from .spec import make_class

__all__ = ["OrbitControls", "TrackballControls", "Picker"]

OrbitControls = make_class("OrbitControls", ThreeJSBase)
TrackballControls = make_class("TrackballControls", ThreeJSBase)


def _controlling_ref(controlling):
    if controlling is None:
        return None
    return controlling.uuid if hasattr(controlling, "uuid") else controlling


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
