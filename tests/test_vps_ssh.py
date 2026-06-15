"""vps-ssh binds the deploy command to the container capability, never to a tool name.

Invariant #1 (capability, not implementation): a deploy layer pulls and runs the image with whatever
the container slot chose, so a docker->podman swap reaches the host too. This locks that the recipe
goes through ${container.runtime} and names no container tool literally.
"""

from pathlib import Path

from initree.manifest import Layer

LAYER = Path(__file__).resolve().parents[1] / "layers" / "vps-ssh" / "layer.yaml"


def _deploy_recipe(layer: Layer) -> str:
    apply_recipe = next(p for p in layer.provides if p.key == "deploy.apply_recipe")
    return "\n".join(apply_recipe.value)


def test_runtime_is_consumed_as_a_capability():
    layer = Layer.from_yaml(LAYER)
    assert "container.runtime" in {c.key for c in layer.consumes}


def test_deploy_recipe_pulls_and_runs_through_the_runtime_capability():
    recipe = _deploy_recipe(Layer.from_yaml(LAYER))
    assert "${container.runtime} pull" in recipe
    assert "${container.runtime} run" in recipe
    # No tool name leaks past the capability boundary — that is what keeps the swap honest.
    assert "docker " not in recipe
    assert "podman " not in recipe
