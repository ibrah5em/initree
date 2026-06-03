"""emit — phase 4: render owned files, then splice injections (docs/01 §5).

Two ordered passes over the frozen bus:

  4a. render owned files. Each layer's ``templates/`` tree is rendered (``${...}`` resolved against
      the bus, ``{{TOKEN}}`` left for the ci layer) and mirrored into the output directory. Every
      rendered path must fall inside that layer's ``owns`` globs, and no two layers may write the
      same path — single-ownership, enforced here.

  4b. splice injections. For each declared ``injection_point``, gather every ``injects`` across the
      recipe that targets its id, order them, render each fragment, and splice into the owner's file
      at the anchor. This runs after every file is written, so a contributor that sorts later in
      topological order still lands correctly in an earlier owner's file — injection is order-free.

Format strategies differ by where the anchor lives. A structured format (``toml-array``) navigates
a key path with a format-preserving parser. A text format (``text-block``, ``line``) finds a marker
region the template author placed — ``>>> initree:inject <id>`` / ``<<< initree:inject <id>`` — and
replaces its body, keying off the injection-point id the way the rendered proof in docs/01 §6 does.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import tomlkit

from initree.context import Bus
from initree.manifest import Inject, InjectionPoint, Layer

# Engine-tier reference, same syntax compute resolves. In a template the whole point is to splice a
# bus value into text, so every match stringifies; type preservation is a compute concern, not here.
_REF = re.compile(r"\$\{([^}]+)\}")

# The marker tag text/line injection points carry. The author writes a comment-prefixed pair around
# the spot; emit replaces the body between them. Disjoint from the {{TOKEN}} tier by construction.
_MARK = "initree:inject"


class EmitError(Exception):
    """Base for every emit-phase failure. emit() raises a subclass, never this directly."""


class OwnershipError(EmitError):
    """A layer renders a path outside its `owns`, or two layers write the same path."""


class TemplateRenderError(EmitError):
    """A template references a `${...}` key that is not on the frozen bus."""


class InjectionError(EmitError):
    """An injection target file is missing, or its anchor / marker region cannot be located."""


class UnsupportedInjectionFormat(EmitError):
    """An injection point declares a format emit does not implement yet."""


def emit(layers: list[Layer], order: list[str], bus: Bus, out_dir: Path) -> list[Path]:
    """Render every owned template, then splice all injections. Returns the rendered file paths.

    Layers are walked in topological `order` for deterministic writes, but injection (4b) is
    independent of order by design. Raises an EmitError subclass on an ownership breach, an unknown
    template reference, a missing injection target, or an unimplemented format.
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
    """Resolve every `${namespace.key}` in `text` against the bus, leaving `{{TOKEN}}` untouched."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in bus:
            raise TemplateRenderError(f"template references '${{{key}}}', which is not on the bus")
        return str(bus[key])

    return _REF.sub(replace, text)


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
        if path.is_file():
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
    elif point.format in ("text-block", "line"):
        _splice_markers(file_path, point, units)
    else:
        raise UnsupportedInjectionFormat(
            f"injection point '{point.id}' uses format '{point.format}', which emit does not "
            "implement yet"
        )


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
