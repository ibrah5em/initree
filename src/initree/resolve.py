"""resolve — phase 1, the buildability proof (docs/01 §5).

Runs the static checks over a loaded recipe and returns the layer ids in topological order, or
raises a ResolveError subclass naming the first violation. No files are written here — that is the
whole point of resolve: prove the recipe is buildable before emit touches the filesystem.

The checks (docs/01 §5, mapped onto the registry §3/§11/§13):
  - no two layers' `owns` globs overlap                 -> OwnsOverlapError
  - every required `consumes` has an upstream `provides` -> MissingProviderError
  - every `requires.slots` is filled (and one_of holds)  -> UnsatisfiedRequirementError
  - every `injects.into` matches a declared point        -> DanglingInjectionError
  - the consumes -> provides graph is acyclic            -> RecipeCycleError

Not implemented yet. tests/test_resolve.py is the red harness that drives this.
"""

from __future__ import annotations

from initree.manifest import Layer


class ResolveError(Exception):
    """Base for every recipe-level rejection. resolve() raises a subclass, never this directly."""


class OwnsOverlapError(ResolveError):
    """Two layers claim ownership of the same file. Single-ownership is absolute (docs/01 §0)."""


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
    raise NotImplementedError(
        "resolve is the next build step — implement it against tests/test_resolve.py"
    )
