"""lifecycle — orchestrates the five engine phases (docs/lifecycle §5).

resolve -> prompt -> compute -> emit -> finalize. Each phase is engine-global; within a phase the
layers run in the topological order resolve computed, each uninterrupted ("layer as a function").
This module sequences them and hands back what the build produced.

`build` is deliberately I/O-free except through the phases it calls: the seed and the asker arrive
as arguments, so the same pipeline drives a real `initree new` and a test fixture. resolve runs
first, so an unbuildable recipe is rejected before emit touches the filesystem.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from initree.context import Bus, compute
from initree.emit import emit
from initree.finalize import finalize
from initree.manifest import Layer
from initree.prompt import Asker, prompt
from initree.resolve import resolve
from initree.secrets import write_secret_report


@dataclass(frozen=True)
class BuildResult:
    """What one run produced: order, frozen bus, files written, secrets report, hooks run."""

    order: list[str]
    bus: Bus
    written: list[Path]
    secrets_report: Path | None
    finalized: list[str]


def build(
    layers: list[Layer],
    *,
    seed: Mapping[str, Any],
    ask: Asker,
    out_dir: Path,
    run_finalize: bool = True,
) -> BuildResult:
    """Run resolve -> prompt -> compute -> emit -> finalize over a recipe and return the result.

    `seed` is the engine-seeded context (see engine_seed); `ask` answers each layer's inputs.
    Raises the phase's own error subclass on failure — resolve's run before anything is written.
    """
    order = resolve(layers)
    context = prompt(layers, order, seed, ask)
    bus = compute(layers, order, context)
    written = emit(layers, order, bus, out_dir)
    secrets_report = write_secret_report(layers, bus, out_dir)
    finalized = finalize(layers, order, bus, out_dir) if run_finalize else []
    return BuildResult(
        order=order,
        bus=bus,
        written=written,
        secrets_report=secrets_report,
        finalized=finalized,
    )


def engine_seed(name: str, out_dir: Path) -> dict[str, Any]:
    """The project.*/git.* keys the engine seeds before any layer runs (docs/lifecycle §1).

    The only values produced by neither a layer nor a prompt. Keys mirror the engine-owned entries
    in the registry; git.is_repo is false at scaffold time — a finalize hook may `git init` later.
    """
    return {
        "project.name": name,
        "project.slug": slugify(name),
        "project.dir": str(out_dir),
        "git.is_repo": False,
    }


def slugify(name: str) -> str:
    """A path/url-safe kebab slug: lowercase, non-alphanumerics collapsed to single hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "project"
