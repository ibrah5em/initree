"""recipe TDD harness — drives recipe.py (#15 recipe rendering, #16 token resolution).

Two dialects stand in for the ci layers that don't exist yet: a GitLab-flavoured one (bare $VAR
refs, predefined registry vars) and a GitHub-flavoured one (${{ secrets.X }}, ${{ github.sha }}).
The headline test renders the *same* backend-agnostic recipe through both and gets each backend's
native syntax with zero change to the recipe — the whole point of the two-tier split. Values mirror
the rendered proofs in docs/lifecycle §6 and docs/generalization §7.
"""

import pytest

from initree.recipe import (
    Dialect,
    MissingImageBaseError,
    SecretRef,
    UnknownTokenError,
    render_recipe,
    resolve_tokens,
    scan_secrets,
)

# GitLab: a secret renders to a bare $VAR; the registry credentials are predefined CI/CD variables,
# so they are overrides rather than the convention. Mirrors docs/generalization §3.6's token map.
GITLAB = Dialect(
    provider="gitlab-ci",
    short_sha="$CI_COMMIT_SHA",
    secrets={"registry": "$CI_REGISTRY_PASSWORD", "registry_user": "$CI_REGISTRY_USER"},
)

# GitHub: a secret renders to ${{ secrets.NAME }} via the prefix/suffix convention, no overrides.
GITHUB = Dialect(
    provider="gh-actions",
    short_sha="${{ github.sha }}",
    secret_prefix="${{ secrets.",
    secret_suffix=" }}",
)

# What the bus carries after compute: registry.image_name_base is untagged
# (docs/generalization §3.3).
BUS = {"registry.image_name_base": "registry.gitlab.com/myapp"}

# docker's container.build_recipe after compute: ${registry.host} concrete, tokens still deferred.
DOCKER_BUILD = [
    "docker login -u {{SECRET:registry_user}} -p {{SECRET:registry}} registry.gitlab.com/myapp",
    "docker build -t {{IMAGE}} .",
    "docker push {{IMAGE}}",
]


def test_renders_build_recipe_to_gitlab_native():
    assert render_recipe(DOCKER_BUILD, GITLAB, BUS) == [
        "docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD registry.gitlab.com/myapp",
        "docker build -t registry.gitlab.com/myapp:$CI_COMMIT_SHA .",
        "docker push registry.gitlab.com/myapp:$CI_COMMIT_SHA",
    ]


def test_same_recipe_renders_to_github_native():
    # The recipe is byte-for-byte the one GitLab rendered; only the dialect changed.
    assert render_recipe(DOCKER_BUILD, GITHUB, BUS) == [
        "docker login -u ${{ secrets.REGISTRY_USER }} -p ${{ secrets.REGISTRY }} "
        "registry.gitlab.com/myapp",
        "docker build -t registry.gitlab.com/myapp:${{ github.sha }} .",
        "docker push registry.gitlab.com/myapp:${{ github.sha }}",
    ]


def test_image_token_composes_base_and_sha():
    assert resolve_tokens("{{IMAGE}}", GITLAB, BUS) == "registry.gitlab.com/myapp:$CI_COMMIT_SHA"


def test_sha_token_is_the_dialects_short_sha():
    assert resolve_tokens("at {{SHA}}", GITHUB, BUS) == "at ${{ github.sha }}"


def test_secret_uses_override_then_convention():
    # registry is overridden; slack_webhook is not, so it falls back to the prefix/UPPER convention.
    assert resolve_tokens("{{SECRET:registry}}", GITLAB, BUS) == "$CI_REGISTRY_PASSWORD"
    assert resolve_tokens("{{SECRET:slack_webhook}}", GITLAB, BUS) == "$SLACK_WEBHOOK"
    assert resolve_tokens("{{SECRET:slack_webhook}}", GITHUB, BUS) == "${{ secrets.SLACK_WEBHOOK }}"


def test_secret_file_token_renders_a_file_variable():
    assert resolve_tokens("--kubeconfig {{SECRET_FILE:kubeconfig}}", GITLAB, BUS) == (
        "--kubeconfig $KUBECONFIG"
    )


def test_secret_file_is_matched_before_secret():
    # SECRET_FILE: must not be parsed as SECRET: with a "FILE:..." purpose.
    dialect = Dialect(
        provider="gitlab-ci",
        short_sha="$SHA",
        secret_files={"kubeconfig": "$KUBE_CONFIG"},
    )
    assert resolve_tokens("{{SECRET_FILE:kubeconfig}}", dialect, BUS) == "$KUBE_CONFIG"


def test_multiline_command_keeps_newlines_and_resolves_each_token():
    recipe = ["set -e\necho {{SHA}}\ndeploy {{IMAGE}}"]
    assert render_recipe(recipe, GITLAB, BUS) == [
        "set -e\necho $CI_COMMIT_SHA\ndeploy registry.gitlab.com/myapp:$CI_COMMIT_SHA",
    ]


def test_shell_syntax_is_left_untouched():
    # A single-brace shell ${VAR} and a $VAR are not tokens; only {{...}} is.
    assert resolve_tokens("run ${HOME}/bin $PATH", GITLAB, BUS) == "run ${HOME}/bin $PATH"


def test_unknown_token_is_rejected():
    with pytest.raises(UnknownTokenError, match="BOGUS"):
        resolve_tokens("{{BOGUS}}", GITLAB, BUS)


def test_hand_written_ci_syntax_is_rejected():
    # A layer wrongly emitting ci-native syntax instead of a token — the {{...}} inside is caught.
    with pytest.raises(UnknownTokenError, match="github.sha"):
        resolve_tokens("${{ github.sha }}", GITHUB, BUS)


def test_empty_secret_purpose_is_rejected():
    with pytest.raises(UnknownTokenError, match="names no secret purpose"):
        resolve_tokens("{{SECRET:}}", GITLAB, BUS)


def test_image_without_registry_base_is_rejected():
    with pytest.raises(MissingImageBaseError, match="registry.image_name_base"):
        resolve_tokens("{{IMAGE}}", GITLAB, bus={})


# scan_secrets — the observer side of the token grammar (#17 INITREE_SECRETS.md).


def test_scan_collects_masked_and_file_secrets():
    refs = scan_secrets(DOCKER_BUILD + ["kubectl --kubeconfig {{SECRET_FILE:kubeconfig}} apply"])
    assert refs == [
        SecretRef(purpose="registry_user", is_file=False),
        SecretRef(purpose="registry", is_file=False),
        SecretRef(purpose="kubeconfig", is_file=True),
    ]


def test_scan_dedupes_across_commands_keeping_first_seen_order():
    refs = scan_secrets(
        ["a {{SECRET:registry}}", "b {{SECRET:slack_webhook}}", "c {{SECRET:registry}}"]
    )
    assert refs == [
        SecretRef(purpose="registry", is_file=False),
        SecretRef(purpose="slack_webhook", is_file=False),
    ]


def test_scan_ignores_image_and_sha():
    # IMAGE and SHA are runtime refs, not secrets — they never belong on the provisioning checklist.
    assert scan_secrets(["docker build -t {{IMAGE}} . at {{SHA}}"]) == []


def test_scan_is_lenient_on_malformed_and_unknown_tokens():
    # The observer reports what it recognizes; resolve_tokens is the one that rejects these.
    assert scan_secrets(["{{SECRET:}}", "{{BOGUS}}", "${{ github.sha }}"]) == []


def test_scan_keeps_masked_and_file_of_the_same_purpose_distinct():
    refs = scan_secrets(["{{SECRET:registry}}", "{{SECRET_FILE:registry}}"])
    assert refs == [
        SecretRef(purpose="registry", is_file=False),
        SecretRef(purpose="registry", is_file=True),
    ]
