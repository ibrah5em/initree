"""initree — a composition orchestrator for project scaffolding.

Compose small, independent layers that exchange data over a typed capability bus.
The contract is locked at v1 (see docs/); the engine is built phase by phase:
resolve -> compute -> emit -> finalize.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth is pyproject's version; read it from the installed distribution
    # rather than duplicating the literal here.
    __version__ = version("initree")
except PackageNotFoundError:  # running from a source tree with nothing installed
    __version__ = "0.0.0"
