"""CLI smoke test — drive `initree new` against a real recipe from layers/, no fixtures.

test_cli.py drives the CLI but against the emit-slice fixture; test_slice{1,2}.py build the real
layers and call build() directly, skipping the CLI. This sits at the intersection: the production
`initree new` entry point — arg parse, engine seed, asker, destination guard, report — over the
shipped layers, scaffolding a real tree onto disk. Smoke level: the golden tests own byte-for-byte;
this proves the binary path runs end to end and writes the files for both dialects.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from initree.cli import app

LAYERS = Path(__file__).resolve().parents[1] / "layers"
runner = CliRunner()

# (recipe, terminal ci layer, a few owned files that must land — one per non-ci slot)
SLICE1 = (
    "python+fastapi+docker+gh-actions+vps-ssh",
    "gh-actions",
    ["pyproject.toml", "Dockerfile", ".github/workflows/ci.yml", "deploy/deploy.sh"],
)
SLICE2 = (
    "go+gin+docker+gitlab-ci+k8s+slack",
    "gitlab-ci",
    ["go.mod", "Dockerfile", ".gitlab-ci.yml", "k8s/deployment.yaml"],
)


@pytest.mark.parametrize("recipe, ci_layer, sentinels", [SLICE1, SLICE2], ids=["slice1", "slice2"])
def test_new_scaffolds_a_real_recipe_into_a_temp_dir(tmp_path, recipe, ci_layer, sentinels):
    out = tmp_path / "myapp"
    result = runner.invoke(
        app,
        [
            "new",
            "myapp",
            "--recipe",
            recipe,
            "--layers-dir",
            str(LAYERS),
            "--out",
            str(out),
            "--no-input",
        ],
    )

    assert result.exit_code == 0, result.output
    for rel in sentinels:
        assert (out / rel).is_file(), f"{rel} missing for {recipe}"
    # the build always emits the secrets checklist from the recipes' declared purposes
    assert (out / "INITREE_SECRETS.md").is_file()
    # report names the destination and sorts the ci assembler last (the terminal-layer invariant)
    assert f"created {out}" in result.output
    order_line = next(line for line in result.output.splitlines() if "order:" in line)
    assert order_line.strip().endswith(ci_layer), order_line


def test_new_defaults_out_dir_to_the_slugified_name(tmp_path, monkeypatch):
    """No --out: the destination derives from the name slug under cwd (CLI-only wiring)."""
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app,
        [
            "new",
            "My Service",
            "--recipe",
            "python+fastapi+docker+gh-actions+vps-ssh",
            "--layers-dir",
            str(LAYERS),
            "--no-input",
        ],
    )

    assert result.exit_code == 0, result.output
    dest = (tmp_path / "my-service").resolve()
    assert (dest / "pyproject.toml").is_file()
    assert f"created {dest}" in result.output
