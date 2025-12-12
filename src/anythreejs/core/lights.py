"""
Light classes for Three.js scenes.
"""

from typing import Any
from .base import Object3D


class AmbientLight(Object3D):
    """Ambient light that illuminates all objects equally."""

    _type = "AmbientLight"

    def __init__(self, color: str = "#ffffff", intensity: float = 1.0, **kwargs):
        super().__init__(**kwargs)
        self._color = color
        self._intensity = intensity

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str):
        old = self._color
        self._color = value
        self._notify("color", old, value)

    @property
    def intensity(self) -> float:
        return self._intensity

    @intensity.setter
    def intensity(self, value: float):
        old = self._intensity
        self._intensity = value
        self._notify("intensity", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"color": self._color, "intensity": self._intensity})
        return data


class DirectionalLight(Object3D):
    """Directional light (like the sun)."""

    _type = "DirectionalLight"

    def __init__(
        self,
        color: str = "#ffffff",
        intensity: float = 1.0,
        castShadow: bool = False,
        target: list = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._color = color
        self._intensity = intensity
        self._castShadow = castShadow
        self._target = target or [0, 0, 0]

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str):
        old = self._color
        self._color = value
        self._notify("color", old, value)

    @property
    def intensity(self) -> float:
        return self._intensity

    @intensity.setter
    def intensity(self, value: float):
        old = self._intensity
        self._intensity = value
        self._notify("intensity", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "color": self._color,
                "intensity": self._intensity,
                "castShadow": self._castShadow,
                "target": self._target,
            }
        )
        return data


class PointLight(Object3D):
    """Point light (like a light bulb)."""

    _type = "PointLight"

    def __init__(
        self,
        color: str = "#ffffff",
        intensity: float = 1.0,
        distance: float = 0,
        decay: float = 2,
        castShadow: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._color = color
        self._intensity = intensity
        self._distance = distance
        self._decay = decay
        self._castShadow = castShadow

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str):
        old = self._color
        self._color = value
        self._notify("color", old, value)

    @property
    def intensity(self) -> float:
        return self._intensity

    @intensity.setter
    def intensity(self, value: float):
        old = self._intensity
        self._intensity = value
        self._notify("intensity", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "color": self._color,
                "intensity": self._intensity,
                "distance": self._distance,
                "decay": self._decay,
                "castShadow": self._castShadow,
            }
        )
        return data


class HemisphereLight(Object3D):
    """Hemisphere light (sky and ground colors)."""

    _type = "HemisphereLight"

    def __init__(
        self,
        skyColor: str = "#ffffff",
        groundColor: str = "#444444",
        intensity: float = 1.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._skyColor = skyColor
        self._groundColor = groundColor
        self._intensity = intensity

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "skyColor": self._skyColor,
                "groundColor": self._groundColor,
                "intensity": self._intensity,
            }
        )
        return data


class SpotLight(Object3D):
    """Spot light (cone-shaped)."""

    _type = "SpotLight"

    def __init__(
        self,
        color: str = "#ffffff",
        intensity: float = 1.0,
        distance: float = 0,
        angle: float = 0.5235987755982988,
        penumbra: float = 0,
        decay: float = 2,
        castShadow: bool = False,
        target: list = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._color = color
        self._intensity = intensity
        self._distance = distance
        self._angle = angle
        self._penumbra = penumbra
        self._decay = decay
        self._castShadow = castShadow
        self._target = target or [0, 0, 0]

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str):
        old = self._color
        self._color = value
        self._notify("color", old, value)

    @property
    def intensity(self) -> float:
        return self._intensity

    @intensity.setter
    def intensity(self, value: float):
        old = self._intensity
        self._intensity = value
        self._notify("intensity", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "color": self._color,
                "intensity": self._intensity,
                "distance": self._distance,
                "angle": self._angle,
                "penumbra": self._penumbra,
                "decay": self._decay,
                "castShadow": self._castShadow,
                "target": self._target,
            }
        )
        return data
