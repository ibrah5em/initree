"""secrets — compile INITREE_SECRETS.md from the secrets a recipe declares (docs/03 §10).

Recipes reference secrets by *logical purpose* through deferred tokens (``{{SECRET:registry}}``,
``{{SECRET_FILE:kubeconfig}}``); the values themselves never enter the bus. After compute freezes
the bus, this module scans every recipe on it for those tokens and writes a provisioning checklist —
the operator's "set these before the first deploy" list.

This is engine behaviour over declared data, not a new contract rule (docs/02 §5): it only reads
what the recipes already declare. The token scan is recipe.scan_secrets; the purpose descriptions
come from the registry, so the vocabulary stays single-sourced.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from initree.manifest import Layer
from initree.recipe import SecretRef, scan_secrets
from initree.registry import secret_purposes

REPORT_NAME = "INITREE_SECRETS.md"

_PREAMBLE = (
    "# Secrets to provision\n"
    "\n"
    "initree generated this from the secrets your recipes reference. Each entry is a logical\n"
    "purpose, not a value — set it in your CI/CD provider's secret store before the first\n"
    "pipeline run. The ci layer resolves each purpose to its native variable; the values\n"
    "themselves never live in the generated project."
)


def write_secret_report(layers: list[Layer], bus: Mapping[str, Any], out_dir: Path) -> Path | None:
    """Write INITREE_SECRETS.md into out_dir from the secrets the recipes declare, else None.

    A project with no secret tokens needs no checklist, so nothing is written and the caller records
    nothing. Otherwise the report lands at the project root next to the generated files.
    """
    refs = observed_secrets(layers, bus)
    if not refs:
        return None
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / REPORT_NAME
    path.write_text(render_report(refs))
    return path


def observed_secrets(layers: list[Layer], bus: Mapping[str, Any]) -> list[SecretRef]:
    """Every distinct secret a recipe on the frozen bus references, in a stable order.

    "Declared data" is the recipes: each layer's recipe-typed provides, read back from the bus where
    compute left their ``{{...}}`` tokens intact. Scanning only those keys keeps the report to
    genuine recipe secrets, never an unrelated string that happens to carry braces.
    """
    refs: list[SecretRef] = []
    seen: set[SecretRef] = set()
    for key in _recipe_keys(layers):
        for ref in scan_secrets(_commands(bus.get(key))):
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs


def render_report(refs: list[SecretRef]) -> str:
    """Render the INITREE_SECRETS.md checklist, secrets split into masked and file-type sections."""
    notes = secret_purposes()
    masked = sorted((ref for ref in refs if not ref.is_file), key=lambda ref: ref.purpose)
    files = sorted((ref for ref in refs if ref.is_file), key=lambda ref: ref.purpose)

    blocks = [_PREAMBLE]
    if masked:
        blocks.append(_section("Masked variables", masked, notes))
    if files:
        blocks.append(_section("File-type variables", files, notes))
    return "\n\n".join(blocks) + "\n"


def _recipe_keys(layers: list[Layer]) -> list[str]:
    """The bus keys recipe-typed provides write, across the recipe, in layer-declared order."""
    return [
        provide.key for layer in layers for provide in layer.provides if provide.type == "recipe"
    ]


def _commands(value: Any) -> list[str]:
    """A recipe bus value as command strings; a bare string or missing key is tolerated."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _section(title: str, refs: list[SecretRef], notes: Mapping[str, str]) -> str:
    items = "\n".join(f"- `{ref.purpose}` — {_note(ref.purpose, notes)}" for ref in refs)
    return f"## {title}\n\n{items}"


def _note(purpose: str, notes: Mapping[str, str]) -> str:
    """The registry's description for a purpose, or a flag that it is off the v1 vocabulary."""
    return (
        notes.get(purpose) or "not in capability registry v1 — add it to keep the vocabulary synced"
    )
