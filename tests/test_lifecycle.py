"""lifecycle TDD harness — drives lifecycle.py.

Runs the whole pipeline over the emit-slice fixture (no inputs, so the prompt phase is a no-op and
the value keys are seeded directly) and proves the five phases hand off correctly. The rejection
test pins the contract that resolve runs first: an unbuildable recipe raises before emit creates the
output directory. The seed/slug tests keep the engine seed aligned with the registry.
"""

from pathlib import Path

import pytest

from initree.lifecycle import BuildResult, build, engine_seed, slugify
from initree.manifest import load_recipe
from initree.prompt import defaults
from initree.registry import engine_seeded_keys
from initree.resolve import OwnsOverlapError

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_runs_the_five_phases_end_to_end(tmp_path):
    layers = load_recipe(FIXTURES / "emit-slice")
    out = tmp_path / "myapp"
    seed = {
        **engine_seed("My App", out),
        "runtime.version": "1.22",
        "app.port": 8080,
        "app.entrypoint": "./cmd/server",
    }

    result = build(layers, seed=seed, ask=defaults, out_dir=out)

    assert isinstance(result, BuildResult)
    assert result.order == ["go", "gin", "docker"]
    # compute resolved the bus, emit rendered owned files against it
    assert "go 1.22" in (out / "go.mod").read_text()
    assert "EXPOSE 8080" in (out / "Dockerfile").read_text()
    assert (out / "go.mod") in result.written
    # the frozen bus carries the engine seed through to the result
    assert result.bus["project.slug"] == "my-app"
    # this slice ships no finalize hooks
    assert result.finalized == []


def test_build_rejects_an_unbuildable_recipe_before_writing(tmp_path):
    layers = load_recipe(FIXTURES / "owns-overlap")
    out = tmp_path / "out"

    with pytest.raises(OwnsOverlapError):
        build(layers, seed=engine_seed("x", out), ask=defaults, out_dir=out)

    # resolve is phase 1: it failed before emit could create the output directory
    assert not out.exists()


def test_engine_seed_matches_the_registry_and_slugs_the_name(tmp_path):
    seed = engine_seed("My App", tmp_path / "my-app")

    assert set(seed) == set(engine_seeded_keys())
    assert seed["project.name"] == "My App"
    assert seed["project.slug"] == "my-app"
    assert seed["project.dir"] == str(tmp_path / "my-app")
    assert seed["git.is_repo"] is False


def test_slugify_normalizes_to_kebab():
    assert slugify("My Cool App!") == "my-cool-app"
    assert slugify("  spaced  out  ") == "spaced-out"
    assert slugify("___") == "project"
