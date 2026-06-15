"""resolve — phase 1, the buildability proof (docs/lifecycle §5).

Runs the static checks over a loaded recipe and returns the layer ids in topological order, or
raises a ResolveError subclass naming the first violation. No files are written here — that is the
whole point of resolve: prove the recipe is buildable before emit touches the filesystem.

The checks (docs/lifecycle §5, mapped onto the registry §3/§11/§13):
  - every `requires.slots` is filled (and one_of holds)  -> UnsatisfiedRequirementError
  - no two layers' `owns` globs overlap                  -> OwnsOverlapError
  - every required `consumes` has a provider             -> MissingProviderError
  - every `injects.into` matches a declared point        -> DanglingInjectionError
  - the consumes -> provides graph is acyclic            -> RecipeCycleError

The order above is the order checks run: a recipe is rejected on the first violation, and the
checks are arranged structural-first (is the right set of slots present?) before data-flow
(does every required value have a producer?) before ordering (does the graph sort?).
"""

from __future__ import annotations

from fnmatch import fnmatch
from graphlib import CycleError, TopologicalSorter
from itertools import combinations

from initree.manifest import Layer
from initree.registry import engine_seeded_keys, provider_slot_for


class ResolveError(Exception):
    """Base for every recipe-level rejection. resolve() raises a subclass, never this directly."""


class OwnsOverlapError(ResolveError):
    """Two layers claim ownership of the same file. Single-ownership is absolute
    (docs/lifecycle §0)."""


class MissingProviderError(ResolveError):
    """A required `consumes` key has no upstream `provides` (nor an engine-seeded value)."""


class UnsatisfiedRequirementError(ResolveError):
    """A `requires.slots` entry is unfilled, or its `one_of` pin does not hold."""


class DanglingInjectionError(ResolveError):
    """An `injects.into` targets an injection-point id that no layer in the recipe declares."""


class RecipeCycleError(ResolveError):
    """The dependency graph contains a cycle (e.g. the container <-> ci cycle the boundary bars)."""


def resolve(layers: list[Layer]) -> list[str]:
    """Validate a recipe and return its layer ids in topological order.

    Raises a ResolveError subclass on the first violation found. No filesystem effects.
    """
    _check_requirements(layers)
    _check_ownership(layers)
    _check_providers(layers)
    _check_injections(layers)
    return _topological_order(layers)


def _check_requirements(layers: list[Layer]) -> None:
    ids_by_slot: dict[str, list[str]] = {}
    for layer in layers:
        ids_by_slot.setdefault(layer.slot, []).append(layer.id)

    for layer in layers:
        if layer.requires is None:
            continue
        for need in layer.requires.slots:
            fillers = ids_by_slot.get(need.slot, [])
            if not fillers:
                raise UnsatisfiedRequirementError(
                    f"layer '{layer.id}' requires a '{need.slot}' slot, "
                    "but no layer in the recipe fills it"
                )
            if need.one_of is not None and not any(fid in need.one_of for fid in fillers):
                raise UnsatisfiedRequirementError(
                    f"layer '{layer.id}' requires its '{need.slot}' slot to be one of "
                    f"{need.one_of}, but it is filled by {fillers}"
                )


def _check_ownership(layers: list[Layer]) -> None:
    for first, second in combinations(layers, 2):
        for glob_a in first.owns:
            for glob_b in second.owns:
                if _globs_overlap(glob_a, glob_b):
                    raise OwnsOverlapError(
                        f"layers '{first.id}' and '{second.id}' both claim overlapping paths "
                        f"('{glob_a}' vs '{glob_b}'); single-ownership is absolute"
                    )


def _check_providers(layers: list[Layer]) -> None:
    provided = engine_seeded_keys() | {p.key for layer in layers for p in layer.provides}
    missing = [
        (layer.id, need.key)
        for layer in layers
        for need in layer.consumes
        if need.required and need.key not in provided
    ]
    if missing:
        details = ", ".join(_describe_missing(consumer, key) for consumer, key in missing)
        raise MissingProviderError(
            f"no provider in the recipe for required key(s): {details}. add a layer for the named "
            "slot, or swap one that already provides the key"
        )


def _describe_missing(consumer: str, key: str) -> str:
    """A missing required key, named with the slot that would provide it so the fix is obvious."""
    slot = provider_slot_for(key)
    if slot is not None and slot != "engine":
        return f"'{key}' (consumed by '{consumer}', provided by the {slot} slot)"
    return f"'{key}' (consumed by '{consumer}')"


def _check_injections(layers: list[Layer]) -> None:
    declared = {point.id for layer in layers for point in layer.injection_points}
    for layer in layers:
        for inj in layer.injects:
            if inj.into not in declared:
                raise DanglingInjectionError(
                    f"layer '{layer.id}' injects into '{inj.into}', which no layer in the recipe "
                    "declares as an injection point"
                )


def _topological_order(layers: list[Layer]) -> list[str]:
    provider_of = {p.key: layer.id for layer in layers for p in layer.provides}
    ids_by_slot: dict[str, list[str]] = {}
    for layer in layers:
        ids_by_slot.setdefault(layer.slot, []).append(layer.id)

    sorter: TopologicalSorter[str] = TopologicalSorter()
    for layer in layers:
        predecessors = _predecessors_of(layer, provider_of, ids_by_slot)
        sorter.add(layer.id, *predecessors)

    try:
        return list(sorter.static_order())
    except CycleError as exc:
        chain = " -> ".join(exc.args[1]) if len(exc.args) > 1 else "(unknown)"
        raise RecipeCycleError(
            f"the recipe's dependency graph has a cycle: {chain}. this usually means a non-ci "
            "layer consumes a ci-runtime ref, which the capability/recipe boundary forbids"
        ) from exc


def _predecessors_of(
    layer: Layer,
    provider_of: dict[str, str],
    ids_by_slot: dict[str, list[str]],
) -> set[str]:
    """Layers that must sort before `layer`: the producers of what it consumes, plus the layers
    filling the slots it requires. An optional consume still orders behind its producer when one
    is present (so the value is on the bus by compute); a missing optional producer adds no edge.
    """
    predecessors: set[str] = set()
    for need in layer.consumes:
        producer = provider_of.get(need.key)
        if producer is not None and producer != layer.id:
            predecessors.add(producer)
    if layer.requires is not None:
        for req in layer.requires.slots:
            predecessors.update(fid for fid in ids_by_slot.get(req.slot, []) if fid != layer.id)
    return predecessors


def _globs_overlap(a: str, b: str) -> bool:
    """Whether two `owns` globs could match a common path. Compared segment by segment, with
    `**` matching zero or more segments — so `app/**` overlaps `app/main.go`, while `cmd/**` and
    `internal/**` do not. Append-only single-ownership depends on catching these statically.
    """
    return _segments_intersect(a.split("/"), b.split("/"))


def _segments_intersect(a: list[str], b: list[str]) -> bool:
    if not a or not b:
        return all(segment == "**" for segment in a + b)
    if a[0] == "**":
        return _segments_intersect(a[1:], b) or _segments_intersect(a, b[1:])
    if b[0] == "**":
        return _segments_intersect(a, b[1:]) or _segments_intersect(a[1:], b)
    if not _segment_matches(a[0], b[0]):
        return False
    return _segments_intersect(a[1:], b[1:])


def _segment_matches(a: str, b: str) -> bool:
    if a == b:
        return True
    if _has_wildcard(a) or _has_wildcard(b):
        return fnmatch(a, b) or fnmatch(b, a)
    return False


def _has_wildcard(segment: str) -> bool:
    return any(char in segment for char in "*?[")
