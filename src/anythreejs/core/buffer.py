"""
Buffer attribute classes for custom geometry data.
"""

from typing import Any, Optional, Callable, Union
import numpy as np


class BufferAttribute:
    """Stores data for BufferGeometry attributes."""

    def __init__(
        self,
        array: Union[list, np.ndarray],
        itemSize: int = 3,
        normalized: bool = False,
        dtype: str = "float32",
    ):
        self._array = (
            np.array(array, dtype=dtype) if not isinstance(array, np.ndarray) else array
        )
        self._itemSize = itemSize
        self._normalized = normalized
        self._dtype = dtype
        self._on_change: Optional[Callable] = None

    def _set_on_change(self, callback: Optional[Callable]):
        self._on_change = callback

    def _notify_change(self):
        if self._on_change:
            self._on_change()

    @property
    def array(self) -> np.ndarray:
        return self._array

    @array.setter
    def array(self, value):
        self._array = (
            np.array(value, dtype=self._dtype)
            if not isinstance(value, np.ndarray)
            else value
        )
        self._notify_change()

    @property
    def itemSize(self) -> int:
        return self._itemSize

    @property
    def normalized(self) -> bool:
        return self._normalized

    @property
    def count(self) -> int:
        return len(self._array) // self._itemSize

    def to_dict(self) -> dict[str, Any]:
        arr = (
            self._array.flatten().tolist()
            if hasattr(self._array, "tolist")
            else self._array
        )
        return {
            "array": arr,
            "itemSize": self._itemSize,
            "normalized": self._normalized,
        }


class Float32BufferAttribute(BufferAttribute):
    def __init__(self, array, itemSize: int = 3, normalized: bool = False):
        super().__init__(array, itemSize, normalized, dtype="float32")


class Uint32BufferAttribute(BufferAttribute):
    def __init__(self, array, itemSize: int = 1, normalized: bool = False):
        super().__init__(array, itemSize, normalized, dtype="uint32")


class Uint16BufferAttribute(BufferAttribute):
    def __init__(self, array, itemSize: int = 1, normalized: bool = False):
        super().__init__(array, itemSize, normalized, dtype="uint16")


class Int32BufferAttribute(BufferAttribute):
    def __init__(self, array, itemSize: int = 1, normalized: bool = False):
        super().__init__(array, itemSize, normalized, dtype="int32")
