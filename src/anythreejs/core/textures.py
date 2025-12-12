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


class DataTexture(ThreeJSBase):
    """Texture created from raw data array."""

    _type = "DataTexture"

    def __init__(
        self,
        data=None,
        width: int = None,
        height: int = None,
        format: str = "RGBAFormat",
        type: str = "UnsignedByteType",
        mapping: str = None,
        wrapS: str = "ClampToEdgeWrapping",
        wrapT: str = "ClampToEdgeWrapping",
        magFilter: str = "LinearFilter",
        minFilter: str = "LinearFilter",
        **kwargs,
    ):
        super().__init__()
        self._data = data
        self._width = width
        self._height = height
        self._format = format
        self._dtype = type  # 'type' is reserved in Python
        self._mapping = mapping
        self._wrapS = wrapS
        self._wrapT = wrapT
        self._magFilter = magFilter
        self._minFilter = minFilter

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        old = self._data
        self._data = value
        self._notify("data", old, value)

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, value: int):
        old = self._width
        self._width = value
        self._notify("width", old, value)

    @property
    def height(self) -> int:
        return self._height

    @height.setter
    def height(self, value: int):
        old = self._height
        self._height = value
        self._notify("height", old, value)

    def to_dict(self) -> dict[str, Any]:
        import numpy as np

        result = {
            "type": self._type,
            "uuid": self._uuid,
            "format": self._format,
            "dtype": self._dtype,
            "wrapS": self._wrapS,
            "wrapT": self._wrapT,
            "magFilter": self._magFilter,
            "minFilter": self._minFilter,
        }

        width = self._width
        height = self._height

        if self._data is not None:
            d = self._data
            # Convert to numpy array to get shape info
            if not isinstance(d, np.ndarray):
                d = np.array(d)

            # Infer width/height from shape if not provided
            # Expected shape is (height, width) or (height, width, channels)
            if width is None and height is None and len(d.shape) >= 2:
                height = d.shape[0]
                width = d.shape[1]

            # Flatten for serialization
            result["data"] = d.flatten().tolist()

        if width is not None:
            result["width"] = int(width)
        if height is not None:
            result["height"] = int(height)
        if self._mapping is not None:
            result["mapping"] = self._mapping
        return result
