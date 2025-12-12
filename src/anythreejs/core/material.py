"""
Material classes for Three.js.
"""

from typing import Any
from .base import ThreeJSBase

SIDE_MAP = {
    "FrontSide": "FrontSide",
    "BackSide": "BackSide",
    "DoubleSide": "DoubleSide",
    "front": "FrontSide",
    "back": "BackSide",
    "double": "DoubleSide",
}


class Material(ThreeJSBase):
    """Base class for materials."""

    _type = "Material"

    def __init__(
        self,
        color: str = "#ffffff",
        opacity: float = 1.0,
        transparent: bool = False,
        visible: bool = True,
        side: str = "FrontSide",
        depthTest: bool = True,
        depthWrite: bool = True,
        **kwargs,
    ):
        super().__init__()
        self._color = color
        self._opacity = opacity
        self._transparent = transparent
        self._visible = visible
        self._side = SIDE_MAP.get(side, side)
        self._depthTest = depthTest
        self._depthWrite = depthWrite

    @property
    def color(self) -> str:
        return self._color

    @color.setter
    def color(self, value: str):
        old = self._color
        self._color = value
        self._notify("color", old, value)

    @property
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, value: float):
        old = self._opacity
        self._opacity = value
        self._notify("opacity", old, value)

    @property
    def transparent(self) -> bool:
        return self._transparent

    @transparent.setter
    def transparent(self, value: bool):
        old = self._transparent
        self._transparent = value
        self._notify("transparent", old, value)

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool):
        old = self._visible
        self._visible = value
        self._notify("visible", old, value)

    @property
    def side(self) -> str:
        return self._side

    @side.setter
    def side(self, value: str):
        old = self._side
        self._side = SIDE_MAP.get(value, value)
        self._notify("side", old, self._side)

    @property
    def depthTest(self) -> bool:
        return self._depthTest

    @depthTest.setter
    def depthTest(self, value: bool):
        old = self._depthTest
        self._depthTest = value
        self._notify("depthTest", old, value)

    @property
    def depthWrite(self) -> bool:
        return self._depthWrite

    @depthWrite.setter
    def depthWrite(self, value: bool):
        old = self._depthWrite
        self._depthWrite = value
        self._notify("depthWrite", old, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self._type,
            "uuid": self._uuid,
            "color": self._color,
            "opacity": self._opacity,
            "transparent": self._transparent,
            "visible": self._visible,
            "side": self._side,
            "depthTest": self._depthTest,
            "depthWrite": self._depthWrite,
        }


class MeshBasicMaterial(Material):
    """Basic material that doesn't respond to lighting."""

    _type = "MeshBasicMaterial"

    def __init__(self, wireframe: bool = False, vertexColors=False, **kwargs):
        super().__init__(**kwargs)
        self._wireframe = wireframe
        self._vertexColors = vertexColors

    @property
    def wireframe(self) -> bool:
        return self._wireframe

    @wireframe.setter
    def wireframe(self, value: bool):
        old = self._wireframe
        self._wireframe = value
        self._notify("wireframe", old, value)

    @property
    def vertexColors(self):
        return self._vertexColors

    @vertexColors.setter
    def vertexColors(self, value):
        old = self._vertexColors
        self._vertexColors = value
        self._notify("vertexColors", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"wireframe": self._wireframe, "vertexColors": self._vertexColors})
        return data


class MeshStandardMaterial(Material):
    """PBR material with roughness and metalness."""

    _type = "MeshStandardMaterial"

    def __init__(
        self,
        roughness: float = 0.5,
        metalness: float = 0.5,
        wireframe: bool = False,
        flatShading: bool = False,
        vertexColors=False,
        emissive: str = "#000000",
        emissiveIntensity: float = 1.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._roughness = roughness
        self._metalness = metalness
        self._wireframe = wireframe
        self._flatShading = flatShading
        self._vertexColors = vertexColors
        self._emissive = emissive
        self._emissiveIntensity = emissiveIntensity

    @property
    def roughness(self) -> float:
        return self._roughness

    @roughness.setter
    def roughness(self, value: float):
        old = self._roughness
        self._roughness = value
        self._notify("roughness", old, value)

    @property
    def metalness(self) -> float:
        return self._metalness

    @metalness.setter
    def metalness(self, value: float):
        old = self._metalness
        self._metalness = value
        self._notify("metalness", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "roughness": self._roughness,
                "metalness": self._metalness,
                "wireframe": self._wireframe,
                "flatShading": self._flatShading,
                "vertexColors": self._vertexColors,
                "emissive": self._emissive,
                "emissiveIntensity": self._emissiveIntensity,
            }
        )
        return data


class MeshPhongMaterial(Material):
    """Material with Phong shading (specular highlights)."""

    _type = "MeshPhongMaterial"

    def __init__(
        self,
        shininess: float = 30,
        specular: str = "#111111",
        wireframe: bool = False,
        flatShading: bool = False,
        vertexColors=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._shininess = shininess
        self._specular = specular
        self._wireframe = wireframe
        self._flatShading = flatShading
        self._vertexColors = vertexColors

    @property
    def shininess(self) -> float:
        return self._shininess

    @shininess.setter
    def shininess(self, value: float):
        old = self._shininess
        self._shininess = value
        self._notify("shininess", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "shininess": self._shininess,
                "specular": self._specular,
                "wireframe": self._wireframe,
                "flatShading": self._flatShading,
                "vertexColors": self._vertexColors,
            }
        )
        return data


class MeshLambertMaterial(Material):
    """Material with Lambert shading (non-shiny)."""

    _type = "MeshLambertMaterial"

    def __init__(self, wireframe: bool = False, vertexColors=False, **kwargs):
        super().__init__(**kwargs)
        self._wireframe = wireframe
        self._vertexColors = vertexColors

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"wireframe": self._wireframe, "vertexColors": self._vertexColors})
        return data


class PointsMaterial(Material):
    """Material for point cloud rendering."""

    _type = "PointsMaterial"

    def __init__(
        self,
        size: float = 1.0,
        sizeAttenuation: bool = True,
        vertexColors=False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._size = size
        self._sizeAttenuation = sizeAttenuation
        self._vertexColors = vertexColors

    @property
    def size(self) -> float:
        return self._size

    @size.setter
    def size(self, value: float):
        old = self._size
        self._size = value
        self._notify("size", old, value)

    @property
    def sizeAttenuation(self) -> bool:
        return self._sizeAttenuation

    @sizeAttenuation.setter
    def sizeAttenuation(self, value: bool):
        old = self._sizeAttenuation
        self._sizeAttenuation = value
        self._notify("sizeAttenuation", old, value)

    @property
    def vertexColors(self):
        return self._vertexColors

    @vertexColors.setter
    def vertexColors(self, value):
        old = self._vertexColors
        self._vertexColors = value
        self._notify("vertexColors", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update(
            {
                "size": self._size,
                "sizeAttenuation": self._sizeAttenuation,
                "vertexColors": self._vertexColors,
            }
        )
        return data


class LineBasicMaterial(Material):
    """Material for line rendering."""

    _type = "LineBasicMaterial"

    def __init__(self, linewidth: float = 1.0, vertexColors=False, **kwargs):
        super().__init__(**kwargs)
        self._linewidth = linewidth
        self._vertexColors = vertexColors

    @property
    def linewidth(self) -> float:
        return self._linewidth

    @linewidth.setter
    def linewidth(self, value: float):
        old = self._linewidth
        self._linewidth = value
        self._notify("linewidth", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"linewidth": self._linewidth, "vertexColors": self._vertexColors})
        return data


class LineDashedMaterial(LineBasicMaterial):
    """Material for dashed line rendering."""

    _type = "LineDashedMaterial"

    def __init__(self, dashSize: float = 3, gapSize: float = 1, **kwargs):
        super().__init__(**kwargs)
        self._dashSize = dashSize
        self._gapSize = gapSize

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data.update({"dashSize": self._dashSize, "gapSize": self._gapSize})
        return data


class SpriteMaterial(ThreeJSBase):
    """Material for sprites."""

    _type = "SpriteMaterial"

    def __init__(
        self,
        map=None,
        color: str = "#ffffff",
        opacity: float = 1.0,
        transparent: bool = False,
        **kwargs,
    ):
        super().__init__()
        self._map = map
        self._color = color
        self._opacity = opacity
        self._transparent = transparent

    @property
    def map(self):
        return self._map

    @map.setter
    def map(self, value):
        old = self._map
        self._map = value
        self._notify("map", old, value)

    @property
    def opacity(self) -> float:
        return self._opacity

    @opacity.setter
    def opacity(self, value: float):
        old = self._opacity
        self._opacity = value
        self._notify("opacity", old, value)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "type": self._type,
            "uuid": self._uuid,
            "color": self._color,
            "opacity": self._opacity,
            "transparent": self._transparent,
        }
        if self._map:
            data["map"] = (
                self._map.to_dict() if hasattr(self._map, "to_dict") else self._map
            )
        return data
