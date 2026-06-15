#!/usr/bin/env python3
"""gh-actions compute hook: turn the consumed recipes into native workflow step blocks.

The ci slot is the sole resolver of deferred {{...}} tokens (docs/registry §7, §9) — only it knows
the runtime's native syntax. This reads the backend-agnostic recipes the engine exported onto the
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

# Toolchain setup per language, as GitHub Actions steps. The ubuntu-latest runner ships neither uv
# nor a pinned Go, so each language brings its native setup action. Keyed on the neutral
# runtime.language so the test job composes with any language the assembler knows — the test command
# itself comes from runtime.test_cmd, never hardcoded here.
TEST_SETUP = {
    "python": ["- uses: astral-sh/setup-uv@v3"],
    "go": ["- uses: actions/setup-go@v5", "  with:", "    go-version-file: go.mod"],
}


def _test_steps() -> str:
    """The test job steps: language toolchain setup, then the install and test commands as plain
    `run:` steps (the commands the language layer provides carry no {{TOKEN}}s)."""
    language = os.environ.get("INITREE_RUNTIME_LANGUAGE", "")
    lines = [
        *TEST_SETUP.get(language, []),
        f"- run: {os.environ['INITREE_RUNTIME_INSTALL_CMD']}",
        f"- run: {os.environ['INITREE_RUNTIME_TEST_CMD']}",
    ]
    return "\n".join(f"{STEP_INDENT}{line}" for line in lines)


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
                "ci.gh_actions.test_steps": _test_steps(),
                "ci.gh_actions.build_steps": _run_step("Build and push image", build),
                "ci.gh_actions.deploy_steps": "\n".join(deploy_steps),
            }
        )
    )


if __name__ == "__main__":
    main()
