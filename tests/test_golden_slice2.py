"""Golden test: slice 2 (go+gin+docker+gitlab-ci+k8s+slack) renders byte-for-byte.

Locks the whole emitted tree against tests/golden/slice2/. The byte-exact complement to
test_slice2.py's behavioral asserts — the concrete form of the docs/generalization §7 proof,
adapted to the shipped layers. test_slice2.py says the right values flow through the second stack
(compiled language, multi-stage container, GitLab CI dialect, namespaced deploy, optional notify);
this says nothing else moved.

One reconciliation with §7: the shipped docker layer hardcodes registry.host = ghcr.io and folds in
the registry.docker.owner input, so the real build emits ghcr.io/<owner>/myapp everywhere §7
illustrates registry.gitlab.com/myapp. §7's host is illustrative; task 28's "docker reused with a
byte-identical manifest" is the contract, so the golden tracks the real ghcr.io output.

Regenerate after an intentional render change:

    UPDATE_GOLDEN=1 pytest tests/test_golden_slice2.py
"""

import os
import shutil
from pathlib import Path

from initree.lifecycle import build, engine_seed
from initree.manifest import load_selected
from initree.prompt import defaults

LAYERS = Path(__file__).resolve().parents[1] / "layers"
GOLDEN = Path(__file__).resolve().parent / "golden" / "slice2"
RECIPE = ["go", "gin", "docker", "gitlab-ci", "k8s", "slack"]


def _emit(out_dir: Path) -> Path:
    layers = load_selected(LAYERS, RECIPE)
    build(layers, seed=engine_seed("myapp", out_dir), ask=defaults, out_dir=out_dir)
    return out_dir


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }


def _refresh_golden(built: Path) -> None:
    if GOLDEN.exists():
        shutil.rmtree(GOLDEN)
    shutil.copytree(built, GOLDEN)


def test_slice2_renders_byte_for_byte(tmp_path):
    built = _emit(tmp_path / "myapp")
    if os.environ.get("UPDATE_GOLDEN"):
        _refresh_golden(built)

    actual = _tree(built)
    expected = _tree(GOLDEN)

    assert set(actual) == set(expected), "emitted file set drifted from golden"
    drifted = [rel for rel in expected if actual[rel] != expected[rel]]
    assert not drifted, f"rendered output drifted from golden: {drifted}"
