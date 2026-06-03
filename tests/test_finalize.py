"""finalize TDD harness — drives finalize.py.

Hooks are real executable scripts written into tmp_path layer dirs (not committed fixtures, whose
exec bit is fragile across checkouts). The tests prove the four behaviours that matter: hooks run in
topological order, in the output directory, with the bus on the environment — and a hook that is
missing or exits non-zero stops the build loudly. Layers without a hook are skipped.
"""

from pathlib import Path

import pytest

from initree.context import Bus
from initree.finalize import FinalizeError, finalize
from initree.manifest import Hooks, Layer


def _hook_layer(
    tmp_path: Path, layer_id: str, slot: str, script: str, *, hook="finalize.sh"
) -> Layer:
    src = tmp_path / layer_id
    src.mkdir(parents=True, exist_ok=True)
    path = src / hook
    path.write_text(script)
    path.chmod(0o755)
    layer = _layer(layer_id, slot, hook)
    layer.source_dir = src
    return layer


def _layer(layer_id: str, slot: str, hook: str | None) -> Layer:
    return Layer(
        apiVersion="initree.dev/v1",
        id=layer_id,
        slot=slot,
        name=layer_id,
        hooks=Hooks(finalize=hook) if hook is not None else None,
    )


def test_finalize_runs_hooks_in_topological_order(tmp_path):
    go = _hook_layer(tmp_path, "go", "language", "#!/bin/sh\necho go >> log.txt\n")
    docker = _hook_layer(tmp_path, "docker", "container", "#!/bin/sh\necho docker >> log.txt\n")
    out = tmp_path / "out"

    ran = finalize([docker, go], ["go", "docker"], Bus({}), out)

    assert ran == ["go", "docker"]
    assert (out / "log.txt").read_text().split() == ["go", "docker"]


def test_finalize_skips_layers_without_a_hook(tmp_path):
    go = _hook_layer(tmp_path, "go", "language", "#!/bin/sh\necho go >> log.txt\n")
    plain = _layer("plain", "framework", None)
    out = tmp_path / "out"

    ran = finalize([go, plain], ["go", "plain"], Bus({}), out)

    assert ran == ["go"]
    assert (out / "log.txt").read_text().split() == ["go"]


def test_finalize_runs_inside_the_output_directory(tmp_path):
    go = _hook_layer(tmp_path, "go", "language", "#!/bin/sh\ntouch marker\n")
    out = tmp_path / "out"

    finalize([go], ["go"], Bus({}), out)

    assert (out / "marker").is_file()


def test_finalize_exposes_the_bus_on_the_environment(tmp_path):
    script = '#!/bin/sh\nprintf "%s" "$INITREE_PROJECT_SLUG" > slug.txt\n'
    go = _hook_layer(tmp_path, "go", "language", script)
    out = tmp_path / "out"

    finalize([go], ["go"], Bus({"project.slug": "myapp"}), out)

    assert (out / "slug.txt").read_text() == "myapp"


def test_finalize_raises_when_a_hook_exits_nonzero(tmp_path):
    go = _hook_layer(tmp_path, "go", "language", "#!/bin/sh\necho boom 1>&2\nexit 3\n")
    with pytest.raises(FinalizeError, match="exited 3"):
        finalize([go], ["go"], Bus({}), tmp_path / "out")


def test_finalize_raises_when_the_hook_is_missing(tmp_path):
    src = tmp_path / "go"
    src.mkdir()
    go = _layer("go", "language", "absent.sh")
    go.source_dir = src
    with pytest.raises(FinalizeError, match="not found"):
        finalize([go], ["go"], Bus({}), tmp_path / "out")
