"""podman is a drop-in for docker: swapping the container slot touches no other layer.

Builds the slice-1 recipe twice — once with docker, once with podman — and asserts the two emitted
trees differ only where they must: the container-owned files (Dockerfile/.dockerignore vs
Containerfile/.containerignore) and the two files that render the container's recipes
(.github/workflows/ci.yml, deploy/deploy.sh). Everything else is byte-identical. That is the
concrete proof of the docker->podman swap claim in CLAUDE.md and docs/registry — a consumer binds to
container.*, never to the tool, so the swap radius is the container slot itself.

The docker side is byte-locked by test_golden_slice1, so every shared file the swap doesn't touch is
transitively locked here too.
"""

from pathlib import Path

from initree.lifecycle import build, engine_seed
from initree.manifest import load_selected
from initree.prompt import defaults

LAYERS = Path(__file__).resolve().parents[1] / "layers"
DOCKER_RECIPE = ["python", "fastapi", "docker", "gh-actions", "vps-ssh"]
PODMAN_RECIPE = ["python", "fastapi", "podman", "gh-actions", "vps-ssh"]

# The only files allowed to differ across the swap: the container slot owns these names, or they
# render the container's build/deploy recipes.
RUNTIME_RENDERED = {".github/workflows/ci.yml", "deploy/deploy.sh"}


def _build(recipe: list[str], out_dir: Path):
    layers = load_selected(LAYERS, recipe)
    result = build(layers, seed=engine_seed("myapp", out_dir), ask=defaults, out_dir=out_dir)
    return result, out_dir


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_podman_provides_the_same_container_contract(tmp_path):
    result, _ = _build(PODMAN_RECIPE, tmp_path / "podman")
    # the keys consumers bind to are the same ones docker provides, just a different runtime id
    assert result.bus["container.runtime"] == "podman"
    assert result.bus["container.image_name"] == "myapp"
    assert result.bus["container.exposed_port"] == 8000
    assert result.bus["registry.image_name_base"] == "ghcr.io/your-org/myapp"


def test_swap_radius_is_the_container_slot_only(tmp_path):
    _, docker_out = _build(DOCKER_RECIPE, tmp_path / "docker")
    _, podman_out = _build(PODMAN_RECIPE, tmp_path / "podman")
    docker_tree, podman_tree = _tree(docker_out), _tree(podman_out)

    # the file sets differ only by the container-owned filenames
    assert set(docker_tree) - set(podman_tree) == {"Dockerfile", ".dockerignore"}
    assert set(podman_tree) - set(docker_tree) == {"Containerfile", ".containerignore"}

    # every shared file is byte-identical except the two that render the container's recipes
    shared = set(docker_tree) & set(podman_tree)
    drifted = {rel for rel in shared if docker_tree[rel] != podman_tree[rel]}
    assert drifted == RUNTIME_RENDERED


def test_podman_commands_render_into_ci_and_the_deploy_script(tmp_path):
    _, out = _build(PODMAN_RECIPE, tmp_path / "podman")
    workflow = (out / ".github/workflows/ci.yml").read_text()
    assert "podman build -t ghcr.io/your-org/myapp:${{ github.sha }} ." in workflow
    assert "podman login ghcr.io" in workflow
    assert "podman pull" in workflow and "podman run" in workflow
    # the swap is total: no docker token survives anywhere in the rendered pipeline
    assert "docker " not in workflow

    script = (out / "deploy/deploy.sh").read_text()
    assert "podman pull" in script and "podman run" in script
    assert "docker " not in script


def test_containerfile_mirrors_the_dockerfile_minus_the_buildkit_directive(tmp_path):
    _, docker_out = _build(DOCKER_RECIPE, tmp_path / "docker")
    _, podman_out = _build(PODMAN_RECIPE, tmp_path / "podman")
    containerfile = (podman_out / "Containerfile").read_text()
    # podman ignores the BuildKit `# syntax=` frontend directive; the OCI build is otherwise equal
    assert not containerfile.startswith("# syntax")
    assert containerfile == (docker_out / "Dockerfile").read_text().split("\n", 1)[1]
    assert "FROM python:3.12-slim" in containerfile
    assert "EXPOSE 8000" in containerfile
    assert "CMD uvicorn app.main:app --host 0.0.0.0 --port 8000" in containerfile
