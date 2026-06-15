"""The single-stage container build is language-agnostic: the language owns its image-prep.

docs/registry §5 — a single-stage language provides runtime.image_prep (its own toolchain setup) and
the container splices it verbatim, so swapping the language never edits the container layer. These
render the real docker/podman templates against a frozen bus to prove the splice works both ways: a
no-prep language gets a clean image, python gets its uv lines, and no tool name is baked into the
template itself.
"""

from pathlib import Path

import pytest

from initree.context import Bus
from initree.emit import render_text

LAYERS = Path(__file__).resolve().parents[1] / "layers"
DOCKERFILE = LAYERS / "docker" / "templates" / "Dockerfile"
CONTAINERFILE = LAYERS / "podman" / "templates" / "Containerfile"

PYTHON_PREP = (
    'ENV PATH="/app/.venv/bin:$PATH"\nCOPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv'
)


def _bus(base_image: str, image_prep: str) -> Bus:
    # No runtime.build_cmd on the bus -> the conditional takes the single-stage branch.
    return Bus(
        {
            "runtime.base_image": base_image,
            "runtime.image_prep": image_prep,
            "runtime.install_cmd": "npm ci",
            "app.port": 3000,
            "app.start_command": "node src/index.js",
        }
    )


@pytest.mark.parametrize("template", [DOCKERFILE, CONTAINERFILE])
def test_no_prep_language_renders_a_clean_single_stage(template):
    out = render_text(template.read_text(), _bus("node:20-slim", ""))
    assert "FROM node:20-slim" in out
    assert "RUN npm ci" in out
    # nothing of python's leaks in, and no engine ref is left dangling
    assert "uv" not in out
    assert ".venv" not in out
    assert "${" not in out


@pytest.mark.parametrize("template", [DOCKERFILE, CONTAINERFILE])
def test_python_prep_splices_its_uv_setup(template):
    out = render_text(template.read_text(), _bus("python:3.12-slim", PYTHON_PREP))
    assert 'ENV PATH="/app/.venv/bin:$PATH"' in out
    assert "COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv" in out


@pytest.mark.parametrize("template", [DOCKERFILE, CONTAINERFILE])
def test_template_bakes_in_no_language_toolchain(template):
    # the prep moved to the language layer; the container template names no language's tooling
    assert "uv" not in template.read_text()
