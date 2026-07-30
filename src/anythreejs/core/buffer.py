"""
Buffer attribute classes for custom geometry data.
"""

from typing import Any, Callable, Optional, Union
import numpy as np


def binary_wrapper(array: np.ndarray, dtype=None) -> dict[str, Any]:
    """Wrap a numpy array as ``{"dtype": ..., "data": memoryview}`` for
    binary transport. The memoryview is extracted into a binary buffer by
    the widget protocol (snapshot trait) or by the op flusher (delta
    messages)."""
    arr = np.asarray(array)
    if dtype is not None and arr.dtype != np.dtype(dtype):
        arr = arr.astype(dtype)
    flat = np.ascontiguousarray(arr).reshape(-1)
    return {"dtype": str(flat.dtype), "data": memoryview(flat).cast("B")}


# WebGL has no 64-bit attribute types (and JS no Float16/64 typed-array
# support we rely on), so wide dtypes narrow at the boundary.
_DTYPE_NARROWING = {
    "float64": "float32",
    "float16": "float32",
    "int64": "int32",
    "uint64": "uint32",
}


def _infer_dtype(array) -> str:
    arr = np.asarray(array)
    name = str(arr.dtype)
    if name in _DTYPE_NARROWING:
        return _DTYPE_NARROWING[name]
    if arr.dtype.kind in "fiu":
        return name
    return "float32"


class BufferAttribute:
    """Stores data for BufferGeometry attributes.

    Like pythreejs, the dtype follows the array you pass in (narrowed to a
    WebGL-representable width); assigning a new array later coerces it back
    to the attribute's dtype.
    """

    def __init__(
        self,
        array: Union[list, np.ndarray],
        itemSize: int = 3,
        normalized: bool = False,
        dtype: str = None,
    ):
        self._dtype = dtype if dtype is not None else _infer_dtype(array)
        self._array = self._coerce(array)
        self._itemSize = itemSize
        self._normalized = normalized
        self._on_change_callbacks: list[Callable] = []

    def _coerce(self, value) -> np.ndarray:
        arr = np.asarray(value)
        if arr.dtype != np.dtype(self._dtype):
            arr = arr.astype(self._dtype)
        return arr

    def _add_on_change(self, callback: Callable):
        if callback not in self._on_change_callbacks:
            self._on_change_callbacks.append(callback)

    def _remove_on_change(self, callback: Callable):
        if callback in self._on_change_callbacks:
            self._on_change_callbacks.remove(callback)

    def _set_on_change(self, callback: Optional[Callable]):
        """Legacy single-callback API; prefer _add_on_change."""
        self._on_change_callbacks = [callback] if callback else []

    def _notify_change(self):
        for callback in list(self._on_change_callbacks):
            callback()

    @property
    def array(self) -> np.ndarray:
        return self._array

    @array.setter
    def array(self, value):
        self._array = self._coerce(value)
        self._notify_change()

    @property
    def itemSize(self) -> int:
        return self._itemSize

    @property
    def normalized(self) -> bool:
        return self._normalized

    @property
    def count(self) -> int:
        return int(self._array.size) // self._itemSize

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "itemSize": self._itemSize,
            "normalized": self._normalized,
        }
        if flat:
            result.update(binary_wrapper(self._array))
        else:
            result["array"] = self._array.reshape(-1).tolist()
        return result


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
