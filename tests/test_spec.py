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
