"""
Texture classes.
"""

from typing import Any
from .base import ThreeJSBase


class TextTexture(ThreeJSBase):
    """Texture containing rendered text."""

    _type = "TextTexture"

    def __init__(
        self,
        string: str = "",
        color: str = "white",
        size: int = 100,
        fontFace: str = "Arial",
        **kwargs,
    ):
        super().__init__()
        self._string = string
        self._color = color
        self._size = size
        self._fontFace = fontFace

    @property
    def string(self) -> str:
        return self._string

    @string.setter
    def string(self, value: str):
        old = self._string
        self._string = value
        self._notify("string", old, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "string": self._string,
            "color": self._color,
            "size": self._size,
            "fontFace": self._fontFace,
        }
