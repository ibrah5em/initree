"""compute TDD harness — drives context.py.

The slice test runs the real pipeline (load -> resolve -> compute) over a fixture with full
`provides` values and pins the frozen bus, proving every interpolation rule the contract names:
literal pass-through, sole-reference type preservation (an int stays an int), nested and
provide->provide references, the self-referential republish of an input, and recipes whose
`${...}` is resolved while `{{TOKEN}}` is left untouched for the ci layer.

The rest are focused unit tests built from in-memory layers, one per rejection path
(reference cycle, unknown reference, duplicate provider, unsupported compute hook) plus the
optional-consume default fallback and the freeze guarantee.
"""

from collections.abc import MutableMapping
from pathlib import Path

import pytest

from initree.context import (
    Bus,
    ComputeError,
    DuplicateProvideError,
    ReferenceCycleError,
    UnknownReferenceError,
    compute,
)
from initree.manifest import Consume, Layer, Provide
from initree.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures"

# A concrete seed: engine-seeded keys plus the input answers the prompt phase would have collected.
SLICE_SEED = {
    "project.name": "myapp",
    "project.slug": "myapp",
    "project.dir": "/tmp/myapp",
    "git.is_repo": False,
    "runtime.version": "3.12",
    "app.module": "app.main:app",
    "app.port": 8000,
}


def _layer(layer_id: str, slot: str, *, provides=None, consumes=None) -> Layer:
    return Layer(
        apiVersion="initree.dev/v1",
        id=layer_id,
        slot=slot,
        name=layer_id,
        provides=provides or [],
        consumes=consumes or [],
    )


def test_compute_resolves_the_full_slice():
    layers = load_slice()
    order = resolve(layers)
    bus = compute(layers, order, SLICE_SEED)

    # literal, and a nested reference resolved into a larger string
    assert bus["runtime.language"] == "python"
    assert bus["runtime.base_image"] == "python:3.12-slim"
    # the republish: a provide whose value is its own input key reads the input, not itself
    assert bus["runtime.version"] == "3.12"
    # interpolated into a string -> stringified; refs to an input and a sibling provide
    assert bus["app.start_command"] == "uvicorn app.main:app --host 0.0.0.0 --port 8000"
    # sole reference preserves the referent's type: still an int, not "8000"
    assert bus["container.exposed_port"] == 8000
    assert isinstance(bus["container.exposed_port"], int)
    # a reference to an engine-seeded key
    assert bus["container.image_name"] == "myapp"
    # provide -> provide sole reference
    assert bus["registry.image_name_base"] == "registry.example.com/myapp"


def test_recipe_resolves_context_refs_but_defers_runtime_tokens():
    layers = load_slice()
    order = resolve(layers)
    bus = compute(layers, order, SLICE_SEED)

    # ${registry.host} is engine-time and resolved; {{...}} belongs to the ci layer and is untouched
    login = (
        "docker login -u {{SECRET:registry_user}} -p {{SECRET:registry}} registry.example.com/myapp"
    )
    assert bus["container.build_recipe"] == [
        login,
        "docker build -t {{IMAGE}} .",
        "docker push {{IMAGE}}",
    ]


def test_self_referential_provide_reads_its_input_without_cycling():
    # provides X = ${X} with X already on the seed is the republish pattern, not a cycle.
    go = _layer(
        "go",
        "language",
        provides=[Provide(key="runtime.version", type="string", value="${runtime.version}")],
    )
    bus = compute([go], ["go"], {"runtime.version": "1.22"})
    assert bus["runtime.version"] == "1.22"


def test_optional_consume_default_fills_an_absent_reference():
    # slack provides a recipe referencing deploy.summary, which no deploy layer supplied.
    slack = _layer(
        "slack",
        "notify",
        consumes=[
            Consume(key="project.name", required=True),
            Consume(key="deploy.summary", required=False, default="a new version"),
        ],
        provides=[
            Provide(
                key="notify.send_recipe",
                type="recipe",
                value=["echo ${project.name} deployed ${deploy.summary}"],
            )
        ],
    )
    bus = compute([slack], ["slack"], {"project.name": "myapp"})
    assert bus["notify.send_recipe"] == ["echo myapp deployed a new version"]


def test_reference_cycle_is_rejected():
    loop = _layer(
        "loop",
        "language",
        provides=[
            Provide(key="runtime.version", type="string", value="${runtime.base_image}"),
            Provide(key="runtime.base_image", type="string", value="${runtime.version}"),
        ],
    )
    with pytest.raises(ReferenceCycleError):
        compute([loop], ["loop"], {})


def test_unknown_reference_is_rejected():
    bad = _layer(
        "bad",
        "language",
        provides=[Provide(key="runtime.base_image", type="string", value="${runtime.nope}")],
    )
    with pytest.raises(UnknownReferenceError):
        compute([bad], ["bad"], {})


def test_duplicate_provider_is_rejected():
    one = _layer(
        "one", "container", provides=[Provide(key="container.runtime", type="string", value="a")]
    )
    two = _layer(
        "two", "deploy", provides=[Provide(key="container.runtime", type="string", value="b")]
    )
    with pytest.raises(DuplicateProvideError):
        compute([one, two], ["one", "two"], {})


def test_compute_hook_value_is_unsupported_for_now():
    hooked = _layer(
        "hooked",
        "language",
        provides=[Provide(key="runtime.version", type="string", value=":hook")],
    )
    with pytest.raises(ComputeError, match="hook"):
        compute([hooked], ["hooked"], {})


def test_the_bus_is_frozen_and_decoupled_from_its_inputs():
    seed = {"project.name": "myapp"}
    bus = compute([], [], seed)

    assert isinstance(bus, Bus)
    assert not isinstance(bus, MutableMapping)
    assert bus["project.name"] == "myapp"
    assert bus.get("absent", "fallback") == "fallback"

    # mutating the original seed must not reach through into the frozen bus
    seed["project.name"] = "changed"
    assert bus["project.name"] == "myapp"
    # and as_dict() hands back a copy, not the backing store
    bus.as_dict()["project.name"] = "changed"
    assert bus["project.name"] == "myapp"


def load_slice() -> list[Layer]:
    from initree.manifest import load_recipe

    return load_recipe(FIXTURES / "compute-slice")
