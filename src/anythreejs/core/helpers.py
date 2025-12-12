"""
Helper objects for visualization (axes, grids).
"""

from typing import Any
from .base import Object3D


class AxesHelper(Object3D):
    """Helper to visualize the coordinate axes."""

    _type = "AxesHelper"

    def __init__(self, size: float = 1, **kwargs):
        super().__init__(**kwargs)
        self._size = size

    @property
    def size(self) -> float:
        return self._size

    @size.setter
    def size(self, value: float):
        old = self._size
        self._size = value
        self._notify("size", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["size"] = self._size
        return data


class GridHelper(Object3D):
    """Helper to visualize a grid."""

    _type = "GridHelper"

    def __init__(
        self,
        size: float = 10,
        divisions: int = 10,
        colorCenterLine: str = "#444444",
        colorGrid: str = "#888888",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._size = size
        self._divisions = divisions
        self._colorCenterLine = colorCenterLine
        self._colorGrid = colorGrid

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "size": self._size,
                "divisions": self._divisions,
                "colorCenterLine": self._colorCenterLine,
                "colorGrid": self._colorGrid,
            }
        )
        return data
