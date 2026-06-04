#!/usr/bin/env python3
"""gh-actions compute hook: turn the consumed recipes into native workflow step blocks.

The ci slot is the sole resolver of deferred {{...}} tokens (docs/03 §7, §9) — only it knows the
runtime's native syntax. This reads the backend-agnostic recipes the engine exported onto the
environment, resolves their tokens through GitHub Actions' dialect, and prints the YAML step blocks
keyed by the ":hook" provides the manifest declares. The workflow template then splices those blocks
into jobs.build.steps / jobs.deploy.steps.

Indentation is owned here: the blocks come back ready to sit under a job's `steps:` (the template
references each on its own line), so the engine's plain ${...} substitution drops them in correctly.
"""

from __future__ import annotations

import json
import os

try:
    from initree.recipe import Dialect, render_recipe
except ModuleNotFoundError:
    # Installed initree is the normal path; this fallback only fires when the engine runs from a
    # source checkout whose interpreter differs from the hook's python3. Walk up to the package src.
    import pathlib
    import sys

    for _parent in pathlib.Path(__file__).resolve().parents:
        if (_parent / "src" / "initree" / "__init__.py").is_file():
            sys.path.insert(0, str(_parent / "src"))
            break
    from initree.recipe import Dialect, render_recipe

# GitHub Actions native syntax: secrets ${{ secrets.NAME }}, the commit ${{ github.sha }}.
GITHUB = Dialect(
    provider="gh-actions",
    short_sha="${{ github.sha }}",
    secret_prefix="${{ secrets.",
    secret_suffix=" }}",
)

STEP_INDENT = " " * 6  # `- name:` under jobs.<job>.steps
RUN_INDENT = " " * 10  # lines inside a `run: |` block scalar


def _recipe(env_key: str) -> list[str]:
    """A recipe the engine exported as INITREE_<KEY> JSON, or [] when the key is absent."""
    value = json.loads(os.environ.get(env_key, "[]"))
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _run_step(name: str, commands: list[str]) -> str:
    lines = [f"{STEP_INDENT}- name: {name}", f"{STEP_INDENT}  run: |"]
    for command in commands:
        lines.extend(f"{RUN_INDENT}{line}" for line in command.split("\n"))
    return "\n".join(lines)


def main() -> None:
    bus = {"registry.image_name_base": os.environ["INITREE_REGISTRY_IMAGE_NAME_BASE"]}

    build = render_recipe(_recipe("INITREE_CONTAINER_BUILD_RECIPE"), GITHUB, bus)
    deploy = render_recipe(_recipe("INITREE_DEPLOY_APPLY_RECIPE"), GITHUB, bus)
    notify = render_recipe(_recipe("INITREE_NOTIFY_SEND_RECIPE"), GITHUB, bus)

    deploy_steps = [_run_step("Deploy over SSH", deploy)]
    if notify:
        deploy_steps.append(_run_step("Notify", notify))

    print(
        json.dumps(
            {
                "ci.gh_actions.build_steps": _run_step("Build and push image", build),
                "ci.gh_actions.deploy_steps": "\n".join(deploy_steps),
            }
        )
    )


if __name__ == "__main__":
    main()
