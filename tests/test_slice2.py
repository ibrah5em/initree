"""Slice 2 end-to-end: build go+gin+docker+gitlab-ci+k8s+slack from the real layers/.

The generalization proof made concrete (docs/02). A stack that differs from slice 1 in every
dimension — compiled language, multi-stage container, a different CI structure, a namespaced deploy
target, and an optional notify slot — composes through the same engine and the same docker layer.
app.port flows from gin through container.exposed_port into the k8s manifests; gin's dependency
injects into go's go.mod via text-block; and gitlab-ci (the second assembler) renders every consumed
recipe into GitLab-native `script:` lines, resolving the {{TOKEN}}s nobody upstream may.
"""

from pathlib import Path

import pytest
from ruamel.yaml import YAML

from initree.lifecycle import build, engine_seed
from initree.manifest import Layer, load_selected
from initree.prompt import defaults

LAYERS = Path(__file__).resolve().parents[1] / "layers"
RECIPE = ["go", "gin", "docker", "gitlab-ci", "k8s", "slack"]


def _build(tmp_path: Path):
    layers = load_selected(LAYERS, RECIPE)
    out = tmp_path / "myapp"
    return build(layers, seed=engine_seed("myapp", out), ask=defaults, out_dir=out), out


def _yaml(path: Path):
    return YAML(typ="safe").load(path.read_text())


def test_slice_resolves_to_the_expected_topological_order(tmp_path):
    result, _ = _build(tmp_path)
    # ci sorts last (terminal assembler); slack after k8s because it consumes deploy.summary.
    assert result.order == ["go", "gin", "docker", "k8s", "slack", "gitlab-ci"]


def test_port_flows_from_framework_to_container_to_the_k8s_manifests(tmp_path):
    result, out = _build(tmp_path)
    # app.port (gin) -> container.exposed_port (docker) -> the k8s containerPort / targetPort.
    assert result.bus["app.port"] == 8080
    assert result.bus["container.exposed_port"] == 8080
    deployment = _yaml(out / "k8s/deployment.yaml")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["ports"][0]["containerPort"] == 8080
    assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
    service = _yaml(out / "k8s/service.yaml")
    assert service["spec"]["ports"][0]["targetPort"] == 8080


def test_framework_dep_injects_into_the_language_go_mod(tmp_path):
    _, out = _build(tmp_path)
    go_mod = (out / "go.mod").read_text()
    assert "module myapp" in go_mod
    # text-block injection between the markers go declares — the same primitive python used, format
    # text-block instead of toml-array.
    lines = go_mod.splitlines()
    start = next(i for i, ln in enumerate(lines) if ">>> initree:inject runtime.dependencies" in ln)
    end = next(i for i, ln in enumerate(lines) if "<<< initree:inject runtime.dependencies" in ln)
    dep = next(i for i, ln in enumerate(lines) if "github.com/gin-gonic/gin v1.10.0" in ln)
    assert start < dep < end


def test_docker_renders_a_multi_stage_image_for_the_compiled_language(tmp_path):
    _, out = _build(tmp_path)
    dockerfile = (out / "Dockerfile").read_text()
    assert "FROM golang:1.22 AS build" in dockerfile
    assert "RUN CGO_ENABLED=0 go build -o /out/server ./cmd/server" in dockerfile
    assert "FROM gcr.io/distroless/static-debian12" in dockerfile
    assert "COPY --from=build /out/server /server" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert 'ENTRYPOINT ["/server"]' in dockerfile
    # the single-stage (python) branch never rendered — no uv, no CMD
    assert "astral-sh/uv" not in dockerfile
    assert "\nCMD " not in dockerfile


def test_ci_layer_renders_recipes_into_gitlab_native_tokens(tmp_path):
    result, out = _build(tmp_path)
    assert result.bus["ci.provider"] == "gitlab-ci"
    pipeline = (out / ".gitlab-ci.yml").read_text()
    # {{IMAGE}} -> base:$CI_COMMIT_SHA, the predefined registry credential pair, {{SECRET}} -> $VAR.
    assert "docker build -t ghcr.io/your-org/myapp:$CI_COMMIT_SHA ." in pipeline
    assert "docker login ghcr.io -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD" in pipeline
    assert (
        "cd k8s && kustomize edit set image app=ghcr.io/your-org/myapp:$CI_COMMIT_SHA && cd .."
        in pipeline
    )
    # the kubeconfig file-token resolves to GitLab's file-variable convention ($KUBECONFIG)
    assert "kubectl --kubeconfig $KUBECONFIG apply -k k8s/ -n default" in pipeline
    # no engine/deferred token survives the ci render (GitLab's own $VARs are fine)
    assert "{{IMAGE}}" not in pipeline
    assert "{{SECRET" not in pipeline
    assert "{{SHA}}" not in pipeline


def test_gitlab_pipeline_is_well_formed_with_the_expected_stages(tmp_path):
    _, out = _build(tmp_path)
    pipeline = _yaml(out / ".gitlab-ci.yml")
    assert pipeline["stages"] == ["test", "build", "deploy", "notify"]
    assert pipeline["test"]["image"] == "golang:1.22"
    assert pipeline["build_image"]["stage"] == "build"
    # the deploy job's image comes from the deploy layer (deploy.runtime_image), not a ci hardcode;
    # the kubeconfig rides the recipe as a token, so there's no leftover hardcoded variables block.
    assert pipeline["deploy"]["image"] == "bitnami/kubectl:latest"
    assert "variables" not in pipeline["deploy"]


def test_test_job_is_rendered_from_language_capabilities(tmp_path):
    _, out = _build(tmp_path)
    # the test job is no longer hardcoded per language: image + script come from runtime.* keys.
    # go's image already carries the toolchain, so there's no setup step — just install then test.
    pipeline = _yaml(out / ".gitlab-ci.yml")
    assert pipeline["test"]["script"] == ["go mod download", "go test ./..."]


def test_optional_notify_renders_a_job_from_the_slack_recipe(tmp_path):
    result, out = _build(tmp_path)
    # deploy.summary is the only channel a namespace-private fact (ns, replicas) reaches slack.
    assert result.bus["deploy.summary"] == "kubernetes · ns/default · 2 replicas"
    pipeline = _yaml(out / ".gitlab-ci.yml")
    notify_script = pipeline["notify"]["script"]
    assert any(
        "✅ myapp deployed — kubernetes · ns/default · 2 replicas" in line for line in notify_script
    )
    assert any("$SLACK_WEBHOOK" in line for line in notify_script)


def test_secret_purposes_are_compiled_from_the_recipes(tmp_path):
    result, out = _build(tmp_path)
    assert result.secrets_report == out / "INITREE_SECRETS.md"
    report = (out / "INITREE_SECRETS.md").read_text()
    assert "`registry`" in report
    assert "`registry_user`" in report
    assert "`slack_webhook`" in report
    # the kubeconfig file-token in the k8s deploy recipe lands in the checklist under file-type vars
    assert "`kubeconfig`" in report
    assert "## File-type variables" in report


def test_docker_is_the_same_manifest_that_serves_slice_1(tmp_path):
    # The swap-radius proof (docs/02 §8): docker's manifest is byte-identical across slices. It
    # declares the build keys as OPTIONAL consumes, so one manifest handles both interpreted
    # (absent) and compiled (present) languages; only the owned Dockerfile branches.
    docker = Layer.from_yaml(LAYERS / "docker" / "layer.yaml")
    optional = {c.key for c in docker.consumes if not c.required}
    assert {"runtime.build_cmd", "runtime.artifact", "runtime.run_base_image"} <= optional
    assert any(p.key == "container.build_recipe" for p in docker.provides)
    # nothing language-specific leaked into the container manifest
    text = (LAYERS / "docker" / "layer.yaml").read_text()
    assert "golang" not in text and "uv" not in text


@pytest.mark.parametrize("path", ["go.mod", "Dockerfile", ".gitlab-ci.yml", "cmd/server/main.go"])
def test_owned_files_are_rendered(tmp_path, path):
    _, out = _build(tmp_path)
    assert (out / path).is_file()
