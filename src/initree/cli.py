"""initree CLI (typer). Entry point: the ``initree`` console script.

`new` drives the whole lifecycle: load the recipe's layers, seed the engine context, then
resolve -> prompt -> compute -> emit -> finalize into the output directory. The engine raises
specific errors per phase; this layer catches them at the boundary and reports a clean message
instead of a traceback.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

import typer

from initree import __version__, resources
from initree.context import ComputeError
from initree.emit import EmitError
from initree.finalize import FinalizeError
from initree.lifecycle import BuildResult, build, engine_seed, slugify
from initree.manifest import Input, Layer, load_recipe, load_selected
from initree.prompt import Asker
from initree.resolve import ResolveError

app = typer.Typer(help="Compose a project from independent layers.", no_args_is_help=True)

# The canonical slot order, so `list` reads top-to-bottom the way a recipe composes.
_SLOT_ORDER = ("language", "framework", "container", "ci", "deploy", "notify")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"initree {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Keep `new` a named subcommand — without a callback Typer collapses the single command."""


@app.command()
def new(
    name: str,
    recipe: str = typer.Option(
        ...,
        "--recipe",
        help="slot layers joined by '+', e.g. go+gin+docker+gitlab-ci+k8s+slack",
    ),
    layers_dir: Path | None = typer.Option(
        None,
        "--layers-dir",
        help="directory holding <id>/layer.yaml layers (default: the bundled layers)",
    ),
    out_dir: Path | None = typer.Option(
        None, "--out", help="output directory (default: ./<project-slug>)"
    ),
    overrides: list[str] = typer.Option(
        [],
        "--set",
        help="seed a context key directly as key=value; repeatable",
        metavar="KEY=VALUE",
    ),
    no_input: bool = typer.Option(False, "--no-input", help="don't prompt; take input defaults"),
    no_finalize: bool = typer.Option(False, "--no-finalize", help="skip finalize hooks"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="resolve and render the recipe, report the plan, write nothing"
    ),
) -> None:
    """Scaffold a new project from a recipe."""
    ids = [part for part in recipe.split("+") if part]
    if not ids:
        _fail("recipe is empty — expected slot layers joined by '+'")

    preset = _parse_overrides(overrides)
    destination = (out_dir or Path.cwd() / slugify(name)).resolve()
    if not dry_run:
        _guard_destination(destination)

    # The bus is seeded with the real destination either way, so a dry run's rendered content
    # matches a real build; only where the files land differs.
    seed = {**engine_seed(name, destination), **preset}
    ask = _make_asker(preset, interactive=not no_input)

    try:
        layers = load_selected(layers_dir or resources.layers_dir(), ids)
        if dry_run:
            # Render into a throwaway dir to exercise the real emit (templates, injections,
            # ownership) without touching the destination, then report and discard it.
            with tempfile.TemporaryDirectory() as tmp:
                result = build(layers, seed=seed, ask=ask, out_dir=Path(tmp), run_finalize=False)
                _report_plan(result, Path(tmp), destination)
            return
        result = build(
            layers, seed=seed, ask=ask, out_dir=destination, run_finalize=not no_finalize
        )
    except (ResolveError, ComputeError, EmitError, FinalizeError, FileNotFoundError) as exc:
        _fail(str(exc))

    _report(result, destination)


@app.command(name="list")
def list_layers(
    layers_dir: Path | None = typer.Option(
        None,
        "--layers-dir",
        help="directory holding <id>/layer.yaml layers (default: the bundled layers)",
    ),
) -> None:
    """List the available layers, grouped by slot."""
    try:
        layers = load_recipe(layers_dir or resources.layers_dir())
    except FileNotFoundError as exc:
        _fail(str(exc))

    by_slot: dict[str, list[Layer]] = {}
    for layer in layers:
        by_slot.setdefault(layer.slot, []).append(layer)

    width = max((len(layer.id) for layer in layers), default=0)
    known = [slot for slot in _SLOT_ORDER if slot in by_slot]
    extra = [slot for slot in sorted(by_slot) if slot not in _SLOT_ORDER]
    for slot in known + extra:
        typer.secho(slot, fg=typer.colors.CYAN)
        for layer in sorted(by_slot[slot], key=lambda item: item.id):
            typer.echo(f"  {layer.id.ljust(width)}  {layer.name}")


def _make_asker(preset: Mapping[str, Any], *, interactive: bool) -> Asker:
    """Prefer a --set value, then an interactive prompt, then the input's declared default."""

    def ask(spec: Input, context: Mapping[str, Any]) -> Any:
        if spec.key in preset:
            return preset[spec.key]
        if interactive:
            return _coerce(typer.prompt(spec.prompt, default=spec.default), spec.type)
        if spec.default is None:
            _fail(
                f"input '{spec.key}' has no default; pass --set {spec.key}=... or drop --no-input"
            )
        return spec.default

    return ask


def _parse_overrides(pairs: list[str]) -> dict[str, Any]:
    preset: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key.strip():
            _fail(f"--set expects key=value, got '{pair}'")
        preset[key.strip()] = _coerce_loose(value)
    return preset


def _coerce(value: Any, type_: str) -> Any:
    """Coerce a prompt answer (always a string) to the input's declared type; pass others on."""
    if not isinstance(value, str):
        return value
    if type_ == "int":
        return int(value)
    if type_ == "bool":
        return value.strip().lower() in ("1", "true", "yes", "on")
    return value


def _coerce_loose(value: str) -> Any:
    """Best-effort typing for a --set value, which has no declared type: bool, int, else string."""
    text = value.strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return value


def _guard_destination(destination: Path) -> None:
    if destination.is_file():
        _fail(f"output path {destination} is a file, not a directory")
    if destination.is_dir() and any(destination.iterdir()):
        _fail(
            f"output directory {destination} already exists and is not empty; choose another --out"
        )


def _report(result: BuildResult, destination: Path) -> None:
    typer.secho(f"created {destination}", fg=typer.colors.GREEN)
    typer.echo(f"  order: {' -> '.join(result.order)}")
    for path in result.written:
        typer.echo(f"  + {path.relative_to(destination)}")
    if result.secrets_report is not None:
        rel = result.secrets_report.relative_to(destination)
        typer.echo(f"  secrets: {rel} (provision before first deploy)")
    if result.finalized:
        typer.echo(f"  finalized: {', '.join(result.finalized)}")


def _report_plan(result: BuildResult, root: Path, destination: Path) -> None:
    """Same shape as _report, but for a dry run: paths are relative to the throwaway render dir."""
    typer.secho(f"would create {destination}", fg=typer.colors.YELLOW)
    typer.echo(f"  order: {' -> '.join(result.order)}")
    for path in result.written:
        typer.echo(f"  + {path.relative_to(root)}")
    if result.secrets_report is not None:
        typer.echo(f"  secrets: {result.secrets_report.relative_to(root)}")
    typer.secho("  dry run — nothing written", fg=typer.colors.YELLOW)


def _fail(message: str) -> NoReturn:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
