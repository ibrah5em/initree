"""initree CLI (typer). Entry point: the ``initree`` console script.

Only the command surface is sketched here; it raises until the engine phases are wired through
lifecycle. The command shape is fixed so the wiring has a stable target.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Compose a project from independent layers.", no_args_is_help=True)


@app.command()
def new(
    name: str,
    recipe: str = typer.Option(
        ...,
        "--recipe",
        help="slot layers joined by '+', e.g. go+gin+docker+gitlab-ci+k8s+slack",
    ),
) -> None:
    """Scaffold a new project from a recipe."""
    raise NotImplementedError(
        "the engine is not wired yet — resolve is the next build step (see tests/test_resolve.py)"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
