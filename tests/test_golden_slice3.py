"""Golden test: slice 3 (node+express+docker+gh-actions+vps-ssh) renders byte-for-byte.

Locks the whole emitted tree against tests/golden/slice3/. The byte-exact complement to
test_slice3.py — that says the right values flow (json-array dep, port hops, node toolchain); this
says nothing else moved. Slice 3 is the third stack, so it also pins the language-agnostic container
and the json package.json injection no other golden covers.

Regenerate after an intentional render change:

    UPDATE_GOLDEN=1 pytest tests/test_golden_slice3.py
"""

import os
import shutil
from pathlib import Path

from initree.lifecycle import build, engine_seed
from initree.manifest import load_selected
from initree.prompt import defaults

LAYERS = Path(__file__).resolve().parents[1] / "layers"
GOLDEN = Path(__file__).resolve().parent / "golden" / "slice3"
RECIPE = ["node", "express", "docker", "gh-actions", "vps-ssh"]


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


def test_slice3_renders_byte_for_byte(tmp_path):
    built = _emit(tmp_path / "myapp")
    if os.environ.get("UPDATE_GOLDEN"):
        _refresh_golden(built)

    actual = _tree(built)
    expected = _tree(GOLDEN)

    assert set(actual) == set(expected), "emitted file set drifted from golden"
    drifted = [rel for rel in expected if actual[rel] != expected[rel]]
    assert not drifted, f"rendered output drifted from golden: {drifted}"
