"""Slice 1 end-to-end: build python+fastapi+docker+gh-actions+vps-ssh from the real layers/.

Not a fixture run — this loads the shipped layers under layers/ and proves the first real recipe
composes: the capability bus carries app.port two hops to the deploy step, deps inject into the
language's pyproject, and the ci layer renders the container/deploy recipes into GitHub-native
syntax, resolving the {{TOKEN}}s nobody upstream is allowed to. Mirrors the rendered proof in
docs/01 §6, adapted to the recipe-based contract (docs/03).
"""

from pathlib import Path

from initree.lifecycle import build, engine_seed
from initree.manifest import load_selected
from initree.prompt import defaults

LAYERS = Path(__file__).resolve().parents[1] / "layers"
RECIPE = ["python", "fastapi", "docker", "gh-actions", "vps-ssh"]


def _build(tmp_path: Path):
    layers = load_selected(LAYERS, RECIPE)
    out = tmp_path / "myapp"
    return build(layers, seed=engine_seed("myapp", out), ask=defaults, out_dir=out), out


def test_slice_resolves_to_the_expected_topological_order(tmp_path):
    result, _ = _build(tmp_path)
    # ci sorts last (terminal assembler); deploy before it because ci consumes deploy.apply_recipe.
    assert result.order == ["python", "fastapi", "docker", "vps-ssh", "gh-actions"]


def test_port_flows_from_framework_to_container_to_deploy(tmp_path):
    result, out = _build(tmp_path)
    # app.port (fastapi) -> container.exposed_port (docker) -> the deploy step's -p 80:8000.
    assert result.bus["app.port"] == 8000
    assert result.bus["container.exposed_port"] == 8000
    workflow = (out / ".github/workflows/ci.yml").read_text()
    assert "-p 80:8000" in workflow


def test_framework_deps_inject_into_the_language_manifest(tmp_path):
    _, out = _build(tmp_path)
    pyproject = (out / "pyproject.toml").read_text()
    # alpha order within the point; the language owns the file, fastapi contributes the deps.
    assert 'dependencies = ["fastapi>=0.110", "uvicorn[standard]>=0.29"]' in pyproject
    assert 'name = "myapp"' in pyproject


def test_ci_layer_renders_recipes_into_github_native_tokens(tmp_path):
    _, out = _build(tmp_path)
    workflow = (out / ".github/workflows/ci.yml").read_text()
    # {{IMAGE}} -> base:sha, {{SECRET:...}} -> ${{ secrets.* }} — resolved only by the ci slot.
    login = "docker login ghcr.io -u ${{ secrets.REGISTRY_USER }} -p ${{ secrets.REGISTRY }}"
    assert "docker build -t ghcr.io/myapp:${{ github.sha }} ." in workflow
    assert login in workflow
    assert 'ssh deploy@example.com "docker pull ghcr.io/myapp:${{ github.sha }}' in workflow
    # no engine token survives the ci render (GitHub's own ${{ ... }} is fine)
    assert "{{IMAGE}}" not in workflow
    assert "{{SECRET" not in workflow
    assert "{{SHA}}" not in workflow


def test_deploy_script_is_owned_rendered_and_executable(tmp_path):
    _, out = _build(tmp_path)
    script = out / "deploy/deploy.sh"
    text = script.read_text()
    # engine ${...} refs resolved; the shell's own $1/$image left untouched.
    assert 'image="ghcr.io/myapp:$1"' in text
    assert "--name myapp -p 80:8000" in text
    # the finalize hook chmod'd it
    import os

    assert os.access(script, os.X_OK)


def test_dockerfile_carries_the_runtime_and_app_contract(tmp_path):
    _, out = _build(tmp_path)
    dockerfile = (out / "Dockerfile").read_text()
    assert "FROM python:3.12-slim" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "CMD uvicorn app.main:app --host 0.0.0.0 --port 8000" in dockerfile


def test_secret_purposes_are_compiled_from_the_build_recipe(tmp_path):
    result, out = _build(tmp_path)
    report_path = result.secrets_report
    assert report_path == out / "INITREE_SECRETS.md"
    assert report_path is not None
    report = report_path.read_text()
    assert "`registry`" in report
    assert "`registry_user`" in report
