"""Slice 3 end-to-end: build node+express+docker+gh-actions+vps-ssh from the real layers/.

The third stack, and the first to exercise the json-array (package.json) dependency injection and
the language-agnostic single-stage container. Proves the same contract composes for an interpreted,
non-python language: express's dep lands in package.json's array, app.port flows two hops to the
deploy step, the container renders a clean single-stage with no python toolchain, and the ci layer
picks node's native toolchain setup from runtime.language.
"""

import json
from pathlib import Path

from ruamel.yaml import YAML

from initree.lifecycle import build, engine_seed
from initree.manifest import load_selected
from initree.prompt import defaults

LAYERS = Path(__file__).resolve().parents[1] / "layers"
RECIPE = ["node", "express", "docker", "gh-actions", "vps-ssh"]


def _build(tmp_path: Path):
    layers = load_selected(LAYERS, RECIPE)
    out = tmp_path / "myapp"
    return build(layers, seed=engine_seed("myapp", out), ask=defaults, out_dir=out), out


def test_slice_resolves_to_the_expected_topological_order(tmp_path):
    result, _ = _build(tmp_path)
    # ci sorts last; deploy before it because ci consumes deploy.apply_recipe.
    assert result.order == ["node", "express", "docker", "vps-ssh", "gh-actions"]


def test_express_dep_injects_into_the_package_json_array(tmp_path):
    _, out = _build(tmp_path)
    manifest = json.loads((out / "package.json").read_text())
    # the language owns package.json; express contributes its dep through the json-array point
    assert manifest["dependencies"] == ["express@^4.18.2"]
    assert isinstance(manifest["dependencies"], list)
    assert manifest["name"] == "myapp"


def test_port_flows_from_framework_to_container_to_deploy(tmp_path):
    result, out = _build(tmp_path)
    # app.port (express) -> container.exposed_port (docker) -> the deploy step's -p 80:3000.
    assert result.bus["app.port"] == 3000
    assert result.bus["container.exposed_port"] == 3000
    workflow = (out / ".github/workflows/ci.yml").read_text()
    assert "-p 80:3000" in workflow


def test_ci_test_job_uses_nodes_native_toolchain(tmp_path):
    _, out = _build(tmp_path)
    workflow = YAML(typ="safe").load((out / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["test"]["steps"]
    assert {"uses": "actions/setup-node@v4", "with": {"node-version-file": ".nvmrc"}} in steps
    assert {"run": "npm test"} in steps


def test_container_is_a_clean_single_stage_for_node(tmp_path):
    _, out = _build(tmp_path)
    dockerfile = (out / "Dockerfile").read_text()
    assert "FROM node:20-slim" in dockerfile
    assert "EXPOSE 3000" in dockerfile
    assert "CMD node src/index.js" in dockerfile
    # the python single-stage prep never leaks into a node image
    assert "uv" not in dockerfile
    assert ".venv" not in dockerfile


def test_nvmrc_pins_the_runtime_version(tmp_path):
    _, out = _build(tmp_path)
    assert (out / ".nvmrc").read_text().strip() == "20"


def test_secret_purposes_are_compiled_from_the_build_recipe(tmp_path):
    result, out = _build(tmp_path)
    report = result.secrets_report
    assert report == out / "INITREE_SECRETS.md"
    text = report.read_text()
    assert "`registry`" in text
    assert "`registry_user`" in text
