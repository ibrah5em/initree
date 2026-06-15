"""secrets TDD harness — drives secrets.py (#17 INITREE_SECRETS.md generation).

Loads the valid-full manifests (which declare the recipe-typed keys: container.build_recipe,
deploy.apply_recipe, notify.send_recipe) and pairs them with a synthetic frozen bus carrying those
recipes with their {{SECRET:...}} tokens still deferred — the state after compute. The report is an
observer over that bus: it reads the purposes the recipes declare and leaves token validation to the
ci render. Purposes mirror docs/generalization §5 and the registry's secret_purposes table.
"""

from pathlib import Path

from initree.manifest import load_recipe
from initree.recipe import SecretRef
from initree.secrets import REPORT_NAME, observed_secrets, render_report, write_secret_report

FIXTURES = Path(__file__).parent / "fixtures"

# What the bus carries after compute for the valid-full recipe: each recipe key with concrete
# ${...} already resolved and {{...}} tokens still deferred for the ci layer.
SECRET_BUS = {
    "container.build_recipe": [
        "docker login -u {{SECRET:registry_user}} -p {{SECRET:registry}} registry.gitlab.com/myapp",
        "docker build -t {{IMAGE}} .",
        "docker push {{IMAGE}}",
    ],
    "deploy.apply_recipe": [
        "kubectl --kubeconfig {{SECRET_FILE:kubeconfig}} apply -f k8s/",
    ],
    "notify.send_recipe": [
        "curl -sf -X POST -d 'deployed' {{SECRET:slack_webhook}}",
    ],
}


def test_observed_secrets_reads_every_recipe_on_the_bus():
    layers = load_recipe(FIXTURES / "valid-full")

    refs = observed_secrets(layers, SECRET_BUS)

    # registry/registry_user from build, kubeconfig from deploy, slack_webhook from notify
    assert set(refs) == {
        SecretRef(purpose="registry_user", is_file=False),
        SecretRef(purpose="registry", is_file=False),
        SecretRef(purpose="kubeconfig", is_file=True),
        SecretRef(purpose="slack_webhook", is_file=False),
    }


def test_observed_secrets_empty_when_no_recipe_uses_a_secret():
    layers = load_recipe(FIXTURES / "valid-full")
    bus = {"container.build_recipe": ["docker build -t {{IMAGE}} .", "docker push {{IMAGE}}"]}

    assert observed_secrets(layers, bus) == []


def test_render_splits_masked_from_file_and_describes_each_from_the_registry():
    refs = [
        SecretRef(purpose="registry", is_file=False),
        SecretRef(purpose="slack_webhook", is_file=False),
        SecretRef(purpose="kubeconfig", is_file=True),
    ]

    report = render_report(refs)

    assert "## Masked variables" in report
    assert "## File-type variables" in report
    # purposes are described with the registry note, not invented here
    assert "- `registry` — registry password/token (push)" in report
    assert "- `kubeconfig` — cluster credentials (file)" in report
    # masked sorts before the file section; within a section, alpha
    assert report.index("registry password") < report.index("cluster credentials")
    assert report.index("- `registry`") < report.index("- `slack_webhook`")


def test_render_omits_a_section_with_no_secrets():
    report = render_report([SecretRef(purpose="registry", is_file=False)])

    assert "## Masked variables" in report
    assert "## File-type variables" not in report


def test_render_flags_a_purpose_off_the_registry_vocabulary():
    report = render_report([SecretRef(purpose="mystery", is_file=False)])

    assert "- `mystery` — not in capability registry v1" in report


def test_write_report_creates_the_file_when_secrets_are_declared(tmp_path):
    layers = load_recipe(FIXTURES / "valid-full")

    path = write_secret_report(layers, SECRET_BUS, tmp_path)

    assert path is not None
    assert path == tmp_path / REPORT_NAME
    assert "Secrets to provision" in path.read_text()


def test_write_report_skips_the_file_when_nothing_to_provision(tmp_path):
    layers = load_recipe(FIXTURES / "valid-full")
    bus = {"container.build_recipe": ["docker build -t {{IMAGE}} ."]}

    assert write_secret_report(layers, bus, tmp_path) is None
    assert not (tmp_path / REPORT_NAME).exists()
