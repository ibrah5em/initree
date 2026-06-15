"""emit — phase 4: render owned files, then splice injections (docs/lifecycle §5).

Two ordered passes over the frozen bus:

  4a. render owned files. Each layer's ``templates/`` tree is rendered (``${...}`` resolved against
      the bus, ``{{TOKEN}}`` left for the ci layer) and mirrored into the output directory. Every
      rendered path must fall inside that layer's ``owns`` globs, and no two layers may write the
      same path — single-ownership, enforced here.

  4b. splice injections. For each declared ``injection_point``, gather every ``injects`` across the
      recipe that targets its id, order them, render each fragment, and splice into the owner's file
      at the anchor. This runs after every file is written, so a contributor that sorts later in
      topological order still lands correctly in an earlier owner's file — injection is order-free.

Format strategies differ by where the anchor lives. A structured format (``toml-array``,
``yaml-seq``, ``json-array``) navigates a key path and appends to the array/sequence it finds;
toml and yaml round-trip the surrounding formatting, json regenerates (it has no comments to keep).
A text format (``text-block``, ``line``) finds a marker region the template author placed —
``>>> initree:inject <id>`` / ``<<< initree:inject <id>`` — and replaces its body, keying off the
injection-point id the way the rendered proof in docs/lifecycle §6 does.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping, MutableMapping
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, assert_never

import tomlkit
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq

from initree.context import Bus
from initree.manifest import Inject, InjectionPoint, Layer

# Engine-tier reference, same syntax compute resolves. In a template the whole point is to splice a
# bus value into text, so every match stringifies; type preservation is a compute concern, not here.
_REF = re.compile(r"\$\{([^}]+)\}")

# The marker tag text/line injection points carry. The author writes a comment-prefixed pair around
# the spot; emit replaces the body between them. Disjoint from the {{TOKEN}} tier by construction.
_MARK = "initree:inject"

# Backend-branching conditional markers. A backend-agnostic owner (docker) ships one template that
# renders differently per stack — multi-stage when `runtime.build_cmd` is present, single-stage when
# it is absent — without the engine learning the stacks. The directives are their own comment-guard
# markers (same family as the injection ones), so they are inert in the host file's syntax and
# disjoint from both interpolation tiers; render_text strips them, keeping only the taken branch.
# Presence-and-truthy of a bus key is the whole predicate: no expressions, no nesting.
_IF = "initree:if"
_ELSE = "initree:else"
_ENDIF = "initree:endif"


class EmitError(Exception):
    """Base for every emit-phase failure. emit() raises a subclass, never this directly."""


class OwnershipError(EmitError):
    """A layer renders a path outside its `owns`, or two layers write the same path."""


class TemplateRenderError(EmitError):
    """A template references a `${...}` key that is not on the frozen bus."""


class InjectionError(EmitError):
    """An injection target file is missing, or its anchor / marker region cannot be located."""


def emit(layers: list[Layer], order: list[str], bus: Bus, out_dir: Path) -> list[Path]:
    """Render every owned template, then splice all injections. Returns the rendered file paths.

    Layers are walked in topological `order` for deterministic writes, but injection (4b) is
    independent of order by design. Raises an EmitError subclass on an ownership breach, an unknown
    template reference, or a missing injection target.
    """
    by_id = {layer.id: layer for layer in layers}
    out = Path(out_dir)
    owner_of: dict[str, str] = {}
    written: list[Path] = []

    for layer_id in order:
        layer = by_id[layer_id]
        for rel_path, content in _render_templates(layer, bus):
            _guard_ownership(layer, rel_path, owner_of)
            owner_of[rel_path] = layer.id
            destination = out / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content)
            written.append(destination)

    for layer_id in order:
        owner = by_id[layer_id]
        for point in owner.injection_points:
            units = _ordered_units(point, layers, order, bus)
            if units:
                _splice(out / point.file, point, units)

    return written


def render_text(text: str, bus: Mapping[str, Any]) -> str:
    """Resolve every `${namespace.key}` in `text` against the bus, leaving `{{TOKEN}}` untouched.

    A template may also carry `initree:if`/`else`/`endif` blocks; those are evaluated first (the
    dropped branch never reaches `${...}` resolution), so a single owned template can branch on the
    stack it lands in. A template with no such markers is rendered byte-for-byte as before.
    """
    if any(tag in text for tag in (_IF, _ELSE, _ENDIF)):
        text = _apply_conditionals(text, bus)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in bus:
            raise TemplateRenderError(f"template references '${{{key}}}', which is not on the bus")
        return str(bus[key])

    return _REF.sub(replace, text)


def _apply_conditionals(text: str, bus: Mapping[str, Any]) -> str:
    """Keep only the taken branch of each `initree:if`/`else`/`endif` block; strip the directives.

    One block, one level — the only branching a layer template needs (a Dockerfile picking single
    vs multi-stage). An unbalanced or nested block is an authoring error, raised loud rather than
    rendered into a broken file.
    """
    kept: list[str] = []
    open_key: str | None = None
    branch_taken = False
    emitting = True
    for line in text.split("\n"):
        directive = _directive(line)
        if directive == _ENDIF:
            if open_key is None:
                raise TemplateRenderError("'initree:endif' has no open 'initree:if'")
            open_key, emitting = None, True
        elif directive == _ELSE:
            if open_key is None:
                raise TemplateRenderError("'initree:else' has no open 'initree:if'")
            emitting = not branch_taken
        elif directive == _IF:
            if open_key is not None:
                raise TemplateRenderError("nested 'initree:if' blocks are not supported")
            open_key = _if_key(line)
            branch_taken = _truthy(bus, open_key)
            emitting = branch_taken
        elif emitting:
            kept.append(line)
    if open_key is not None:
        raise TemplateRenderError(f"'initree:if {open_key}' is never closed by 'initree:endif'")
    return "\n".join(kept)


def _directive(line: str) -> str | None:
    """Which conditional directive a line carries, if any. Longer tags are tested first so a line is
    never misread (`initree:endif` is disjoint from `initree:if` by construction, but order keeps it
    obvious)."""
    if _ENDIF in line:
        return _ENDIF
    if _ELSE in line:
        return _ELSE
    if _IF in line:
        return _IF
    return None


def _if_key(line: str) -> str:
    """The bus key an `initree:if` line tests, with an optional `${...}` wrapper stripped."""
    after = line.split(_IF, 1)[1].split()
    token = after[0] if after else ""
    token = token.removeprefix("${").removesuffix("}")
    if not token:
        raise TemplateRenderError("'initree:if' needs a bus key to test")
    return token


def _truthy(bus: Mapping[str, Any], key: str) -> bool:
    """Whether `key` is present on the bus with a non-empty value — the conditional's predicate."""
    if key not in bus:
        return False
    value = bus[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip() != ""
    return value is not None


def _render_templates(layer: Layer, bus: Bus) -> Iterator[tuple[str, str]]:
    """Yield (relative output path, rendered content) for each file in the layer's templates/ tree.
    A layer with no templates/ (or none loaded) contributes nothing — `owns` is a right to write,
    not an obligation."""
    if layer.source_dir is None:
        return
    templates = layer.source_dir / "templates"
    if not templates.is_dir():
        return
    for path in sorted(templates.rglob("*")):
        if not path.is_file():
            continue
        # pip byte-compiles every .py it installs, including template files, leaving __pycache__
        # next to them in an installed wheel. Those .pyc are not templates — skip them, or the
        # text render below chokes on the bytecode.
        if "__pycache__" in path.parts:
            continue
        yield path.relative_to(templates).as_posix(), render_text(path.read_text(), bus)


def _guard_ownership(layer: Layer, rel_path: str, owner_of: Mapping[str, str]) -> None:
    if rel_path in owner_of:
        raise OwnershipError(
            f"both '{owner_of[rel_path]}' and '{layer.id}' render '{rel_path}'; "
            "single-ownership is absolute"
        )
    if not any(_path_matches(rel_path, glob) for glob in layer.owns):
        raise OwnershipError(
            f"layer '{layer.id}' renders '{rel_path}', which none of its owns {layer.owns} cover"
        )


def _ordered_units(
    point: InjectionPoint, layers: list[Layer], order: list[str], bus: Bus
) -> list[str]:
    """Every fragment targeting this point, rendered and ordered per the point's policy. A unit is
    one array element / line, or one rendered text block."""
    position = {layer_id: index for index, layer_id in enumerate(order)}
    contributions: list[tuple[int, int, int, str]] = []
    for layer in layers:
        for declared, inject in enumerate(layer.injects):
            if inject.into != point.id:
                continue
            priority = inject.order if inject.order is not None else 0
            for unit in _render_units(inject, bus):
                contributions.append((priority, position[layer.id], declared, unit))

    if point.order == "alpha":
        contributions.sort(key=lambda item: item[3])
    elif point.order == "priority":
        contributions.sort(key=lambda item: (item[0], item[1], item[2]))
    else:  # declared: source order, layers in topological order
        contributions.sort(key=lambda item: (item[1], item[2]))
    return [unit for *_, unit in contributions]


def _render_units(inject: Inject, bus: Bus) -> list[str]:
    if inject.items is not None:
        return [render_text(item, bus) for item in inject.items]
    if inject.template is not None:
        return [render_text(inject.template, bus).rstrip("\n")]
    return []


def _splice(file_path: Path, point: InjectionPoint, units: list[str]) -> None:
    if not file_path.exists():
        raise InjectionError(
            f"injection point '{point.id}' targets '{point.file}', which no layer rendered"
        )
    if point.format == "toml-array":
        _splice_toml_array(file_path, point, units)
    elif point.format == "yaml-seq":
        _splice_yaml_seq(file_path, point, units)
    elif point.format == "json-array":
        _splice_json_array(file_path, point, units)
    elif point.format == "text-block" or point.format == "line":
        _splice_markers(file_path, point, units)
    else:
        assert_never(point.format)


def _splice_toml_array(file_path: Path, point: InjectionPoint, units: list[str]) -> None:
    document = tomlkit.parse(file_path.read_text())
    array = _navigate_toml(document, point)
    for unit in units:
        array.append(unit)
    file_path.write_text(tomlkit.dumps(document))


def _navigate_toml(document: Any, point: InjectionPoint) -> Any:
    node = document
    for key in point.anchor.replace("[", "").replace("]", "").split("."):
        try:
            node = node[key]
        except (KeyError, TypeError) as exc:
            raise InjectionError(
                f"injection point '{point.id}' anchor '{point.anchor}' is not a path in "
                f"'{point.file}'"
            ) from exc
    return node


def _splice_json_array(file_path: Path, point: InjectionPoint, units: list[str]) -> None:
    """Append each unit as a string element to the JSON array at the anchor, then re-serialise.

    The toml-array twin for JSON dependency files (e.g. package.json). JSON carries no comments, so
    there is nothing to round-trip — the document is reparsed and dumped at the two-space indent
    these files conventionally use. Units are appended as strings, the same as toml-array.
    """
    document = json.loads(file_path.read_text())
    array = _navigate_json(document, point)
    if not isinstance(array, list):
        raise InjectionError(
            f"injection point '{point.id}' anchor '{point.anchor}' is not an array in "
            f"'{point.file}'"
        )
    array.extend(units)
    file_path.write_text(json.dumps(document, indent=2) + "\n")


def _navigate_json(document: Any, point: InjectionPoint) -> Any:
    node = document
    for key in point.anchor.split("."):
        try:
            node = node[key]
        except (KeyError, TypeError) as exc:
            raise InjectionError(
                f"injection point '{point.id}' anchor '{point.anchor}' is not a path in "
                f"'{point.file}'"
            ) from exc
    return node


# Block style with the dash inset under its key — the de-facto convention for CI workflow files,
# and what keeps a re-dumped point readable next to the template author's hand-written blocks.
def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def _splice_yaml_seq(file_path: Path, point: InjectionPoint, units: list[str]) -> None:
    """Round-trip the owner's YAML, append each fragment to the anchored sequence, write it back.

    Each unit is itself a YAML sequence fragment (one or more list items); its items extend the
    target. ruamel preserves the rest of the file — key order, comments, block scalars — so only the
    point grows. An empty or absent sequence at the anchor is materialised as a block sequence.
    """
    yaml = _yaml()
    document = yaml.load(file_path)
    sequence = _anchored_sequence(document, point)
    for unit in units:
        items = yaml.load(unit)
        if not isinstance(items, list):
            raise InjectionError(
                f"injection point '{point.id}' fragment is not a YAML sequence: {unit!r}"
            )
        sequence.extend(items)
    yaml.dump(document, file_path)


def _anchored_sequence(document: Any, point: InjectionPoint) -> CommentedSeq:
    *path, last = point.anchor.split(".")
    parent = document
    for key in path:
        try:
            parent = parent[key]
        except (KeyError, TypeError) as exc:
            raise InjectionError(
                f"injection point '{point.id}' anchor '{point.anchor}' is not a path in "
                f"'{point.file}'"
            ) from exc
    if not isinstance(parent, MutableMapping) or last not in parent:
        raise InjectionError(
            f"injection point '{point.id}' anchor '{point.anchor}' is not a path in '{point.file}'"
        )
    sequence = parent[last]
    if sequence is None:
        sequence = CommentedSeq()
        parent[last] = sequence
    if not isinstance(sequence, CommentedSeq):
        raise InjectionError(
            f"injection point '{point.id}' anchor '{point.anchor}' is not a sequence in "
            f"'{point.file}'"
        )
    sequence.fa.set_block_style()
    return sequence


def _splice_markers(file_path: Path, point: InjectionPoint, units: list[str]) -> None:
    lines = file_path.read_text().splitlines()
    start = _find_marker(lines, f">>> {_MARK} {point.id}")
    end = _find_marker(lines, f"<<< {_MARK} {point.id}")
    if start is None or end is None or end <= start:
        raise InjectionError(
            f"injection point '{point.id}' declares no marker region in '{point.file}' "
            f"(expected '>>> {_MARK} {point.id}' / '<<< {_MARK} {point.id}')"
        )
    indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
    body = [f"{indent}{line}" if line else "" for unit in units for line in unit.split("\n")]
    spliced = lines[: start + 1] + body + lines[end:]
    file_path.write_text("\n".join(spliced) + "\n")


def _find_marker(lines: list[str], tag: str) -> int | None:
    for index, line in enumerate(lines):
        if tag in line:
            return index
    return None


def _path_matches(path: str, glob: str) -> bool:
    return _segments_match(path.split("/"), glob.split("/"))


def _segments_match(path: list[str], glob: list[str]) -> bool:
    """Whether a concrete path matches an `owns` glob, with `**` spanning zero or more segments."""
    if not glob:
        return not path
    if glob[0] == "**":
        if len(glob) == 1:
            return True
        return any(_segments_match(path[i:], glob[1:]) for i in range(len(path) + 1))
    if not path:
        return False
    if fnmatch(path[0], glob[0]):
        return _segments_match(path[1:], glob[1:])
    return False
