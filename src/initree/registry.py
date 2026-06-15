"""registry — the locked capability vocabulary, loaded as data (docs/registry).

The registry is the single source of truth for the shared contract; hardcoding any of it here
would let the vocabulary drift. So the engine reads it from
``.claude/skills/capability-registry/capabilities.yaml`` (CLAUDE.md) instead. ``resources``
resolves that path — the checkout copy in a dev tree, the bundled copy in an installed wheel.

resolve only needs one thing from the registry: which keys the engine seeds onto the bus before
any layer runs, so a consumer of e.g. ``project.name`` is satisfied without a providing layer.
Later phases (compute/emit) will read more from the same loaded data.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ruamel.yaml import YAML

from initree import resources


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    path = resources.registry_path()
    if not path.exists():
        raise FileNotFoundError(f"capability registry not found at {path}")
    return YAML(typ="safe").load(path.read_text())


@lru_cache(maxsize=1)
def engine_seeded_keys() -> frozenset[str]:
    """Keys present on the bus before any layer runs — the ``project.*`` and ``git.*`` namespaces.

    A required ``consumes`` of one of these needs no providing layer
    (docs/lifecycle §0, docs/registry §4).
    """
    data = _load()
    return frozenset(entry["key"] for entry in data["keys"] if entry.get("owner") == "engine")


@lru_cache(maxsize=1)
def secret_purposes() -> dict[str, str]:
    """Each declared secret purpose mapped to its human-readable note (docs/registry §10).

    The provisioning report (INITREE_SECRETS.md) renders an observed purpose with this note, so the
    registry stays the one place the secret vocabulary and its descriptions live.
    """
    data = _load()
    return {entry["purpose"]: entry.get("note", "") for entry in data.get("secret_purposes", [])}
