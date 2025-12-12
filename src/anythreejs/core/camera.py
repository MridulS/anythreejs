"""
Camera classes for Three.js.
"""

from typing import Any
from .base import Object3D


class PerspectiveCamera(Object3D):
    """Camera with perspective projection."""

    _type = "PerspectiveCamera"

    def __init__(
        self,
        fov: float = 50,
        aspect: float = 1.0,
        near: float = 0.1,
        far: float = 2000,
        position: tuple = (0, 0, 5),
        **kwargs,
    ):
        super().__init__(position=position, **kwargs)
        self._fov = fov
        self._aspect = aspect
        self._near = near
        self._far = far

    @property
    def fov(self) -> float:
        return self._fov

    @fov.setter
    def fov(self, value: float):
        old = self._fov
        self._fov = value
        self._notify("fov", old, value)

    @property
    def aspect(self) -> float:
        return self._aspect

    @aspect.setter
    def aspect(self, value: float):
        old = self._aspect
        self._aspect = value
        self._notify("aspect", old, value)

    @property
    def near(self) -> float:
        return self._near

    @near.setter
    def near(self, value: float):
        old = self._near
        self._near = value
        self._notify("near", old, value)

    @property
    def far(self) -> float:
        return self._far

    @far.setter
    def far(self, value: float):
        old = self._far
        self._far = value
        self._notify("far", old, value)

    def lookAt(self, target):
        """Set the camera to look at a target point."""
        # In Three.js this would update the rotation, but for our use case
        # we just store it for serialization
        if hasattr(target, "__iter__"):
            self._lookAt = list(target)
        else:
            self._lookAt = [target, 0, 0]
        self._notify("lookAt", None, self._lookAt)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "fov": self._fov,
                "aspect": self._aspect,
                "near": self._near,
                "far": self._far,
            }
        )
        if hasattr(self, "_lookAt"):
            data["lookAt"] = self._lookAt
        return data


class OrthographicCamera(Object3D):
    """Camera with orthographic projection."""

    _type = "OrthographicCamera"

    def __init__(
        self,
        left: float = -1,
        right: float = 1,
        top: float = 1,
        bottom: float = -1,
        near: float = 0.1,
        far: float = 2000,
        zoom: float = 1,
        position: tuple = (0, 0, 5),
        **kwargs,
    ):
        super().__init__(position=position, **kwargs)
        self._left = left
        self._right = right
        self._top = top
        self._bottom = bottom
        self._near = near
        self._far = far
        self._zoom = zoom

    @property
    def left(self) -> float:
        return self._left

    @left.setter
    def left(self, value: float):
        old = self._left
        self._left = value
        self._notify("left", old, value)

    @property
    def right(self) -> float:
        return self._right

    @right.setter
    def right(self, value: float):
        old = self._right
        self._right = value
        self._notify("right", old, value)

    @property
    def top(self) -> float:
        return self._top

    @top.setter
    def top(self, value: float):
        old = self._top
        self._top = value
        self._notify("top", old, value)

    @property
    def bottom(self) -> float:
        return self._bottom

    @bottom.setter
    def bottom(self, value: float):
        old = self._bottom
        self._bottom = value
        self._notify("bottom", old, value)

    @property
    def zoom(self) -> float:
        return self._zoom

    @zoom.setter
    def zoom(self, value: float):
        old = self._zoom
        self._zoom = value
        self._notify("zoom", old, value)

    def lookAt(self, target):
        """Set the camera to look at a target point."""
        if hasattr(target, "__iter__"):
            self._lookAt = list(target)
        else:
            self._lookAt = [target, 0, 0]
        self._notify("lookAt", None, self._lookAt)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "left": self._left,
                "right": self._right,
                "top": self._top,
                "bottom": self._bottom,
                "near": self._near,
                "far": self._far,
                "zoom": self._zoom,
            }
        )
        if hasattr(self, "_lookAt"):
            data["lookAt"] = self._lookAt
        return data
