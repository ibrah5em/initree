"""registry — the locked capability vocabulary, loaded as data (docs/03).

The registry is the single source of truth for the shared contract; hardcoding any of it here
would let the vocabulary drift. So the engine reads it from
``.claude/skills/capability-registry/capabilities.yaml`` (CLAUDE.md) instead.

resolve only needs one thing from the registry: which keys the engine seeds onto the bus before
any layer runs, so a consumer of e.g. ``project.name`` is satisfied without a providing layer.
Later phases (compute/emit) will read more from the same loaded data.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# src/initree/registry.py -> repo root is two parents above the package dir. The registry lives
# under .claude/ by design (the documented source of truth), not inside the installed package.
_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "skills"
    / "capability-registry"
    / "capabilities.yaml"
)


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    if not _REGISTRY_PATH.exists():
        raise FileNotFoundError(f"capability registry not found at {_REGISTRY_PATH}")
    return YAML(typ="safe").load(_REGISTRY_PATH.read_text())


@lru_cache(maxsize=1)
def engine_seeded_keys() -> frozenset[str]:
    """Keys present on the bus before any layer runs — the ``project.*`` and ``git.*`` namespaces.

    A required ``consumes`` of one of these needs no providing layer (docs/01 §0, docs/03 §4).
    """
    data = _load()
    return frozenset(entry["key"] for entry in data["keys"] if entry.get("owner") == "engine")
