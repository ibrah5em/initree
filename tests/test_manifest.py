"""The manifest schema + loader are implemented, so these pass. They prove the fixtures parse
against the locked layer.yaml shape, which is what gives the resolve tests something real to run.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from initree.manifest import Layer, load_recipe

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_recipe_reads_every_layer_in_topo_dir():
    layers = load_recipe(FIXTURES / "valid-full")
    by_slot = {layer.slot: layer.id for layer in layers}
    assert {layer.id for layer in layers} == {
        "go",
        "gin",
        "docker",
        "k8s",
        "slack",
        "gitlab-ci",
    }
    assert by_slot == {
        "language": "go",
        "framework": "gin",
        "container": "docker",
        "deploy": "k8s",
        "notify": "slack",
        "ci": "gitlab-ci",
    }


def test_optional_blocks_default_empty():
    # k8s declares no injection_points and no requires; the model should fill sane empties.
    k8s = next(layer for layer in load_recipe(FIXTURES / "valid-full") if layer.id == "k8s")
    assert k8s.injection_points == []
    assert k8s.injects == []
    assert k8s.requires is None


def test_load_recipe_on_empty_dir_is_loud(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_recipe(tmp_path)


def test_unknown_field_is_rejected(tmp_path):
    bad = tmp_path / "bad" / "layer.yaml"
    bad.parent.mkdir(parents=True)
    bad.write_text(
        "apiVersion: initree.dev/v1\nid: bad\nslot: language\nname: Bad layer\nnonsense: true\n"
    )
    with pytest.raises(ValidationError):
        Layer.from_yaml(bad)
