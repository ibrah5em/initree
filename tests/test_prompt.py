"""prompt TDD harness — drives prompt.py.

The prompt phase is a pure fold: walk the layers in topological order, ask each declared input, and
land the answer on a copy of the seed. These tests pin that order, prove an asker sees earlier
answers already in context, and check the layers-without-inputs and default-asker paths.
"""

from initree.manifest import Input, Layer
from initree.prompt import defaults, prompt


def _layer(layer_id: str, slot: str, inputs=None) -> Layer:
    return Layer(
        apiVersion="initree.dev/v1",
        id=layer_id,
        slot=slot,
        name=layer_id,
        inputs=inputs or [],
    )


def test_prompt_collects_inputs_in_topological_order_onto_the_seed():
    go = _layer(
        "go",
        "language",
        [Input(key="runtime.version", prompt="Go version", type="string", default="1.22")],
    )
    web = _layer(
        "web", "framework", [Input(key="app.port", prompt="Port", type="int", default=8080)]
    )
    seen: list[tuple[str, dict]] = []

    def ask(spec: Input, context):
        seen.append((spec.key, dict(context)))
        return spec.default

    # layers passed out of order; prompt must walk the given topological order, not list order
    out = prompt([web, go], ["go", "web"], {"project.name": "myapp"}, ask)

    assert out == {"project.name": "myapp", "runtime.version": "1.22", "app.port": 8080}
    assert [key for key, _ in seen] == ["runtime.version", "app.port"]
    # the framework input is asked with go's answer already on the context
    assert seen[1][1]["runtime.version"] == "1.22"


def test_prompt_copies_the_seed_and_leaves_it_untouched_without_inputs():
    plain = _layer("plain", "framework")
    seed = {"project.name": "myapp"}

    out = prompt([plain], ["plain"], seed, defaults)

    assert out == seed
    assert out is not seed


def test_defaults_asker_takes_the_declared_default():
    spec = Input(key="app.port", prompt="Port", type="int", default=8080)
    assert defaults(spec, {}) == 8080
