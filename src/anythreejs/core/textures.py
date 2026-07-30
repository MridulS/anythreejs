"""
Texture classes.

TextTexture is generated from the declarative catalog in ``spec.py``;
DataTexture has custom shape-inference and binary serialization and stays
hand-written.
"""

from typing import Any

import numpy as np

from .base import ThreeJSBase
from .buffer import binary_wrapper
from .spec import make_class

__all__ = ["TextTexture", "DataTexture"]

TextTexture = make_class("TextTexture", ThreeJSBase)


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
        super().__init__(**kwargs)
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

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
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
            if not isinstance(d, np.ndarray):
                d = np.array(d)

            # Infer width/height from shape if not provided.
            # Expected shape is (height, width) or (height, width, channels).
            if width is None and height is None and len(d.shape) >= 2:
                height = d.shape[0]
                width = d.shape[1]

            if flat:
                result["data"] = binary_wrapper(d)
            else:
                result["data"] = d.flatten().tolist()

        if width is not None:
            result["width"] = int(width)
        if height is not None:
            result["height"] = int(height)
        if self._mapping is not None:
            result["mapping"] = self._mapping
        return result
