"""context — the capability bus and ${...} resolution (docs/01 §3, phase 3 `compute`).

Holds the namespaced key/value store every layer reads (`consumes`) and writes (`provides`),
resolves `${namespace.key}` references in dependency order, then freezes. Built after resolve.
"""

from __future__ import annotations

# Build order: resolve -> compute -> emit -> finalize. This module is `compute`.
