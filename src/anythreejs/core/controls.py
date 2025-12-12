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
