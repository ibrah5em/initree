"""resources — locate the bundled data the engine reads at runtime.

Two data sets are the engine's runtime inputs but live outside ``src/initree`` as the development
source of truth: the layers (repo-root ``layers/``) and the capability registry
(``.claude/skills/capability-registry/capabilities.yaml``, per CLAUDE.md). From a checkout those
repo-root copies are authoritative. An installed wheel has no repo root, so the build copies both
into the package under ``_bundled/`` (see the force-include in pyproject). This module prefers the
checkout copy and falls back to the bundled one, so dev and installed runs resolve the same data.
"""

from __future__ import annotations

from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
# src/initree -> src -> repo root. None of this exists once installed into site-packages, which is
# the whole point: the lookups below miss and fall through to the bundled copy.
_REPO_ROOT = _PACKAGE_DIR.parents[1]
_BUNDLED = _PACKAGE_DIR / "_bundled"


def layers_dir() -> Path:
    """Directory holding the shipped ``<id>/layer.yaml`` layers (checkout copy, else bundled)."""
    checkout = _REPO_ROOT / "layers"
    return checkout if checkout.is_dir() else _BUNDLED / "layers"


def registry_path() -> Path:
    """The capability registry YAML — the locked vocabulary loaded as data (docs/03)."""
    checkout = _REPO_ROOT / ".claude" / "skills" / "capability-registry" / "capabilities.yaml"
    return checkout if checkout.is_file() else _BUNDLED / "capabilities.yaml"
