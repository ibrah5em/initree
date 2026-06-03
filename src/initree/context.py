"""context — the capability bus and ${...} resolution (docs/01 §3, phase 3 `compute`).

Holds the namespaced key/value store every layer reads (`consumes`) and writes (`provides`),
resolves `${namespace.key}` references in dependency order, then freezes. Built after resolve.

Two-tier interpolation (docs/03 §1): this phase resolves the engine tier — `${namespace.key}`,
a concrete value already on the bus — and deliberately leaves the `{{TOKEN}}` tier alone. Those
deferred runtime tokens ({{IMAGE}}, {{SHA}}, {{SECRET:...}}) are the ci layer's to resolve at its
render, because only it knows the runtime's native syntax. Secret values never enter the bus.

The bus arrives seeded: engine keys (project.*, git.*) plus the input answers the prompt phase
collected, all concrete. compute applies each layer's `provides` on top, in topological order,
and the result is frozen — no value changes after this point.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from typing import Any

from initree.manifest import Layer

# A provides value of exactly this marker means "computed by hooks.compute" (docs/01 §1). No hook
# runner exists yet, so compute refuses it loudly rather than writing the literal onto the bus.
_HOOK_SENTINEL = ":hook"

# Engine-tier reference: ${namespace.key}. Disjoint from the {{TOKEN}} tier, which has no leading $.
_REF = re.compile(r"\$\{([^}]+)\}")


class ComputeError(Exception):
    """Base for every failure while resolving the bus. compute() raises a subclass or this."""


class ReferenceCycleError(ComputeError):
    """A `${...}` reference chain loops back on itself with no concrete value to break it."""


class UnknownReferenceError(ComputeError):
    """A `${...}` names a key that is neither seeded nor provided by any layer in the recipe."""


class DuplicateProvideError(ComputeError):
    """Two layers (or one layer twice) provide the same key — each key has one writer."""


class Bus(Mapping[str, Any]):
    """The frozen capability bus: a read-only namespaced key/value store.

    Subclassing Mapping is the freeze — it exposes the read surface (`[]`, `get`, `in`, `items`)
    with no mutators, and the constructor copies its input so the bus is decoupled from whatever
    dict built it.
    """

    def __init__(self, values: Mapping[str, Any]) -> None:
        self._values = dict(values)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def as_dict(self) -> dict[str, Any]:
        """A shallow copy for callers (emit, tests) that want a plain dict to read or render."""
        return dict(self._values)

    def __repr__(self) -> str:
        return f"Bus({self._values!r})"


def compute(layers: list[Layer], order: list[str], seed: Mapping[str, Any]) -> Bus:
    """Resolve every layer's `provides` over the seeded bus and return the frozen result.

    `seed` is the concrete starting context (engine keys + prompt answers). Layers are processed in
    `order` (resolve's topological order), each writing its provides onto the bus so a later layer
    reads an upstream value already resolved. Raises a ComputeError subclass on a reference cycle,
    an unknown reference, or a duplicate provider.
    """
    by_id = {layer.id: layer for layer in layers}
    bus: dict[str, Any] = dict(seed)
    provided: set[str] = set()

    for layer_id in order:
        layer = by_id[layer_id]
        resolved = _resolve_layer(layer, view=_view_for(layer, bus))
        for key, value in resolved.items():
            if key in provided:
                raise DuplicateProvideError(
                    f"key '{key}' is provided by more than one layer; each capability key has "
                    f"exactly one authoritative provider (offending layer: '{layer_id}')"
                )
            provided.add(key)
            bus[key] = value

    return Bus(bus)


def _view_for(layer: Layer, bus: Mapping[str, Any]) -> dict[str, Any]:
    """The context this layer resolves against: the bus, plus its own defaults for optional
    consumes whose key is absent. A default is this layer's private fallback — it fills a reference
    in this layer's provides without leaking onto the shared bus (docs/02 §3.5, slack)."""
    defaults = {
        need.key: need.default
        for need in layer.consumes
        if not need.required and need.default is not None and need.key not in bus
    }
    return {**defaults, **bus}


def _resolve_layer(layer: Layer, view: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve all of one layer's `provides`, lazily so the entries may reference each other in any
    order. A reference resolves against this layer's own provides first, then `view`."""
    raw = _raw_provides(layer)
    resolved: dict[str, Any] = {}
    in_progress: list[str] = []

    def resolve_ref(key: str) -> Any:
        if key in resolved:
            return resolved[key]
        if key in in_progress:
            # A key referencing itself (directly or through a chain) breaks on its seeded value:
            # the `provides X = ${X}` republish of an input. Without one, it is a true cycle.
            if key in view:
                return view[key]
            chain = " -> ".join([*in_progress[in_progress.index(key) :], key])
            raise ReferenceCycleError(f"layer '{layer.id}' has a ${{...}} reference cycle: {chain}")
        if key in raw:
            in_progress.append(key)
            resolved[key] = _interpolate(raw[key], resolve_ref)
            in_progress.pop()
            return resolved[key]
        if key in view:
            return view[key]
        raise UnknownReferenceError(
            f"layer '{layer.id}' references '${{{key}}}', which is not on the bus "
            "and no layer provides it"
        )

    for key in raw:
        resolve_ref(key)
    return resolved


def _raw_provides(layer: Layer) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for provide in layer.provides:
        if provide.key in raw:
            raise DuplicateProvideError(
                f"layer '{layer.id}' provides '{provide.key}' more than once"
            )
        if provide.value == _HOOK_SENTINEL:
            raise ComputeError(
                f"layer '{layer.id}' computes '{provide.key}' via a hooks.compute escape hatch, "
                "which the compute phase does not run yet"
            )
        raw[provide.key] = provide.value
    return raw


def _interpolate(raw: Any, resolve_ref: Callable[[str], Any]) -> Any:
    """Substitute `${...}` references anywhere inside a value, recursing into recipe lists and maps.

    A string that is exactly one reference yields the referent with its type intact (an int stays
    an int); any other string is rendered with each referent stringified. `{{TOKEN}}`s pass through.
    """
    if isinstance(raw, str):
        return _interpolate_str(raw, resolve_ref)
    if isinstance(raw, list):
        return [_interpolate(item, resolve_ref) for item in raw]
    if isinstance(raw, dict):
        return {key: _interpolate(value, resolve_ref) for key, value in raw.items()}
    return raw


def _interpolate_str(text: str, resolve_ref: Callable[[str], Any]) -> Any:
    sole = _REF.fullmatch(text)
    if sole is not None:
        return resolve_ref(sole.group(1).strip())
    return _REF.sub(lambda match: str(resolve_ref(match.group(1).strip())), text)
