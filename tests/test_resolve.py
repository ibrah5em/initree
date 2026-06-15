"""resolve TDD harness — RED until resolve() is implemented.

One test accepts the full recipe and pins its topological order; the rest each feed a recipe that
violates exactly one static check and assert resolve rejects it with the matching error. The four
named in the build order (cycle, owns-overlap, missing provider, missing container) are here, plus
two more so every check in docs/lifecycle §5 — dangling injection and unsatisfied requirement —
has a red test of its own. No check should ship without one.
"""

from pathlib import Path

import pytest

from initree.manifest import load_recipe
from initree.resolve import (
    DanglingInjectionError,
    MissingProviderError,
    OwnsOverlapError,
    RecipeCycleError,
    UnsatisfiedRequirementError,
    resolve,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_full_recipe_resolves_in_topological_order():
    order = resolve(load_recipe(FIXTURES / "valid-full"))
    assert order == ["go", "gin", "docker", "k8s", "slack", "gitlab-ci"]


def test_cycle_is_rejected():
    with pytest.raises(RecipeCycleError):
        resolve(load_recipe(FIXTURES / "cycle"))


def test_owns_overlap_is_rejected():
    with pytest.raises(OwnsOverlapError):
        resolve(load_recipe(FIXTURES / "owns-overlap"))


def test_missing_provider_is_rejected():
    with pytest.raises(MissingProviderError):
        resolve(load_recipe(FIXTURES / "missing-provider"))


def test_recipe_missing_a_required_container_is_rejected():
    with pytest.raises(MissingProviderError):
        resolve(load_recipe(FIXTURES / "missing-container"))


def test_missing_provider_error_names_the_owning_slot():
    with pytest.raises(MissingProviderError) as exc:
        resolve(load_recipe(FIXTURES / "missing-container"))

    message = str(exc.value)
    assert "container.exposed_port" in message
    assert "provided by the container slot" in message


def test_dangling_injection_target_is_rejected():
    with pytest.raises(DanglingInjectionError):
        resolve(load_recipe(FIXTURES / "dangling-inject"))


def test_unsatisfied_requirement_is_rejected():
    with pytest.raises(UnsatisfiedRequirementError):
        resolve(load_recipe(FIXTURES / "unsatisfied-requirement"))
