#!/usr/bin/env python3
"""gitlab-ci compute hook: turn the consumed recipes into native `script:` lines.

The ci slot is the sole resolver of deferred {{...}} tokens (docs/03 §7, §9) — only it knows the
runtime's native syntax. This reads the backend-agnostic recipes the engine exported onto the
environment, resolves their tokens through GitLab CI's dialect, and prints the script lines keyed by
the ":hook" provides the manifest declares. The pipeline template then splices each block under its
job's `script:`.

Only the token map and the file structure differ from the gh-actions hook; the recipes it consumes
are identical. That is the whole point of the recipe boundary (docs/02 §6) — swap the ci layer,
every other layer is untouched.

Indentation is owned here: the lines come back ready to sit under a job's `script:` (four spaces,
one `- ` item per command), so the engine's plain ${...} substitution drops them in correctly.
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

# GitLab native syntax: the commit is $CI_COMMIT_SHA; the registry credential pair is predefined
# (CI_REGISTRY_USER / CI_REGISTRY_PASSWORD), so those purposes are explicit overrides. Every other
# purpose renders through the default convention ($UPPER), e.g. slack_webhook -> $SLACK_WEBHOOK.
GITLAB = Dialect(
    provider="gitlab-ci",
    short_sha="$CI_COMMIT_SHA",
    secrets={"registry": "$CI_REGISTRY_PASSWORD", "registry_user": "$CI_REGISTRY_USER"},
)

SCRIPT_INDENT = " " * 4  # `- ` items under a job's `script:`


def _recipe(env_key: str) -> list[str]:
    """A recipe the engine exported as INITREE_<KEY> JSON, or [] when the key is absent."""
    value = json.loads(os.environ.get(env_key, "[]"))
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def _script(commands: list[str]) -> str:
    """The commands as `script:` list items. Empty string when the recipe is absent, so the template
    can drop the whole job with `initree:if`."""
    return "\n".join(
        f"{SCRIPT_INDENT}- {line}" for command in commands for line in command.split("\n")
    )


def main() -> None:
    bus = {"registry.image_name_base": os.environ["INITREE_REGISTRY_IMAGE_NAME_BASE"]}

    build = render_recipe(_recipe("INITREE_CONTAINER_BUILD_RECIPE"), GITLAB, bus)
    deploy = render_recipe(_recipe("INITREE_DEPLOY_APPLY_RECIPE"), GITLAB, bus)
    notify = render_recipe(_recipe("INITREE_NOTIFY_SEND_RECIPE"), GITLAB, bus)

    print(
        json.dumps(
            {
                "ci.gitlab_ci.build_script": _script(build),
                "ci.gitlab_ci.deploy_script": _script(deploy),
                "ci.gitlab_ci.notify_script": _script(notify),
            }
        )
    )


if __name__ == "__main__":
    main()
