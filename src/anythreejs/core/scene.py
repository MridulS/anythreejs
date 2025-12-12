"""
Scene class - container for the 3D scene.
"""

from typing import Any, Optional
from .base import Object3D


class Scene(Object3D):
    """Scene holds all objects, lights, and is the root of the scene graph."""

    _type = "Scene"

    def __init__(
        self, children: Optional[list] = None, background: str = "#000000", **kwargs
    ):
        super().__init__(**kwargs)
        self._background = background
        if children:
            for child in children:
                self.add(child)

    @property
    def background(self) -> str:
        return self._background

    @background.setter
    def background(self, value: str):
        old = self._background
        self._background = value
        self._notify("background", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["background"] = self._background
        return data
