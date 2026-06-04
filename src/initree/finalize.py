"""finalize — phase 5: run each layer's finalize hook (docs/01 §5).

The last phase, and the only one that runs layer-authored code. A layer that needs a real-world
side effect the declarative contract can't express — ``chmod +x`` a script, ``git init``,
``go mod tidy``, run a formatter — ships an executable hook and points ``hooks.finalize`` at it.

Each hook runs in topological order, with its working directory set to the generated project and the
frozen bus exported to the environment (``app.port`` -> ``INITREE_APP_PORT``), so a hook can read
context without the engine inventing an interface. The bus is read-only here; finalize observes it,
it does not write to it. A hook that is missing, not runnable, or exits non-zero stops the build.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path

from initree.context import Bus, hook_env
from initree.manifest import Layer


class FinalizeError(Exception):
    """A finalize hook is missing, could not be executed, or exited non-zero."""


def finalize(layers: list[Layer], order: list[str], bus: Bus, out_dir: Path) -> list[str]:
    """Run every layer's finalize hook in topological order. Returns the ids that ran.

    Layers without a hook are skipped — most need none. Raises FinalizeError on the first hook that
    is missing, not executable, or exits non-zero, so a broken finalize never passes silently.
    """
    by_id = {layer.id: layer for layer in layers}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    env = hook_env(bus)

    ran: list[str] = []
    for layer_id in order:
        layer = by_id[layer_id]
        hook_rel = layer.hooks.finalize if layer.hooks is not None else None
        if hook_rel is None:
            continue
        _run_hook(layer_id, _resolve_hook(layer, hook_rel), out, env)
        ran.append(layer_id)
    return ran


def _resolve_hook(layer: Layer, hook_rel: str) -> Path:
    if layer.source_dir is None:
        raise FinalizeError(
            f"layer '{layer.id}' declares a finalize hook but was not loaded from a directory"
        )
    hook = layer.source_dir / hook_rel
    if not hook.is_file():
        raise FinalizeError(f"layer '{layer.id}' finalize hook '{hook_rel}' not found at {hook}")
    return hook


def _run_hook(layer_id: str, hook: Path, out_dir: Path, env: Mapping[str, str]) -> None:
    try:
        # Absolute path: the hook runs with cwd=out_dir, so a path relative to the engine's cwd
        # would resolve against the wrong base (e.g. a relative --layers-dir).
        result = subprocess.run(
            [str(hook.resolve())],
            cwd=out_dir,
            env=dict(env),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise FinalizeError(
            f"layer '{layer_id}' finalize hook '{hook}' could not be executed ({exc}); "
            "it must be executable and carry a shebang"
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FinalizeError(
            f"layer '{layer_id}' finalize hook exited {result.returncode}: {detail}"
        )
