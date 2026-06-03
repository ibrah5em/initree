"""emit — phase 4: render owned files, then splice injections (docs/01 §5).

Two ordered passes: (4a) render every `owns` template against the frozen bus, exactly one writer
per file; (4b) gather all `injects` targeting each declared injection point, order them, render,
and splice at the anchor. Injection runs after compute, so it is order-independent. Built after
compute.
"""

from __future__ import annotations

# Build order: resolve -> compute -> emit -> finalize. This module is `emit`.
