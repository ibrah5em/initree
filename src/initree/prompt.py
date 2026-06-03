"""prompt — phase 2: collect each layer's inputs onto the bus seed (docs/01 §5).

Walks the layers in resolve's topological order and asks for every declared input, writing each
answer onto a copy of the seed. Inputs land exactly like provided values, so a later layer's input
can default off an earlier answer or an engine-seeded key. No files are touched here — this phase
only gathers the concrete context compute will resolve `provides` against.

The act of asking is injected as an `Asker`: the interactive CLI prompts a real user, a `--no-input`
run takes declared defaults, tests pass a stub. Pushing that I/O to the edge leaves this core a pure
fold over the inputs.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from initree.manifest import Input, Layer

# Turns one input spec into a concrete value. Receives the context gathered so far, so an asker may
# resolve a default against an earlier answer; what it returns is what lands on the bus seed.
Asker = Callable[[Input, Mapping[str, Any]], Any]


def prompt(
    layers: list[Layer], order: list[str], seed: Mapping[str, Any], ask: Asker
) -> dict[str, Any]:
    """Collect every layer's inputs in topological order onto a copy of the seed.

    Returns the concrete context compute resolves `provides` against. The input loop runs in `order`
    so an asker sees earlier answers already in context.
    """
    by_id = {layer.id: layer for layer in layers}
    context: dict[str, Any] = dict(seed)
    for layer_id in order:
        for spec in by_id[layer_id].inputs:
            context[spec.key] = ask(spec, context)
    return context


def defaults(spec: Input, context: Mapping[str, Any]) -> Any:
    """An Asker that always takes the input's declared default — the --no-input and test policy."""
    return spec.default
