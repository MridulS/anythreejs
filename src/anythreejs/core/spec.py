"""
Declarative class catalog and factory.

Most anythreejs classes are plain bundles of observable, serializable
fields; hand-writing them meant maintaining every field three times
(constructor, property, serializer) — the drift between those copies (and
their JavaScript counterparts) is where past bugs lived. Here each class is
described ONCE as data in ``CATALOG`` and ``make_class`` generates the
class: positional-or-keyword constructor, validating observable
properties, ``to_dict`` (nested and flat forms), ``_owned_objects`` for
renderer attachment/GC, and an inspectable signature.

Classes with genuinely custom behavior (BufferGeometry, EdgesGeometry,
cameras, Picker, DataTexture, the Object3D core) stay hand-written.

Field spec keys:
    default     Default value (lists are copied per instance).
    kind        "value" (default) | "vector" (stored list, exposed tuple)
                | "color" (validated hex/name string) | "css" (any string)
                | "side" (normalized via SIDE_MAP) | "ref" (ThreeJSBase
                reference: owned, uuid in flat mode, nested to_dict
                otherwise) | "ref_unowned" (uuid in both modes, not owned).
    validate    ("positive",) | ("non_negative",) | ("range01",)
                | ("min_int", n)
    omit_none   Skip the key in to_dict when the value is None.

The category on each class ("geometry", "material", "light", "helper",
"controls", "texture") is metadata for tests and future tooling.
"""

import copy
import inspect
from typing import Any, Iterator

from .base import ThreeJSBase

SIDE_MAP = {
    "FrontSide": "FrontSide",
    "BackSide": "BackSide",
    "DoubleSide": "DoubleSide",
    "front": "FrontSide",
    "back": "BackSide",
    "double": "DoubleSide",
}

_OMIT = object()


def _check_positive(value, name):
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def _check_non_negative(value, name):
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


def _check_range01(value, name):
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0.0 and 1.0, got {value}")
    return value


def _resolve_validator(spec):
    if not spec:
        return None
    kind, *args = spec
    if kind == "positive":
        return _check_positive
    if kind == "non_negative":
        return _check_non_negative
    if kind == "range01":
        return _check_range01
    if kind == "min_int":
        minimum = args[0]

        def check(value, name):
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}, got {value}")
            return value

        return check
    raise KeyError(f"unknown validator {spec!r}")


class Prop:
    """Data descriptor for one catalog field: coerces/validates on set,
    stores in the instance dict, and notifies observers/renderers."""

    def __init__(self, field: dict):
        self.field = field
        self.kind = field.get("kind", "value")
        self.validator = _resolve_validator(field.get("validate"))

    def __set_name__(self, owner, name):
        self.name = name

    def _coerce(self, value):
        if self.kind == "vector":
            if value is None:
                default = self.field.get("default")
                return list(default) if default is not None else None
            return list(value)
        if self.kind == "side":
            return SIDE_MAP.get(value, value)
        if self.kind == "color":
            if isinstance(value, str) and not (
                value.startswith("#") or value.isalpha()
            ):
                raise ValueError(
                    f"Invalid color format: {value}. "
                    "Expected hex color (#RRGGBB) or color name"
                )
            return value
        return value

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        value = obj.__dict__[self.name]
        if self.kind == "vector" and value is not None:
            return tuple(value)
        return value

    def __set__(self, obj, value):
        value = self._coerce(value)
        if self.validator is not None:
            value = self.validator(value, self.name)
        old = obj.__dict__.get(self.name)
        obj.__dict__[self.name] = value
        obj._notify(self.name, old, value)

    def serialize(self, obj, flat):
        value = obj.__dict__.get(self.name)
        if value is None and (
            self.field.get("omit_none") or self.kind in ("ref", "ref_unowned")
        ):
            return _OMIT
        if self.kind == "vector":
            return list(value) if value is not None else None
        if self.kind == "ref":
            if flat:
                return value.uuid if hasattr(value, "uuid") else value
            return value.to_dict() if hasattr(value, "to_dict") else value
        if self.kind == "ref_unowned":
            return value.uuid if hasattr(value, "uuid") else value
        return value


def make_class(name: str, base: type, extra_namespace: dict = None) -> type:
    """Generate a class from its CATALOG entry."""
    entry = CATALOG[name]
    fields: dict[str, dict] = entry["fields"]
    order = list(fields)
    props = {fname: Prop(field) for fname, field in fields.items()}
    ref_fields = [
        fname for fname, field in fields.items() if field.get("kind") == "ref"
    ]

    def __init__(self, *args, **kwargs):
        if len(args) > len(order):
            raise TypeError(
                f"{name}() takes at most {len(order)} positional arguments, "
                f"got {len(args)}"
            )
        for fname, value in zip(order, args):
            if fname in kwargs:
                raise TypeError(f"{name}() got multiple values for '{fname}'")
            kwargs[fname] = value
        own = {fname: kwargs.pop(fname) for fname in order if fname in kwargs}
        super(cls, self).__init__(**kwargs)
        for fname in order:
            if fname in own:
                setattr(self, fname, own[fname])
            else:
                setattr(self, fname, copy.copy(fields[fname].get("default")))

    def to_dict(self, buffer_manager=None, flat=False) -> dict[str, Any]:
        data = super(cls, self).to_dict(buffer_manager=buffer_manager, flat=flat)
        for fname in order:
            value = props[fname].serialize(self, flat)
            if value is not _OMIT:
                data[fname] = value
        return data

    def _owned_objects(self) -> Iterator[ThreeJSBase]:
        yield from super(cls, self)._owned_objects()
        for fname in ref_fields:
            value = self.__dict__.get(fname)
            if isinstance(value, ThreeJSBase):
                yield value

    namespace = {
        "_type": name,
        "__doc__": entry.get("doc", ""),
        "__init__": __init__,
        "to_dict": to_dict,
        **props,
    }
    if ref_fields:
        namespace["_owned_objects"] = _owned_objects
    if extra_namespace:
        namespace.update(extra_namespace)

    cls = type(name, (base,), namespace)

    parameters = [
        inspect.Parameter(
            fname,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=fields[fname].get("default"),
        )
        for fname in order
    ]
    parameters.append(inspect.Parameter("kwargs", inspect.Parameter.VAR_KEYWORD))
    cls.__signature__ = inspect.Signature(parameters)
    return cls


TAU = 6.283185307179586
PI = 3.141592653589793


CATALOG: dict[str, dict] = {
    # ------------------------------------------------------------------
    # Geometries (parametric)
    # ------------------------------------------------------------------
    "BoxGeometry": {
        "category": "geometry",
        "doc": "Box geometry with specified dimensions.",
        "fields": {
            "width": {"default": 1, "validate": ("positive",)},
            "height": {"default": 1, "validate": ("positive",)},
            "depth": {"default": 1, "validate": ("positive",)},
            "widthSegments": {"default": 1, "validate": ("min_int", 1)},
            "heightSegments": {"default": 1, "validate": ("min_int", 1)},
            "depthSegments": {"default": 1, "validate": ("min_int", 1)},
        },
    },
    "SphereGeometry": {
        "category": "geometry",
        "doc": "Sphere geometry.",
        "fields": {
            "radius": {"default": 1, "validate": ("positive",)},
            "widthSegments": {"default": 32, "validate": ("min_int", 3)},
            "heightSegments": {"default": 16, "validate": ("min_int", 2)},
            # Angles pass through untouched: three.js accepts negative
            # starts and partial sweeps, and pythreejs never validated them.
            "phiStart": {"default": 0},
            "phiLength": {"default": TAU},
            "thetaStart": {"default": 0},
            "thetaLength": {"default": PI},
        },
    },
    "PlaneGeometry": {
        "category": "geometry",
        "doc": "Plane geometry.",
        "fields": {
            "width": {"default": 1, "validate": ("positive",)},
            "height": {"default": 1, "validate": ("positive",)},
            "widthSegments": {"default": 1, "validate": ("min_int", 1)},
            "heightSegments": {"default": 1, "validate": ("min_int", 1)},
        },
    },
    "CylinderGeometry": {
        "category": "geometry",
        "doc": "Cylinder geometry.",
        "fields": {
            "radiusTop": {"default": 1, "validate": ("non_negative",)},
            "radiusBottom": {"default": 1, "validate": ("non_negative",)},
            "height": {"default": 1, "validate": ("positive",)},
            "radialSegments": {"default": 32, "validate": ("min_int", 3)},
            "heightSegments": {"default": 1, "validate": ("min_int", 1)},
            "openEnded": {"default": False},
            "thetaStart": {"default": 0},
            "thetaLength": {"default": TAU},
        },
    },
    "TorusGeometry": {
        "category": "geometry",
        "doc": "Torus (donut) geometry.",
        "fields": {
            "radius": {"default": 1, "validate": ("positive",)},
            "tube": {"default": 0.4, "validate": ("positive",)},
            "radialSegments": {"default": 16, "validate": ("min_int", 2)},
            "tubularSegments": {"default": 100, "validate": ("min_int", 3)},
            "arc": {"default": TAU},
        },
    },
    # ------------------------------------------------------------------
    # Materials
    # ------------------------------------------------------------------
    "Material": {
        "category": "material",
        "doc": "Base class for materials.",
        "fields": {
            "color": {"default": "#ffffff", "kind": "color"},
            "opacity": {"default": 1.0, "validate": ("range01",)},
            "transparent": {"default": False},
            "visible": {"default": True},
            "side": {"default": "FrontSide", "kind": "side"},
            "depthTest": {"default": True},
            "depthWrite": {"default": True},
        },
    },
    "MeshBasicMaterial": {
        "category": "material",
        "doc": "Basic material that doesn't respond to lighting.",
        "fields": {
            "wireframe": {"default": False},
            "vertexColors": {"default": False},
            "map": {"default": None, "kind": "ref"},
        },
    },
    "MeshStandardMaterial": {
        "category": "material",
        "doc": "PBR material with roughness and metalness.",
        "fields": {
            "roughness": {"default": 0.5},
            "metalness": {"default": 0.5},
            "wireframe": {"default": False},
            "flatShading": {"default": False},
            "vertexColors": {"default": False},
            "emissive": {"default": "#000000", "kind": "css"},
            "emissiveIntensity": {"default": 1.0},
        },
    },
    "MeshPhongMaterial": {
        "category": "material",
        "doc": "Material with Phong shading (specular highlights).",
        "fields": {
            "shininess": {"default": 30},
            "specular": {"default": "#111111", "kind": "css"},
            "wireframe": {"default": False},
            "flatShading": {"default": False},
            "vertexColors": {"default": False},
        },
    },
    "MeshLambertMaterial": {
        "category": "material",
        "doc": "Material with Lambert shading (non-shiny).",
        "fields": {
            "wireframe": {"default": False},
            "vertexColors": {"default": False},
        },
    },
    "PointsMaterial": {
        "category": "material",
        "doc": "Material for point cloud rendering.",
        "fields": {
            "size": {"default": 1.0},
            "sizeAttenuation": {"default": True},
            "vertexColors": {"default": False},
        },
    },
    "LineBasicMaterial": {
        "category": "material",
        "doc": "Material for line rendering.",
        "fields": {
            "linewidth": {"default": 1.0},
            "vertexColors": {"default": False},
        },
    },
    "LineDashedMaterial": {
        "category": "material",
        "doc": "Material for dashed line rendering.",
        "fields": {
            "dashSize": {"default": 3},
            "gapSize": {"default": 1},
        },
    },
    "SpriteMaterial": {
        "category": "material",
        "doc": "Material for sprites.",
        "fields": {
            "map": {"default": None, "kind": "ref"},
            "color": {"default": "#ffffff", "kind": "css"},
            "opacity": {"default": 1.0},
            "transparent": {"default": False},
        },
    },
    "LineMaterial": {
        "category": "material",
        "doc": "Material for fat lines (Line2) with configurable line width.",
        "fields": {
            "color": {"default": "#ffffff", "kind": "css"},
            "linewidth": {"default": 1.0},
            "opacity": {"default": 1.0},
            "transparent": {"default": False},
            "dashed": {"default": False},
            "dashScale": {"default": 1.0},
            "dashSize": {"default": 1.0},
            "gapSize": {"default": 1.0},
            "vertexColors": {"default": False},
            "resolution": {"default": None, "kind": "vector", "omit_none": True},
        },
    },
    "ShaderMaterial": {
        "category": "material",
        "doc": "Material with custom GLSL shaders (uniforms must be "
        "JSON-serializable; textures in uniforms are not supported yet).",
        "fields": {
            "uniforms": {"default": None, "omit_none": True},
            "vertexShader": {"default": None, "omit_none": True},
            "fragmentShader": {"default": None, "omit_none": True},
            "transparent": {"default": False},
            "opacity": {"default": 1.0},
            "visible": {"default": True},
            "side": {"default": "FrontSide", "kind": "side"},
            "depthTest": {"default": True},
            "depthWrite": {"default": True},
        },
    },
    # ------------------------------------------------------------------
    # Lights (Object3D-based: transforms come from the base class)
    # ------------------------------------------------------------------
    "AmbientLight": {
        "category": "light",
        "doc": "Ambient light that illuminates all objects equally.",
        "fields": {
            "color": {"default": "#ffffff", "kind": "css"},
            "intensity": {"default": 1.0},
        },
    },
    "DirectionalLight": {
        "category": "light",
        "doc": "Directional light (like the sun).",
        "fields": {
            "color": {"default": "#ffffff", "kind": "css"},
            "intensity": {"default": 1.0},
            "castShadow": {"default": False},
            "target": {"default": [0, 0, 0], "kind": "vector"},
        },
    },
    "PointLight": {
        "category": "light",
        "doc": "Point light (like a light bulb).",
        "fields": {
            "color": {"default": "#ffffff", "kind": "css"},
            "intensity": {"default": 1.0},
            "distance": {"default": 0},
            "decay": {"default": 2},
            "castShadow": {"default": False},
        },
    },
    "HemisphereLight": {
        "category": "light",
        "doc": "Hemisphere light (sky and ground colors).",
        "fields": {
            "skyColor": {"default": "#ffffff", "kind": "css"},
            "groundColor": {"default": "#444444", "kind": "css"},
            "intensity": {"default": 1.0},
        },
    },
    "SpotLight": {
        "category": "light",
        "doc": "Spot light (cone-shaped).",
        "fields": {
            "color": {"default": "#ffffff", "kind": "css"},
            "intensity": {"default": 1.0},
            "distance": {"default": 0},
            "angle": {"default": 0.5235987755982988},
            "penumbra": {"default": 0},
            "decay": {"default": 2},
            "castShadow": {"default": False},
            "target": {"default": [0, 0, 0], "kind": "vector"},
        },
    },
    # ------------------------------------------------------------------
    # Helpers (Object3D-based)
    # ------------------------------------------------------------------
    "AxesHelper": {
        "category": "helper",
        "doc": "Helper to visualize the coordinate axes.",
        "fields": {
            "size": {"default": 1},
        },
    },
    "GridHelper": {
        "category": "helper",
        "doc": "Helper to visualize a grid.",
        "fields": {
            "size": {"default": 10},
            "divisions": {"default": 10},
            "colorCenterLine": {"default": "#444444", "kind": "css"},
            "colorGrid": {"default": "#888888", "kind": "css"},
        },
    },
    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------
    "OrbitControls": {
        "category": "controls",
        "doc": "Orbit controls for camera manipulation.",
        "fields": {
            "controlling": {"default": None, "kind": "ref_unowned"},
            "target": {"default": [0, 0, 0], "kind": "vector"},
            "enableDamping": {"default": True},
            "dampingFactor": {"default": 0.05},
            "enableZoom": {"default": True},
            "enableRotate": {"default": True},
            "enablePan": {"default": True},
            "autoRotate": {"default": False},
            "autoRotateSpeed": {"default": 2.0},
            "screenSpacePanning": {"default": True},
        },
    },
    "TrackballControls": {
        "category": "controls",
        "doc": "Trackball controls for camera manipulation.",
        "fields": {
            "controlling": {"default": None, "kind": "ref_unowned"},
            "target": {"default": [0, 0, 0], "kind": "vector"},
        },
    },
    # ------------------------------------------------------------------
    # Textures
    # ------------------------------------------------------------------
    "TextTexture": {
        "category": "texture",
        "doc": "Texture containing rendered text.",
        "fields": {
            "string": {"default": ""},
            "color": {"default": "white", "kind": "css"},
            "size": {"default": 100},
            "fontFace": {"default": "Arial"},
            "squareTexture": {"default": False},
        },
    },
}
