"""emit TDD harness — drives emit.py.

The slice test runs the real pipeline (load -> resolve -> compute -> emit) over a fixture with full
templates and proves both passes: every owned template is rendered against the frozen bus, and the
two text-format injection points (text-block deps, alpha-ordered line ignores) are spliced into the
owner's file. The rest are focused tests — toml-array injection, the single-ownership guard, and one
per rejection path (write outside owns, two writers, missing target, unimplemented format).
"""

from pathlib import Path

import pytest
import tomlkit

from initree.context import Bus, compute
from initree.emit import (
    InjectionError,
    OwnershipError,
    TemplateRenderError,
    UnsupportedInjectionFormat,
    emit,
    render_text,
)
from initree.manifest import Inject, InjectionPoint, Layer, load_recipe
from initree.resolve import resolve

FIXTURES = Path(__file__).parent / "fixtures"

# Engine keys plus the input answers compute needs to resolve the slice's provides.
EMIT_SEED = {
    "project.name": "myapp",
    "project.slug": "myapp",
    "project.dir": "/tmp/myapp",
    "git.is_repo": False,
    "runtime.version": "1.22",
    "app.port": 8080,
    "app.entrypoint": "./cmd/server",
}


def _layer(layer_id, slot, *, owns=None, points=None, injects=None, source_dir=None) -> Layer:
    layer = Layer(
        apiVersion="initree.dev/v1",
        id=layer_id,
        slot=slot,
        name=layer_id,
        owns=owns or [],
        injection_points=points or [],
        injects=injects or [],
    )
    layer.source_dir = source_dir
    return layer


def _template(root: Path, rel: str, content: str) -> Path:
    path = root / "templates" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return root


def test_emit_renders_and_injects_the_slice(tmp_path):
    layers = load_recipe(FIXTURES / "emit-slice")
    order = resolve(layers)
    bus = compute(layers, order, EMIT_SEED)
    out = tmp_path / "myapp"

    written = emit(layers, order, bus, out)

    # 4a — templates rendered against the bus, written under the output dir
    go_mod = (out / "go.mod").read_text()
    assert "module myapp" in go_mod
    assert "go 1.22" in go_mod

    dockerfile = (out / "Dockerfile").read_text()
    assert "FROM golang:1.22 AS build" in dockerfile
    assert "RUN CGO_ENABLED=0 go build -o /out/server ./cmd/server" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert 'ENTRYPOINT ["/server"]' in dockerfile
    assert (out / "cmd" / "main.go").read_text().splitlines()[2] == "// myapp listens on :8080"
    assert (out / "go.mod") in written

    # 4b — text-block dep spliced between the markers in the require block
    lines = go_mod.splitlines()
    start = next(
        i for i, line in enumerate(lines) if ">>> initree:inject runtime.dependencies" in line
    )
    end = next(
        i for i, line in enumerate(lines) if "<<< initree:inject runtime.dependencies" in line
    )
    dep = next(i for i, line in enumerate(lines) if "github.com/gin-gonic/gin v1.10.0" in line)
    assert start < dep < end

    # 4b — line injection, alpha-ordered: '*.log' (0x2a) sorts before '/server' (0x2f)
    ignore = (out / ".gitignore").read_text()
    assert "*.log" in ignore and "/server" in ignore
    assert ignore.index("*.log") < ignore.index("/server")


def test_emit_injects_into_a_toml_array_in_alpha_order(tmp_path):
    src = _template(
        tmp_path / "python",
        "pyproject.toml",
        '[project]\nname = "${project.name}"\ndependencies = []\n',
    )
    python = _layer(
        "python",
        "language",
        owns=["pyproject.toml"],
        points=[
            InjectionPoint(
                id="runtime.dependencies",
                file="pyproject.toml",
                format="toml-array",
                anchor="[project].dependencies",
                order="alpha",
            )
        ],
        source_dir=src,
    )
    web = _layer(
        "web",
        "framework",
        owns=["app/**"],
        injects=[
            Inject(
                into="runtime.dependencies",
                format="toml-array",
                items=["uvicorn[standard]>=0.29", "fastapi>=0.110"],
            )
        ],
    )
    out = tmp_path / "out"

    emit([python, web], ["python", "web"], Bus({"project.name": "myapp"}), out)

    doc = tomlkit.parse((out / "pyproject.toml").read_text())
    assert list(doc["project"]["dependencies"]) == ["fastapi>=0.110", "uvicorn[standard]>=0.29"]
    assert doc["project"]["name"] == "myapp"


def test_render_text_resolves_refs_and_defers_runtime_tokens():
    bus = Bus({"project.slug": "myapp"})
    assert render_text("image ${project.slug} at {{SHA}}", bus) == "image myapp at {{SHA}}"


def test_render_text_is_loud_on_an_unknown_reference():
    with pytest.raises(TemplateRenderError):
        render_text("${nope.missing}", Bus({}))


def test_emit_rejects_a_render_outside_the_layers_owns(tmp_path):
    src = _template(tmp_path / "rogue", "secrets.env", "x")
    rogue = _layer("rogue", "language", owns=["allowed.txt"], source_dir=src)
    with pytest.raises(OwnershipError):
        emit([rogue], ["rogue"], Bus({}), tmp_path / "out")


def test_emit_rejects_two_writers_of_the_same_path(tmp_path):
    first = _template(tmp_path / "first", "shared.txt", "a")
    second = _template(tmp_path / "second", "shared.txt", "b")
    layer_a = _layer("first", "language", owns=["shared.txt"], source_dir=first)
    layer_b = _layer("second", "framework", owns=["shared.txt"], source_dir=second)
    with pytest.raises(OwnershipError):
        emit([layer_a, layer_b], ["first", "second"], Bus({}), tmp_path / "out")


def test_emit_rejects_injection_into_an_unrendered_file(tmp_path):
    owner = _layer(
        "owner",
        "language",
        owns=["go.mod"],
        points=[
            InjectionPoint(
                id="runtime.dependencies",
                file="go.mod",
                format="text-block",
                anchor="require-block",
            )
        ],
    )
    web = _layer(
        "web",
        "framework",
        owns=["x/**"],
        injects=[Inject(into="runtime.dependencies", format="text-block", template="dep")],
    )
    with pytest.raises(InjectionError):
        emit([owner, web], ["owner", "web"], Bus({}), tmp_path / "out")


def test_emit_rejects_an_unimplemented_injection_format(tmp_path):
    src = _template(tmp_path / "ci", "ci.yml", "jobs:\n  build:\n    steps: []\n")
    ci = _layer(
        "ci",
        "ci",
        owns=["ci.yml"],
        points=[
            InjectionPoint(
                id="ci.steps", file="ci.yml", format="yaml-seq", anchor="jobs.build.steps"
            )
        ],
        source_dir=src,
    )
    web = _layer(
        "web",
        "container",
        owns=["x/**"],
        injects=[Inject(into="ci.steps", format="yaml-seq", template="- run: echo hi")],
    )
    with pytest.raises(UnsupportedInjectionFormat):
        emit([ci, web], ["ci", "web"], Bus({}), tmp_path / "out")
