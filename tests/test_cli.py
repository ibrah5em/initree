"""CLI TDD harness — drives cli.py via typer's CliRunner.

The happy path scaffolds the emit-slice recipe into a tmp dir (value keys supplied with --set, since
that slice declares no inputs) and checks the rendered files. The rest pin the error boundary: a
missing layer, an empty recipe, and a --no-input run that hits an input with no default all exit
non-zero with a readable message rather than a traceback.
"""

from pathlib import Path

from typer.testing import CliRunner

from initree.cli import app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_new_scaffolds_a_project_end_to_end(tmp_path):
    out = tmp_path / "myapp"
    result = runner.invoke(
        app,
        [
            "new",
            "myapp",
            "--recipe",
            "go+gin+docker",
            "--layers-dir",
            str(FIXTURES / "emit-slice"),
            "--out",
            str(out),
            "--no-input",
            "--set",
            "runtime.version=1.22",
            "--set",
            "app.port=8080",
            "--set",
            "app.entrypoint=./cmd/server",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "go 1.22" in (out / "go.mod").read_text()
    assert "EXPOSE 8080" in (out / "Dockerfile").read_text()
    assert "order: go -> gin -> docker" in result.output


def test_new_fails_clearly_on_a_missing_layer(tmp_path):
    result = runner.invoke(
        app,
        [
            "new",
            "myapp",
            "--recipe",
            "go+nope",
            "--layers-dir",
            str(FIXTURES / "emit-slice"),
            "--out",
            str(tmp_path / "out"),
            "--no-input",
        ],
    )

    assert result.exit_code == 1
    assert "nope" in result.output
    assert not (tmp_path / "out").exists()


def test_new_rejects_an_empty_recipe(tmp_path):
    result = runner.invoke(
        app, ["new", "myapp", "--recipe", "", "--out", str(tmp_path / "out"), "--no-input"]
    )

    assert result.exit_code == 1
    assert "recipe is empty" in result.output


def test_new_requires_a_value_for_an_input_without_a_default(tmp_path):
    layers_dir = tmp_path / "layers"
    (layers_dir / "lang").mkdir(parents=True)
    (layers_dir / "lang" / "layer.yaml").write_text(
        "apiVersion: initree.dev/v1\n"
        "id: lang\n"
        "slot: language\n"
        "name: lang\n"
        "inputs:\n"
        "  - { key: runtime.version, prompt: Version, type: string }\n"
        'provides:\n  - { key: runtime.version, type: string, value: "${runtime.version}" }\n'
        'owns: [".tool-versions"]\n'
    )
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        [
            "new",
            "app",
            "--recipe",
            "lang",
            "--layers-dir",
            str(layers_dir),
            "--out",
            str(out),
            "--no-input",
        ],
    )

    assert result.exit_code == 1
    assert "runtime.version" in result.output
    assert not out.exists()
