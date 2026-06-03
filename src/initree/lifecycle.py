"""lifecycle — orchestrates the five engine phases (docs/01 §5).

resolve -> prompt -> compute -> emit -> finalize. Each phase is engine-global; within a phase
layers run in the topological order resolve computed, each uninterrupted ("layer as a function").
Wired up once the phases it drives exist.
"""

from __future__ import annotations

# Build order: resolve -> compute -> emit -> finalize. This module sequences all of them.
