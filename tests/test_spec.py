"""Catalog-driven coverage: every generated class must construct, expose
observable fields, serialize cleanly in both forms, and be introspectable.
These loops mean a class added to the catalog is tested by existing."""

import inspect
import json

import pytest

import anythreejs as p3
from anythreejs.core.spec import CATALOG
from anythreejs.renderer import _extract_buffers


@pytest.mark.parametrize("name", list(CATALOG))
def test_class_constructs_and_serializes(name):
    cls = getattr(p3, name)
    obj = cls()
    assert obj._type == name
    assert type(obj).__name__ == name

    for flat in (False, True):
        data = obj.to_dict(flat=flat)
        assert data["type"] == name
        assert data["uuid"] == obj.uuid
        buffers = []
        json.dumps(_extract_buffers(data, buffers))  # wire-transportable


@pytest.mark.parametrize("name", list(CATALOG))
def test_every_field_is_an_observable_property(name):
    cls = getattr(p3, name)
    obj = cls()
    seen = []
    obj.observe(lambda change: seen.append(change["name"]))
    for fname in CATALOG[name]["fields"]:
        setattr(obj, fname, getattr(obj, fname))
    assert set(seen) == set(CATALOG[name]["fields"])


def test_signatures_are_introspectable():
    signature = inspect.signature(p3.MeshStandardMaterial)
    assert "roughness" in signature.parameters
    assert signature.parameters["roughness"].default == 0.5
    assert "radius" in inspect.signature(p3.SphereGeometry).parameters


def test_positional_arguments_follow_catalog_order():
    box = p3.BoxGeometry(2, 3, 4)
    assert (box.width, box.height, box.depth) == (2, 3, 4)
    light = p3.AmbientLight("#123456", 0.7)
    assert light.color == "#123456"
    assert light.intensity == 0.7
    with pytest.raises(TypeError):
        p3.AxesHelper(1, 2)  # more positionals than fields


def test_material_hierarchy_preserved():
    assert issubclass(p3.MeshStandardMaterial, p3.Material)
    assert issubclass(p3.LineDashedMaterial, p3.LineBasicMaterial)
    assert not issubclass(p3.SpriteMaterial, p3.Material)
    assert isinstance(p3.AmbientLight(), p3.Object3D)


def test_mutable_defaults_are_not_shared():
    a = p3.DirectionalLight()
    b = p3.DirectionalLight()
    assert a.__dict__["target"] is not b.__dict__["target"]


def test_vector_fields_expose_tuples_and_serialize_lists():
    controls = p3.OrbitControls(target=(1, 2, 3))
    assert controls.target == (1, 2, 3)
    assert controls.to_dict()["target"] == [1, 2, 3]


def test_css_color_forms_accepted():
    """Regression: pythreejs (via the ipywidgets Color trait) accepts
    rgb()/rgba()/hsl() strings and THREE.Color parses them; the catalog's
    color validation once rejected them at construction time."""
    material = p3.MeshBasicMaterial(color="rgb(100,100,100)")
    assert material.color == "rgb(100,100,100)"
    material.color = "hsl(120, 50%, 50%)"
    material.color = "rgba(10, 20, 30, 0.5)"
    with pytest.raises(ValueError):
        material.color = "not a color!"


def test_lit_materials_own_their_texture_maps():
    """Regression: map= on Standard/Phong/Lambert was silently dropped
    with only an unknown-kwargs warning."""
    import warnings

    import numpy as np

    for cls in (
        p3.MeshStandardMaterial,
        p3.MeshPhongMaterial,
        p3.MeshLambertMaterial,
    ):
        texture = p3.DataTexture(data=np.zeros((2, 2, 4), dtype="uint8"))
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            material = cls(map=texture)
        assert material.map is texture
        assert material.to_dict(flat=True)["map"] == texture.uuid
        assert texture in list(material._owned_objects())


def test_hemisphere_light_accepts_pythreejs_color_kwarg():
    """pythreejs names HemisphereLight's first parameter `color`."""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        light = p3.HemisphereLight(color="#123456")
    assert light.skyColor == "#123456"


def test_generated_classes_are_picklable():
    """Regression: generated classes claimed __module__ ==
    anythreejs.core.spec, where pickle could not find them."""
    import pickle

    material = p3.MeshStandardMaterial(roughness=0.3)
    assert type(material).__module__ == "anythreejs.core.material"
    clone = pickle.loads(pickle.dumps(material))
    assert type(clone) is p3.MeshStandardMaterial
    assert clone.roughness == 0.3


def test_shader_material_matplotgl_style():
    """matplotgl builds scatter markers with custom shaders."""
    material = p3.ShaderMaterial(
        vertexShader="void main() { gl_Position = vec4(position, 1.0); }",
        fragmentShader="void main() { gl_FragColor = vec4(1.0); }",
        transparent=True,
    )
    spec = material.to_dict(flat=True)
    assert spec["type"] == "ShaderMaterial"
    assert spec["vertexShader"].startswith("void main")
    assert spec["transparent"] is True
    assert "uniforms" not in spec  # omitted when unset

    material.uniforms = {"u_scale": {"value": 2.0}}
    assert material.to_dict()["uniforms"] == {"u_scale": {"value": 2.0}}
